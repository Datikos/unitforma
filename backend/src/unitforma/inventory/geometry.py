"""Polygon helpers: validation, calibration transform, measured area (plan §5.1)."""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import Polygon

Ring = list[list[float]]


def validate_ring(ring: Ring) -> Polygon:
    if len(ring) < 3:
        raise ValueError("a boundary needs at least 3 points")
    for pt in ring:
        if len(pt) != 2 or not all(isinstance(c, (int, float)) and 0.0 <= c <= 1.0 for c in pt):
            raise ValueError("points must be normalised sheet coordinates in [0, 1]")
    poly = Polygon(ring)
    if not poly.is_valid or poly.area <= 0:
        raise ValueError("boundary polygon is self-intersecting or degenerate")
    return poly


def calibration_from_points(
    p1: list[float], p2: list[float], distance_m: float, raster_width: int, raster_height: int
) -> dict[str, Any]:
    """Two normalised points and the real distance between them → metres per raster pixel.

    Sheet rasters are not square, so a normalised dx and dy correspond to different pixel lengths.
    We express the scale as metres per raster pixel (isotropic), derived from the pixel distance.
    """
    if distance_m <= 0:
        raise ValueError("distance must be positive")
    dx_px = (p2[0] - p1[0]) * raster_width
    dy_px = (p2[1] - p1[1]) * raster_height
    px = math.hypot(dx_px, dy_px)
    if px < 2:
        raise ValueError("calibration points are too close together")
    return {
        "p1": p1,
        "p2": p2,
        "distance_m": distance_m,
        "m_per_px": distance_m / px,
        "raster_width": raster_width,
        "raster_height": raster_height,
    }


def ring_to_metres(ring: Ring, calibration: dict[str, Any]) -> Ring:
    m = calibration["m_per_px"]
    w, h = calibration["raster_width"], calibration["raster_height"]
    return [[round(x * w * m, 4), round(y * h * m, 4)] for x, y in ring]


def area_m2(ring_m: Ring) -> float:
    return round(Polygon(ring_m).area, 2)


def overlap_ratio(a: Ring, b: Ring) -> float:
    pa, pb = Polygon(a), Polygon(b)
    inter = pa.intersection(pb).area
    return inter / min(pa.area, pb.area) if min(pa.area, pb.area) > 0 else 0.0
