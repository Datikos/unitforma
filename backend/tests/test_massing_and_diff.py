"""Pure-function tests: massing GLB builder, vector suggestions, revision diff classifier."""

from __future__ import annotations

import struct

from tests.pdf_fixture import make_plan_pdf
from unitforma.documents import processing
from unitforma.geometry import massing
from unitforma.mapping import diff, suggest

SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)]
L_SHAPE = [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (4.0, 4.0), (4.0, 8.0), (0.0, 8.0)]


def test_ear_clip_covers_polygon_area():
    for ring in (SQUARE, L_SHAPE, list(reversed(L_SHAPE))):
        tris = massing.ear_clip(ring)
        assert len(tris) == len(ring) - 2
        area = sum(abs(massing.signed_area([ring[a], ring[b], ring[c]])) for a, b, c in tris)
        assert abs(area - abs(massing.signed_area(ring))) < 1e-9


def test_extrude_produces_closed_solid():
    positions, indices = massing.extrude([(0, 0), (10, 0), (10, 8), (0, 8)], base=3.0, height=3.0)
    assert len(positions) == 8 * 3
    # 4 walls × 2 triangles + 2 caps × 2 triangles
    assert len(indices) == (8 + 4) * 3
    ys = positions[1::3]
    assert min(ys) == 3.0 and max(ys) == 6.0


def test_build_glb_is_valid_container_with_unit_nodes():
    bld = massing.BuildingSolids(
        building_id="b1",
        code="A",
        name="Block A",
        placement=massing.Placement(tx=100, ty=50, rotation_deg=90, scale=1, elevation=2),
        units=[
            massing.UnitSolid("u1", "A-00-01", "apartment", "A", 0, SQUARE, 0.0, 3.0),
            massing.UnitSolid(
                "u2",
                "A-01-01",
                "commercial",
                "A",
                1,
                L_SHAPE,
                3.0,
                3.2,
                extras={"lifecycle_status": "draft"},
            ),
        ],
    )
    data, stats = massing.build_glb([bld], {"project_id": "p"})
    assert data[:4] == b"glTF" and struct.unpack_from("<I", data, 8)[0] == len(data)
    gltf, blob = massing.parse_glb(data)
    assert gltf["asset"]["version"] == "2.0"
    assert gltf["buffers"][0]["byteLength"] == len(blob) or len(blob) - gltf["buffers"][0][
        "byteLength"
    ] in (1, 2, 3)
    names = {n["name"] for n in gltf["nodes"]}
    assert {"A", "A-00-01", "A-01-01"} <= names
    unit_nodes = [n for n in gltf["nodes"] if "mesh" in n]
    assert [n["extras"]["unit_id"] for n in unit_nodes] == ["u1", "u2"]
    # the viewer draws drafts translucent from this flag (ADR-0011)
    assert unit_nodes[1]["extras"]["lifecycle_status"] == "draft"
    assert "lifecycle_status" not in unit_nodes[0]["extras"]
    # roofs are their own material (ADR-0017 Decision 2)
    assert {m["name"] for m in gltf["materials"]} == {"apartment", "commercial", "roof"}
    assert stats["units"] == 2 and stats["triangles"] > 0 and stats["bytes"] == len(data)
    # rotation by 90° around the site origin: local (10, 0) → site (100 - 0, 50 + 10)
    acc = gltf["accessors"][0]
    assert abs(acc["min"][1] - 2.0) < 1e-6  # elevation applied to Y
    assert gltf["extras"]["unitforma"]["disclaimer"].startswith("Schematic model")
    # every accessor's byte range lies inside the binary chunk
    for a in gltf["accessors"]:
        bv = gltf["bufferViews"][a["bufferView"]]
        assert bv["byteOffset"] + bv["byteLength"] <= len(blob)


def test_build_glb_empty_project():
    data, stats = massing.build_glb([])
    gltf, _ = massing.parse_glb(data)
    assert gltf["scenes"] == [{"nodes": []}] and stats["units"] == 0


def test_closed_loops_from_fixture_pdf():
    ex = processing.extract_page(make_plan_pdf(), "application/pdf", 1)
    assert len(ex["rects"]) == 2
    cands = suggest.closed_loops(ex)
    assert len(cands) == 2
    labels = sorted(c.label for c in cands)
    assert labels == ["bina #1", "bina #2"]
    assert all(c.confidence >= 0.9 for c in cands)
    assert all(len(c.ring) == 4 for c in cands)
    assert suggest.closed_loops({"segments": [], "rects": []}) == []


def _rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def test_classify_all_kinds():
    olds = [
        diff.OldBoundary("b1", "u1", _rect(0.1, 0.1, 0.3, 0.3), "bina #1", "A-00-01", "approved"),
        diff.OldBoundary("b2", "u2", _rect(0.4, 0.1, 0.6, 0.3), "bina #2", "A-00-02", "approved"),
        diff.OldBoundary("b3", "u3", _rect(0.1, 0.4, 0.3, 0.6), "bina #3", "A-00-03", "approved"),
        diff.OldBoundary("b4", "u4", _rect(0.4, 0.4, 0.5, 0.6), None, "A-00-04", "approved"),
        diff.OldBoundary("b5", "u5", _rect(0.5, 0.4, 0.6, 0.6), None, "A-00-05", "approved"),
        diff.OldBoundary("b6", "u6", _rect(0.7, 0.7, 0.8, 0.8), "bina #6", "A-00-06", "draft"),
    ]
    news = [
        diff.NewCandidate(0, _rect(0.1, 0.1, 0.3, 0.3), "bina #1"),  # matched
        diff.NewCandidate(1, _rect(0.4, 0.1, 0.6, 0.3), "bina #2A"),  # relabelled
        diff.NewCandidate(2, _rect(0.1, 0.4, 0.2, 0.6), "bina #3"),  # split (part 1)
        diff.NewCandidate(3, _rect(0.2, 0.4, 0.3, 0.6), "bina #3B"),  # split (part 2)
        diff.NewCandidate(4, _rect(0.4, 0.4, 0.6, 0.6), "bina #4"),  # merged u4+u5
        diff.NewCandidate(5, _rect(0.7, 0.1, 0.9, 0.3), "bina #9"),  # new
    ]
    items = diff.classify(olds, news)
    by_kind = {it.kind: it for it in items}
    assert set(by_kind) == {"matched", "relabelled", "split", "merged", "new", "missing"}
    assert by_kind["matched"].old_unit_ids == ["u1"] and by_kind["matched"].new_indexes == [0]
    assert by_kind["relabelled"].old_unit_ids == ["u2"]
    assert by_kind["split"].old_unit_ids == ["u3"] and by_kind["split"].new_indexes == [2, 3]
    assert by_kind["merged"].old_unit_ids == ["u4", "u5"] and by_kind["merged"].new_indexes == [4]
    assert by_kind["new"].new_indexes == [5] and by_kind["new"].old_unit_ids == []
    assert by_kind["missing"].old_unit_ids == ["u6"]
    # risky changes are listed first so the reviewer sees them
    assert [it.kind for it in items][:2] == ["missing", "merged"]
    assert diff.summarise(items)["total"] == 6


def test_small_overlap_is_not_a_match():
    olds = [diff.OldBoundary("b1", "u1", _rect(0.1, 0.1, 0.3, 0.3), "1", "A", "approved")]
    news = [diff.NewCandidate(0, _rect(0.25, 0.25, 0.5, 0.5), "1")]  # ~6 % of either area
    kinds = {it.kind for it in diff.classify(olds, news)}
    assert kinds == {"missing", "new"}


def test_normalise_label():
    assert suggest.normalise_label("bina #12") == "12"
    assert suggest.normalise_label("Apt. 3A") == "3A"
    assert suggest.normalise_label("  7 ") == "7"
    assert suggest.normalise_label(None) is None


def test_queue_massing_swallows_duplicates_and_outages(monkeypatch):
    """ADR-0011: one waiting build per project; a queue outage never fails the reviewer's edit."""
    import asyncio
    import uuid

    from procrastinate.exceptions import AlreadyEnqueued

    from unitforma.geometry import service
    from unitforma.jobs import app as jobs_app

    calls: list[dict] = []
    outcome: dict = {"fail": None}

    class Deferrer:
        async def defer_async(self, **kw):
            calls.append(kw)
            if outcome["fail"]:
                raise outcome["fail"]

    def configure_task(name, **options):
        assert name == "geometry.build_massing"
        assert options["queueing_lock"].startswith("massing:")
        return Deferrer()

    monkeypatch.setattr(jobs_app.app, "configure_task", configure_task)
    tid, pid = uuid.uuid4(), uuid.uuid4()
    assert asyncio.run(service.queue_massing(tid, pid)) is True
    outcome["fail"] = AlreadyEnqueued()
    assert asyncio.run(service.queue_massing(tid, pid)) is True  # already waiting: fine
    outcome["fail"] = RuntimeError("queue down")
    assert asyncio.run(service.queue_massing(tid, pid)) is False
    assert len(calls) == 3 and calls[0] == {"tenant_id": str(tid), "project_id": str(pid)}
