"""The architect's IFC model on the site (ADR-0037 Decision 1).

The plan fit (ADR-0030 Decision 4) maps building metres, the reference floor's sheet frame (x
right, y down; ADR-0030 #D2), into the IFC plan: ``q = R(θ)·(x, −y) + t``. The site placement
maps building metres onto the site: ``s = T + scale·R(φ)·p`` (``massing.Placement``). The IFC GLB
holds ``(q.x − ox, z − oz, −(q.y − oy))`` (``ifc._to_gltf``), the schematic GLB ``(s.x, h, s.y)``.
``placement ∘ fit⁻¹`` turns the first into the second; the two y flips cancel, so it is a rotation,
a translation and the placement's scale. Heights: the fit storey's elevation lands on the fit
floor's base. Computed when it is needed, never stored, so a new placement or re-run is followed.
"""

from __future__ import annotations

import math
from typing import Any


def site_matrix_of(
    *,
    rotation_deg: float,
    tx: float,
    ty: float,
    offset_m: list[float],
    placement: dict[str, Any],
    fit_base_m: float,
    storey_elevation_m: float,
) -> list[float]:
    """The 4×4 matrix, column-major (three.js ``Matrix4.fromArray``), from IFC GLB metres to
    schematic GLB (site) metres."""
    ox, oy, oz = (float(v) for v in offset_m)
    k = float(placement.get("scale", 1) or 1)
    big_tx, big_ty = float(placement.get("tx", 0) or 0), float(placement.get("ty", 0) or 0)
    lift = float(placement.get("elevation", 0) or 0)
    # A = k·R(φ)·diag(1, −1)·R(−θ) = k·[[C, S], [S, −C]] with α = φ + θ
    alpha = math.radians(float(placement.get("rotation_deg", 0) or 0) + rotation_deg)
    c, s = math.cos(alpha), math.sin(alpha)
    # q = (Gx + ox, −Gz + oy), s = T + A·(q − t) = A·(Gx, −Gz) + T + A·(o − t)
    dx, dy = ox - tx, oy - ty
    cx = big_tx + k * (c * dx + s * dy)
    cz = big_ty + k * (s * dx - c * dy)
    lift_y = oz + fit_base_m - storey_elevation_m + lift
    # on (Gx, Gz) A·diag(1, −1) = k·R(α): site x = k(C·Gx − S·Gz) + cx, site z = k(S·Gx + C·Gz) + cz
    rows = (
        (k * c, 0.0, -k * s, cx),
        (0.0, 1.0, 0.0, lift_y),
        (k * s, 0.0, k * c, cz),
        (0.0, 0.0, 0.0, 1.0),
    )
    return [round(rows[r][c], 6) for c in range(4) for r in range(4)]


def apply(matrix: list[float], p: tuple[float, float, float]) -> tuple[float, float, float]:
    """A column-major matrix applied to a point (for tests and checks)."""
    x, y, z = p
    m = matrix
    return (
        m[0] * x + m[4] * y + m[8] * z + m[12],
        m[1] * x + m[5] * y + m[9] * z + m[13],
        m[2] * x + m[6] * y + m[10] * z + m[14],
    )
