"""Staff API: building footprints, placement and the generated massing model (plan §11.3)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from unitforma.api.schemas import (
    BuildingModelOut,
    FootprintOut,
    IfcSpaceLinkDecide,
    IfcSpaceLinkOut,
    MassingOut,
)
from unitforma.core.errors import ProblemError
from unitforma.geometry import ifc_service
from unitforma.geometry import service as geometry
from unitforma.identity.authz import Action
from unitforma.identity.deps import TenantContext, tenant_context
from unitforma.jobs.app import app as jobs
from unitforma.projects import service as projects
from unitforma.tenants.models import Floor, Unit

router = APIRouter(prefix="/api/v1/admin/tenants/{tenant_id}", tags=["geometry"])
Ctx = Annotated[TenantContext, Depends(tenant_context)]


def _actor(ctx: TenantContext) -> tuple[uuid.UUID, str]:
    return ctx.principal.user_id, ctx.actor_role


def _massing_out(m) -> MassingOut:
    out = MassingOut.model_validate(m)
    out.glb_url = geometry.signed_url(m)
    return out


@router.get("/projects/{project_id}/footprints", response_model=list[FootprintOut])
async def list_footprints(project_id: uuid.UUID, ctx: Ctx):
    """Building outlines (lowest mapped floor, building-local metres) for the placement editor."""
    ctx.require("project", Action.READ)
    ctx.require_project(project_id)
    project = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    return await geometry.footprints(ctx.session, project)


@router.get("/projects/{project_id}/massing", response_model=MassingOut)
async def get_massing(project_id: uuid.UUID, ctx: Ctx):
    ctx.require("project", Action.READ)
    ctx.require_project(project_id)
    return _massing_out(await geometry.require_model(ctx.session, ctx.tenant_id, project_id))


@router.post("/projects/{project_id}/massing", response_model=MassingOut, status_code=202)
async def regenerate_massing(project_id: uuid.UUID, ctx: Ctx):
    """Queue a rebuild of the massing GLB (``geometry.build_massing``). The worker replaces the
    current model; until then the previous one stays available."""
    ctx.require("mapping", Action.WRITE)
    ctx.require_project(project_id)
    project = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    try:
        await jobs.configure_task(name="geometry.build_massing", queue="geometry").defer_async(
            tenant_id=str(ctx.tenant_id), project_id=str(project.id)
        )
    except Exception as e:  # noqa: BLE001
        raise ProblemError(503, "Worker queue unavailable", str(e)[:300]) from e
    current = await geometry.current_massing(ctx.session, project.id)
    if current is None:
        # nothing to show yet: report the queued state without a model row
        return MassingOut(
            id=uuid.UUID(int=0),
            project_id=project.id,
            kind="massing_generated",
            status="generating",
            stats={},
            error=None,
            glb_url=None,
            created_at=project.updated_at,
        )
    return _massing_out(current)


# --- IFC models per building (ADR-0006 Phase C) ---------------------------------------------
def _model_out(m, links) -> BuildingModelOut:
    out = BuildingModelOut.model_validate(m)
    out.glb_url = geometry.signed_url(m)
    out.links = ifc_service.link_counts(links)
    return out


async def _link_out(ctx: TenantContext, lk) -> IfcSpaceLinkOut:
    out = IfcSpaceLinkOut.model_validate(lk)
    if lk.unit_id:
        u = (
            await ctx.session.execute(select(Unit.code).where(Unit.id == lk.unit_id))
        ).scalar_one_or_none()
        out.unit_code = u
    if lk.floor_id:
        out.floor_level = (
            await ctx.session.execute(select(Floor.level).where(Floor.id == lk.floor_id))
        ).scalar_one_or_none()
    return out


@router.get("/buildings/{building_id}/model", response_model=BuildingModelOut | None)
async def get_building_model(building_id: uuid.UUID, ctx: Ctx):
    """The building's current IFC-derived model, or null when none was ingested."""
    ctx.require("project", Action.READ)
    b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
    ctx.require_project(b.project_id)
    m = await ifc_service.current_model(ctx.session, b.id)
    if m is None:
        return None
    out = _model_out(m, await ifc_service.list_links(ctx.session, m.id))
    out.plan_fit_realigned = await ifc_service.realigned_levels(ctx.session, m)
    return out


@router.get("/buildings/{building_id}/ifc-links", response_model=list[IfcSpaceLinkOut])
async def list_ifc_links(building_id: uuid.UUID, ctx: Ctx):
    ctx.require("mapping", Action.READ)
    b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
    ctx.require_project(b.project_id)
    m = await ifc_service.current_model(ctx.session, b.id)
    if m is None:
        return []
    return [await _link_out(ctx, lk) for lk in await ifc_service.list_links(ctx.session, m.id)]


@router.post("/buildings/{building_id}/ifc-links/confirm-plan", response_model=dict)
async def confirm_plan_ifc_links(building_id: uuid.UUID, ctx: Ctx) -> dict:
    """Confirm every suggested plan space of the building's model as its unit (ADR-0030)."""
    ctx.require("mapping", Action.APPROVE)
    b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
    ctx.require_project(b.project_id)
    m = await ifc_service.current_model(ctx.session, b.id)
    if m is None:
        raise ProblemError(404, "No IFC model for this building")
    return {"confirmed": await ifc_service.confirm_plan_links(ctx.session, m, _actor(ctx))}


@router.post("/ifc-links/{link_id}", response_model=IfcSpaceLinkOut)
async def decide_ifc_link(link_id: uuid.UUID, body: IfcSpaceLinkDecide, ctx: Ctx):
    """Confirm a space as a unit (the suggested one or another), reject it, or reset it."""
    ctx.require("mapping", Action.APPROVE)
    lk = await ifc_service.get_link(ctx.session, ctx.tenant_id, link_id)
    ctx.require_project(lk.project_id)
    lk = await ifc_service.decide(
        ctx.session, lk, decision=body.decision, unit_id=body.unit_id, actor=_actor(ctx)
    )
    return await _link_out(ctx, lk)


@router.post("/buildings/{building_id}/model/rebuild", status_code=202)
async def rebuild_building_model(building_id: uuid.UUID, ctx: Ctx) -> dict:
    """Queue the IFC ingestion again for the revision the current model came from."""
    ctx.require("mapping", Action.WRITE)
    b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
    ctx.require_project(b.project_id)
    m = await ifc_service.current_model(ctx.session, b.id)
    if m is None or m.revision_id is None:
        raise ProblemError(404, "No IFC model for this building")
    try:
        await jobs.configure_task(name="geometry.ingest_ifc", queue="geometry-heavy").defer_async(
            tenant_id=str(ctx.tenant_id), revision_id=str(m.revision_id)
        )
    except Exception as e:  # noqa: BLE001
        raise ProblemError(503, "Worker queue unavailable", str(e)[:300]) from e
    return {"queued": True, "revision_id": str(m.revision_id)}
