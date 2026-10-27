"""Generated 3D plan renders of a unit: request, list, approve, reject (ADR-0017 Decision 3).

Writes need the ``sales`` resource like unit media; the generated image is a media item that
stays private until ``approve``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from unitforma.api.schemas import (
    RenderOut,
    RenderPromptOut,
    RenderPromptUpdate,
    RenderRequest,
    RendersOut,
)
from unitforma.identity.authz import Action
from unitforma.identity.deps import TenantContext, tenant_context
from unitforma.renders import service as renders
from unitforma.sales import media as media_service
from unitforma.sales import service as sales
from unitforma.tenants.models import Tenant, Unit, UnitMedia, UnitRender

router = APIRouter(prefix="/api/v1/admin/tenants/{tenant_id}", tags=["renders"])
Ctx = Annotated[TenantContext, Depends(tenant_context)]


def _actor(ctx: TenantContext) -> tuple[uuid.UUID, str]:
    return ctx.principal.user_id, ctx.actor_role


def _out(
    r: UnitRender,
    m: UnitMedia | None,
    partner_code: str | None = None,
    source_code: str | None = None,
) -> RenderOut:
    out = RenderOut.model_validate(r)
    out.url = media_service.signed_url(m) if m is not None else None
    out.partner_code = partner_code
    out.source_code = source_code
    return out


async def _unit(ctx: TenantContext, unit_id: uuid.UUID, action: Action):
    ctx.require("sales", action)
    unit = await sales.get_unit_in_project(ctx.session, ctx.tenant_id, unit_id)
    ctx.require_project(unit.project_id)
    return unit


async def unit_renders(ctx: TenantContext, unit: Unit) -> RendersOut:
    """The renders of a unit with the feature's settings and today's use; shared with the MCP
    ``list_renders`` tool (ADR-0028 #C2). The caller has checked ``sales`` read on the unit."""
    data = await renders.overview(ctx.session, unit.tenant_id, unit_id=unit.id)
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


@router.get("/units/{unit_id}/renders", response_model=RendersOut)
async def list_renders(unit_id: uuid.UUID, ctx: Ctx):
    return await unit_renders(ctx, await _unit(ctx, unit_id, Action.READ))


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
    """The generated image becomes public media of its owner: the unit, or the layout when the
    render was requested for one (ADR-0022)."""
    r, m = await _render(ctx, render_id)
    await renders.approve(ctx.session, r, m, _actor(ctx))
    return _out(r, m)


@router.post("/renders/{render_id}/reject", response_model=RenderOut)
async def reject_render(render_id: uuid.UUID, ctx: Ctx):
    """Deletes the generated image; the request stays as a record."""
    r, m = await _render(ctx, render_id)
    await renders.reject(ctx.session, r, m, _actor(ctx))
    return _out(r, None)


# --- workspace render prompt (ADR-0023 Decision 2) ----------------------------------------------
async def _tenant(ctx: TenantContext) -> Tenant:
    return (
        await ctx.session.execute(select(Tenant).where(Tenant.id == ctx.tenant_id))
    ).scalar_one()


def _prompt_out(tenant: Tenant) -> RenderPromptOut:
    own = renders.workspace_prompt(tenant)
    return RenderPromptOut(
        default=renders.PROMPT, prompt=own, source="workspace" if own else "default"
    )


@router.get("/render-prompt", response_model=RenderPromptOut)
async def get_render_prompt(ctx: Ctx):
    ctx.require("tenant.settings", Action.READ)
    return _prompt_out(await _tenant(ctx))


@router.put("/render-prompt", response_model=RenderPromptOut)
async def set_render_prompt(body: RenderPromptUpdate, ctx: Ctx):
    ctx.require("tenant.settings", Action.WRITE)
    tenant = await _tenant(ctx)
    await renders.set_workspace_prompt(
        ctx.session, tenant, body.prompt, _actor(ctx), ctx.request_id
    )
    return _prompt_out(tenant)
