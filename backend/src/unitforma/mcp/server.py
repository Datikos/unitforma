"""The MCP server: tools over projects and buildings, Streamable HTTP at ``/mcp`` (ADR-0015).

Every tool is a thin wrapper over the same service function the admin router calls, inside the
tenant context of the token's owner, and returns the admin API's response shapes so the shape
has one home (``api/schemas.py``).
"""

from __future__ import annotations

import uuid
from typing import Any

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.types import ASGIApp

from unitforma import __version__
from unitforma.api.schemas import (
    BlockAccept,
    BlocksAcceptOut,
    BuildingCreate,
    BuildingOut,
    BuildingUpdate,
    FloorIn,
    FloorOut,
    FloorProposalOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    SiteFeatureCreate,
    SiteFeatureOut,
)
from unitforma.core.errors import ProblemError
from unitforma.core.settings import Settings
from unitforma.documents import floor_proposal as proposal
from unitforma.identity.authz import Action
from unitforma.identity.deps import TenantContext
from unitforma.mcp.auth import BearerTokenMiddleware, current_principal, tenant_ctx
from unitforma.projects import service as projects
from unitforma.publishing import service as publishing
from unitforma.tenants.models import Project, SiteFeature, Tenant

INSTRUCTIONS = """Unitforma staff tools for one developer workspace (tenant). Calls act as the \
token's owner with their role; a read-only token cannot change anything.
A project holds buildings, a building holds floors; every project also has a virtual "SITE" \
building for outdoor units. Lengths are metres, areas square metres, money in the project's \
currency; null means unknown, never 0.
Updates need the record's current `version` (optimistic concurrency): read it first, send it back.
Deleting projects or buildings is not available here; use the admin app."""

MAX_BODY_BYTES = 1024 * 1024  # Caddy limits /mcp to 1 MB as well (Decision 1)


class WhoAmI(BaseModel):
    tenant_id: uuid.UUID
    tenant_slug: str
    tenant_name: str
    user_email: str
    role: str
    token_scope: str
    all_projects: bool
    project_ids: list[uuid.UUID] = Field(default_factory=list)


def _actor(ctx: TenantContext) -> tuple[uuid.UUID, str]:
    return ctx.principal.user_id, ctx.actor_role


async def _refuse_if_published(ctx: TenantContext, p: Project, verb: str) -> None:
    if await publishing.current_publication(ctx.session, p.id) is not None:
        raise ProblemError(
            409, "Project is published", f"Unpublish {p.name} before it can be {verb}"
        )


def build_server() -> MCPServer:
    mcp = MCPServer("Unitforma", instructions=INSTRUCTIONS, version=__version__)

    @mcp.tool()
    async def whoami() -> WhoAmI:
        """Which workspace, user, role and token scope this connection acts as."""
        async with tenant_ctx() as ctx:
            t = (
                await ctx.session.execute(select(Tenant).where(Tenant.id == ctx.tenant_id))
            ).scalar_one()
            m = ctx.membership
            return WhoAmI(
                tenant_id=t.id,
                tenant_slug=t.slug,
                tenant_name=t.name,
                user_email=ctx.principal.email,
                role=m.role.value,
                token_scope=current_principal().scope,
                all_projects=m.all_projects,
                project_ids=sorted(m.project_ids, key=str),
            )

    @mcp.tool()
    async def list_projects() -> list[ProjectOut]:
        """Projects the token's owner may see, by name."""
        async with tenant_ctx() as ctx:
            ctx.require("project", Action.READ)
            q = select(Project).where(Project.tenant_id == ctx.tenant_id)
            if not ctx.membership.all_projects:
                q = q.where(Project.id.in_(ctx.membership.project_ids))
            rows = await ctx.session.execute(q.order_by(Project.name))
            return [ProjectOut.model_validate(p) for p in rows.scalars()]

    @mcp.tool()
    async def get_project(project_id: uuid.UUID) -> ProjectOut:
        """One project with its version, address, area definitions and settings."""
        async with tenant_ctx() as ctx:
            ctx.require("project", Action.READ)
            ctx.require_project(project_id)
            return ProjectOut.model_validate(
                await projects.get_project(ctx.session, ctx.tenant_id, project_id)
            )

    @mcp.tool()
    async def create_project(project: ProjectCreate) -> ProjectOut:
        """Create a project (slug 3 to 63 lowercase chars, unique in the workspace). Currency
        defaults to the workspace's; the virtual SITE building is created with it."""
        async with tenant_ctx(write=True) as ctx:
            ctx.require("project", Action.WRITE)
            tenant = (
                await ctx.session.execute(select(Tenant).where(Tenant.id == ctx.tenant_id))
            ).scalar_one()
            p = await projects.create_project(
                ctx.session,
                tenant_id=ctx.tenant_id,
                data=project.model_dump(),
                actor=_actor(ctx),
                default_currency=tenant.default_currency,
            )
            return ProjectOut.model_validate(p)

    @mcp.tool()
    async def update_project(project_id: uuid.UUID, changes: ProjectUpdate) -> ProjectOut:
        """Change name, status (draft, active, archived), currency, address, description, code
        pattern, area definitions or portal settings. `changes.version` must be the current one.
        Archiving is refused while the project is published."""
        async with tenant_ctx(write=True) as ctx:
            ctx.require("project", Action.WRITE)
            ctx.require_project(project_id)
            p = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
            data = changes.model_dump(exclude={"version"}, exclude_none=True)
            if data.get("status") == "archived" and p.status != "archived":
                await _refuse_if_published(ctx, p, "archived")
            p = await projects.update_project(ctx.session, p, data, changes.version, _actor(ctx))
            return ProjectOut.model_validate(p)

    @mcp.tool()
    async def list_buildings(project_id: uuid.UUID) -> list[BuildingOut]:
        """Buildings of a project with their floors (the SITE building included)."""
        async with tenant_ctx() as ctx:
            ctx.require("project", Action.READ)
            ctx.require_project(project_id)
            await projects.get_project(ctx.session, ctx.tenant_id, project_id)
            rows = await projects.list_buildings(ctx.session, project_id)
            return [BuildingOut.model_validate(b) for b in rows]

    @mcp.tool()
    async def create_building(project_id: uuid.UUID, building: BuildingCreate) -> BuildingOut:
        """Add a building (code 1 to 20 chars, unique in the project). Floors come next with
        set_floors or from the drawings with get_floor_proposal."""
        async with tenant_ctx(write=True) as ctx:
            ctx.require("project", Action.WRITE)
            ctx.require_project(project_id)
            p = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
            b = await projects.create_building(ctx.session, p, building.model_dump(), _actor(ctx))
            return BuildingOut.model_validate(
                await projects.get_building(ctx.session, ctx.tenant_id, b.id)
            )

    @mcp.tool()
    async def update_building(building_id: uuid.UUID, changes: BuildingUpdate) -> BuildingOut:
        """Change name, sort order, construction status (planned, under_construction, completed),
        completion, terms, site placement or elevation sheet. Fields left out are kept; name,
        construction_status, completion, terms and elevation_sheet_id sent as null are cleared.
        `changes.version` must be the current one."""
        async with tenant_ctx(write=True) as ctx:
            ctx.require("project", Action.WRITE)
            b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
            ctx.require_project(b.project_id)
            data: dict[str, Any] = changes.model_dump(exclude={"version"}, exclude_unset=True)
            data = {
                k: v for k, v in data.items() if v is not None or k in projects.BUILDING_CLEARABLE
            }
            if changes.site_transform is not None:
                data["site_transform"] = changes.site_transform.model_dump()
            if "site_transform" in data and "placement_status" not in data:
                if b.placement_status == "unplaced":
                    data["placement_status"] = "draft"
            b = await projects.update_building(ctx.session, b, data, changes.version, _actor(ctx))
            return BuildingOut.model_validate(
                await projects.get_building(ctx.session, ctx.tenant_id, b.id)
            )

    @mcp.tool()
    async def set_floors(building_id: uuid.UUID, floors: list[FloorIn]) -> list[FloorOut]:
        """Replace the building's floor list: level (integer, 0 = ground, negative below),
        display name, height and elevation in metres (null when unknown)."""
        async with tenant_ctx(write=True) as ctx:
            ctx.require("project", Action.WRITE)
            b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
            ctx.require_project(b.project_id)
            rows = await projects.set_floors(
                ctx.session, b, [f.model_dump() for f in floors], _actor(ctx)
            )
            out = [FloorOut.model_validate(f) for f in rows]
            await proposal.queue_resuggest(ctx.tenant_id, b.project_id)
            return out

    @mcp.tool()
    async def get_floor_proposal(building_id: uuid.UUID) -> FloorProposalOut:
        """Floors read from the building's drawings (level markers): elevations, heights, and
        split-level blocks when the sheets draw several side by side. Accept with set_floors or
        accept_floor_proposal_blocks."""
        async with tenant_ctx() as ctx:
            ctx.require("project", Action.READ)
            b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
            ctx.require_project(b.project_id)
            return FloorProposalOut.model_validate(await proposal.floor_proposal(ctx.session, b))

    @mcp.tool()
    async def accept_floor_proposal_blocks(
        building_id: uuid.UUID, blocks: list[BlockAccept], delete_source: bool = False
    ) -> BlocksAcceptOut:
        """Create one building per split-level block with its floors; delete_source removes the
        source building when it has no units and no documents."""
        async with tenant_ctx(write=True) as ctx:
            ctx.require("project", Action.WRITE)
            b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
            ctx.require_project(b.project_id)
            project_id = b.project_id
            created, removed = await proposal.accept_blocks(
                ctx.session,
                b,
                [blk.model_dump() for blk in blocks],
                delete_source=delete_source,
                actor=_actor(ctx),
            )
            out = [
                BuildingOut.model_validate(
                    await projects.get_building(ctx.session, ctx.tenant_id, c.id)
                )
                for c in created
            ]
            await proposal.queue_resuggest(ctx.tenant_id, project_id)
            return BlocksAcceptOut(buildings=out, source_removed=removed)

    @mcp.tool()
    async def list_site_features(project_id: uuid.UUID) -> list[SiteFeatureOut]:
        """Site features of a project (gardens, roads, parking zones, amenities, entrances)."""
        async with tenant_ctx() as ctx:
            ctx.require("project", Action.READ)
            ctx.require_project(project_id)
            rows = await ctx.session.execute(
                select(SiteFeature)
                .where(SiteFeature.project_id == project_id)
                .order_by(SiteFeature.sort_order, SiteFeature.name)
            )
            return [SiteFeatureOut.model_validate(f) for f in rows.scalars()]

    @mcp.tool()
    async def create_site_feature(
        project_id: uuid.UUID, feature: SiteFeatureCreate
    ) -> SiteFeatureOut:
        """Add a site feature; the polygon is optional GeoJSON in the project's site frame
        (metres)."""
        async with tenant_ctx(write=True) as ctx:
            ctx.require("project", Action.WRITE)
            ctx.require_project(project_id)
            p = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
            f = await projects.create_site_feature(
                ctx.session, p, feature.model_dump(), _actor(ctx)
            )
            return SiteFeatureOut.model_validate(f)

    return mcp


def transport_security(settings: Settings) -> TransportSecuritySettings:
    """Host and Origin checks the MCP spec requires; only the admin host in production."""
    hosts = [settings.admin_host, f"{settings.admin_host}:*"]
    origins = [f"https://{settings.admin_host}"]
    if not settings.is_production:
        hosts += ["127.0.0.1:*", "localhost:*", "[::1]:*", "testserver"]
        origins += ["http://127.0.0.1:*", "http://localhost:*", "https://localhost:*"]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins
    )


def mcp_asgi(settings: Settings, path: str = "/mcp") -> tuple[MCPServer, ASGIApp]:
    """The server and the ASGI app to register at ``path``: stateless Streamable HTTP with JSON
    responses (any api replica answers any request), behind the bearer-token middleware."""
    server = build_server()
    app = server.streamable_http_app(
        streamable_http_path=path,
        json_response=True,
        stateless_http=True,
        transport_security=transport_security(settings),
        max_request_body_size=MAX_BODY_BYTES,
    )
    return server, BearerTokenMiddleware(app)
