"""Facades pass (ADR-0025 Decision 5 "facades"): the building's elevation sheets (stacked level
markers) are measured along their floor lines and matched to the two side lengths of the footprint
rectangle; a unique match assigns each drawing to a side, flagged for the person to check which
of the two parallel sides it is. Axis labels in the titles are a later refinement (ADR-0025
Revisit)."""

from __future__ import annotations

import uuid
from statistics import median
from typing import Any

from sqlalchemy import select

from unitforma.autopilot import rules
from unitforma.autopilot.service import Context, session
from unitforma.documents import levels
from unitforma.geometry import service as geometry_service
from unitforma.mapping import service as mapping
from unitforma.projects import service as projects
from unitforma.tenants.models import Building, Project, Sheet

STEP = "facades"
LINE_Y_TOLERANCE = 0.012  # a floor line runs within this of its level marker (sheet-normalised)
FRAME_SPAN = 0.9  # a horizontal line longer than this is the sheet frame, not the building


def drawn_width_m(sheet: Sheet) -> float | None:
    """Median length in metres of the horizontal segments at the level markers' heights."""
    markers = [levels.Marker.from_dict(d) for d in (sheet.hints or {}).get("level_markers") or []]
    if len(markers) < 2:
        return None
    extract = mapping.load_extract(sheet)
    size = mapping.sheet_metres(sheet, extract)
    if not size:
        return None
    ys = sorted({round(m.y, 4) for m in markers})
    lengths = []
    for seg in extract.get("segments") or []:
        try:
            x0, y0, x1, y1 = (float(v) for v in seg[:4])
        except (TypeError, ValueError):
            continue
        if abs(y1 - y0) > 0.002:
            continue
        span = abs(x1 - x0)
        if span < 0.05 or span > FRAME_SPAN:
            continue
        if any(abs(y0 - y) <= LINE_Y_TOLERANCE for y in ys):
            lengths.append(span)
    if len(lengths) < 2:
        return None
    return median(lengths) * size[0]


def assign(
    sides: list[dict[str, Any]], widths: list[tuple[uuid.UUID, int, float]]
) -> list[dict[str, Any]] | None:
    """Sheets to sides by width: the long sides take the drawings matching the long length, the
    short sides the others; None unless the lengths differ and every drawing matches one."""
    if len(sides) != 4 or not widths:
        return None
    long_len = max(s["length_m"] for s in sides)
    short_len = min(s["length_m"] for s in sides)
    if long_len <= 0 or (long_len - short_len) / long_len <= rules.FACADE_WIDTH_TOLERANCE:
        return None
    long_sides = [s["index"] for s in sides if abs(s["length_m"] - long_len) / long_len <= 1e-3]
    short_sides = [s["index"] for s in sides if s["index"] not in long_sides]
    longs, shorts = [], []
    for sheet_id, _page_no, w in sorted(widths, key=lambda t: t[1]):
        if abs(w - long_len) / long_len <= rules.FACADE_WIDTH_TOLERANCE:
            longs.append(sheet_id)
        elif abs(w - short_len) / short_len <= rules.FACADE_WIDTH_TOLERANCE:
            shorts.append(sheet_id)
        else:
            return None
    if len(longs) > len(long_sides) or len(shorts) > len(short_sides):
        return None
    items = [
        {"side": side, "sheet_id": str(sid), "region": None, "flip": False}
        for side, sid in list(zip(long_sides, longs, strict=False))
        + list(zip(short_sides, shorts, strict=False))
    ]
    return items or None


async def run(ctx: Context) -> None:
    async with session(ctx) as db:
        project = (
            await db.execute(select(Project).where(Project.id == ctx.project_id))
        ).scalar_one()
        feet = {f["building_id"]: f for f in await geometry_service.footprints(db, project)}
        for b in await projects.list_buildings(db, ctx.project_id):
            if b.kind != "building" or geometry_service.facade_assignments(project, b):
                continue
            foot = feet.get(b.id)
            if not foot or not foot.get("sides"):
                continue
            cands = await projects.elevation_candidates(db, b)
            if not cands:
                continue
            widths: list[tuple[uuid.UUID, int, float]] = []
            for c in cands:
                sheet = (
                    await db.execute(select(Sheet).where(Sheet.id == c["sheet_id"]))
                ).scalar_one_or_none()
                if sheet is None:
                    continue
                w = drawn_width_m(sheet)
                if w:
                    widths.append((sheet.id, int(c["page_no"]), w))
            items = assign(foot["sides"], widths)
            if not items:
                ctx.decide(
                    STEP,
                    "skipped",
                    f"Building {b.code}: {len(cands)} elevation sheet(s) need you",
                    "Their drawn widths do not single out the building's sides; pick the "
                    "elevation for each side on Site placement",
                    needs_you=True,
                    entity_type="building",
                    entity_id=b.id,
                )
                continue
            fresh = (await db.execute(select(Building).where(Building.id == b.id))).scalar_one()
            await projects.update_building(db, fresh, {"facades": items}, fresh.version, ctx.actor)
            ctx.decide(
                STEP,
                "accepted",
                f"Building {b.code}: {len(items)} facade drawing(s) on the 3D model",
                "Matched by drawn width to the long and short sides; which of the two parallel "
                "sides each one shows is a guess: check it on Site placement",
                confidence=rules.FACADE_CONFIDENCE,
                needs_you=True,
                entity_type="building",
                entity_id=b.id,
            )
