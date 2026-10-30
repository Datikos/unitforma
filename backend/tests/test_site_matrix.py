"""ADR-0037 Decision 1: the architect's IFC model onto the site, ``placement ∘ fit⁻¹``.

A point of a floor outline (building metres, sheet frame y down) goes through the plan fit into
the IFC plan, into the IFC GLB; the matrix must bring it to where the schematic model draws the
same point (the placement), at the fit floor's height."""

from __future__ import annotations

import math

import pytest

from unitforma.geometry.site_matrix import apply, site_matrix_of


def _ifc_glb(p, theta, t, offset, z):
    """Building metres → IFC plan (``plan_fit``) → IFC GLB (``ifc._to_gltf``)."""
    x, y = p[0], -p[1]
    c, s = math.cos(math.radians(theta)), math.sin(math.radians(theta))
    qx, qy = t[0] + c * x - s * y, t[1] + s * x + c * y
    ox, oy, oz = offset
    return (qx - ox, z - oz, -(qy - oy))


def _site(p, placement):
    """Building metres → site (``massing.Placement``), as the schematic GLB (x, h, y)."""
    a = math.radians(placement["rotation_deg"])
    k = placement["scale"]
    return (
        placement["tx"] + k * (math.cos(a) * p[0] - math.sin(a) * p[1]),
        placement["ty"] + k * (math.sin(a) * p[0] + math.cos(a) * p[1]),
    )


@pytest.mark.parametrize(
    ("theta", "phi", "scale"),
    [(0.0, 0.0, 1.0), (2.5, 0.0, 1.0), (33.0, -71.0, 1.0), (190.0, 12.0, 1.02)],
)
def test_a_point_of_an_outline_lands_where_the_schematic_model_draws_it(theta, phi, scale):
    t, offset = (-20.498, 30.5), (-14.078, -26.889, -5.2)
    placement = {"tx": 40.926, "ty": 29.089, "rotation_deg": phi, "scale": scale, "elevation": 0.5}
    m = site_matrix_of(
        rotation_deg=theta,
        tx=t[0],
        ty=t[1],
        offset_m=list(offset),
        placement=placement,
        fit_base_m=-3.0,
        storey_elevation_m=-2.4,  # the IFC storey and the floor disagree by 0.6 m
    )
    for p in [(12.7, 20.2), (74.6, 54.1), (0.0, 0.0), (-5.0, 33.3)]:
        sx, sy, sz = apply(m, _ifc_glb(p, theta, t, offset, z=-2.4))
        ex, ez = _site(p, placement)
        assert (sx, sz) == pytest.approx((ex, ez), abs=1e-3)
        assert sy == pytest.approx(-3.0 + 0.5, abs=1e-6)  # the fit floor's base, lifted


def test_n4_level_0_lands_on_the_schematic_model():
    # measured 2026-10-30: N4 building A, plan fit at level -2, placement (40.926, 29.089)
    m = site_matrix_of(
        rotation_deg=0.0,
        tx=-20.498,
        ty=30.5,
        offset_m=[-14.078, -26.889, -5.2],
        placement={"tx": 40.926, "ty": 29.089, "rotation_deg": 0.0},
        fit_base_m=-3.0,
        storey_elevation_m=-3.0,
    )
    x, y, z = apply(m, _ifc_glb((12.7, 20.2), 0.0, (-20.498, 30.5), (-14.078, -26.889, -5.2), 0.0))
    assert (x, y, z) == pytest.approx((53.626, 0.0, 49.289), abs=1e-3)
