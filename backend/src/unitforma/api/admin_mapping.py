"""Staff API: unit boundaries, draft units, review/approve, lineage, areas (plan §13)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from unitforma.api.schemas import (
    AreaOut,
    AreaSet,
    BoundaryCreate,
    BoundaryOut,
    BoundaryUpdate,
    CodeHistoryOut,
    LineageOut,
    UnitCreated,
    UnitMerge,
    UnitOut,
    UnitRelabel,
    UnitRemove,
    UnitSplit,
)
from unitforma.core.errors import ProblemError
from unitforma.documents import service as documents
from unitforma.identity.authz import Action
from unitforma.identity.deps import TenantContext, tenant_context
from unitforma.inventory import service as inventory
from unitforma.projects import service as projects
from unitforma.tenants.models import Unit, UnitArea, UnitBoundary, UnitCodeHistory, UnitLineageEvent

router = APIRouter(prefix="/api/v1/admin/tenants/{tenant_id}", tags=["mapping"])
Ctx = Annotated[TenantContext, Depends(tenant_context)]


def _actor(ctx: TenantContext) -> tuple[uuid.UUID, str]:
    return ctx.principal.user_id, ctx.actor_role


async def _unit_out(ctx: TenantContext, unit: Unit) -> UnitOut:
    out = UnitOut.model_validate(unit)
    areas = await ctx.session.execute(
        select(UnitArea)
        .where(UnitArea.unit_id == unit.id, UnitArea.is_current.is_(True))
        .order_by(UnitArea.area_type)
    )
    out.areas = [AreaOut.model_validate(a) for a in areas.scalars()]
    bounds = await ctx.session.execute(
        select(UnitBoundary).where(
            UnitBoundary.unit_id == unit.id, UnitBoundary.is_current.is_(True)
        )
    )
    out.boundaries = [BoundaryOut.model_validate(b) for b in bounds.scalars()]
    return out


async def _get_unit(ctx: TenantContext, unit_id: uuid.UUID) -> Unit:
    u = (
        await ctx.session.execute(
            select(Unit).where(Unit.tenant_id == ctx.tenant_id, Unit.id == unit_id)
        )
    ).scalar_one_or_none()
    if u is None:
        raise ProblemError(404, "Unit not found")
    ctx.require_project(u.project_id)
    return u


# --- boundaries on a sheet ----------------------------------------------------------------
@router.get("/sheets/{sheet_id}/boundaries", response_model=list[BoundaryOut])
async def list_boundaries(sheet_id: uuid.UUID, ctx: Ctx):
    ctx.require("mapping", Action.READ)
    sheet = await documents.get_sheet(ctx.session, ctx.tenant_id, sheet_id)
    ctx.require_project(await documents.sheet_project_id(ctx.session, sheet))
    rows = await ctx.session.execute(
        select(UnitBoundary)
        .where(UnitBoundary.sheet_id == sheet.id, UnitBoundary.is_current.is_(True))
        .order_by(UnitBoundary.created_at)
    )
    return list(rows.scalars())


@router.post("/sheets/{sheet_id}/boundaries", response_model=UnitCreated, status_code=201)
async def create_boundary(sheet_id: uuid.UUID, body: BoundaryCreate, ctx: Ctx):
    """Draw a unit boundary: creates a draft unit with a permanent id and a generated code."""
    ctx.require("mapping", Action.WRITE)
    sheet = await documents.get_sheet(ctx.session, ctx.tenant_id, sheet_id)
    project_id = await documents.sheet_project_id(ctx.session, sheet)
    ctx.require_project(project_id)
    project = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    try:
        unit, boundary = await inventory.create_unit_from_boundary(
            ctx.session,
            project=project,
            sheet=sheet,
            ring=body.ring,
            unit_type=body.unit_type,
            code=body.code,
            label=body.label,
            revision_id=sheet.revision_id,
            actor=_actor(ctx),
        )
    except ValueError as e:
        raise ProblemError(422, "Invalid boundary", str(e)) from e
    return UnitCreated(
        unit=await _unit_out(ctx, unit), boundary=BoundaryOut.model_validate(boundary)
    )


@router.patch("/boundaries/{boundary_id}", response_model=BoundaryOut)
async def update_boundary(boundary_id: uuid.UUID, body: BoundaryUpdate, ctx: Ctx):
    ctx.require("mapping", Action.WRITE)
    b = (
        await ctx.session.execute(
            select(UnitBoundary).where(
                UnitBoundary.tenant_id == ctx.tenant_id, UnitBoundary.id == boundary_id
            )
        )
    ).scalar_one_or_none()
    if b is None:
        raise ProblemError(404, "Boundary not found")
    await _get_unit(ctx, b.unit_id)
    try:
        return await inventory.update_boundary(ctx.session, b, body.ring, body.version, _actor(ctx))
    except ValueError as e:
        raise ProblemError(422, "Invalid boundary", str(e)) from e


@router.post("/sheets/{sheet_id}/approve", response_model=dict)
async def approve_sheet(sheet_id: uuid.UUID, ctx: Ctx):
    """Architectural reviewer approves the mapping on a sheet (plan §13.1 step 5)."""
    ctx.require("mapping", Action.APPROVE)
    sheet = await documents.get_sheet(ctx.session, ctx.tenant_id, sheet_id)
    ctx.require_project(await documents.sheet_project_id(ctx.session, sheet))
    n = await inventory.approve_sheet(ctx.session, sheet, _actor(ctx))
    return {"approved_units": n}


# --- units ---------------------------------------------------------------------------------
@router.get("/projects/{project_id}/units", response_model=list[UnitOut])
async def list_units(project_id: uuid.UUID, ctx: Ctx, include_removed: bool = False):
    ctx.require("project", Action.READ)
    ctx.require_project(project_id)
    q = select(Unit).where(Unit.project_id == project_id)
    if not include_removed:
        q = q.where(Unit.lifecycle_status != "removed")
    rows = await ctx.session.execute(q.order_by(Unit.code))
    return [await _unit_out(ctx, u) for u in rows.scalars()]


@router.get("/units/{unit_id}", response_model=UnitOut)
async def get_unit(unit_id: uuid.UUID, ctx: Ctx):
    ctx.require("project", Action.READ)
    return await _unit_out(ctx, await _get_unit(ctx, unit_id))


@router.post("/units/{unit_id}/relabel", response_model=UnitOut)
async def relabel_unit(unit_id: uuid.UUID, body: UnitRelabel, ctx: Ctx):
    ctx.require("mapping", Action.WRITE)
    u = await _get_unit(ctx, unit_id)
    try:
        return await _unit_out(
            ctx,
            await inventory.relabel(
                ctx.session, u, body.code, body.version, _actor(ctx), body.reason
            ),
        )
    except ValueError as e:
        raise ProblemError(422, "Invalid code", str(e)) from e


@router.post("/units/{unit_id}/remove", response_model=UnitOut)
async def remove_unit(unit_id: uuid.UUID, body: UnitRemove, ctx: Ctx):
    ctx.require("mapping", Action.APPROVE)
    u = await _get_unit(ctx, unit_id)
    return await _unit_out(
        ctx, await inventory.remove_unit(ctx.session, u, body.version, _actor(ctx), None, body.note)
    )


@router.post("/projects/{project_id}/units/merge", response_model=UnitOut)
async def merge_units(project_id: uuid.UUID, body: UnitMerge, ctx: Ctx):
    ctx.require("mapping", Action.APPROVE)
    ctx.require_project(project_id)
    project = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    survivor = await _get_unit(ctx, body.survivor_id)
    absorbed = [await _get_unit(ctx, i) for i in body.absorbed_ids]
    sheet = (
        await documents.get_sheet(ctx.session, ctx.tenant_id, body.sheet_id)
        if body.sheet_id
        else None
    )
    try:
        u = await inventory.merge_units(
            ctx.session, project, survivor, absorbed, body.ring, sheet, _actor(ctx), None, body.note
        )
    except ValueError as e:
        raise ProblemError(422, "Invalid boundary", str(e)) from e
    return await _unit_out(ctx, u)


@router.post("/units/{unit_id}/split", response_model=list[UnitOut])
async def split_unit(unit_id: uuid.UUID, body: UnitSplit, ctx: Ctx):
    ctx.require("mapping", Action.APPROVE)
    u = await _get_unit(ctx, unit_id)
    project = await projects.get_project(ctx.session, ctx.tenant_id, u.project_id)
    sheet = await documents.get_sheet(ctx.session, ctx.tenant_id, body.sheet_id)
    try:
        units = await inventory.split_unit(
            ctx.session, project, u, sheet, body.rings, body.codes, _actor(ctx), None, body.note
        )
    except ValueError as e:
        raise ProblemError(422, "Invalid boundary", str(e)) from e
    return [await _unit_out(ctx, x) for x in units]


@router.put("/units/{unit_id}/areas", response_model=AreaOut)
async def set_area(unit_id: uuid.UUID, body: AreaSet, ctx: Ctx):
    ctx.require("mapping", Action.WRITE)
    u = await _get_unit(ctx, unit_id)
    if body.verified:
        ctx.require("mapping", Action.APPROVE)
    return await inventory.set_manual_area(
        ctx.session, u, body.area_type, float(body.value_m2), _actor(ctx), body.verified
    )


@router.post("/areas/{area_id}/verify", response_model=AreaOut)
async def verify_area(area_id: uuid.UUID, ctx: Ctx):
    ctx.require("mapping", Action.APPROVE)
    a = (
        await ctx.session.execute(
            select(UnitArea).where(UnitArea.tenant_id == ctx.tenant_id, UnitArea.id == area_id)
        )
    ).scalar_one_or_none()
    if a is None:
        raise ProblemError(404, "Area not found")
    await _get_unit(ctx, a.unit_id)
    return await inventory.verify_area(ctx.session, a, _actor(ctx))


@router.get("/units/{unit_id}/history", response_model=dict)
async def unit_history(unit_id: uuid.UUID, ctx: Ctx):
    ctx.require("project", Action.READ)
    u = await _get_unit(ctx, unit_id)
    codes = await ctx.session.execute(
        select(UnitCodeHistory)
        .where(UnitCodeHistory.unit_id == u.id)
        .order_by(UnitCodeHistory.changed_at)
    )
    lineage = await ctx.session.execute(
        select(UnitLineageEvent)
        .where(
            UnitLineageEvent.project_id == u.project_id,
            (UnitLineageEvent.from_unit_ids.any(u.id)) | (UnitLineageEvent.to_unit_ids.any(u.id)),
        )
        .order_by(UnitLineageEvent.decided_at)
    )
    return {
        "codes": [
            CodeHistoryOut.model_validate(c).model_dump(mode="json") for c in codes.scalars()
        ],
        "lineage": [
            LineageOut.model_validate(e).model_dump(mode="json") for e in lineage.scalars()
        ],
    }


@router.get("/projects/{project_id}/lineage", response_model=list[LineageOut])
async def project_lineage(project_id: uuid.UUID, ctx: Ctx):
    ctx.require("project", Action.READ)
    ctx.require_project(project_id)
    rows = await ctx.session.execute(
        select(UnitLineageEvent)
        .where(UnitLineageEvent.project_id == project_id)
        .order_by(UnitLineageEvent.decided_at.desc())
        .limit(500)
    )
    return list(rows.scalars())
