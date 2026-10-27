"""Spaces for a zoneless IFC from the approved plan outlines (ADR-0030 Decisions 3 to 5).

Pure: the service loads floors and outlines, this module decides the fit and builds the solids.
A plan space is the unit's outline mapped from the sheet frame to the IFC frame
(:func:`plan_fit.sheet_to_ifc`, then one rotation and translation for the whole building),
extruded between the storey's elevation and the next storey's. Its GlobalId is the unit id
compressed the IFC way, so the viewer contract, the relink and the published copy do not change.

Amended 2026-10-27 after the first real file (an Archicad export of a three-block complex, blocks
B, C and D separate buildings in the platform, composite slabs exploded into parts):

* the target of a storey is the union of its slab footprints, or their convex hull when the union
  is under half of the hull (exploded slabs leave only balconies and landings as ``IfcSlab``);
* the fit is tried in two scopes: the filed building's outlines alone, and the outlines of every
  building of the project on the same floor levels (blocks mapped on one sheet share the frame);
  the scope with the higher mean IoU wins, and spaces are built for the filed building only;
* one transform is scored jointly over every level that has outlines and a storey
  (:func:`plan_fit.joint_fit`), which breaks the 180° ambiguity of a long rectangular block.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from shapely.geometry import MultiPoint
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from unitforma.geometry import ifc, ifc_match, plan_fit

DEFAULT_HEIGHT_M = 3.0
HULL_WHEN_UNION_BELOW = 0.5  # share of the hull area under which the slab union is not trusted
# a storey for the XY target only, when no storey is within ifc_match's 0.3 m of the floor: the
# blocks of a split-level site sit at other elevations than the complex's storeys (C at +1.0 m,
# D at +2.0 m on 2026-10-27) while the footprints barely differ between storeys
LOOSE_STOREY_M = 1.6
MIN_COVERAGE = 0.85  # with mean IoU >= MIN_IOU_WITH_COVERAGE: outlines inside a real slab target
MIN_IOU_WITH_COVERAGE = 0.20


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
    building_id: Any = None
    level: int | None = None  # the floor's level, for outlines of the other buildings


def guid_for(unit_id: Any) -> str:
    """A valid 22-character IFC GlobalId derived from the unit id (reversible with guid.expand)."""
    import ifcopenshell.guid

    return ifcopenshell.guid.compress(uuid.UUID(str(unit_id)).hex)


def storey_target(parsed: ifc.ParsedIfc, storey_gid: str) -> tuple[BaseGeometry, str] | None:
    """The storey's footprint to fit against: slab union, or their hull when the union is small
    (exploded composites); ``None`` when the storey has no slab."""
    rings = parsed.storey_slabs.get(storey_gid) or []
    polys = [plan_fit.polygon([(float(x), float(y)) for x, y in r]) for r in rings if len(r) >= 3]
    polys = [p for p in polys if not p.is_empty]
    if not polys:
        return None
    union = unary_union(polys).buffer(0)
    hull = MultiPoint([pt for p in polys for pt in p.exterior.coords]).convex_hull
    if hull.is_empty or hull.area <= 0:
        return None
    if union.area >= HULL_WHEN_UNION_BELOW * hull.area:
        return union, "slabs"
    return hull, "hull"


def _foot(items: list[Outline]) -> BaseGeometry:
    return unary_union([plan_fit.polygon(plan_fit.sheet_to_ifc(o.ring_m)) for o in items]).buffer(0)


def build(
    parsed: ifc.ParsedIfc,
    floors: list[PlanFloor],
    outlines: list[Outline],
    *,
    building_id: Any = None,
) -> tuple[list[tuple[ifc.Space, list[float], list[int]]], dict[str, Any]]:
    """Plan spaces with their geometry for the filed building, and ``plan_fit`` for the model
    stats (a ``reason`` key and no spaces when the outlines cannot be placed).

    ``outlines`` may hold every building of the project (``building_id`` and ``level`` set);
    only those of ``building_id`` (or all, when it is ``None``) become spaces."""
    mine = [o for o in outlines if building_id is None or o.building_id == building_id]
    if not mine:
        return [], {"reason": "no calibrated unit outline in this building"}
    floors_by_id = {f.id: f for f in floors}
    by_floor: dict[Any, list[Outline]] = {}
    for o in mine:
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

    # the target per level: the filed building's floor at that level → its storey → slabs;
    # for the XY target a storey within LOOSE_STOREY_M also serves (heights for the spaces still
    # come from the strict match or the floor)
    level_floor = {floors_by_id[fid].level: floors_by_id[fid] for fid in by_floor}
    targets = {
        st.global_id: t for st in storeys if (t := storey_target(parsed, st.global_id)) is not None
    }
    faces: dict[int, BaseGeometry] = {}
    face_kind: dict[int, str] = {}
    target_storey: dict[int, ifc.Storey] = {}
    for level, f in level_floor.items():
        idx = storey_of_floor.get(f.id)
        st = storeys[idx] if idx is not None else None
        if st is None or st.global_id not in targets:
            ref = f.elevation_m if f.elevation_m is not None else f.base_m
            near = [
                (abs(x.elevation_m - ref), x)
                for x in storeys
                if x.elevation_m is not None and x.global_id in targets
            ]
            near = [n for n in near if n[0] <= LOOSE_STOREY_M]
            st = min(near, key=lambda n: n[0])[1] if near else None
        if st is not None and st.global_id in targets:
            faces[level], face_kind[level] = targets[st.global_id]
            target_storey[level] = st
    fit_level = min(faces) if faces else min(level_floor)
    if not faces:
        # no storey matched or no slab anywhere: the whole model's bounds, lowest floor only
        faces[fit_level] = plan_fit.polygon(parsed.bounds_ring())
        face_kind[fit_level] = "bounds"

    scopes: dict[str, dict[int, BaseGeometry]] = {
        "building": {lvl: _foot(by_floor[f.id]) for lvl, f in level_floor.items() if lvl in faces}
    }
    others = [
        o
        for o in outlines
        if building_id is not None
        and o.building_id != building_id
        and o.level in faces
        and len(o.ring_m) >= 3
    ]
    if others:
        project: dict[int, BaseGeometry] = {}
        for lvl in faces:
            items = list(by_floor.get(level_floor[lvl].id, [])) + [
                o for o in others if o.level == lvl
            ]
            if items:
                project[lvl] = _foot(items)
        scopes["project"] = project
    best_scope, best_fit = None, None
    for scope, feet in scopes.items():
        feet = {k: v for k, v in feet.items() if not v.is_empty}
        if fit_level not in feet:
            continue
        fit = plan_fit.joint_fit(feet, faces, fit_level)
        if best_fit is None or fit["mean_iou"] > best_fit["mean_iou"]:
            best_scope, best_fit = scope, fit
    if best_fit is None:
        return [], {"reason": "the fit floor has no usable outline or the IFC storey no slab"}
    info: dict[str, Any] = {
        "scope": best_scope,
        "rotation_deg": round(best_fit["rotation_deg"], 1),
        "tx": round(best_fit["tx"], 3),
        "ty": round(best_fit["ty"], 3),
        "iou": round(best_fit["mean_iou"], 3),
        "min_coverage": round(best_fit["min_coverage"], 3),
        "per_level": best_fit["per_level"],
        "floor_level": fit_level,
        "storey": target_storey[fit_level].name if fit_level in target_storey else None,
        "face": face_kind.get(fit_level),
        "min_iou": plan_fit.IFC_PLAN_FIT_MIN_IOU,
    }
    # a real slab target with the outlines inside it may pass on coverage; the model's bounds
    # may not, since anything inside the box covers fully
    real_target = face_kind.get(fit_level) in ("slabs", "hull")
    accepted = best_fit["mean_iou"] >= plan_fit.IFC_PLAN_FIT_MIN_IOU or (
        real_target
        and best_fit["min_coverage"] >= MIN_COVERAGE
        and best_fit["mean_iou"] >= MIN_IOU_WITH_COVERAGE
    )
    if not accepted:
        info["reason"] = (
            f"the plan outlines overlap the IFC storeys by {best_fit['mean_iou']:.0%} on average "
            f"(the worst level lies {best_fit['min_coverage']:.0%} inside), below "
            f"{plan_fit.IFC_PLAN_FIT_MIN_IOU:.0%}"
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
                plan_fit.sheet_to_ifc(o.ring_m),
                best_fit["rotation_deg"],
                best_fit["tx"],
                best_fit["ty"],
            )
            verts, faces_ = ifc.prism(ring, base, base + height)
            out.append(
                (
                    ifc.Space(
                        global_id=guid_for(o.unit_id),
                        name=o.code,
                        long_name=None,
                        storey=storey,
                        footprint_m=[[round(x, 3), round(y, 3)] for x, y in ring],
                        areas={},
                        triangles=len(faces_) // 3,
                        source="plan",
                        floor_level=f.level,
                        unit_id=o.unit_id,
                        floor_id=f.id,
                    ),
                    verts,
                    faces_,
                )
            )
    return out, info
