"""ADR-0006 Phase C, the parts that need no IfcOpenShell: storey → floor and space → unit
matching, and rewriting a GLB's space extras after the reviewer confirms links."""

from __future__ import annotations

from unitforma.geometry import ifc, ifc_match, massing
from unitforma.geometry.massing import _GltfBuilder, parse_glb

F0, F1, F2 = (
    ifc_match.FloorRef("f0", 0, 0.0),
    ifc_match.FloorRef("f1", 1, 3.2),
    ifc_match.FloorRef("f2", 2, 6.4),
)


def test_storeys_match_floors_by_elevation_then_by_order():
    assert ifc_match.match_floors([(0, 0.05), (1, 3.3), (2, 6.4)], [F0, F1, F2]) == {
        0: "f0",
        1: "f1",
        2: "f2",
    }
    # model at +100.00 above sea level: nothing within 0.3 m, same count → matched by order
    assert ifc_match.match_floors([(0, 100.0), (1, 103.2)], [F0, F1]) == {0: "f0", 1: "f1"}
    # different counts and no elevation match: unmatched
    assert ifc_match.match_floors([(0, 100.0)], [F0, F1]) == {0: None}
    # floors without elevations: by order only
    bare = [ifc_match.FloorRef("a", 0, None), ifc_match.FloorRef("b", 1, None)]
    assert ifc_match.match_floors([(0, 0.0), (1, 3.2)], bare) == {0: "a", 1: "b"}


def test_spaces_match_units_by_label_then_by_being_the_only_one():
    units = [
        ifc_match.UnitRef("u1", "A-00-01", "f0", "ბინა №1 48.0 m²"),
        ifc_match.UnitRef("u2", "A-00-02", "f0", "ბინა №2"),
        ifc_match.UnitRef("u7", "A-01-07", "f1", None),
    ]
    spaces = [
        ifc_match.SpaceRef("g1", "1", "ბინა 1", 0, 0.0),
        ifc_match.SpaceRef("g2", "Apt 2", None, 0, 0.0),
        ifc_match.SpaceRef("g3", "Flat", "Living room", 1, 3.2),  # only space on level 1
        ifc_match.SpaceRef("g9", "Stair", None, 2, 6.4),  # storey with no floor
    ]
    out = {m.global_id: m for m in ifc_match.match_spaces(spaces, [F0, F1], units)}
    assert (out["g1"].unit_id, out["g1"].confidence, out["g1"].status) == ("u1", 0.9, "suggested")
    assert (out["g2"].unit_id, out["g2"].confidence) == ("u2", 0.9)
    assert (out["g3"].unit_id, out["g3"].confidence) == ("u7", 0.6)
    assert (out["g9"].floor_id, out["g9"].status) == (None, "unmatched")


def test_two_spaces_with_the_same_label_are_ambiguous():
    units = [ifc_match.UnitRef("u1", "A-00-01", "f0", "ბინა №1")]
    spaces = [
        ifc_match.SpaceRef("a", "1", None, 0, 0.0),
        ifc_match.SpaceRef("b", "1", None, 0, 0.0),
    ]
    out = ifc_match.match_spaces(spaces, [F0], units)
    assert [(m.unit_id, m.confidence, m.status) for m in out] == [
        ("u1", 0.9, "suggested"),
        (None, None, "unmatched"),  # the unit is taken; the second "1" waits for the reviewer
    ]


def _space_glb() -> bytes:
    b = _GltfBuilder()
    square = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 1.0]
    extras = {"ifc_global_id": "GID1", "unit_id": "space:GID1", "code": "1"}
    m = b.mesh("1", square, [0, 1, 2, 0, 2, 3], b.material("apartment"), extras)
    n1 = b.node("1", m, [], extras)
    wall = {"ifc_class": "IfcWall", "elements": 1}
    m2 = b.mesh("IfcWall", square, [0, 1, 2], b.material("commercial"), wall)
    n2 = b.node("IfcWall", m2, [], wall)
    return b.glb([b.node("B", None, [n1, n2], {})], {"unitforma": {"kind": "ifc"}})


def test_relink_rewrites_space_extras_only_and_keeps_geometry():
    data = _space_glb()
    linked = ifc.relink_glb(data, {"GID1": "unit-uuid"})
    gltf, blob = parse_glb(linked)
    gltf0, blob0 = parse_glb(data)
    assert blob == blob0 and gltf["accessors"] == gltf0["accessors"]
    space = next(n for n in gltf["nodes"] if n.get("extras", {}).get("ifc_global_id") == "GID1")
    assert space["extras"]["unit_id"] == "unit-uuid"
    wall = next(n for n in gltf["nodes"] if n.get("extras", {}).get("ifc_class") == "IfcWall")
    assert "unit_id" not in wall["extras"]
    # published variant: an unlisted or unconfirmed space is not pickable at all
    hidden = ifc.relink_glb(data, {"GID1": None})
    g2, _ = parse_glb(hidden)
    assert (
        "unit_id"
        not in next(n for n in g2["nodes"] if n.get("extras", {}).get("ifc_global_id"))["extras"]
    )
    # a space not in the mapping falls back to its space id
    g3, _ = parse_glb(ifc.relink_glb(data, {}))
    assert (
        next(n for n in g3["nodes"] if n.get("extras", {}).get("ifc_global_id"))["extras"][
            "unit_id"
        ]
        == "space:GID1"
    )
    assert massing.parse_glb(linked)[0]["extras"]["unitforma"]["kind"] == "ifc"
    # the full form: unit id, the unit's code (what the portal routes to) and the floor's level
    full = {"GID1": {"unit_id": "u1", "code": "A-00-01", "floor_level": -1}}
    g4, _ = parse_glb(ifc.relink_glb(data, full))
    ex = next(n for n in g4["nodes"] if n.get("extras", {}).get("ifc_global_id"))["extras"]
    assert (ex["unit_id"], ex["code"], ex["floor_level"]) == ("u1", "A-00-01", -1)
    # floor level alone, unit still unknown: stays a space, but on the right floor
    g5, _ = parse_glb(ifc.relink_glb(data, {"GID1": {"unit_id": None, "floor_level": 2}}))
    ex = next(n for n in g5["nodes"] if n.get("extras", {}).get("ifc_global_id"))["extras"]
    assert (ex["unit_id"], ex["floor_level"]) == ("space:GID1", 2)
