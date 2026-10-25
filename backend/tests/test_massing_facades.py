"""Facade drawings on the massing (ADR-0016 Decision 2): the building rectangle, its side
numbering, and the textured wall primitives in the GLB."""

import io
import json
import math

from PIL import Image

from unitforma.geometry import massing


def _jpeg(w: int = 64, h: int = 16) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (180, 90, 60)).save(buf, format="JPEG")
    return buf.getvalue()


def _rot(p, deg):
    a = math.radians(deg)
    return (p[0] * math.cos(a) - p[1] * math.sin(a), p[0] * math.sin(a) + p[1] * math.cos(a))


def test_rectangle_is_clockwise_and_numbered_from_the_smallest_corner():
    rect = massing.building_rectangle([[(0, 0), (62.3, 0), (62.3, 15.2), (0, 15.2)]])
    assert rect == [(0, 0), (62.3, 0), (62.3, 15.2), (0, 15.2)]
    sides = massing.rectangle_sides(rect)
    assert [s.length for s in sides] == [62.3, 15.2, 62.3, 15.2]
    assert sides[0].normal == (0.0, -1.0)  # the top side faces "up" on the sheet
    assert massing.signed_area(rect) > 0  # clockwise as drawn on a y-down sheet


def test_rectangle_of_an_l_shape_and_stability_under_rotation():
    l_shape = [(0, 0), (40, 0), (40, 10), (15, 10), (15, 20), (0, 20)]
    rect = massing.building_rectangle([l_shape])
    assert rect is not None
    lengths = [s.length for s in massing.rectangle_sides(rect)]
    assert sorted(lengths) == [20.0, 20.0, 40.0, 40.0]
    # a rotated drawing gives the same rectangle (lengths); the side numbering is taken from the
    # building-local frame and carried through the placement, never recomputed after rotation
    rotated = massing.building_rectangle([[_rot(p, 30) for p in l_shape]])
    assert sorted(s.length for s in massing.rectangle_sides(rotated)) == sorted(lengths)


def test_glb_carries_the_facade_as_textured_wall_primitives():
    ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)]
    unit = massing.UnitSolid("u1", "A-1", "apartment", "A", 0, ring, 0.0, 3.2)
    bld = massing.BuildingSolids(
        "b1",
        "A",
        None,
        massing.Placement(),
        [unit],
        facades=[
            massing.FacadeImage(side=0, image=_jpeg()),
            massing.FacadeImage(side=2, image=_jpeg(), flip=True),
        ],
    )
    data, stats = massing.build_glb([bld])
    gltf, _bin = massing.parse_glb(data)
    assert len(gltf["images"]) == 2 and gltf["images"][0]["mimeType"] == "image/jpeg"
    assert gltf["textures"][1]["source"] == 1 and gltf["samplers"][0]["wrapS"] == 33071
    [mesh] = gltf["meshes"]
    prims = mesh["primitives"]
    # caps + inner walls, plus one textured primitive per facade side the unit touches
    assert len(prims) == 3
    textured = [p for p in prims if "TEXCOORD_0" in p["attributes"]]
    assert len(textured) == 2
    for p in textured:
        mat = gltf["materials"][p["material"]]
        assert "baseColorTexture" in mat["pbrMetallicRoughness"]
    # every primitive shares the one position accessor, and the UV accessor has one entry per vertex
    assert len({p["attributes"]["POSITION"] for p in prims}) == 1
    pos = gltf["accessors"][prims[0]["attributes"]["POSITION"]]
    uv = gltf["accessors"][textured[0]["attributes"]["TEXCOORD_0"]]
    assert uv["count"] == pos["count"] and uv["type"] == "VEC2"
    assert stats["units"] == 1 and stats["triangles"] == 12
    assert mesh["extras"]["unit_id"] == "u1"


def test_building_without_facades_keeps_one_primitive_per_unit():
    ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)]
    unit = massing.UnitSolid("u1", "A-1", "apartment", "A", 0, ring, 0.0, 3.2)
    data, _ = massing.build_glb(
        [massing.BuildingSolids("b1", "A", None, massing.Placement(), [unit])]
    )
    gltf, _ = massing.parse_glb(data)
    assert "images" not in gltf and len(gltf["meshes"][0]["primitives"]) == 1
    assert json.dumps(gltf["extras"])  # serialisable root extras


def _floats(gltf: dict, blob: bytes, accessor: int) -> list[float]:
    import struct

    acc = gltf["accessors"][accessor]
    view = gltf["bufferViews"][acc["bufferView"]]
    n = acc["count"] * {"VEC2": 2, "VEC3": 3, "SCALAR": 1}[acc["type"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    return list(struct.unpack_from(f"<{n}f", blob, start))


def test_recessed_walls_and_balconies_project_onto_the_facade_and_parking_stays_out():
    """The drawing is an orthographic projection: a wall facing the side within FACADE_DEPTH_M
    shows the drawing at its own position (u = its projection on the side), whether it is set
    back or sticks out; parking stalls neither define the rectangle nor carry a facade."""
    rect_ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)]
    ground = massing.UnitSolid("u1", "A-1", "apartment", "A", 0, rect_ring, 0.0, 3.0)
    recessed = massing.UnitSolid(
        "u2", "A-2", "apartment", "A", 1, [(2.0, 2.5), (8.0, 2.5), (8.0, 8.0), (2.0, 8.0)], 3.0, 3.0
    )
    balcony_ring = [(1.0, -1.5), (6.0, -1.5), (6.0, 8.0), (1.0, 8.0)]
    balcony = massing.UnitSolid("u3", "A-3", "apartment", "A", 2, balcony_ring, 6.0, 3.0)
    stall_ring = [(0.0, -12.0), (5.0, -12.0), (5.0, -7.0), (0.0, -7.0)]
    stall = massing.UnitSolid("p1", "P-1", "parking", "A", 0, stall_ring, 0.0, 2.5)
    bld = massing.BuildingSolids(
        "b1",
        "A",
        None,
        massing.Placement(),
        [ground, recessed, balcony, stall],
        facades=[massing.FacadeImage(side=0, image=_jpeg())],
    )
    data, _ = massing.build_glb([bld])
    gltf, blob = massing.parse_glb(data)
    meshes = {m["extras"]["unit_id"]: m for m in gltf["meshes"]}

    def facade_us(mesh: dict) -> list[float]:
        [prim] = [p for p in mesh["primitives"] if "TEXCOORD_0" in p["attributes"]]
        uv = _floats(gltf, blob, prim["attributes"]["TEXCOORD_0"])
        # vertices the textured walls do not use keep (0, 0); the facade's own vertices have v > 0
        # at the base or u > 0
        return sorted({round(uv[2 * k], 3) for k in range(len(uv) // 2) if uv[2 * k + 1] > 0})

    # the ground unit spans the whole side: its facade runs u = 0..1
    assert 0.0 in facade_us(meshes["u1"]) and 1.0 in facade_us(meshes["u1"])
    # the recessed wall at y = 2.5 (2.5 m inside) is textured; x = 2..8 projects to u = 0.2..0.8
    us = facade_us(meshes["u2"])
    assert min(us) == 0.2 and max(us) == 0.8, us
    # the balcony front at y = -1.5 (outside the rectangle) is textured too: x = 1..6 → u = 0.4..0.9
    us = facade_us(meshes["u3"])
    assert min(us) == 0.4 and max(us) == 0.9, us
    # the stall is 7 m away and did not define the rectangle: no textured primitive
    assert all("TEXCOORD_0" not in p["attributes"] for p in meshes["p1"]["primitives"])


def test_a_rectangle_fixed_by_the_building_survives_a_filtered_portal_build():
    """The portal GLB holds listed units only (``snapshot._massing``); ``collect()`` fixes the
    rectangle on the building from every unit, so the drawing stays where the admin page's sides
    say even when the units that defined the rectangle are not listed."""
    rect_ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)]
    recessed_ring = [(2.0, 2.5), (8.0, 2.5), (8.0, 8.0), (2.0, 8.0)]
    recessed = massing.UnitSolid("u2", "A-2", "apartment", "A", 1, recessed_ring, 3.0, 3.0)

    def facade_us(fixed_rect):
        bld = massing.BuildingSolids(
            "b1",
            "A",
            None,
            massing.Placement(),
            [recessed],
            facades=[massing.FacadeImage(side=0, image=_jpeg())],
            facade_rect=fixed_rect,
        )
        data, _ = massing.build_glb([bld])
        gltf, blob = massing.parse_glb(data)
        [prim] = [p for p in gltf["meshes"][0]["primitives"] if "TEXCOORD_0" in p["attributes"]]
        uv = _floats(gltf, blob, prim["attributes"]["TEXCOORD_0"])
        return sorted({round(uv[2 * k], 3) for k in range(len(uv) // 2) if uv[2 * k + 1] > 0})

    # alone, the unit would define the rectangle and span the whole drawing
    assert facade_us(None) == [0.0, 1.0]
    # with the building's rectangle fixed, it keeps its place in the drawing
    assert facade_us(massing.building_rectangle([rect_ring])) == [0.2, 0.8]
