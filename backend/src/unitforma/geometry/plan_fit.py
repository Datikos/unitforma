"""Rotation-and-translation fit of one footprint onto another, scored by IoU.

Shared by the placement pass (ADR-0025 Decision 5: a building's footprint onto a face of the site
plan) and the plan spaces of a zoneless IFC (ADR-0030 Decision 4: the apartment outlines of a floor
onto the slab footprint of its storey). A fit never mirrors; the sheet frame (y down) becomes the
IFC frame (y up) with :func:`sheet_to_ifc` before the search.
"""

from __future__ import annotations

import math
from typing import Any

from shapely import affinity
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

Point = tuple[float, float]

COARSE_STEP_DEG = 3.0
FINE_STEP_DEG = 0.5
# below this overlap the plan outlines are not taken as the IFC's spaces (ADR-0030 Decision 5;
# a start, the first real building sets it)
IFC_PLAN_FIT_MIN_IOU = 0.30
# each floor plan sheet has its own origin, so a level whose outlines leave its own storey's slab
# under the shared fit gets its own translation on top (ADR-0030 #D1; N4 levels 1-3 sat 3.1-3.9 m
# off on 2026-10-29)
LEVEL_SHIFT_MAX_M = 5.0
LEVEL_SHIFT_STEP_M = 0.25
LEVEL_SHIFT_MIN_GAIN = 0.05  # coverage a level must gain before it is moved
LEVEL_SHIFT_PLATEAU = 0.005  # coverage this close to the best counts as the best


def sheet_to_ifc(ring: list[Any]) -> list[Point]:
    """Sheet frame (x right, y down, metres) → IFC frame (x right, y up): (x, −y)."""
    return [(float(x), -float(y)) for x, y in ring]


def placed(poly: BaseGeometry, angle_deg: float, tx: float, ty: float) -> BaseGeometry:
    """``Placement.apply``: p' = (tx, ty) + R(angle) p."""
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    return affinity.affine_transform(poly, [c, -s, s, c, tx, ty])


def apply(ring: list[Point], angle_deg: float, tx: float, ty: float) -> list[Point]:
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    return [(tx + c * x - s * y, ty + s * x + c * y) for x, y in ring]


def fit_at(foot: BaseGeometry, face: BaseGeometry, angle: float) -> tuple[float, float, float]:
    """Translation that puts the rotated footprint's centroid on the face's, and the IoU."""
    a = math.radians(angle)
    c, s = math.cos(a), math.sin(a)
    fc, cf = foot.centroid, face.centroid
    tx = cf.x - (c * fc.x - s * fc.y)
    ty = cf.y - (s * fc.x + c * fc.y)
    moved = placed(foot, angle, tx, ty)
    union = moved.union(face).area
    iou = moved.intersection(face).area / union if union > 0 else 0.0
    return iou, tx, ty


def angles(lo: float, hi: float, step: float) -> list[float]:
    n = int(round((hi - lo) / step))
    return [lo + i * step for i in range(n)]


def best_rotation(
    foot: BaseGeometry,
    face: BaseGeometry,
    *,
    coarse: float = COARSE_STEP_DEG,
    fine: float = FINE_STEP_DEG,
) -> dict[str, float]:
    """The rotation (0–360°, ``coarse`` steps, refined at ``fine`` steps around the best) and the
    centroid translation with the highest IoU: ``{iou, tx, ty, rotation_deg}``."""
    (iou, tx, ty), ang = max(
        ((fit_at(foot, face, a), a) for a in angles(0.0, 360.0, coarse)), key=lambda t: t[0][0]
    )
    for f in angles(ang - coarse, ang + coarse, fine):
        f_iou, f_tx, f_ty = fit_at(foot, face, f)
        if f_iou > iou:
            iou, tx, ty, ang = f_iou, f_tx, f_ty, f
    return {"iou": iou, "tx": tx, "ty": ty, "rotation_deg": ang % 360.0}


def level_shift(
    foot: BaseGeometry,
    face: BaseGeometry,
    *,
    max_m: float = LEVEL_SHIFT_MAX_M,
    step: float = LEVEL_SHIFT_STEP_M,
) -> dict[str, Any]:
    """The translation of one level's placed footprint onto its own storey's ``face``.

    The coverage (share of the footprint inside the face) is scored on a ``step`` grid within
    ``max_m``; the shift is the smallest one whose coverage is within ``LEVEL_SHIFT_PLATEAU`` of the
    best, since a hull target is slack and the best coverage holds over a range of shifts. Returns
    ``{dx, dy, coverage, refused}``: (0, 0) when the gain is under ``LEVEL_SHIFT_MIN_GAIN`` or when
    the shift would reach the cap (the real offset may be larger; ``refused`` is then true).
    """
    area = foot.area
    if area <= 0:
        return {"dx": 0.0, "dy": 0.0, "coverage": 0.0, "refused": False}

    def cover(dx: float, dy: float) -> float:
        return affinity.translate(foot, dx, dy).intersection(face).area / area

    here = cover(0.0, 0.0)
    n = int(round(max_m / step))
    scored = [
        (cover(i * step, j * step), i * step, j * step)
        for i in range(-n, n + 1)
        for j in range(-n, n + 1)
        if math.hypot(i, j) <= n
    ]
    best = max(c for c, _dx, _dy in scored)
    if best - here < LEVEL_SHIFT_MIN_GAIN:
        return {"dx": 0.0, "dy": 0.0, "coverage": here, "refused": False}
    c, dx, dy = min(
        (t for t in scored if t[0] >= best - LEVEL_SHIFT_PLATEAU),
        key=lambda t: math.hypot(t[1], t[2]),
    )
    if math.hypot(dx, dy) > max_m - step:
        return {"dx": 0.0, "dy": 0.0, "coverage": here, "refused": True}
    return {"dx": dx, "dy": dy, "coverage": c, "refused": False}


def polygon(ring: list[Point]) -> Polygon:
    return Polygon(ring).buffer(0)


def joint_fit(
    feet: dict[Any, BaseGeometry],
    faces: dict[Any, BaseGeometry],
    fit_key: Any,
    *,
    coarse: float = COARSE_STEP_DEG,
    fine: float = FINE_STEP_DEG,
) -> dict[str, Any]:
    """One transform for several levels (ADR-0030 Decision 4, amended 2026-10-27).

    Candidates are the rotations of the ``fit_key`` level with their centroid translations; the
    winner has the highest IoU summed over every level present in both ``feet`` and ``faces``,
    which breaks the 180° ambiguity of a near-rectangular building that a single level leaves.
    Returns ``rotation_deg, tx, ty, iou`` (the fit level's), ``mean_iou``, ``min_coverage`` and
    ``per_level`` = {level: {"iou", "coverage"}}.
    """
    foot0, face0 = feet[fit_key], faces[fit_key]
    levels = [k for k in feet if k in faces]

    def total(angle: float, tx: float, ty: float) -> tuple[float, dict[Any, dict[str, float]]]:
        per: dict[Any, dict[str, float]] = {}
        tot = 0.0
        for k in levels:
            moved = placed(feet[k], angle, tx, ty)
            inter = moved.intersection(faces[k]).area
            union = moved.union(faces[k]).area
            iou = inter / union if union > 0 else 0.0
            cov = inter / feet[k].area if feet[k].area > 0 else 0.0
            per[k] = {"iou": round(iou, 3), "coverage": round(cov, 3)}
            tot += iou
        return tot, per

    best: tuple[float, float, float, float, dict[Any, dict[str, float]]] | None = None
    for a in angles(0.0, 360.0, coarse):
        _iou, tx, ty = fit_at(foot0, face0, a)
        tot, per = total(a, tx, ty)
        if best is None or tot > best[0]:
            best = (tot, a, tx, ty, per)
    assert best is not None
    _tot, ang, _tx, _ty, _per = best
    for f in angles(ang - coarse, ang + coarse, fine):
        _iou, tx, ty = fit_at(foot0, face0, f)
        tot, per = total(f, tx, ty)
        if tot > best[0]:
            best = (tot, f, tx, ty, per)
    tot, ang, tx, ty, per = best
    return {
        "rotation_deg": ang % 360.0,
        "tx": tx,
        "ty": ty,
        "iou": per[fit_key]["iou"],
        "mean_iou": tot / len(levels) if levels else 0.0,
        "min_coverage": min((v["coverage"] for v in per.values()), default=0.0),
        "per_level": per,
    }
