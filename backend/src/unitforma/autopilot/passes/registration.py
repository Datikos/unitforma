"""Floor registration pass (ADR-0030 #D2): every floor sheet of a building is registered to the
building's reference floor (the footprint floor, so the placement does not move) on the
drawing's grid axes. The shift lands on ``sheet_floors.registration``; the massing, the
footprint and the IFC plan outlines apply it when they read outlines in building metres.

A floor sheet that shares too few axes or whose axes disagree keeps its outlines as drawn, with
the reason on the row. A run that changes no shift decides nothing and queues nothing."""

from __future__ import annotations

import uuid
from typing import Any

from shapely.geometry import Polygon
from shapely.ops import unary_union
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.autopilot.service import Context, session
from unitforma.geometry import registration
from unitforma.geometry import service as geometry_service
from unitforma.mapping.service import load_extract
from unitforma.tenants.models import Building, Floor, Sheet, SheetFloor, Unit, UnitBoundary

STEP = "registration"


async def _outline_bounds(
    db: AsyncSession, floor_id: uuid.UUID, sheet_id: uuid.UUID
) -> tuple[tuple[float, float, float, float], int] | None:
    """Bounds in sheet metres of the floor's current outlines on the sheet, and their count."""
    polys = [
        Polygon(bd.polygon_m["ring"])
        for (bd,) in await db.execute(
            select(UnitBoundary)
            .join(Unit, Unit.id == UnitBoundary.unit_id)
            .where(
                Unit.floor_id == floor_id,
                Unit.lifecycle_status != "removed",
                UnitBoundary.sheet_id == sheet_id,
                UnitBoundary.is_current.is_(True),
            )
        )
        if isinstance(bd.polygon_m, dict) and bd.polygon_m.get("ring")
    ]
    if not polys:
        return None
    return unary_union([p.buffer(0) for p in polys]).bounds, len(polys)


def _grid(sheet: Sheet, near: tuple[float, float, float, float]) -> registration.Grid:
    m = float((sheet.calibration or {})["m_per_px"])
    words = load_extract(sheet).get("words") or []
    return registration.grid_axes(
        words, (sheet.raster_width or 0) * m, (sheet.raster_height or 0) * m, near
    )


def _same(old: dict[str, Any] | None, new: dict[str, Any]) -> bool:
    if not isinstance(old, dict):
        return False
    keys = ("method", "dx_m", "dy_m", "ref_sheet_id")
    return all(old.get(k) == new.get(k) for k in keys)


async def run(ctx: Context) -> None:
    changed = False
    async with session(ctx) as db:
        buildings = (
            await db.execute(
                select(Building)
                .where(Building.project_id == ctx.project_id, Building.kind == "building")
                .order_by(Building.sort_order, Building.code)
            )
        ).scalars()
        for b in list(buildings):
            changed |= await _building(ctx, db, b)
    if changed:
        await geometry_service.queue_massing(ctx.tenant_id, ctx.project_id)


async def _building(ctx: Context, db: AsyncSession, b: Building) -> bool:
    floors = list((await db.execute(select(Floor).where(Floor.building_id == b.id))).scalars())
    _union, ref_level = await geometry_service.lowest_floor_union(db, floors)
    if ref_level is None:
        return False
    level_of = {f.id: f.level for f in floors}
    rows = [
        (sf, sheet, near)
        for sf, sheet in await db.execute(
            select(SheetFloor, Sheet)
            .join(Sheet, Sheet.id == SheetFloor.sheet_id)
            .where(
                SheetFloor.floor_id.in_(list(level_of)),
                SheetFloor.status == "confirmed",
                Sheet.excluded.is_(False),
            )
        )
        if (sheet.calibration or {}).get("m_per_px")
        and (near := await _outline_bounds(db, sf.floor_id, sheet.id)) is not None
    ]
    refs = [r for r in rows if level_of[r[0].floor_id] == ref_level]
    if not refs or len(rows) < 2:
        return False
    # the reference floor's sheet holding most of its outlines
    _ref_sf, ref_sheet, (ref_near, _n) = max(refs, key=lambda r: r[2][1])
    ref_grid = _grid(ref_sheet, ref_near)
    moved: list[str] = []
    left: list[str] = []
    changed = False
    for sf, sheet, (near, _n) in sorted(rows, key=lambda r: level_of[r[0].floor_id]):
        level = level_of[sf.floor_id]
        if sheet.id == ref_sheet.id:
            # the same drawing: the same origin
            new: dict[str, Any] = {"method": "same_sheet", "dx_m": 0.0, "dy_m": 0.0}
        else:
            new = registration.register(ref_grid, _grid(sheet, near))
        new = {"v": 1, **new, "ref_sheet_id": str(ref_sheet.id)}
        if new["method"] == "grid_axes":
            moved.append(f"level {level} by {(new['dx_m'] ** 2 + new['dy_m'] ** 2) ** 0.5:.1f} m")
        elif new["method"] == "none":
            left.append(f"level {level} (p.{sheet.page_no}): {new['reason']}")
        if _same(sf.registration, new):
            continue
        sf.registration = new
        changed = True
    if not changed:
        return False
    await db.flush()
    ref_page = f"level {ref_level} (p.{ref_sheet.page_no})"
    if moved:
        ctx.decide(
            STEP,
            "accepted",
            f"Building {b.code}: floors aligned on the grid axes",
            f"Each floor sheet has its own origin; moved onto {ref_page}: " + ", ".join(moved),
            entity_type="building",
            entity_id=b.id,
        )
    if left:
        ctx.decide(
            STEP,
            "skipped",
            f"Building {b.code}: {len(left)} floor sheet(s) left as drawn",
            "; ".join(left) + ". Their outlines may sit off the other floors in 3D.",
            entity_type="building",
            entity_id=b.id,
        )
    return True
