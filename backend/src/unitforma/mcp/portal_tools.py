"""The public, read-only MCP tools on the portal hosts (ADR-0034 Decisions 4 and 5): what a
buyer's assistant may ask a developer's portal, anonymous, over the published snapshot only.

Every tool reads through ``publishing.portal`` exactly as ``api/portal.py`` does, keyed by the
request host that the dispatcher put in :data:`current_host`; nothing a portal does not already
publish is returned, and nothing is written. No preview links: a preview is for the staff who
hold its token.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from unitforma.core.db import tenant_session
from unitforma.core.errors import ProblemError
from unitforma.publishing import portal

current_host: ContextVar[str] = ContextVar("portal_mcp_host", default="")

Availability = Literal["available", "reserved", "sold", "withdrawn"]
Sort = Literal["code", "price_asc", "price_desc", "area_asc", "area_desc"]


def _host() -> str:
    host = current_host.get()
    if not host:  # only reachable when the dispatcher is bypassed
        raise ToolError("No portal host on this request")
    return host


async def _site() -> portal.Site:
    try:
        return await portal.site_for_host(_host())
    except ProblemError as e:
        raise ToolError(f"{e.title}: {e.detail}" if e.detail else e.title) from None


async def site() -> dict[str, Any]:
    """This portal: the developer's name and branding, whether it is one project or several,
    and the published projects with their slugs. Start here; every other tool takes a project
    slug from this list (omit it on a single-project portal)."""
    return await portal.site_summary(await _site())


async def get_project(slug: str | None = None) -> dict[str, Any]:
    """A published project: description, address, buildings with floors and the units on
    each floor (code, type, availability), site plan, payment plans and promotions, stats.
    Prices are in the project's currency; null means "price on request", never 0."""
    site_ = await _site()
    try:
        async with tenant_session(site_.tenant_id, scope="tenant") as db:
            _project, pub, _ = await portal.resolve_publication(db, site_, slug, None)
            return portal.load_doc(pub)
    except ProblemError as e:
        raise ToolError(f"{e.title}: {e.detail}" if e.detail else e.title) from None


async def list_units(
    slug: str | None = None,
    availability: list[Availability] | None = None,
    unit_type: list[str] | None = None,
    building: list[str] | None = None,
    floor: list[int] | None = None,
    rooms: list[int] | None = None,
    layout: list[str] | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_area: float | None = None,
    max_area: float | None = None,
    sort: Sort = "code",
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """Units of a published project with the portal's filters: availability, unit type
    (apartment, commercial, parking, storage), building code, floor level, rooms (5 = five or
    more), plan type code, price and area ranges in the project's currency and square metres.
    Pages of up to 200. Each unit carries its code, floor, areas, price (null = on request) and
    plan type."""
    site_ = await _site()
    limit = max(1, min(int(limit), 200))
    try:
        async with tenant_session(site_.tenant_id, scope="tenant") as db:
            _project, pub, _ = await portal.resolve_publication(db, site_, slug, None)
            return await portal.list_units(
                db,
                pub,
                {
                    "availability": availability,
                    "unit_type": unit_type,
                    "building": building,
                    "floor": floor,
                    "rooms": rooms,
                    "layout": layout,
                    "min_price": min_price,
                    "max_price": max_price,
                    "min_area": min_area,
                    "max_area": max_area,
                    "sort": sort,
                    "offset": max(0, int(offset)),
                    "limit": limit,
                },
            )
    except ProblemError as e:
        raise ToolError(f"{e.title}: {e.detail}" if e.detail else e.title) from None


async def get_unit(code: str, slug: str | None = None) -> dict[str, Any]:
    """One unit by its code as printed on the portal (case ignored): plan, areas with their
    definitions, price and payment terms, media, plan type, entrance, building and floor."""
    site_ = await _site()
    try:
        async with tenant_session(site_.tenant_id, scope="tenant") as db:
            _project, pub, _ = await portal.resolve_publication(db, site_, slug, None)
            return await portal.get_unit(db, pub, code)
    except ProblemError as e:
        raise ToolError(f"{e.title}: {e.detail}" if e.detail else e.title) from None


async def list_layouts(slug: str | None = None) -> dict[str, Any]:
    """The project's plan types: code, name, rooms, area range, lowest price and how many
    units of each are still available."""
    site_ = await _site()
    try:
        async with tenant_session(site_.tenant_id, scope="tenant") as db:
            _project, pub, _ = await portal.resolve_publication(db, site_, slug, None)
            return await portal.list_layouts(db, pub)
    except ProblemError as e:
        raise ToolError(f"{e.title}: {e.detail}" if e.detail else e.title) from None


PORTAL_TOOLS = [
    (site, "This portal"),
    (get_project, "A published project"),
    (list_units, "Units with filters"),
    (get_unit, "One unit"),
    (list_layouts, "Plan types"),
]


def portal_annotations(title: str) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
