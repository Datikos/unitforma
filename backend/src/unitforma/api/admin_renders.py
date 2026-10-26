"""Generated 3D plan renders of a unit: request, list, approve, reject (ADR-0017 Decision 3).

Writes need the ``sales`` resource like unit media; the generated image is a media item that
stays private until ``approve``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from unitforma.api.schemas import RenderOut, RenderRequest, RendersOut
from unitforma.identity.authz import Action
from unitforma.identity.deps import TenantContext, tenant_context
from unitforma.renders import service as renders
from unitforma.sales import media as media_service
from unitforma.sales import service as sales
from unitforma.tenants.models import Unit, UnitMedia, UnitRender

router = APIRouter(prefix="/api/v1/admin/tenants/{tenant_id}", tags=["renders"])
Ctx = Annotated[TenantContext, Depends(tenant_context)]


def _actor(ctx: TenantContext) -> tuple[uuid.UUID, str]:
    return ctx.principal.user_id, ctx.actor_role


def _out(r: UnitRender, m: UnitMedia | None, partner_code: str | None = None) -> RenderOut:
    out = RenderOut.model_validate(r)
    out.url = media_service.signed_url(m) if m is not None else None
    out.partner_code = partner_code
    return out


async def _unit(ctx: TenantContext, unit_id: uuid.UUID, action: Action):
    ctx.require("sales", action)
    unit = await sales.get_unit_in_project(ctx.session, ctx.tenant_id, unit_id)
    ctx.require_project(unit.project_id)
    return unit


@router.get("/units/{unit_id}/renders", response_model=RendersOut)
async def list_renders(unit_id: uuid.UUID, ctx: Ctx):
    unit = await _unit(ctx, unit_id, Action.READ)
    data = await renders.overview(ctx.session, unit)
    partner_ids = {r.partner_unit_id for r, _ in data["items"] if r.partner_unit_id}
    codes = (
        {
            u.id: u.code
            for u in (
                await ctx.session.execute(select(Unit).where(Unit.id.in_(partner_ids)))
            ).scalars()
        }
        if partner_ids
        else {}
    )
    items = [_out(r, m, codes.get(r.partner_unit_id)) for r, m in data["items"]]
    return RendersOut(**{**data, "items": items})


@router.post("/units/{unit_id}/renders", response_model=RenderOut, status_code=202)
async def request_render(unit_id: uuid.UUID, body: RenderRequest, ctx: Ctx):
    """Queue one render of the unit's current outline; 409 when not configured or no outline,
    429 past the tenant's daily cap."""
    unit = await _unit(ctx, unit_id, Action.WRITE)
    partner = (
        await sales.get_unit_in_project(ctx.session, ctx.tenant_id, body.with_unit_id)
        if body.with_unit_id
        else None
    )
    r = await renders.request_render(ctx.session, unit, body.note, _actor(ctx), partner)
    return _out(r, None, partner.code if partner else None)


async def _render(ctx: TenantContext, render_id: uuid.UUID):
    ctx.require("sales", Action.WRITE)
    r, m = await renders.get_render(ctx.session, ctx.tenant_id, render_id)
    ctx.require_project(r.project_id)
    return r, m


@router.post("/renders/{render_id}/approve", response_model=RenderOut)
async def approve_render(render_id: uuid.UUID, ctx: Ctx):
    """The generated image becomes public media of the unit (and of its layout, ADR-0016)."""
    r, m = await _render(ctx, render_id)
    await renders.approve(ctx.session, r, m, _actor(ctx))
    return _out(r, m)


@router.post("/renders/{render_id}/reject", response_model=RenderOut)
async def reject_render(render_id: uuid.UUID, ctx: Ctx):
    """Deletes the generated image; the request stays as a record."""
    r, m = await _render(ctx, render_id)
    await renders.reject(ctx.session, r, m, _actor(ctx))
    return _out(r, None)
