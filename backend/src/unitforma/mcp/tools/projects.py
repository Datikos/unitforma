"""Tools over projects and site features (ADR-0015 Decision 5), moved from ``mcp/server.py``
unchanged (ADR-0028 #C1)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field
from sqlalchemy import select

from unitforma.api.schemas import (
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    SiteFeatureCreate,
    SiteFeatureOut,
)
from unitforma.core.errors import ProblemError
from unitforma.identity.authz import Action
from unitforma.identity.deps import TenantContext
from unitforma.mcp.auth import current_principal, tenant_ctx
from unitforma.mcp.tools.base import Tool, actor
from unitforma.projects import service as projects
from unitforma.publishing import service as publishing
from unitforma.tenants.models import Project, SiteFeature, Tenant


class WhoAmI(BaseModel):
    tenant_id: uuid.UUID
    tenant_slug: str
    tenant_name: str
    user_email: str
    role: str
    token_scope: str
    all_projects: bool
    project_ids: list[uuid.UUID] = Field(default_factory=list)


async def _refuse_if_published(ctx: TenantContext, p: Project, verb: str) -> None:
    if await publishing.current_publication(ctx.session, p.id) is not None:
        raise ProblemError(
            409, "Project is published", f"Unpublish {p.name} before it can be {verb}"
        )


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


async def list_projects() -> list[ProjectOut]:
    """Projects the token's owner may see, by name."""
    async with tenant_ctx() as ctx:
        ctx.require("project", Action.READ)
        q = select(Project).where(Project.tenant_id == ctx.tenant_id)
        if not ctx.membership.all_projects:
            q = q.where(Project.id.in_(ctx.membership.project_ids))
        rows = await ctx.session.execute(q.order_by(Project.name))
        return [ProjectOut.model_validate(p) for p in rows.scalars()]


async def get_project(project_id: uuid.UUID) -> ProjectOut:
    """One project with its version, address, area definitions and settings."""
    async with tenant_ctx() as ctx:
        ctx.require("project", Action.READ)
        ctx.require_project(project_id)
        return ProjectOut.model_validate(
            await projects.get_project(ctx.session, ctx.tenant_id, project_id)
        )


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
            actor=actor(ctx),
            default_currency=tenant.default_currency,
        )
        return ProjectOut.model_validate(p)


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
        p = await projects.update_project(ctx.session, p, data, changes.version, actor(ctx))
        return ProjectOut.model_validate(p)


async def list_site_features(project_id: uuid.UUID) -> list[SiteFeatureOut]:
    """Site features of a project (gardens, roads, parking zones, amenities, entrances).
    A polygon is `{"ring": [[x, y], ...]}` in fractions 0 to 1 of the site plan sheet
    (origin top left, y down), not metres."""
    async with tenant_ctx() as ctx:
        ctx.require("project", Action.READ)
        ctx.require_project(project_id)
        rows = await ctx.session.execute(
            select(SiteFeature)
            .where(SiteFeature.project_id == project_id)
            .order_by(SiteFeature.sort_order, SiteFeature.name)
        )
        return [SiteFeatureOut.model_validate(f) for f in rows.scalars()]


async def create_site_feature(project_id: uuid.UUID, feature: SiteFeatureCreate) -> SiteFeatureOut:
    """Add a site feature. The optional polygon is `{"ring": [[x, y], ...]}`, each point a
    fraction 0 to 1 of the project's site plan sheet raster (x across its width, y down
    its height, origin top left); not GeoJSON, not metres. The publication converts it
    to site-frame metres with the sheet's calibration."""
    async with tenant_ctx(write=True) as ctx:
        ctx.require("project", Action.WRITE)
        ctx.require_project(project_id)
        p = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
        f = await projects.create_site_feature(ctx.session, p, feature.model_dump(), actor(ctx))
        return SiteFeatureOut.model_validate(f)


TOOLS = [
    Tool(whoami, "read", "Who am I"),
    Tool(list_projects, "read", "List projects"),
    Tool(get_project, "read", "Get a project"),
    Tool(create_project, "write", "Create a project"),
    Tool(update_project, "write", "Update a project", destructive=True),
    Tool(list_site_features, "read", "List site features"),
    Tool(create_site_feature, "write", "Add a site feature"),
]
