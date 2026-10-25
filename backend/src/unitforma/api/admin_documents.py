"""Staff API: documents, uploads, revisions, sheets (assignment, calibration)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from unitforma.api.schemas import (
    DocumentCreate,
    DocumentOut,
    DocumentUpdate,
    PagesExclude,
    RevisionOut,
    SheetAssign,
    SheetCalibrate,
    SheetExclude,
    SheetFloorOut,
    SheetFloorsSet,
    SheetOut,
    UploadIntentCreate,
    UploadIntentOut,
)
from unitforma.core.errors import ProblemError
from unitforma.documents import assignments
from unitforma.documents import service as documents
from unitforma.geometry import service as geometry_service
from unitforma.identity.authz import Action
from unitforma.identity.deps import TenantContext, tenant_context
from unitforma.inventory import geometry
from unitforma.inventory import service as inventory
from unitforma.jobs.app import app as jobs
from unitforma.projects import service as projects
from unitforma.tenants.models import Document

router = APIRouter(prefix="/api/v1/admin/tenants/{tenant_id}", tags=["documents"])
Ctx = Annotated[TenantContext, Depends(tenant_context)]


def _actor(ctx: TenantContext) -> tuple[uuid.UUID, str]:
    return ctx.principal.user_id, ctx.actor_role


def _doc_out(d: Document, r) -> DocumentOut:
    out = DocumentOut.model_validate(d)
    out.current_revision = RevisionOut.model_validate(r) if r is not None else None
    return out


async def _sheet_out(ctx: TenantContext, s) -> SheetOut:
    return (await _sheets_out(ctx, [s]))[0]


async def _sheets_out(ctx: TenantContext, sheets: list) -> list[SheetOut]:
    floors = await assignments.list_for_sheets(ctx.session, [s.id for s in sheets])
    out = []
    for s in sheets:
        o = SheetOut.model_validate(s)
        for k, v in documents.signed_urls(s).items():
            setattr(o, k, v)
        o.floors = [SheetFloorOut.model_validate(a) for a in floors.get(s.id, [])]
        out.append(o)
    return out


async def _project_of_document(ctx: TenantContext, document_id: uuid.UUID) -> Document:
    d = await documents.get_document(ctx.session, ctx.tenant_id, document_id)
    ctx.require_project(d.project_id)
    return d


@router.get("/projects/{project_id}/documents", response_model=list[DocumentOut])
async def list_documents(project_id: uuid.UUID, ctx: Ctx):
    ctx.require("documents", Action.READ)
    ctx.require_project(project_id)
    await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    return [_doc_out(d, r) for d, r in await documents.list_documents(ctx.session, project_id)]


@router.post("/projects/{project_id}/documents", response_model=DocumentOut, status_code=201)
async def create_document(project_id: uuid.UUID, body: DocumentCreate, ctx: Ctx):
    ctx.require("documents", Action.WRITE)
    ctx.require_project(project_id)
    await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    d = await documents.create_document(
        ctx.session,
        tenant_id=ctx.tenant_id,
        project_id=project_id,
        data=body.model_dump(),
        actor=_actor(ctx),
    )
    return _doc_out(d, None)


@router.patch("/documents/{document_id}", response_model=DocumentOut)
async def update_document(document_id: uuid.UUID, body: DocumentUpdate, ctx: Ctx):
    """Confirm or change the kind, rename, re-file under a building (ADR-0008)."""
    ctx.require("documents", Action.WRITE)
    d = await _project_of_document(ctx, document_id)
    d = await documents.update_document(ctx.session, d, body.model_dump(), _actor(ctx))
    r = (
        await documents.get_revision(ctx.session, ctx.tenant_id, d.current_revision_id)
        if d.current_revision_id
        else None
    )
    return _doc_out(d, r)


@router.post("/documents/{document_id}/uploads", response_model=UploadIntentOut, status_code=201)
async def create_upload(document_id: uuid.UUID, body: UploadIntentCreate, ctx: Ctx):
    ctx.require("documents", Action.WRITE)
    d = await _project_of_document(ctx, document_id)
    rev, url = await documents.create_upload_intent(
        ctx.session,
        d,
        file_name=body.file_name,
        content_type=body.content_type,
        byte_size=body.byte_size,
        uploaded_by=ctx.principal.user_id,
        source_note=body.source_note,
    )
    return UploadIntentOut(
        revision=RevisionOut.model_validate(rev),
        upload_url=url,
        headers={"Content-Type": body.content_type},
    )


@router.post("/revisions/{revision_id}/complete", response_model=RevisionOut)
async def complete_upload(revision_id: uuid.UUID, ctx: Ctx):
    ctx.require("documents", Action.WRITE)
    rev = await documents.get_revision(ctx.session, ctx.tenant_id, revision_id)
    await _project_of_document(ctx, rev.document_id)
    rev = await documents.complete_upload(ctx.session, rev, _actor(ctx))
    if rev.processing_status == "queued":
        try:
            await jobs.configure_task(name="documents.ingest_revision", queue="docs").defer_async(
                tenant_id=str(ctx.tenant_id), revision_id=str(rev.id)
            )
        except Exception as e:  # noqa: BLE001 - the worker schema may be absent in minimal setups
            rev.processing_error = f"could not enqueue: {e}"[:500]
    return rev


@router.get("/documents/{document_id}/revisions", response_model=list[RevisionOut])
async def list_revisions(document_id: uuid.UUID, ctx: Ctx):
    ctx.require("documents", Action.READ)
    await _project_of_document(ctx, document_id)
    return await documents.list_revisions(ctx.session, document_id)


@router.get("/revisions/{revision_id}/sheets", response_model=list[SheetOut])
async def list_sheets(revision_id: uuid.UUID, ctx: Ctx):
    ctx.require("documents", Action.READ)
    rev = await documents.get_revision(ctx.session, ctx.tenant_id, revision_id)
    await _project_of_document(ctx, rev.document_id)
    return await _sheets_out(ctx, await documents.list_sheets(ctx.session, revision_id))


@router.get("/revisions/{revision_id}/download")
async def download_url(revision_id: uuid.UUID, ctx: Ctx) -> dict:
    ctx.require("documents", Action.READ)
    rev = await documents.get_revision(ctx.session, ctx.tenant_id, revision_id)
    await _project_of_document(ctx, rev.document_id)
    from unitforma.storage.service import get_storage

    return {"url": get_storage().presign_get(rev.object_key, filename=rev.file_name)}


@router.get("/sheets/{sheet_id}", response_model=SheetOut)
async def get_sheet(sheet_id: uuid.UUID, ctx: Ctx):
    ctx.require("documents", Action.READ)
    sheet = await documents.get_sheet(ctx.session, ctx.tenant_id, sheet_id)
    ctx.require_project(await documents.sheet_project_id(ctx.session, sheet))
    return await _sheet_out(ctx, sheet)


@router.patch("/sheets/{sheet_id}/floor", response_model=SheetOut)
async def assign_sheet_floor(sheet_id: uuid.UUID, body: SheetAssign, ctx: Ctx):
    ctx.require("mapping", Action.WRITE)
    sheet = await documents.get_sheet(ctx.session, ctx.tenant_id, sheet_id)
    ctx.require_project(await documents.sheet_project_id(ctx.session, sheet))
    await documents.assign_floor(ctx.session, sheet, body.floor_id, body.version, _actor(ctx))
    return await _sheet_out(ctx, sheet)


@router.put("/sheets/{sheet_id}/floors", response_model=SheetOut)
async def set_sheet_floors(sheet_id: uuid.UUID, body: SheetFloorsSet, ctx: Ctx):
    """Every floor the sheet shows, each optionally limited to a region of the sheet.

    A split-level or multi-block sheet shows several floors side by side; units drawn on it
    belong to the floor whose region holds them (plan §13.2). Suggested assignments (from
    level markers or the previous revision) become confirmed when they are sent here.
    """
    ctx.require("mapping", Action.WRITE)
    sheet = await documents.get_sheet(ctx.session, ctx.tenant_id, sheet_id)
    ctx.require_project(await documents.sheet_project_id(ctx.session, sheet))
    await assignments.set_floors(
        ctx.session,
        sheet,
        [
            {"floor_id": f.floor_id, "region": f.region.model_dump() if f.region else None}
            for f in body.floors
        ],
        body.version,
        _actor(ctx),
    )
    return await _sheet_out(ctx, sheet)


@router.patch("/sheets/{sheet_id}/exclusion", response_model=SheetOut)
async def exclude_sheet(sheet_id: uuid.UUID, body: SheetExclude, ctx: Ctx):
    """Take a sheet out of mapping (a reprint, a detail, a schedule) or bring it back."""
    ctx.require("mapping", Action.WRITE)
    sheet = await documents.get_sheet(ctx.session, ctx.tenant_id, sheet_id)
    ctx.require_project(await documents.sheet_project_id(ctx.session, sheet))
    if sheet.version != body.version:
        raise ProblemError(409, "Conflict", f"Sheet changed concurrently (version {sheet.version})")
    await documents.set_excluded(ctx.session, [sheet], body.excluded, body.reason, _actor(ctx))
    return await _sheet_out(ctx, sheet)


@router.post("/revisions/{revision_id}/exclusions", response_model=list[SheetOut])
async def exclude_pages(revision_id: uuid.UUID, body: PagesExclude, ctx: Ctx):
    """Exclude or include several pages at once, e.g. the reprinted plan sets of a bundle."""
    ctx.require("mapping", Action.WRITE)
    rev = await documents.get_revision(ctx.session, ctx.tenant_id, revision_id)
    await _project_of_document(ctx, rev.document_id)
    sheets = await documents.list_sheets(ctx.session, revision_id)
    wanted = set(body.pages)
    missing = sorted(wanted - {s.page_no for s in sheets})
    if missing:
        raise ProblemError(422, "No such pages", ", ".join(map(str, missing[:20])))
    await documents.set_excluded(
        ctx.session,
        [s for s in sheets if s.page_no in wanted],
        body.excluded,
        body.reason,
        _actor(ctx),
    )
    return await _sheets_out(ctx, sheets)


@router.patch("/sheets/{sheet_id}/calibration", response_model=SheetOut)
async def calibrate_sheet(sheet_id: uuid.UUID, body: SheetCalibrate, ctx: Ctx):
    ctx.require("mapping", Action.WRITE)
    sheet = await documents.get_sheet(ctx.session, ctx.tenant_id, sheet_id)
    project_id = await documents.sheet_project_id(ctx.session, sheet)
    ctx.require_project(project_id)
    if sheet.version != body.version:
        raise ProblemError(409, "Conflict", f"Sheet changed concurrently (version {sheet.version})")
    if not sheet.raster_width or not sheet.raster_height:
        raise ProblemError(409, "Sheet not rasterised yet")
    try:
        cal = geometry.calibration_from_points(
            body.calibration.p1,
            body.calibration.p2,
            body.calibration.distance_m,
            sheet.raster_width,
            sheet.raster_height,
        )
    except ValueError as e:
        raise ProblemError(422, "Invalid calibration", str(e)) from e
    n = await inventory.recalibrate_sheet(ctx.session, sheet, cal)
    sheet.version += 1
    from unitforma.audit.service import write_audit

    await write_audit(
        ctx.session,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.principal.user_id,
        actor_role=ctx.actor_role,
        entity_type="sheet",
        entity_id=sheet.id,
        action="calibrate",
        after={"m_per_px": cal["m_per_px"], "boundaries_recomputed": n},
    )
    await geometry_service.queue_massing(ctx.tenant_id, project_id)  # outlines moved (ADR-0011)
    return await _sheet_out(ctx, sheet)


@router.get("/floors/{floor_id}/sheets", response_model=list[SheetOut])
async def sheets_for_floor(floor_id: uuid.UUID, ctx: Ctx):
    ctx.require("documents", Action.READ)
    from unitforma.tenants.models import Sheet, SheetFloor

    rows = await ctx.session.execute(
        select(Sheet)
        .join(SheetFloor, SheetFloor.sheet_id == Sheet.id)
        .where(
            SheetFloor.floor_id == floor_id,
            SheetFloor.status == "confirmed",
            Sheet.excluded.is_(False),
        )
        .order_by(Sheet.created_at)
    )
    sheets = list(rows.scalars())
    for s in sheets:
        ctx.require_project(await documents.sheet_project_id(ctx.session, s))
    return await _sheets_out(ctx, sheets)
