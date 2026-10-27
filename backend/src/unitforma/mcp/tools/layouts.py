"""Plan type tools (ADR-0022, ADR-0025 Decision 6, ADR-0028 Decision 6): the layout registry of a
project and the confirmation of a layout the setup solver proposed."""

from __future__ import annotations

import uuid

from unitforma.api.admin_layouts import _one as layout_one
from unitforma.api.admin_layouts import _out as layout_out
from unitforma.api.schemas import LayoutOut
from unitforma.identity.authz import Action
from unitforma.mcp.auth import tenant_ctx
from unitforma.mcp.tools.base import Tool, actor
from unitforma.projects import service as projects
from unitforma.sales import layouts as layout_service


async def list_layouts(project_id: uuid.UUID) -> list[LayoutOut]:
    """The project's plan types by code: name, status (confirmed, or proposed by the setup
    solver and not yet shared), the units linked to each with their availability, and media
    counts."""
    async with tenant_ctx() as ctx:
        ctx.require("sales", Action.READ)
        ctx.require_project(project_id)
        project = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
        return [layout_out(x) for x in await layout_service.overview(ctx.session, project)]


async def confirm_layout(layout_id: uuid.UUID) -> LayoutOut:
    """Confirm a plan type the setup solver proposed: from then on it can own media and renders
    and its code reaches the portal. A layout already confirmed is returned unchanged."""
    async with tenant_ctx(write=True) as ctx:
        ctx.require("sales", Action.WRITE)
        lay = await layout_service.get_layout(ctx.session, ctx.tenant_id, layout_id)
        ctx.require_project(lay.project_id)
        await layout_service.confirm(ctx.session, lay, actor(ctx))
        return await layout_one(ctx, lay)


TOOLS = [
    Tool(list_layouts, "read", "List plan types"),
    Tool(confirm_layout, "write", "Confirm a proposed plan type", idempotent=True),
]
