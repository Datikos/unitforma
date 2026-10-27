"""Staff API: the layout registry of a project (ADR-0022): layouts, their media and the renders
generated for them. Writes need the ``sales`` resource like unit media."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select

from unitforma.api.admin_renders import _out as render_out
from unitforma.api.admin_sales import _media_out
from unitforma.api.schemas import (
    LayoutIn,
    LayoutOut,
    LayoutRenderRequest,
    LayoutUnitOut,
    LayoutUpdate,
    MediaCreate,
    MediaIntentOut,
    MediaOrder,
    MediaOut,
    RenderOut,
    RendersOut,
)
from unitforma.core.errors import ProblemError
from unitforma.identity.authz import Action
from unitforma.identity.deps import TenantContext, tenant_context
from unitforma.projects import service as projects
from unitforma.renders import service as renders
from unitforma.sales import layouts as layout_service
from unitforma.sales import media as media_service
from unitforma.tenants.models import Unit, UnitLayout

router = APIRouter(prefix="/api/v1/admin/tenants/{tenant_id}", tags=["layouts"])
Ctx = Annotated[TenantContext, Depends(tenant_context)]


def _actor(ctx: TenantContext) -> tuple[uuid.UUID, str]:
    return ctx.principal.user_id, ctx.actor_role


async def _project(ctx: TenantContext, project_id: uuid.UUID, action: Action):
    ctx.require("sales", action)
    ctx.require_project(project_id)
    return await projects.get_project(ctx.session, ctx.tenant_id, project_id)


async def _layout(ctx: TenantContext, layout_id: uuid.UUID, action: Action) -> UnitLayout:
    ctx.require("sales", action)
    lay = await layout_service.get_layout(ctx.session, ctx.tenant_id, layout_id)
    ctx.require_project(lay.project_id)
    return lay


def _out(item: dict) -> LayoutOut:
    lay: UnitLayout = item["layout"]
    return LayoutOut(
        id=lay.id,
        project_id=lay.project_id,
        code=lay.code,
        name=lay.name,
        status=lay.status,
        source=lay.source,
        match=lay.match,
        version=lay.version,
        created_at=lay.created_at,
        updated_at=lay.updated_at,
        units=[LayoutUnitOut(**u) for u in item["units"]],
        media_count=item["media_count"],
        public_media_count=item["public_media_count"],
        cover_url=item["cover_url"],
    )


async def _one(ctx: TenantContext, lay: UnitLayout) -> LayoutOut:
    project = await projects.get_project(ctx.session, ctx.tenant_id, lay.project_id)
    item = next(
        x for x in await layout_service.overview(ctx.session, project) if x["layout"].id == lay.id
    )
    return _out(item)


@router.get("/projects/{project_id}/layouts", response_model=list[LayoutOut])
async def list_layouts(project_id: uuid.UUID, ctx: Ctx):
    """Every layout with its linked units, media counts and cover, ordered by code."""
    project = await _project(ctx, project_id, Action.READ)
    return [_out(x) for x in await layout_service.overview(ctx.session, project)]


@router.post("/projects/{project_id}/layouts", response_model=LayoutOut, status_code=201)
async def create_layout(project_id: uuid.UUID, body: LayoutIn, ctx: Ctx):
    """409 when the code exists in the project (compared without case)."""
    project = await _project(ctx, project_id, Action.WRITE)
    lay = await layout_service.create(ctx.session, project, body.model_dump(), _actor(ctx))
    return await _one(ctx, lay)


@router.get("/layouts/{layout_id}", response_model=LayoutOut)
async def get_layout(layout_id: uuid.UUID, ctx: Ctx):
    return await _one(ctx, await _layout(ctx, layout_id, Action.READ))


@router.patch("/layouts/{layout_id}", response_model=LayoutOut)
async def update_layout(layout_id: uuid.UUID, body: LayoutUpdate, ctx: Ctx):
    """Rename the code (every linked unit follows) or the name; version-checked."""
    lay = await _layout(ctx, layout_id, Action.WRITE)
    data = body.model_dump(exclude_unset=True, exclude={"version"})
    await layout_service.update(ctx.session, lay, data, body.version, _actor(ctx))
    return await _one(ctx, lay)


@router.delete("/layouts/{layout_id}", status_code=204)
async def delete_layout(
    layout_id: uuid.UUID,
    ctx: Ctx,
    unlink_units: Annotated[
        bool, Query(description="Unlink the units instead of refusing")
    ] = False,
):
    """409 ``layout-in-use`` while units link to it unless ``unlink_units`` is sent; the layout's
    media files are removed at once."""
    lay = await _layout(ctx, layout_id, Action.WRITE)
    await layout_service.delete(ctx.session, lay, unlink_units=unlink_units, actor=_actor(ctx))
    return Response(status_code=204)


@router.post("/layouts/{layout_id}/confirm", response_model=LayoutOut)
async def confirm_layout(layout_id: uuid.UUID, ctx: Ctx):
    """A plan type the setup solver proposed becomes a confirmed layout (ADR-0025 Decision 6):
    from now on it can own media and renders and its code reaches the portal."""
    lay = await _layout(ctx, layout_id, Action.WRITE)
    await layout_service.confirm(ctx.session, lay, _actor(ctx))
    return await _one(ctx, lay)


# --- media of a layout --------------------------------------------------------------------------
@router.get("/layouts/{layout_id}/media", response_model=list[MediaOut])
async def list_layout_media(layout_id: uuid.UUID, ctx: Ctx):
    lay = await _layout(ctx, layout_id, Action.READ)
    return [_media_out(m) for m in await media_service.list_media(ctx.session, layout_id=lay.id)]


@router.post("/layouts/{layout_id}/media", response_model=MediaIntentOut, status_code=201)
async def create_layout_media(layout_id: uuid.UUID, body: MediaCreate, ctx: Ctx):
    """Reserve a media item owned by the layout and return a presigned PUT URL; then call
    ``/media/{id}/complete`` like unit media."""
    lay = await _layout(ctx, layout_id, Action.WRITE)
    m, url = await media_service.create_intent(ctx.session, lay, body.model_dump(), _actor(ctx))
    return MediaIntentOut(
        media=_media_out(m), upload_url=url, headers={"Content-Type": body.content_type}
    )


@router.put("/layouts/{layout_id}/media/order", response_model=list[MediaOut])
async def reorder_layout_media(layout_id: uuid.UUID, body: MediaOrder, ctx: Ctx):
    lay = await _layout(ctx, layout_id, Action.WRITE)
    items = await media_service.reorder(ctx.session, lay, body.ids, _actor(ctx))
    return [_media_out(m) for m in items]


# --- generated renders of a layout --------------------------------------------------------------
async def _source_codes(ctx: TenantContext, items) -> dict[uuid.UUID, str]:
    ids = {r.unit_id for r, _ in items}
    if not ids:
        return {}
    rows = await ctx.session.execute(select(Unit.id, Unit.code).where(Unit.id.in_(ids)))
    return dict(rows.all())


@router.get("/layouts/{layout_id}/renders", response_model=RendersOut)
async def list_layout_renders(layout_id: uuid.UUID, ctx: Ctx):
    lay = await _layout(ctx, layout_id, Action.READ)
    data = await renders.overview(ctx.session, lay.tenant_id, layout_id=lay.id)
    codes = await _source_codes(ctx, data["items"])
    items = [render_out(r, m, None, codes.get(r.unit_id)) for r, m in data["items"]]
    return RendersOut(**{**data, "items": items})


@router.post("/layouts/{layout_id}/renders", response_model=RenderOut, status_code=202)
async def request_layout_render(layout_id: uuid.UUID, body: LayoutRenderRequest, ctx: Ctx):
    """Queue one render owned by the layout, cropped from one member unit: ``unit_id`` or the
    first member by code that has an outline on a processed sheet. 409 when not configured, when
    no member has an outline or when a render is running; 429 past the daily cap."""
    lay = await _layout(ctx, layout_id, Action.WRITE)
    members = await layout_service.members(ctx.session, lay.id)
    source: Unit | None = None
    if body.unit_id is not None:
        source = next((u for u in members if u.id == body.unit_id), None)
        if source is None:
            raise ProblemError(422, "The unit is not linked to this layout")
    else:
        for u in members:
            outline = await renders.current_outline(ctx.session, u.id)
            if outline is not None and outline[1].raster_key:
                source = u
                break
        if source is None:
            raise ProblemError(
                409,
                "No linked unit has an outline on a processed sheet",
                "Link a unit to the layout and outline it in the sheet editor first",
            )
    r = await renders.request_render(ctx.session, source, body.note, _actor(ctx), layout=lay)
    return render_out(r, None, None, source.code)
