"""Generated 3D plan render tools (ADR-0017 Decision 3, ADR-0028 Decision 6): request one, follow
it, list a unit's. There is no approve tool: the review of a generated image is a person's click
in the admin app."""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import Field
from sqlalchemy import select

from unitforma.api.admin_renders import _out as render_out
from unitforma.api.admin_renders import unit_renders
from unitforma.api.schemas import RenderOut, RendersOut
from unitforma.identity.authz import Action
from unitforma.mcp.auth import tenant_ctx
from unitforma.mcp.tools.base import Tool, actor
from unitforma.renders import service as renders
from unitforma.sales import service as sales
from unitforma.tenants.models import Unit


async def request_render(
    unit_id: uuid.UUID,
    with_unit_id: uuid.UUID | None = None,
    note: Annotated[str | None, Field(max_length=500)] = None,
) -> RenderOut:
    """Queue one generated 3D cutaway of the unit's plan (an external image model draws it from
    the unit's outline on its processed sheet). `with_unit_id`: a neighbouring unit on the same
    floor and sheet to show joined into one apartment. `note`: extra instructions such as floor
    material or style, at most 500 characters. Refused when renders are not configured, the
    unit has no outline, a render already runs for it, or the workspace's daily limit is used.
    The answer has status "queued"; follow it with get_render. The image stays private until a
    person approves it in the admin app."""
    async with tenant_ctx(write=True) as ctx:
        ctx.require("sales", Action.WRITE)
        unit = await sales.get_unit_in_project(ctx.session, ctx.tenant_id, unit_id)
        ctx.require_project(unit.project_id)
        partner = (
            await sales.get_unit_in_project(ctx.session, ctx.tenant_id, with_unit_id)
            if with_unit_id
            else None
        )
        r = await renders.request_render(ctx.session, unit, note, actor(ctx), partner)
        return render_out(r, None, partner.code if partner else None)


async def get_render(render_id: uuid.UUID) -> RenderOut:
    """One render: status (queued, running, review, approved, rejected, failed), the error when
    it failed, its cost in USD, and while the image exists a short-lived signed `url` a person
    can open."""
    async with tenant_ctx() as ctx:
        ctx.require("sales", Action.READ)
        r, m = await renders.get_render(ctx.session, ctx.tenant_id, render_id)
        ctx.require_project(r.project_id)
        partner = (
            (
                await ctx.session.execute(select(Unit.code).where(Unit.id == r.partner_unit_id))
            ).scalar_one_or_none()
            if r.partner_unit_id
            else None
        )
        return render_out(r, m, partner)


async def list_renders(unit_id: uuid.UUID) -> RendersOut:
    """The unit's renders, newest first, with whether renders are configured, the model, the
    workspace's daily limit and today's use."""
    async with tenant_ctx() as ctx:
        ctx.require("sales", Action.READ)
        unit = await sales.get_unit_in_project(ctx.session, ctx.tenant_id, unit_id)
        ctx.require_project(unit.project_id)
        return await unit_renders(ctx, unit)


TOOLS = [
    Tool(request_render, "write", "Request a generated plan render", open_world=True),
    Tool(get_render, "read", "Get a render"),
    Tool(list_renders, "read", "List a unit's renders"),
]
