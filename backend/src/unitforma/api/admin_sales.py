"""Staff API: sales workspace — inventory grid, edits, bulk, plans, promotions, media,
import/export, history and the public preview (plan §6)."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import select

from unitforma.api.schemas import (
    AuditOut,
    AvailabilityHistoryOut,
    BulkResult,
    BulkUpdate,
    ImportApply,
    ImportBatchOut,
    ImportDryRun,
    InventoryRow,
    MediaCreate,
    MediaIntentOut,
    MediaOrder,
    MediaOut,
    MediaUpdate,
    PaymentPlanIn,
    PaymentPlanOut,
    PaymentPlanUpdate,
    PriceHistoryOut,
    PromotionIn,
    PromotionOut,
    PromotionUpdate,
    SalesHistoryOut,
    SalesSettingsIn,
    SalesSettingsOut,
    SalesUpdate,
)
from unitforma.core.errors import ProblemError
from unitforma.identity.authz import Action
from unitforma.identity.deps import TenantContext, tenant_context
from unitforma.projects import service as projects
from unitforma.sales import media as media_service
from unitforma.sales import rules, spreadsheet
from unitforma.sales import service as sales
from unitforma.tenants.models import ImportBatch, PaymentPlan, Promotion

router = APIRouter(prefix="/api/v1/admin/tenants/{tenant_id}", tags=["sales"])
Ctx = Annotated[TenantContext, Depends(tenant_context)]


def _actor(ctx: TenantContext) -> tuple[uuid.UUID, str]:
    return ctx.principal.user_id, ctx.actor_role


async def _project(ctx: TenantContext, project_id: uuid.UUID, action: Action):
    ctx.require("sales", action)
    ctx.require_project(project_id)
    return await projects.get_project(ctx.session, ctx.tenant_id, project_id)


async def _unit_project(ctx: TenantContext, unit_id: uuid.UUID, action: Action):
    ctx.require("sales", action)
    unit = await sales.get_unit_in_project(ctx.session, ctx.tenant_id, unit_id)
    ctx.require_project(unit.project_id)
    return unit, await projects.get_project(ctx.session, ctx.tenant_id, unit.project_id)


# --- inventory grid ---------------------------------------------------------------------------
@router.get("/projects/{project_id}/inventory", response_model=list[InventoryRow])
async def list_inventory(project_id: uuid.UUID, ctx: Ctx, include_removed: bool = False):
    project = await _project(ctx, project_id, Action.READ)
    return await sales.inventory(ctx.session, project, include_removed=include_removed)


@router.get("/units/{unit_id}/sales", response_model=InventoryRow)
async def get_unit_sales(unit_id: uuid.UUID, ctx: Ctx):
    unit, project = await _unit_project(ctx, unit_id, Action.READ)
    return await sales.unit_row(ctx.session, project, unit.id)


@router.patch(
    "/units/{unit_id}/sales",
    response_model=InventoryRow,
    responses={409: {"description": "Version conflict; the body carries `current` (the row)"}},
)
async def update_unit_sales(
    unit_id: uuid.UUID,
    body: SalesUpdate,
    ctx: Ctx,
    if_match: Annotated[str | None, Header()] = None,
):
    """Inline edit. Send the row ``version`` in the body or as ``If-Match``; a stale version
    returns 409 with the current row so the UI can show both and re-apply (plan §6.4)."""
    unit, project = await _unit_project(ctx, unit_id, Action.WRITE)
    version = body.version
    if if_match is not None:
        try:
            version = int(if_match.strip().strip('"').removeprefix("W/").strip('"'))
        except ValueError as e:
            raise ProblemError(400, "If-Match must be the row version") from e
    if version is None:
        raise ProblemError(428, "Precondition required", "Send the row version")
    changes = body.model_dump(
        exclude_unset=True, exclude={"version", "reason", "confirm_zero_price"}
    )
    return await sales.update_unit_sales(
        ctx.session,
        project,
        unit,
        changes,
        version=version,
        actor=_actor(ctx),
        reason=body.reason,
        confirm_zero_price=body.confirm_zero_price,
    )


@router.post(
    "/projects/{project_id}/inventory/bulk",
    response_model=BulkResult,
    responses={409: {"description": "Stale units listed in `stale`"}},
)
async def bulk_update(project_id: uuid.UUID, body: BulkUpdate, ctx: Ctx):
    """Same change on many units; ``preview=true`` returns before/after without writing."""
    project = await _project(ctx, project_id, Action.READ if body.preview else Action.WRITE)
    return await sales.bulk_update(
        ctx.session,
        project,
        [(i.unit_id, i.version) for i in body.items],
        body.changes.model_dump(exclude_unset=True),
        price_adjust_percent=body.price_adjust_percent,
        preview=body.preview,
        actor=_actor(ctx),
        reason=body.reason,
        confirm_zero_price=body.confirm_zero_price,
    )


@router.get("/units/{unit_id}/sales/history", response_model=SalesHistoryOut)
async def unit_sales_history(unit_id: uuid.UUID, ctx: Ctx):
    unit, _ = await _unit_project(ctx, unit_id, Action.READ)
    h = await sales.history(ctx.session, unit.id)
    return SalesHistoryOut(
        prices=[PriceHistoryOut.model_validate(x) for x in h["prices"]],
        availability=[AvailabilityHistoryOut.model_validate(x) for x in h["availability"]],
        audit=[AuditOut.model_validate(x) for x in h["audit"]],
    )


@router.get("/units/{unit_id}/sales/public-preview", response_model=dict)
async def public_preview(unit_id: uuid.UUID, ctx: Ctx):
    """What a buyer would see for this unit once published (allow-listed fields only)."""
    unit, project = await _unit_project(ctx, unit_id, Action.READ)
    row = await sales.unit_row(ctx.session, project, unit.id)
    plan = (
        await ctx.session.get(PaymentPlan, row["payment_plan_id"])
        if row["payment_plan_id"]
        else None
    )
    promos = (
        list(
            (
                await ctx.session.execute(
                    select(Promotion).where(Promotion.id.in_(row["promotion_ids"]))
                )
            ).scalars()
        )
        if row["promotion_ids"]
        else []
    )
    media = await media_service.list_media(ctx.session, unit.id)
    return sales.public_view(row, plan, promos, media)


# --- settings --------------------------------------------------------------------------------
def _settings_out(project) -> SalesSettingsOut:
    s = project.sales_settings or {}
    return SalesSettingsOut(
        price_area_type=rules.resolve_price_area_type(project, None),
        public_fields=rules.effective_public_fields(project, None),
        import_mapping=s.get("import_mapping") or {},
        import_options=s.get("import_options") or {},
        area_definitions=project.area_definitions or [],
        project_version=project.version,
    )


@router.get("/projects/{project_id}/sales-settings", response_model=SalesSettingsOut)
async def get_sales_settings(project_id: uuid.UUID, ctx: Ctx):
    return _settings_out(await _project(ctx, project_id, Action.READ))


@router.put("/projects/{project_id}/sales-settings", response_model=SalesSettingsOut)
async def put_sales_settings(project_id: uuid.UUID, body: SalesSettingsIn, ctx: Ctx):
    project = await _project(ctx, project_id, Action.WRITE)
    await sales.update_settings(
        ctx.session,
        project,
        body.model_dump(exclude={"version"}, exclude_none=True),
        body.version,
        _actor(ctx),
    )
    return _settings_out(project)


# --- payment plans & promotions -----------------------------------------------------------
@router.get("/projects/{project_id}/payment-plans", response_model=list[PaymentPlanOut])
async def list_plans(project_id: uuid.UUID, ctx: Ctx):
    await _project(ctx, project_id, Action.READ)
    rows = await ctx.session.execute(
        select(PaymentPlan)
        .where(PaymentPlan.project_id == project_id)
        .order_by(PaymentPlan.sort_order, PaymentPlan.name)
    )
    return list(rows.scalars())


@router.post("/projects/{project_id}/payment-plans", response_model=PaymentPlanOut, status_code=201)
async def create_plan(project_id: uuid.UUID, body: PaymentPlanIn, ctx: Ctx):
    project = await _project(ctx, project_id, Action.WRITE)
    return await sales.create_plan(ctx.session, project, body.model_dump(mode="json"), _actor(ctx))


@router.patch("/payment-plans/{plan_id}", response_model=PaymentPlanOut)
async def update_plan(plan_id: uuid.UUID, body: PaymentPlanUpdate, ctx: Ctx):
    plan = await ctx.session.get(PaymentPlan, plan_id)
    if plan is None or plan.tenant_id != ctx.tenant_id:
        raise ProblemError(404, "Payment plan not found")
    await _project(ctx, plan.project_id, Action.WRITE)
    data = body.model_dump(mode="json", exclude_unset=True, exclude={"version"})
    return await sales.update_plan(ctx.session, plan, data, body.version, _actor(ctx))


@router.get("/projects/{project_id}/promotions", response_model=list[PromotionOut])
async def list_promotions(project_id: uuid.UUID, ctx: Ctx):
    await _project(ctx, project_id, Action.READ)
    rows = await ctx.session.execute(
        select(Promotion).where(Promotion.project_id == project_id).order_by(Promotion.name)
    )
    return list(rows.scalars())


@router.post("/projects/{project_id}/promotions", response_model=PromotionOut, status_code=201)
async def create_promotion(project_id: uuid.UUID, body: PromotionIn, ctx: Ctx):
    project = await _project(ctx, project_id, Action.WRITE)
    return await sales.create_promotion(ctx.session, project, body.model_dump(), _actor(ctx))


@router.patch("/promotions/{promotion_id}", response_model=PromotionOut)
async def update_promotion(promotion_id: uuid.UUID, body: PromotionUpdate, ctx: Ctx):
    promo = await ctx.session.get(Promotion, promotion_id)
    if promo is None or promo.tenant_id != ctx.tenant_id:
        raise ProblemError(404, "Promotion not found")
    await _project(ctx, promo.project_id, Action.WRITE)
    data = body.model_dump(exclude_unset=True, exclude={"version"})
    return await sales.update_promotion(ctx.session, promo, data, body.version, _actor(ctx))


# --- media ------------------------------------------------------------------------------------
def _media_out(m) -> MediaOut:
    out = MediaOut.model_validate(m)
    out.url = media_service.signed_url(m)
    return out


@router.get("/units/{unit_id}/media", response_model=list[MediaOut])
async def list_media(unit_id: uuid.UUID, ctx: Ctx):
    unit, _ = await _unit_project(ctx, unit_id, Action.READ)
    return [_media_out(m) for m in await media_service.list_media(ctx.session, unit.id)]


@router.post("/units/{unit_id}/media", response_model=MediaIntentOut, status_code=201)
async def create_media(unit_id: uuid.UUID, body: MediaCreate, ctx: Ctx):
    """Reserve a media item and return a presigned PUT URL; then call ``complete``."""
    unit, _ = await _unit_project(ctx, unit_id, Action.WRITE)
    m, url = await media_service.create_intent(ctx.session, unit, body.model_dump(), _actor(ctx))
    return MediaIntentOut(
        media=_media_out(m), upload_url=url, headers={"Content-Type": body.content_type}
    )


async def _media(ctx: TenantContext, media_id: uuid.UUID, action: Action):
    m = await media_service.get_media(ctx.session, ctx.tenant_id, media_id)
    ctx.require("sales", action)
    ctx.require_project(m.project_id)
    return m


@router.post("/media/{media_id}/complete", response_model=MediaOut)
async def complete_media(media_id: uuid.UUID, ctx: Ctx):
    m = await _media(ctx, media_id, Action.WRITE)
    return _media_out(await media_service.complete(ctx.session, m, _actor(ctx)))


@router.patch("/media/{media_id}", response_model=MediaOut)
async def update_media(media_id: uuid.UUID, body: MediaUpdate, ctx: Ctx):
    m = await _media(ctx, media_id, Action.WRITE)
    data = body.model_dump(exclude_unset=True, exclude={"version"})
    return _media_out(await media_service.update(ctx.session, m, data, body.version, _actor(ctx)))


@router.put("/units/{unit_id}/media/order", response_model=list[MediaOut])
async def reorder_media(unit_id: uuid.UUID, body: MediaOrder, ctx: Ctx):
    unit, _ = await _unit_project(ctx, unit_id, Action.WRITE)
    items = await media_service.reorder(ctx.session, unit, body.ids, _actor(ctx))
    return [_media_out(m) for m in items]


@router.delete("/media/{media_id}", status_code=204)
async def delete_media(media_id: uuid.UUID, ctx: Ctx):
    m = await _media(ctx, media_id, Action.WRITE)
    await media_service.delete(ctx.session, m, _actor(ctx))
    return Response(status_code=204)


# --- import / export ------------------------------------------------------------------------
def _batch_out(b: ImportBatch) -> ImportBatchOut:
    out = ImportBatchOut.model_validate(b)
    out.targets = list(spreadsheet.TARGETS)
    return out


@router.post(
    "/projects/{project_id}/imports",
    response_model=ImportBatchOut,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
async def upload_import(
    project_id: uuid.UUID,
    request: Request,
    ctx: Ctx,
    file_name: Annotated[str, Query(min_length=1, max_length=255)],
):
    """Upload a CSV or XLSX file as the raw request body. Returns its columns and a suggested
    mapping (the project's saved mapping first)."""
    project = await _project(ctx, project_id, Action.WRITE)
    data = await request.body()
    return _batch_out(await spreadsheet.upload(ctx.session, project, file_name, data, _actor(ctx)))


@router.get("/projects/{project_id}/imports", response_model=list[ImportBatchOut])
async def list_imports(project_id: uuid.UUID, ctx: Ctx):
    await _project(ctx, project_id, Action.READ)
    rows = await ctx.session.execute(
        select(ImportBatch)
        .where(ImportBatch.project_id == project_id)
        .order_by(ImportBatch.created_at.desc())
        .limit(100)
    )
    out = []
    for b in rows.scalars():
        o = _batch_out(b)
        o.report = {"summary": (b.report or {}).get("summary", {})}  # rows only on detail
        out.append(o)
    return out


async def _batch(ctx: TenantContext, batch_id: uuid.UUID, action: Action):
    b = await spreadsheet.get_batch(ctx.session, ctx.tenant_id, batch_id)
    project = await _project(ctx, b.project_id, action)
    return b, project


@router.get("/imports/{batch_id}", response_model=ImportBatchOut)
async def get_import(batch_id: uuid.UUID, ctx: Ctx):
    b, _ = await _batch(ctx, batch_id, Action.READ)
    return _batch_out(b)


@router.post("/imports/{batch_id}/dry-run", response_model=ImportBatchOut)
async def dry_run_import(batch_id: uuid.UUID, body: ImportDryRun, ctx: Ctx):
    """Validate every row against current data and report the changes; writes nothing to units."""
    b, project = await _batch(ctx, batch_id, Action.WRITE)
    return _batch_out(
        await spreadsheet.dry_run(
            ctx.session, project, b, body.mapping, body.options.model_dump(), _actor(ctx)
        )
    )


@router.post("/imports/{batch_id}/apply", response_model=ImportBatchOut)
async def apply_import(batch_id: uuid.UUID, body: ImportApply, ctx: Ctx):
    """Apply the dry-run changes in one transaction; 409 if the inventory changed since."""
    b, project = await _batch(ctx, batch_id, Action.WRITE)
    return _batch_out(
        await spreadsheet.apply(ctx.session, project, b, body.skip_invalid_rows, _actor(ctx))
    )


@router.post("/imports/{batch_id}/discard", response_model=ImportBatchOut)
async def discard_import(batch_id: uuid.UUID, ctx: Ctx):
    b, _ = await _batch(ctx, batch_id, Action.WRITE)
    if b.status == "applied":
        raise ProblemError(409, "An applied import cannot be discarded")
    b.status = "discarded"
    return _batch_out(b)


@router.get(
    "/projects/{project_id}/inventory/export",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}, "application/octet-stream": {}}}},
)
async def export_inventory(
    project_id: uuid.UUID,
    ctx: Ctx,
    file_format: Annotated[Literal["csv", "xlsx"], Query(alias="format")] = "xlsx",
    columns: Literal["internal", "public"] = "internal",
):
    """The same column set the importer reads, so an export can be edited and re-imported."""
    project = await _project(ctx, project_id, Action.READ)
    data, name, media_type = await spreadsheet.export(ctx.session, project, file_format, columns)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
