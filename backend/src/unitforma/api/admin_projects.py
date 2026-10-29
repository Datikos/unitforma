"""Staff workspace API: projects, buildings, floors, site features."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select

from unitforma.api import admin_setup
from unitforma.api.schemas import (
    BlocksAcceptIn,
    BlocksAcceptOut,
    BuildingCreate,
    BuildingOut,
    BuildingUpdate,
    ElevationCandidateOut,
    FloorOut,
    FloorProposalOut,
    FloorsBulkCreate,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    SetupOut,
    SiteFeatureCreate,
    SiteFeatureOut,
    SiteFeatureUpdate,
)
from unitforma.autopilot import control as setup_control
from unitforma.autopilot import service as autopilot
from unitforma.autopilot.queue import queue_run
from unitforma.core.errors import ProblemError
from unitforma.documents import floor_proposal as proposal
from unitforma.geometry import service as geometry_service
from unitforma.identity.authz import Action, is_allowed
from unitforma.identity.deps import TenantContext, tenant_context
from unitforma.projects import service as projects
from unitforma.publishing import service as publishing
from unitforma.tenants.models import Project, SiteFeature, Tenant

router = APIRouter(prefix="/api/v1/admin/tenants/{tenant_id}", tags=["projects"])
Ctx = Annotated[TenantContext, Depends(tenant_context)]


def _actor(ctx: TenantContext) -> tuple[uuid.UUID, str]:
    return ctx.principal.user_id, ctx.actor_role


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(ctx: Ctx):
    ctx.require("project", Action.READ)
    q = select(Project).where(Project.tenant_id == ctx.tenant_id)
    if ctx.scope != "platform" and not ctx.membership.all_projects:
        q = q.where(Project.id.in_(ctx.membership.project_ids))
    rows = await ctx.session.execute(q.order_by(Project.name))
    return list(rows.scalars())


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreate, ctx: Ctx):
    ctx.require("project", Action.WRITE)
    tenant = (
        await ctx.session.execute(select(Tenant).where(Tenant.id == ctx.tenant_id))
    ).scalar_one()
    if body.setup_auto and body.setup_auto.enabled and body.setup_auto.approve_sheets:
        ctx.require("mapping", Action.APPROVE)
    if body.setup_auto and body.setup_auto.enabled and body.setup_auto.publish_defaults:
        admin_setup.require_publish_defaults(ctx)
    p = await projects.create_project(
        ctx.session,
        tenant_id=ctx.tenant_id,
        data=body.model_dump(exclude={"building_code", "setup_auto"}),
        actor=_actor(ctx),
        default_currency=tenant.default_currency,
    )
    # the intake form (ADR-0025 Decision 1): the building the drawings are filed under, and the
    # solver's switches; the first processed document queues the first run
    if body.building_code:
        await projects.create_building(ctx.session, p, {"code": body.building_code}, _actor(ctx))
    if body.setup_auto is not None:
        autopilot.set_auto_settings(
            p,
            enabled=body.setup_auto.enabled,
            approve_sheets=body.setup_auto.approve_sheets,
            publish_defaults=body.setup_auto.publish_defaults,
            actor=_actor(ctx),
        )
    await ctx.session.flush()
    await ctx.session.refresh(p)
    return p


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: uuid.UUID, ctx: Ctx):
    ctx.require("project", Action.READ)
    ctx.require_project(project_id)
    return await projects.get_project(ctx.session, ctx.tenant_id, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(project_id: uuid.UUID, body: ProjectUpdate, ctx: Ctx):
    ctx.require("project", Action.WRITE)
    ctx.require_project(project_id)
    p = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    changes = body.model_dump(exclude={"version"}, exclude_none=True)
    if changes.get("status") == "archived" and p.status != "archived":
        await _take_offline(ctx, p)
    return await projects.update_project(ctx.session, p, changes, body.version, _actor(ctx))


async def _take_offline(ctx: TenantContext, p) -> None:
    """ADR-0012 amendment of 2026-10-27: archiving or deleting a published project retires its
    live publication in the same transaction (the portal shows "coming soon" within seconds);
    the caller needs the publish right on top of its own. Nothing happens when it is not live."""
    if await publishing.current_publication(ctx.session, p.id) is None:
        return
    ctx.require("publication", Action.PUBLISH)
    await publishing.unpublish(ctx.session, p, _actor(ctx))


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: uuid.UUID, confirm: str, ctx: Ctx):
    """Permanent delete, tenant admin only, typed slug; a live publication is retired first
    (ADR-0012 Decision 4, amended 2026-10-27)."""
    ctx.require("project", Action.MANAGE)
    ctx.require_project(project_id)
    p = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    projects.check_confirm(p, confirm)  # a wrong slug must not take the portal offline
    await _take_offline(ctx, p)
    await projects.delete_project(ctx.session, p, confirm, _actor(ctx))
    return Response(status_code=204)


@router.get("/projects/{project_id}/buildings", response_model=list[BuildingOut])
async def list_buildings(project_id: uuid.UUID, ctx: Ctx):
    ctx.require("project", Action.READ)
    ctx.require_project(project_id)
    await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    return await projects.list_buildings(ctx.session, project_id)


@router.post("/projects/{project_id}/buildings", response_model=BuildingOut, status_code=201)
async def create_building(project_id: uuid.UUID, body: BuildingCreate, ctx: Ctx):
    ctx.require("project", Action.WRITE)
    ctx.require_project(project_id)
    p = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    return await projects.create_building(ctx.session, p, body.model_dump(), _actor(ctx))


@router.patch("/buildings/{building_id}", response_model=BuildingOut)
async def update_building(building_id: uuid.UUID, body: BuildingUpdate, ctx: Ctx):
    ctx.require("project", Action.READ)
    b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
    ctx.require_project(b.project_id)
    # unset fields are kept, an explicit null clears the clearable ones (ADR-0014 Decision 3);
    # the nested transform keeps its defaults (exclude_unset would drop scale and elevation)
    changes = body.model_dump(exclude={"version"}, exclude_unset=True)
    changes = {
        k: v for k, v in changes.items() if v is not None or k in projects.BUILDING_CLEARABLE
    }
    if body.site_transform is not None:
        changes["site_transform"] = body.site_transform.model_dump()
    if changes and set(changes) <= {"site_transform", "placement_status"}:
        # placing a building on the site plan is mapping work (plan §13.1 step 3a): the
        # architectural reviewer may do it even without project write rights
        if not (
            ctx.scope == "platform"
            or is_allowed(ctx.membership, "project", Action.WRITE)
            or is_allowed(ctx.membership, "mapping", Action.WRITE)
        ):
            raise ProblemError(403, "Not allowed", "write on project or mapping")
    else:
        ctx.require("project", Action.WRITE)
    if "site_transform" in changes and "placement_status" not in changes:
        changes["placement_status"] = "draft" if b.placement_status == "unplaced" else None
        changes = {k: v for k, v in changes.items() if v is not None}
    return await projects.update_building(ctx.session, b, changes, body.version, _actor(ctx))


@router.delete("/buildings/{building_id}", status_code=204)
async def delete_building(building_id: uuid.UUID, ctx: Ctx):
    """Delete an empty building; 409 building-has-units otherwise (ADR-0012 Decision 3)."""
    ctx.require("project", Action.WRITE)
    b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
    ctx.require_project(b.project_id)
    await projects.delete_building(ctx.session, b, _actor(ctx))
    return Response(status_code=204)


@router.get(
    "/buildings/{building_id}/elevation-candidates", response_model=list[ElevationCandidateOut]
)
async def elevation_candidates(building_id: uuid.UUID, ctx: Ctx):
    """Sections and elevations of the building that can become its floor picker (ADR-0014)."""
    ctx.require("project", Action.READ)
    b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
    ctx.require_project(b.project_id)
    return await projects.elevation_candidates(ctx.session, b)


@router.get("/buildings/{building_id}/floor-proposal", response_model=FloorProposalOut)
async def floor_proposal(building_id: uuid.UUID, ctx: Ctx):
    """Floors read from the drawings' level markers; accept them with PUT /floors (ADR-0010)."""
    ctx.require("project", Action.READ)
    b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
    ctx.require_project(b.project_id)
    return await proposal.floor_proposal(ctx.session, b)


@router.post("/buildings/{building_id}/floor-proposal/blocks", response_model=BlocksAcceptOut)
async def accept_blocks(building_id: uuid.UUID, body: BlocksAcceptIn, ctx: Ctx):
    """Split-level blocks become buildings with their floors (ADR-0014); the source building is
    removed when asked and empty; the sheets' floor suggestions are refreshed afterwards."""
    ctx.require("project", Action.WRITE)
    b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
    ctx.require_project(b.project_id)
    project_id = b.project_id
    created, removed = await proposal.accept_blocks(
        ctx.session,
        b,
        [blk.model_dump() for blk in body.blocks],
        delete_source=body.delete_source,
        actor=_actor(ctx),
    )
    await proposal.queue_resuggest(ctx.tenant_id, project_id)
    await queue_run(ctx.tenant_id, project_id, "floors_saved", requested_by=ctx.principal.user_id)
    out = [await projects.get_building(ctx.session, ctx.tenant_id, c.id) for c in created]
    return BlocksAcceptOut(buildings=out, source_removed=removed)


@router.put("/buildings/{building_id}/floors", response_model=list[FloorOut])
async def set_floors(building_id: uuid.UUID, body: FloorsBulkCreate, ctx: Ctx):
    ctx.require("project", Action.WRITE)
    b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
    ctx.require_project(b.project_id)
    floors = await projects.set_floors(
        ctx.session, b, [f.model_dump() for f in body.floors], _actor(ctx)
    )
    # sheets processed before these floors existed get their page → floor suggestions now
    await proposal.queue_resuggest(ctx.tenant_id, b.project_id)
    await queue_run(ctx.tenant_id, b.project_id, "floors_saved", requested_by=ctx.principal.user_id)
    return floors


@router.delete("/buildings/{building_id}/floors/{floor_id}", status_code=204)
async def delete_floor(building_id: uuid.UUID, floor_id: uuid.UUID, ctx: Ctx):
    """Delete a floor no unit uses (ADR-0031 #E1); 409 floor-has-units otherwise. The sheets'
    floor suggestions and the massing are refreshed."""
    ctx.require("project", Action.WRITE)
    b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
    ctx.require_project(b.project_id)
    await projects.delete_floor(ctx.session, b, floor_id, _actor(ctx))
    await proposal.queue_resuggest(ctx.tenant_id, b.project_id)
    await geometry_service.queue_massing(ctx.tenant_id, b.project_id)
    return Response(status_code=204)


@router.get("/projects/{project_id}/site-features", response_model=list[SiteFeatureOut])
async def list_site_features(project_id: uuid.UUID, ctx: Ctx):
    ctx.require("project", Action.READ)
    ctx.require_project(project_id)
    rows = await ctx.session.execute(
        select(SiteFeature)
        .where(SiteFeature.project_id == project_id)
        .order_by(SiteFeature.sort_order, SiteFeature.name)
    )
    return list(rows.scalars())


@router.post("/projects/{project_id}/site-features", response_model=SiteFeatureOut, status_code=201)
async def create_site_feature(project_id: uuid.UUID, body: SiteFeatureCreate, ctx: Ctx):
    ctx.require("project", Action.WRITE)
    ctx.require_project(project_id)
    p = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    return await projects.create_site_feature(ctx.session, p, body.model_dump(), _actor(ctx))


async def _site_feature(ctx: Ctx, feature_id: uuid.UUID) -> SiteFeature:
    sf = (
        await ctx.session.execute(select(SiteFeature).where(SiteFeature.id == feature_id))
    ).scalar_one_or_none()
    if sf is None:
        raise ProblemError(404, "Site feature not found")
    ctx.require_project(sf.project_id)
    return sf


@router.patch("/site-features/{feature_id}", response_model=SiteFeatureOut)
async def update_site_feature(feature_id: uuid.UUID, body: SiteFeatureUpdate, ctx: Ctx):
    ctx.require("project", Action.WRITE)
    sf = await _site_feature(ctx, feature_id)
    return await projects.update_site_feature(ctx.session, sf, body.model_dump(), _actor(ctx))


@router.delete("/site-features/{feature_id}", status_code=204)
async def delete_site_feature(feature_id: uuid.UUID, ctx: Ctx):
    ctx.require("project", Action.WRITE)
    sf = await _site_feature(ctx, feature_id)
    await projects.delete_site_feature(ctx.session, sf, _actor(ctx))


@router.get("/projects/{project_id}/setup", response_model=SetupOut)
async def project_setup(project_id: uuid.UUID, ctx: Ctx):
    """The setup checklist: the order of work and what each step still needs (ADR-0017), with
    what the setup solver did and left (ADR-0025 Decision 7)."""
    return await setup_control.checklist(ctx, project_id)
