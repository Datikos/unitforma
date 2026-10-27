"""Spaces for a zoneless IFC from the approved plan outlines (ADR-0030 Decisions 3 to 5).

Pure: the service loads floors and outlines, this module decides the fit and builds the solids.
A plan space is the unit's outline mapped from the sheet frame to the IFC frame
(:func:`plan_fit.sheet_to_ifc`, then the rotation and translation that lay the fit floor's
outlines over its storey's slab footprint), extruded between the storey's elevation and the next
storey's. Its GlobalId is the unit id compressed the IFC way, so the viewer contract, the relink
and the published copy do not change.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from shapely.ops import unary_union

from unitforma.geometry import ifc, ifc_match, plan_fit

DEFAULT_HEIGHT_M = 3.0


@dataclass(frozen=True)
class PlanFloor:
    id: Any
    level: int
    elevation_m: float | None  # as the project says, for the storey match
    base_m: float  # stacked elevation (geometry_service.floor_elevations)
    height_m: float


@dataclass(frozen=True)
class Outline:
    unit_id: Any
    code: str
    floor_id: Any
    ring_m: list[Any]  # sheet frame metres (x right, y down)


def guid_for(unit_id: Any) -> str:
    """A valid 22-character IFC GlobalId derived from the unit id (reversible with guid.expand)."""
    import ifcopenshell.guid

    return ifcopenshell.guid.compress(uuid.UUID(str(unit_id)).hex)


def build(
    parsed: ifc.ParsedIfc, floors: list[PlanFloor], outlines: list[Outline]
) -> tuple[list[tuple[ifc.Space, list[float], list[int]]], dict[str, Any]]:
    """Plan spaces with their geometry, and ``plan_fit`` for the model stats (a ``reason`` key
    and no spaces when the outlines cannot be placed)."""
    if not outlines:
        return [], {"reason": "no calibrated unit outline in this building"}
    floors_by_id = {f.id: f for f in floors}
    by_floor: dict[Any, list[Outline]] = {}
    for o in outlines:
        if o.floor_id in floors_by_id and len(o.ring_m) >= 3:
            by_floor.setdefault(o.floor_id, []).append(o)
    if not by_floor:
        return [], {"reason": "the unit outlines belong to no floor of this building"}
    storeys = parsed.storeys
    floor_of_storey = ifc_match.match_floors(
        [(s.index, s.elevation_m) for s in storeys],
        [ifc_match.FloorRef(f.id, f.level, f.elevation_m) for f in floors],
    )
    storey_of_floor = {fid: idx for idx, fid in floor_of_storey.items() if fid is not None}

    fit_floor = min((floors_by_id[fid] for fid in by_floor), key=lambda f: f.level)
    st_idx = storey_of_floor.get(fit_floor.id)
    face_ring = None
    face_from = "bounds"
    if st_idx is not None:
        face_ring = ifc.storey_footprint(parsed, storeys[st_idx].global_id)
        face_from = "slabs"
    if face_ring is None:
        face_ring = parsed.bounds_ring()
        face_from = "bounds"
    foot = unary_union(
        [plan_fit.polygon(plan_fit.sheet_to_ifc(o.ring_m)) for o in by_floor[fit_floor.id]]
    ).buffer(0)
    face = plan_fit.polygon(face_ring)
    if foot.is_empty or face.is_empty or face.area <= 0:
        return [], {"reason": "the fit floor has no usable outline or the IFC storey no slab"}
    fit = plan_fit.best_rotation(foot, face)
    info: dict[str, Any] = {
        "rotation_deg": round(fit["rotation_deg"], 1),
        "tx": round(fit["tx"], 3),
        "ty": round(fit["ty"], 3),
        "iou": round(fit["iou"], 3),
        "floor_level": fit_floor.level,
        "storey": storeys[st_idx].name if st_idx is not None else None,
        "face": face_from,
        "min_iou": plan_fit.IFC_PLAN_FIT_MIN_IOU,
    }
    if fit["iou"] < plan_fit.IFC_PLAN_FIT_MIN_IOU:
        info["reason"] = (
            f"the plan outlines of floor {fit_floor.level} overlap the IFC storey by "
            f"{fit['iou']:.0%}, below {plan_fit.IFC_PLAN_FIT_MIN_IOU:.0%}"
        )
        return [], info

    out: list[tuple[ifc.Space, list[float], list[int]]] = []
    for fid, items in by_floor.items():
        f = floors_by_id[fid]
        idx = storey_of_floor.get(fid)
        storey = storeys[idx] if idx is not None else None
        if storey is not None and storey.elevation_m is not None:
            base = storey.elevation_m
            nxt = storeys[idx + 1].elevation_m if idx + 1 < len(storeys) else None
            height = (nxt - base) if nxt is not None and nxt > base else f.height_m
        else:
            base, height = f.base_m, f.height_m
        height = height if height and height > 0 else DEFAULT_HEIGHT_M
        for o in items:
            ring = plan_fit.apply(
                plan_fit.sheet_to_ifc(o.ring_m), fit["rotation_deg"], fit["tx"], fit["ty"]
            )
            verts, faces = ifc.prism(ring, base, base + height)
            out.append(
                (
                    ifc.Space(
                        global_id=guid_for(o.unit_id),
                        name=o.code,
                        long_name=None,
                        storey=storey,
                        footprint_m=[[round(x, 3), round(y, 3)] for x, y in ring],
                        areas={},
                        triangles=len(faces) // 3,
                        source="plan",
                        floor_level=f.level,
                        unit_id=o.unit_id,
                        floor_id=f.id,
                    ),
                    verts,
                    faces,
                )
            )
    return out, info
