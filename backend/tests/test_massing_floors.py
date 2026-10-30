"""ADR-0037 Decision 5: the schematic model drawn as floors, not boxes.

A plate closes the corridor and the core between a floor's outlines but keeps a wide courtyard
open; the infill is the plate minus the units of the GLB (an unlisted unit becomes infill, not a
hole); every floor has a slab band, only the top floor a parapet; none of them is pickable."""

from __future__ import annotations

import pytest
from shapely.geometry import box

from unitforma.geometry import massing
from unitforma.geometry.massing import (
    PLATE_CLOSE_M,
    BuildingSolids,
    Placement,
    UnitSolid,
    build_glb,
    extrude_polygon,
    floor_plates,
    parse_glb,
)


def _unit(code: str, ring, level: int = 0, base: float = 0.0) -> UnitSolid:
    return UnitSolid(code, code, "apartment", "A", level, [list(p) for p in ring], base, 3.0)


def _rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def test_a_plate_closes_the_corridor_between_two_rows_of_flats():
    # two rows 8 m deep with a 3 m corridor between them (N4's bar in miniature)
    units = [_unit("a", _rect(0, 0, 20, 8)), _unit("b", _rect(0, 11, 20, 19))]
    [plate] = floor_plates(units)
    assert plate.polygon.geom_type == "Polygon"
    assert plate.polygon.area == pytest.approx(20 * 19, rel=0.01)


def test_a_courtyard_wider_than_the_closing_stays_open():
    # four flats around a 10 m yard, wider than twice the closing
    assert 10 > 2 * PLATE_CLOSE_M
    # a ring with a hole cannot be one unit outline: four flats around the yard
    units = [
        _unit("n", _rect(0, 0, 30, 10)),
        _unit("s", _rect(0, 20, 30, 30)),
        _unit("w", _rect(0, 10, 10, 20)),
        _unit("e", _rect(20, 10, 30, 20)),
    ]
    [plate] = floor_plates(units)
    assert len(plate.polygon.interiors) == 1 and plate.polygon.area == pytest.approx(800, rel=0.01)


def test_a_polygon_with_a_hole_extrudes_with_caps_of_its_area():
    poly = box(0, 0, 10, 10).difference(box(3, 3, 6, 6))
    pos, idx = extrude_polygon(poly, 0.0, 3.0)
    tops = [idx[i : i + 3] for i in range(0, len(idx), 3)]
    area = 0.0
    for a, b, c in tops:
        ys = {pos[3 * a + 1], pos[3 * b + 1], pos[3 * c + 1]}
        if ys == {3.0}:
            (x0, z0), (x1, z1), (x2, z2) = [(pos[3 * v], pos[3 * v + 2]) for v in (a, b, c)]
            area += abs((x1 - x0) * (z2 - z0) - (x2 - x0) * (z1 - z0)) / 2
    assert area == pytest.approx(91.0, rel=1e-6)


def _nodes(data):
    gltf, _ = parse_glb(data)
    return [n.get("extras") or {} for n in gltf["nodes"]]


def test_the_glb_has_infill_slabs_and_one_parapet_and_none_is_pickable():
    units = [
        _unit("a0", _rect(0, 0, 20, 8)),
        _unit("b0", _rect(0, 11, 20, 19)),
        _unit("a1", _rect(0, 0, 20, 8), level=1, base=3.0),
        _unit("b1", _rect(0, 11, 20, 19), level=1, base=3.0),
    ]
    bld = BuildingSolids("id", "A", "A", Placement(tx=100, ty=50), units)
    bld.plates = floor_plates(units)
    extras = _nodes(build_glb([bld])[0])
    kinds = sorted((e["structure"], e["floor_level"]) for e in extras if "structure" in e)
    assert kinds == [
        ("infill", 0),
        ("infill", 1),
        ("parapet", 1),
        ("slab", 0),
        ("slab", 1),
    ]
    assert all("unit_id" not in e for e in extras if "structure" in e)


def test_an_unlisted_unit_becomes_infill_in_the_public_model():
    units = [_unit("a", _rect(0, 0, 20, 8)), _unit("b", _rect(0, 11, 20, 19))]
    plates = floor_plates(units)
    public = BuildingSolids("id", "A", "A", Placement(), [units[0]], plates=plates)
    gltf, blob = parse_glb(build_glb([public])[0])
    infill = next(n for n in gltf["nodes"] if (n.get("extras") or {}).get("structure") == "infill")
    acc = gltf["accessors"][
        gltf["meshes"][infill["mesh"]]["primitives"][0]["attributes"]["POSITION"]
    ]
    # the infill reaches over the removed row: its bounds run to z 19
    assert acc["max"][2] == pytest.approx(19.0, abs=0.01)
    assert massing.PARAPET_M > 0
