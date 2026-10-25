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
    ProposalAcceptAll,
    ProposalDecide,
    ProposalItemOut,
    ProposalOut,
    SuggestionOut,
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
from unitforma.jobs.app import app as jobs
from unitforma.mapping import service as mapping
from unitforma.projects import service as projects
from unitforma.tenants.models import (
    MappingProposal,
    MappingProposalItem,
    Unit,
    UnitArea,
    UnitBoundary,
    UnitCodeHistory,
    UnitLineageEvent,
)

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
            source=body.source,
            floor_id=body.floor_id,
        )
    except ValueError as e:
        raise ProblemError(422, "Invalid boundary", str(e)) from e
    return UnitCreated(
        unit=await _unit_out(ctx, unit), boundary=BoundaryOut.model_validate(boundary)
    )


@router.post("/sheets/{sheet_id}/suggestions", response_model=list[SuggestionOut])
async def suggest_boundaries(sheet_id: uuid.UUID, ctx: Ctx):
    """Closed loops found in the sheet's vector line work, labelled from inner text (plan §13.2).

    Nothing is written: the reviewer accepts candidates one by one (creating boundaries with
    ``source=vector_suggest``). Scanned sheets have no vectors and return an empty list.
    """
    ctx.require("mapping", Action.READ)
    sheet = await documents.get_sheet(ctx.session, ctx.tenant_id, sheet_id)
    ctx.require_project(await documents.sheet_project_id(ctx.session, sheet))
    return [
        SuggestionOut(**c.as_dict(), floor_id=fid)
        for c, fid in await mapping.suggest_for_sheet(ctx.session, sheet)
    ]


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
    project_id = await documents.sheet_project_id(ctx.session, sheet)
    ctx.require_project(project_id)
    n = await inventory.approve_sheet(ctx.session, sheet, _actor(ctx))
    massing_queued = False
    if n:
        # approval → massing regeneration in the same transaction (plan §4.3 transactional enqueue)
        try:
            await jobs.configure_task(name="geometry.build_massing", queue="geometry").defer_async(
                tenant_id=str(ctx.tenant_id), project_id=str(project_id)
            )
            massing_queued = True
        except Exception as e:  # noqa: BLE001 - approval must not fail because the queue is down
            import structlog

            structlog.get_logger().warning("geometry.enqueue_failed", error=str(e))
    return {"approved_units": n, "massing_queued": massing_queued}


# --- revision diff proposals ----------------------------------------------------------------
async def _proposal_out(ctx: TenantContext, p: MappingProposal, with_items: bool) -> ProposalOut:
    out = ProposalOut.model_validate(p)
    if with_items:
        out.items = [
            ProposalItemOut.model_validate(i) for i in await mapping.list_items(ctx.session, p.id)
        ]
    return out


@router.get("/projects/{project_id}/proposals", response_model=list[ProposalOut])
async def list_proposals(project_id: uuid.UUID, ctx: Ctx, status: str | None = None):
    ctx.require("mapping", Action.READ)
    ctx.require_project(project_id)
    q = select(MappingProposal).where(MappingProposal.project_id == project_id)
    if status:
        q = q.where(MappingProposal.status == status)
    rows = await ctx.session.execute(q.order_by(MappingProposal.created_at.desc()).limit(200))
    return [await _proposal_out(ctx, p, False) for p in rows.scalars()]


@router.get("/proposals/{proposal_id}", response_model=ProposalOut)
async def get_proposal(proposal_id: uuid.UUID, ctx: Ctx):
    ctx.require("mapping", Action.READ)
    p = await mapping.get_proposal(ctx.session, ctx.tenant_id, proposal_id)
    ctx.require_project(p.project_id)
    return await _proposal_out(ctx, p, True)


@router.post("/revisions/{revision_id}/proposals", response_model=ProposalOut, status_code=201)
async def build_proposal(revision_id: uuid.UUID, ctx: Ctx):
    """(Re)build the diff of a processed revision against the revision it supersedes.

    The worker does this automatically after processing; this endpoint re-runs it (for
    example after the reviewer finished mapping the old revision late).
    """
    ctx.require("mapping", Action.WRITE)
    rev = await documents.get_revision(ctx.session, ctx.tenant_id, revision_id)
    doc = await documents.get_document(ctx.session, ctx.tenant_id, rev.document_id)
    ctx.require_project(doc.project_id)
    if rev.processing_status not in ("done", "partial"):
        raise ProblemError(409, "Revision is not processed yet", rev.processing_status)
    p = await mapping.build_proposal(ctx.session, ctx.tenant_id, rev, ctx.principal.user_id)
    if p is None:
        raise ProblemError(
            409,
            "Nothing to diff",
            "The revision has no predecessor with mapped pages (same page numbers)",
        )
    return await _proposal_out(ctx, p, True)


@router.post("/proposals/{proposal_id}/items/{item_id}", response_model=ProposalItemOut)
async def decide_item(proposal_id: uuid.UUID, item_id: uuid.UUID, body: ProposalDecide, ctx: Ctx):
    """Accept (apply through identity-preserving operations) or reject one proposal item."""
    ctx.require("mapping", Action.APPROVE)
    p = await mapping.get_proposal(ctx.session, ctx.tenant_id, proposal_id)
    ctx.require_project(p.project_id)
    item = (
        await ctx.session.execute(
            select(MappingProposalItem).where(
                MappingProposalItem.proposal_id == p.id, MappingProposalItem.id == item_id
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise ProblemError(404, "Proposal item not found")
    overrides = body.model_dump(exclude={"decision"}, exclude_none=True)
    return await mapping.decide_item(
        ctx.session, p, item, decision=body.decision, overrides=overrides, actor=_actor(ctx)
    )


@router.post("/proposals/{proposal_id}/accept-all", response_model=ProposalOut)
async def accept_all(proposal_id: uuid.UUID, body: ProposalAcceptAll, ctx: Ctx):
    """Accept every pending item of the given kinds (default: confident 1:1 matches)."""
    ctx.require("mapping", Action.APPROVE)
    p = await mapping.get_proposal(ctx.session, ctx.tenant_id, proposal_id)
    ctx.require_project(p.project_id)
    await mapping.accept_all(ctx.session, p, set(body.kinds), _actor(ctx))
    return await _proposal_out(ctx, p, True)


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
