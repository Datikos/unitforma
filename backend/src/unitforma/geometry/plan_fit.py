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


def polygon(ring: list[Point]) -> Polygon:
    return Polygon(ring).buffer(0)
