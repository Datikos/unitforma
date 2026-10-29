"""The site plan's own outline of a placed building (ADR-0035 Decision 1).

A footprint made of unit outlines misses what no unit covers (a stair core, a corridor), so an
L-shaped block unions into two parts and its convex hull covers the courtyard. The architect's
site plan draws the envelope as a closed face. Once a building is placed on a calibrated site
plan, the smallest face that holds most of the placed units, and is not much larger than the
footprint, is that envelope. Finding the faces costs about a second per sheet (0.86 s on N4), so
the massing job does it and stores the result on the building with the sheet, scale and
transform it was found for; readers ignore it once any of the three changed.
"""

from __future__ import annotations

import uuid
from typing import Any

import numpy as np
import shapely
import structlog
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.geometry import massing
from unitforma.inventory import geometry
from unitforma.mapping import service as mapping
from unitforma.mapping import suggest
from unitforma.tenants.models import Building, Floor, Project, Sheet

log = structlog.get_logger()

OUTLINE_MIN_COVER = 0.8  # share of the placed units the face holds (balconies stay outside)
OUTLINE_MAX_GROWTH = 1.25  # the face may be at most this many times the footprint's area


def site_faces(sheet: Sheet) -> list[Polygon]:
    """Closed faces of the site sheet in site metres (the calibration's frame)."""
    extract = mapping.load_extract(sheet)
    cal = sheet.calibration or {}
    if not extract or not cal.get("m_per_px"):
        return []
    cands = suggest.closed_loops(
        extract, page_m=mapping.sheet_metres(sheet, extract), min_area=0.0002, max_area=0.6
    )
    out = []
    for c in cands:
        try:
            p = Polygon(geometry.ring_to_metres(c.ring, cal)).buffer(0)
        except (ValueError, TypeError, KeyError):
            continue
        if not p.is_empty and p.geom_type == "Polygon":
            out.append(p)
    return out


def placed(geom: BaseGeometry, site_transform: dict[str, Any] | None) -> BaseGeometry:
    """Building-local metres → site metres by the building's ``site_transform``."""
    place = massing.Placement.from_dict(site_transform)
    return shapely.transform(
        geom, lambda xy: np.array([place.apply((float(x), float(y))) for x, y in xy])
    )


def drawn_outline(
    units: BaseGeometry, footprint: Polygon, faces: list[Polygon]
) -> tuple[Polygon, float] | None:
    """The smallest face holding ``OUTLINE_MIN_COVER`` of the placed units and no larger than
    ``OUTLINE_MAX_GROWTH`` times the placed footprint, with the share it holds."""
    if units.is_empty or units.area <= 0:
        return None
    best: tuple[Polygon, float] | None = None
    for face in faces:
        if face.area < units.area * OUTLINE_MIN_COVER:
            continue
        if face.area > footprint.area * OUTLINE_MAX_GROWTH:
            continue
        cover = face.intersection(units).area / units.area
        if cover < OUTLINE_MIN_COVER:
            continue
        if best is None or face.area < best[0].area:
            best = (face, cover)
    return best


def _transform_key(site_transform: dict[str, Any] | None) -> dict[str, float]:
    p = massing.Placement.from_dict(site_transform)
    return {
        "tx": round(p.tx, 3),
        "ty": round(p.ty, 3),
        "rotation_deg": round(p.rotation_deg, 2),
        "scale": round(p.scale, 4),
    }


async def site_sheet(db: AsyncSession, project: Project) -> Sheet | None:
    """The project's calibrated site plan sheet, if any."""
    sid = (project.site_frame or {}).get("sheet_id")
    if not sid:
        return None
    try:
        sheet = (
            await db.execute(select(Sheet).where(Sheet.id == uuid.UUID(str(sid))))
        ).scalar_one_or_none()
    except ValueError:
        return None
    if sheet is None or not (sheet.calibration or {}).get("m_per_px"):
        return None
    return sheet


def current_ring(b: Building, sheet: Sheet | None) -> list[list[float]] | None:
    """The stored outline in site metres while its sheet, scale and transform are the current
    ones and the building is placed; ``None`` otherwise (the reader falls back to the hull)."""
    o = b.site_outline
    if not isinstance(o, dict) or o.get("v") != 1 or sheet is None:
        return None
    if b.placement_status == "unplaced" or o.get("sheet_id") != str(sheet.id):
        return None
    m = (sheet.calibration or {}).get("m_per_px")
    if not m or abs(float(o.get("m_per_px") or 0) - float(m)) > 1e-12:
        return None
    if o.get("transform") != _transform_key(b.site_transform):
        return None
    ring = o.get("ring")
    return ring if isinstance(ring, list) and len(ring) >= 3 else None


async def refresh(db: AsyncSession, project: Project) -> dict[str, int]:
    """Find and store the drawn outline of every placed building (the massing job calls this).
    A building without a match gets ``null``, so a stale outline never survives a rebuild."""
    from unitforma.geometry import service  # service imports this module

    sheet = await site_sheet(db, project)
    buildings = list(
        (
            await db.execute(
                select(Building).where(
                    Building.project_id == project.id, Building.kind == "building"
                )
            )
        ).scalars()
    )
    out = {"found": 0, "none": 0}
    faces: list[Polygon] | None = None
    for b in buildings:
        found = None
        if sheet is not None and b.placement_status != "unplaced":
            floors = list(
                (await db.execute(select(Floor).where(Floor.building_id == b.id))).scalars()
            )
            units, _level = await service.lowest_floor_union(db, floors)
            if units is not None:
                if faces is None:
                    faces = site_faces(sheet)
                units_site = placed(units, b.site_transform)
                found = drawn_outline(units_site, units_site.convex_hull, faces)
        if found is None:
            if b.site_outline is not None:
                b.site_outline = None
            out["none"] += 1
            continue
        face, cover = found
        b.site_outline = {
            "v": 1,
            "sheet_id": str(sheet.id),
            "m_per_px": float(sheet.calibration["m_per_px"]),
            "transform": _transform_key(b.site_transform),
            "ring": [[round(x, 3), round(y, 3)] for x, y in face.exterior.coords[:-1]],
            "area_m2": round(face.area, 1),
            "cover": round(cover, 3),
        }
        out["found"] += 1
    return out
