"""Unit tools (ADR-0028 Decision 6): find by the codes a person types, list a page, read one.

They return the inventory row of the admin grid (``InventoryRow``): code, building, floor,
layout, lifecycle, availability, price and areas in one shape. The row needs the ``sales`` read
right, which every role holds.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from unitforma.api.schemas import Availability, InventoryRow
from unitforma.identity.authz import Action
from unitforma.identity.deps import TenantContext
from unitforma.inventory.codes import match_key
from unitforma.mcp.auth import tenant_ctx
from unitforma.mcp.tools.base import Tool
from unitforma.projects import service as projects
from unitforma.sales import service as sales

FIND_LIMIT = 50


class UnitPage(BaseModel):
    total: int = Field(description="Units matching the filters, across all pages")
    offset: int
    limit: int
    items: list[InventoryRow]


class UnitMatches(BaseModel):
    items: list[InventoryRow]
    not_found: list[str] = Field(
        default_factory=list, description="Requested codes that match no unit of the project"
    )


async def _rows(ctx: TenantContext, project_id: uuid.UUID) -> list[InventoryRow]:
    ctx.require("sales", Action.READ)
    ctx.require_project(project_id)
    project = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    return [InventoryRow.model_validate(r) for r in await sales.inventory(ctx.session, project)]


async def find_units(
    project_id: uuid.UUID, codes: list[str] | None = None, query: str | None = None
) -> UnitMatches:
    """Find units by the codes a person types: "A 21", "a-21" and "A21" all match unit A21 or
    A-21 (letters and digits compared, case ignored). Send `codes` for exact units (the answer
    lists the codes that matched nothing in `not_found`), or `query` for a part of a code or a
    layout code or name ("A-0", "2-bedroom"); at most 50 matches. Removed units are left out.
    Each row has the building, floor, layout, availability, price (null = unknown or on
    request) and areas in square metres."""
    if not codes and not (query or "").strip():
        raise ToolError("Send `codes` (a list of unit codes) or `query` (part of a code)")
    async with tenant_ctx() as ctx:
        rows = await _rows(ctx, project_id)
    if codes:
        wanted = {match_key(c): c for c in codes if match_key(c)}
        found = [r for r in rows if match_key(r.code) in wanted]
        hit = {match_key(r.code) for r in found}
        return UnitMatches(items=found, not_found=[c for k, c in wanted.items() if k not in hit])
    q = (query or "").strip()
    key, text = match_key(q), q.casefold()

    def hits(r: InventoryRow) -> bool:
        return bool(key and key in match_key(r.code)) or any(
            text in (v or "").casefold() for v in (r.layout, r.layout_name)
        )

    return UnitMatches(items=[r for r in rows if hits(r)][:FIND_LIMIT])


async def list_units(
    project_id: uuid.UUID,
    building_id: uuid.UUID | None = None,
    floor_id: uuid.UUID | None = None,
    availability: Availability | None = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> UnitPage:
    """Units of a project ordered by building, floor and code, one page at a time (`limit` 1 to
    200, default 50; `total` says how many match). Filter by building, floor or availability
    (available, reserved, sold, withdrawn). Removed units are left out."""
    async with tenant_ctx() as ctx:
        rows = await _rows(ctx, project_id)
    rows = [
        r
        for r in rows
        if (building_id is None or r.building_id == building_id)
        and (floor_id is None or r.floor_id == floor_id)
        and (availability is None or r.availability == availability)
    ]
    return UnitPage(
        total=len(rows), offset=offset, limit=limit, items=rows[offset : offset + limit]
    )


async def get_unit(unit_id: uuid.UUID) -> InventoryRow:
    """One unit with its building, floor, layout, lifecycle, availability, price, payment plan,
    promotions, areas (square metres) and the row `version` a sales change needs."""
    async with tenant_ctx() as ctx:
        ctx.require("sales", Action.READ)
        unit = await sales.get_unit_in_project(ctx.session, ctx.tenant_id, unit_id)
        ctx.require_project(unit.project_id)
        project = await projects.get_project(ctx.session, ctx.tenant_id, unit.project_id)
        return InventoryRow.model_validate(await sales.unit_row(ctx.session, project, unit.id))


TOOLS = [
    Tool(find_units, "read", "Find units by code"),
    Tool(list_units, "read", "List units"),
    Tool(get_unit, "read", "Get a unit"),
]
