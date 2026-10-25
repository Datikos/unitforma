"""Split-level and multi-block sheets (plan §13.2): one sheet shows several floors.

Covers the three gaps found on a real stepped building (three blocks side by side, each at
its own level on every typical sheet):
1. a sheet carries several floor assignments, each with a region; units drawn on it get the
   floor of the region that holds them; footprints and the published plans follow the units;
2. unit outlines come from the drawing's filled zones, or from labelled faces grown to the
   printed area, instead of single rooms;
3. floor suggestions come from level markers matched to floor elevations, with title-block
   repeats and sections ignored.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon

from tests.fake_kratos import cookie
from tests.pdf_fixture import (
    make_split_level_pdf,
    split_apartment_area,
)
from unitforma.documents import levels
from unitforma.mapping import suggest
from unitforma.publishing.snapshot import crop_for, recrop

needs_db = pytest.mark.skipif(
    not (os.environ.get("UF_TEST_DATABASE_ADMIN_URL") and os.environ.get("UF_TEST_DATABASE_URL")),
    reason="needs the PostgreSQL test database",
)


# --- pure functions ------------------------------------------------------------------------
def _w(t: str, x: float, y: float) -> dict:
    return {"t": t, "x0": x - 0.01, "x1": x + 0.01, "y0": y - 0.005, "y1": y + 0.005}


def test_markers_tolerate_cad_glyphs_and_skip_captions_and_ranges():
    words = [
        _w("O+3.20", 0.2, 0.4),
        _w("(652.2)", 0.23, 0.4),
        _w("+O", 0.47, 0.4),
        _w("4.20", 0.49, 0.4),
        _w("(654.2)", 0.52, 0.4),
        _w("gegma", 0.2, 0.85),
        _w("+3.20,", 0.22, 0.85),
        _w("+4.20", 0.24, 0.85),
        _w("(-4.05", 0.03, 0.98),
        _w("12.50", 0.5, 0.5),  # a dimension, not a level
    ]
    ms = levels.markers_from_words(words)
    assert [(m.text, m.absolute) for m in ms] == [("+3.20", 652.2), ("+4.20", 654.2)]


def test_title_block_repeats_dropped_but_duplicate_plans_kept():
    def page(*texts_xy):
        return [levels.Marker(t, float(t), x, y) for t, x, y in texts_xy]

    per = {
        1: page(("+0.00", 0.2, 0.4), ("+1.00", 0.5, 0.4), ("+14.70", 0.07, 0.98)),
        2: page(("+3.20", 0.2, 0.4), ("+4.20", 0.5, 0.4), ("+14.70", 0.07, 0.98)),
        3: page(("+6.40", 0.2, 0.4), ("+7.40", 0.5, 0.4), ("+14.70", 0.07, 0.98)),
        # three reprints of the +3.20 plan (fire, egress, accessibility sets)
        4: page(("+3.20", 0.3, 0.5)),
        5: page(("+3.20", 0.3, 0.5)),
        6: page(("+3.20", 0.3, 0.5)),
    }
    kept = levels.drop_repeated(per)
    assert [m.text for m in kept[1]] == ["+0.00", "+1.00"]
    assert [m.text for m in kept[4]] == ["+3.20"]


def test_stacked_markers_are_a_section():
    col = [
        levels.Marker(t, float(t), 0.1, y)
        for t, y in (("+0.00", 0.8), ("+3.20", 0.6), ("+6.40", 0.4))
    ]
    row = [
        levels.Marker(t, float(t), x, 0.4)
        for t, x in (("+0.00", 0.2), ("+1.00", 0.5), ("+2.00", 0.8))
    ]
    assert levels.is_stacked(col) and not levels.is_stacked(row)


def test_floors_matched_by_elevation_and_split_into_regions():
    a, b = uuid.uuid4(), uuid.uuid4()
    fa = levels.FloorRef(uuid.uuid4(), a, 1, 3.2)
    fb = levels.FloorRef(uuid.uuid4(), b, 1, 4.2)
    other = levels.FloorRef(uuid.uuid4(), b, 2, 7.4)
    ms = [levels.Marker("+3.20", 3.2, 0.25, 0.4), levels.Marker("+4.20", 4.2, 0.75, 0.4)]
    matched = levels.match_floors(ms, [fa, fb, other])
    assert [(m.text, f.id) for m, f in matched] == [("+3.20", fa.id), ("+4.20", fb.id)]
    regions = levels.floor_regions(matched, aspect=0.7)
    assert [r["floor_id"] for r in regions] == [fa.id, fb.id]
    left = Polygon(regions[0]["region"]["ring"])
    assert left.contains(Polygon([(0.1, 0.1), (0.4, 0.1), (0.4, 0.9)]).centroid)
    assert abs(left.area - 0.5) < 1e-6
    pairs = [(r["floor_id"], r["region"]) for r in regions]
    assert levels.region_floor((0.9, 0.5), pairs) == fb.id
    # a single floor needs no region and takes the whole sheet
    one = levels.floor_regions(matched[:1])
    assert one[0]["region"] is None
    assert levels.region_floor((0.9, 0.9), [(fa.id, None)]) == fa.id
    # no elevations entered: a lone ±0.00 still means the entrance floor of the building
    g = levels.FloorRef(uuid.uuid4(), a, 0, None)
    assert levels.match_floors([levels.Marker("+0.00", 0.0, 0.5, 0.5)], [g], a)[0][1] == g


def _box(x0, y0, x1, y1):
    return [x0, y0, x1, y1]


def test_labelled_room_grows_to_the_printed_area_but_not_into_other_zones():
    # page = 100 m × 100 m, so 0.01 normalised² = 100 m²
    w = [
        _w("bina", 0.13, 0.2),
        _w("#1", 0.16, 0.2),
        _w("430.0", 0.13, 0.22),
        _w("m2", 0.16, 0.22),
        _w("+3.20", 0.3, 0.325),  # corridor: carries the level marker
        _w("50.0", 0.15, 0.075),  # balcony: its own printed area
        _w("m2", 0.17, 0.075),
        _w("bina", 0.38, 0.2),
        _w("#2", 0.41, 0.2),
        _w("400.0", 0.38, 0.22),
        _w("m2", 0.41, 0.22),
    ]
    extract = {
        "words": w,
        "segments": [],
        "rects": [
            _box(0.1, 0.1, 0.2, 0.3),  # room 1a (label)
            _box(0.2, 0.1, 0.3, 0.3),  # room 1b
            _box(0.1, 0.3, 0.5, 0.35),  # corridor
            _box(0.1, 0.05, 0.2, 0.1),  # balcony
            _box(0.3, 0.1, 0.5, 0.3),  # apartment 2, one face
        ],
        "fills": [],
    }
    cands = suggest.closed_loops(extract, page_m=(100.0, 100.0), min_area=0.001)
    by = {(c.label, c.method): c for c in cands}
    grown = by[("bina #1", "grown")]
    assert grown.confidence == 0.7 and grown.printed_area_m2 == 430.0
    assert abs(Polygon(grown.ring).area - 0.04) < 1e-6  # both rooms, no balcony, no corridor
    plain = by[("bina #2", "loop")]
    assert plain.confidence == 0.9 and plain.measured_area_m2 == 400.0
    # the seed room on its own is no longer offered as the unit
    assert ("bina #1", "loop") not in by


def test_partial_room_is_flagged_when_growth_cannot_reach_the_printed_area():
    w = [_w("bina", 0.13, 0.2), _w("#1", 0.16, 0.2), _w("900.0", 0.13, 0.22), _w("m2", 0.16, 0.22)]
    extract = {"words": w, "segments": [], "rects": [_box(0.1, 0.1, 0.2, 0.3)], "fills": []}
    c = next(
        x for x in suggest.closed_loops(extract, page_m=(100.0, 100.0)) if x.label == "bina #1"
    )
    assert c.method == "loop" and c.confidence == 0.5 and c.measured_area_m2 == 200.0


def test_fill_zone_beats_rooms_and_background_fills_are_ignored():
    w = [
        _w("bina", 0.15, 0.14),
        _w("#7", 0.18, 0.14),
        _w("200.0", 0.15, 0.16),
        _w("m2", 0.18, 0.16),
        _w("bina", 0.45, 0.2),
        _w("#8", 0.48, 0.2),
    ]
    zone = [[0.1, 0.1], [0.3, 0.1], [0.3, 0.2], [0.1, 0.2]]
    background = [[0.05, 0.05], [0.6, 0.05], [0.6, 0.4], [0.05, 0.4]]
    extract = {
        "words": w,
        "segments": [[0.2, 0.1, 0.2, 0.2]],
        "rects": [_box(0.1, 0.1, 0.3, 0.2)],
        "fills": [{"ring": background, "rgb": [1, 1, 1]}, {"ring": zone, "rgb": [0.5, 0.75, 1]}],
    }
    cands = suggest.closed_loops(extract, page_m=(100.0, 100.0))
    units = [c for c in cands if c.label == "bina #7"]
    assert len(units) == 1 and units[0].method == "fill" and units[0].confidence == 0.95
    assert units[0].measured_area_m2 == 200.0
    assert not any(c.method == "fill" and abs(c.area_norm - 0.1925) < 1e-6 for c in cands)


def test_crop_follows_one_floors_units():
    rings = [
        [[0.1, 0.4], [0.2, 0.4], [0.2, 0.6], [0.1, 0.6]],
        [[0.25, 0.4], [0.3, 0.4], [0.3, 0.6]],
    ]
    crop = crop_for(rings)
    assert crop == (0.07, 0.37, 0.33, 0.63)
    assert recrop([[0.07, 0.37], [0.33, 0.63]], crop) == [[0.0, 0.0], [1.0, 1.0]]
    assert crop_for([[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]]) is None  # most of the sheet


# --- API: process, assign, draw, footprints -----------------------------------------------
@pytest.fixture(scope="module")
def world(client: TestClient, kratos) -> dict:
    s = uuid.uuid4().hex[:6]
    kratos.add("rootsl", f"rootsl-{s}@unitforma.example.com", aal="aal2")
    assert client.get("/api/v1/admin/me", headers=cookie("rootsl")).status_code == 200
    from sqlalchemy import create_engine, text

    eng = create_engine(os.environ["UF_TEST_DATABASE_ADMIN_URL"])
    with eng.begin() as conn:
        conn.execute(
            text("UPDATE users SET is_platform_admin = true WHERE email = :e"),
            {"e": f"rootsl-{s}@unitforma.example.com"},
        )
    eng.dispose()
    from unitforma.identity.deps import clear_whoami_cache

    clear_whoami_cache()
    root = cookie("rootsl")
    kratos.add("archsl", f"archsl-{s}@a.example.com")
    t = client.post(
        "/api/v1/platform/tenants", headers=root, json={"slug": f"lisi{s}", "name": "Lisi Co"}
    ).json()
    base = f"/api/v1/admin/tenants/{t['id']}"
    inv = client.post(
        f"/api/v1/platform/tenants/{t['id']}/invitations",
        headers=root,
        params={"email": f"archsl-{s}@a.example.com"},
    ).json()
    client.post(
        "/api/v1/admin/invitations/accept",
        headers=cookie("archsl"),
        json={"token": inv["accept_url"].rsplit("/", 1)[1]},
    )
    arch = cookie("archsl")
    p = client.post(
        f"{base}/projects", headers=arch, json={"slug": "lisi", "name": "Lisi Residences"}
    ).json()
    buildings, floors = {}, {}
    for code, base_elev in (("A", 0.0), ("B", 1.0), ("C", 2.0)):
        b = client.post(
            f"{base}/projects/{p['id']}/buildings",
            headers=arch,
            json={"code": code, "name": f"Block {code}"},
        ).json()
        fl = client.put(
            f"{base}/buildings/{b['id']}/floors",
            headers=arch,
            json={
                "floors": [
                    {
                        "level": 0,
                        "display_name": "Ground",
                        "elevation_m": base_elev,
                        "height_m": 3.2,
                    },
                    {
                        "level": 1,
                        "display_name": "1",
                        "elevation_m": base_elev + 3.2,
                        "height_m": 3.2,
                    },
                ]
            },
        )
        assert fl.status_code in (200, 201), fl.text
        buildings[code] = b
        for f in fl.json():
            floors[(code, f["level"])] = f
    return {"base": base, "tenant": t, "project": p, "arch": arch, "b": buildings, "f": floors}


@pytest.fixture(scope="module")
def kratos():
    from tests.fake_kratos import FakeKratos

    return FakeKratos()


@pytest.fixture(scope="module")
def client(kratos, tmp_path_factory):
    os.environ["UF_STORAGE_BACKEND"] = "local"
    os.environ["UF_STORAGE_LOCAL_ROOT"] = str(tmp_path_factory.mktemp("storage-sl"))
    from unitforma.core.settings import get_settings
    from unitforma.identity.deps import clear_whoami_cache, get_kratos
    from unitforma.main import create_app
    from unitforma.storage.service import reset_storage

    get_settings.cache_clear()
    reset_storage()
    clear_whoami_cache()
    app = create_app()
    app.dependency_overrides[get_kratos] = lambda: kratos
    with TestClient(app, headers={"X-Requested-With": "unitforma"}) as c:
        yield c
    get_settings.cache_clear()
    reset_storage()


def _upload(client: TestClient, world: dict, data: bytes, document_id: str | None = None) -> dict:
    base, arch = world["base"], world["arch"]
    if document_id is None:
        doc = client.post(
            f"{base}/projects/{world['project']['id']}/documents",
            headers=arch,
            json={
                "kind": "floor_plan",
                "title": "Typical plans",
                "building_id": world["b"]["A"]["id"],
            },
        )
        assert doc.status_code == 201, doc.text
        document_id = doc.json()["id"]
    intent = client.post(
        f"{base}/documents/{document_id}/uploads",
        headers=arch,
        json={"file_name": "plans.pdf", "content_type": "application/pdf", "byte_size": len(data)},
    ).json()
    assert (
        client.put(
            intent["upload_url"], content=data, headers={"Content-Type": "application/pdf"}
        ).status_code
        == 200
    )
    done = client.post(f"{base}/revisions/{intent['revision']['id']}/complete", headers=arch)
    assert done.status_code == 200, done.text
    from unitforma.documents.jobs import process_revision

    result = client.portal.call(
        process_revision, uuid.UUID(world["tenant"]["id"]), uuid.UUID(intent["revision"]["id"])
    )
    sheets = client.get(f"{base}/revisions/{intent['revision']['id']}/sheets", headers=arch).json()
    return {"document_id": document_id, "result": result, "sheets": sheets}


@pytest.fixture(scope="module")
def uploaded(client: TestClient, world: dict) -> dict:
    return _upload(client, world, make_split_level_pdf())


def _fid(world, code, level):
    return world["f"][(code, level)]["id"]


@needs_db
def test_level_markers_suggest_one_floor_per_block_with_regions(world: dict, uploaded: dict):
    s1, s2, s3 = uploaded["sheets"]
    assert [m["text"] for m in s1["hints"]["level_markers"]] == ["+0.00", "+1.00", "+2.00"]
    assert s1["assignment_status"] == "suggested" and s1["floor_id"] is None
    got = [(f["floor_id"], f["status"], f["source"], f["marker"]) for f in s1["floors"]]
    assert got == [
        (_fid(world, "A", 0), "suggested", "level_marker", "+0.00"),
        (_fid(world, "B", 0), "suggested", "level_marker", "+1.00"),
        (_fid(world, "C", 0), "suggested", "level_marker", "+2.00"),
    ]
    assert all(f["region"] and len(f["region"]["ring"]) >= 4 for f in s1["floors"])
    assert [f["floor_id"] for f in s2["floors"]] == [_fid(world, c, 1) for c in ("A", "B", "C")]
    # the section stacks its markers: no floor; the title-block range never counts
    assert s3["floors"] == [] and s3["assignment_status"] == "unassigned"
    assert "-2.55" not in [m["text"] for m in s3["hints"]["level_markers"]]


@needs_db
def test_drawing_needs_confirmed_floors_then_units_take_their_region(
    client: TestClient, world: dict, uploaded: dict
):
    base, arch = world["base"], world["arch"]
    s1 = uploaded["sheets"][0]
    sug = client.post(f"{base}/sheets/{s1['id']}/suggestions", headers=arch).json()
    units = [c for c in sug if c["method"] == "fill" and c["label"]]
    assert len(units) == 6 and all(c["confidence"] == 0.95 for c in units)
    assert all(c["printed_area_m2"] == split_apartment_area() for c in units)
    assert all(c["floor_id"] is None for c in units)  # nothing confirmed yet
    r = client.post(
        f"{base}/sheets/{s1['id']}/boundaries", headers=arch, json={"ring": units[0]["ring"]}
    )
    assert r.status_code == 409

    # confirm the suggested floors with their regions (what the editor sends)
    body = {
        "floors": [{"floor_id": f["floor_id"], "region": f["region"]} for f in s1["floors"]],
        "version": s1["version"],
    }
    r = client.put(f"{base}/sheets/{s1['id']}/floors", headers=arch, json=body)
    assert r.status_code == 200, r.text
    sheet = r.json()
    assert sheet["assignment_status"] == "confirmed"
    assert sheet["floor_id"] == _fid(world, "A", 0)  # primary kept for older clients
    assert all(f["status"] == "confirmed" for f in sheet["floors"])
    stale = client.put(f"{base}/sheets/{s1['id']}/floors", headers=arch, json=body)
    assert stale.status_code == 409

    sug = client.post(f"{base}/sheets/{s1['id']}/suggestions", headers=arch).json()
    floor_by_label = {c["label"]: c["floor_id"] for c in sug if c["method"] == "fill"}
    assert floor_by_label["bina #1"] == _fid(world, "A", 0)
    assert floor_by_label["bina #3"] == _fid(world, "B", 0)
    assert floor_by_label["bina #6"] == _fid(world, "C", 0)
    for c in sug:
        if c["method"] == "fill" and c["label"]:
            r = client.post(
                f"{base}/sheets/{s1['id']}/boundaries",
                headers=arch,
                json={"ring": c["ring"], "label": c["label"], "source": "vector_suggest"},
            )
            assert r.status_code == 201, r.text
            assert r.json()["unit"]["floor_id"] == c["floor_id"]
            assert (
                r.json()["unit"]["building_id"]
                == world["b"][
                    {"1": "A", "2": "A", "3": "B", "4": "B", "5": "C", "6": "C"}[c["label"][-1]]
                ]["id"]
            )

    # an explicit floor must be one of the sheet's floors
    ring = [[0.4, 0.8], [0.45, 0.8], [0.45, 0.85]]
    bad = client.post(
        f"{base}/sheets/{s1['id']}/boundaries",
        headers=arch,
        json={"ring": ring, "floor_id": _fid(world, "A", 1)},
    )
    assert bad.status_code == 422
    ok = client.post(
        f"{base}/sheets/{s1['id']}/boundaries",
        headers=arch,
        json={"ring": ring, "floor_id": _fid(world, "B", 0), "unit_type": "storage"},
    )
    assert ok.status_code == 201 and ok.json()["unit"]["floor_id"] == _fid(world, "B", 0)

    # a floor that holds units drawn on this sheet cannot be dropped from it
    sheet = client.get(f"{base}/sheets/{s1['id']}", headers=arch).json()
    r = client.put(
        f"{base}/sheets/{s1['id']}/floors",
        headers=arch,
        json={"floors": [{"floor_id": _fid(world, "A", 0)}], "version": sheet["version"]},
    )
    assert r.status_code == 409 and "Remove or move" in r.json()["detail"]

    listed = client.get(f"{base}/floors/{_fid(world, 'C', 0)}/sheets", headers=arch).json()
    assert [s["id"] for s in listed] == [s1["id"]]


@needs_db
def test_several_floors_without_regions_ask_for_the_floor(
    client: TestClient, world: dict, uploaded: dict
):
    base, arch = world["base"], world["arch"]
    s2 = uploaded["sheets"][1]
    r = client.put(
        f"{base}/sheets/{s2['id']}/floors",
        headers=arch,
        json={
            "floors": [{"floor_id": _fid(world, "A", 1)}, {"floor_id": _fid(world, "B", 1)}],
            "version": s2["version"],
        },
    )
    assert r.status_code == 200, r.text
    ring = [[0.1, 0.5], [0.2, 0.5], [0.2, 0.6]]
    ask = client.post(
        f"{base}/sheets/{s2['id']}/boundaries", headers=world["arch"], json={"ring": ring}
    )
    assert ask.status_code == 409
    assert set(ask.json()["floor_ids"]) == {_fid(world, "A", 1), _fid(world, "B", 1)}


@needs_db
def test_footprints_come_from_each_buildings_units(client: TestClient, world: dict, uploaded: dict):
    base, arch = world["base"], world["arch"]
    s1 = client.get(f"{base}/sheets/{uploaded['sheets'][0]['id']}", headers=arch).json()
    r = client.patch(
        f"{base}/sheets/{s1['id']}/calibration",
        headers=arch,
        json={
            "calibration": {"p1": [60 / 842, 0.5], "p2": [300 / 842, 0.5], "distance_m": 8.4667},
            "version": s1["version"],
        },
    )
    assert r.status_code == 200, r.text
    fp = client.get(f"{base}/projects/{world['project']['id']}/footprints", headers=arch).json()
    by = {f["code"]: f for f in fp}
    for code in ("A", "B", "C"):
        assert by[code]["ring_m"] and by[code]["source_floor_level"] == 0, by[code]


@needs_db
def test_new_revision_inherits_all_floors_with_regions(
    client: TestClient, world: dict, uploaded: dict
):
    nxt = _upload(client, world, make_split_level_pdf(), document_id=uploaded["document_id"])
    s1 = nxt["sheets"][0]
    assert [(f["floor_id"], f["status"], f["source"]) for f in s1["floors"]] == [
        (_fid(world, c, 0), "suggested", "inherited") for c in ("A", "B", "C")
    ]
    assert all(f["region"] for f in s1["floors"])
    prop = nxt["result"]["diff"]
    assert prop.get("proposal"), prop


@needs_db
def test_published_plan_of_a_shared_sheet_is_cropped_to_each_floor(
    client: TestClient, world: dict, uploaded: dict
):
    from sqlalchemy import create_engine, select, text

    from unitforma.core.db import tenant_session
    from unitforma.publishing import snapshot
    from unitforma.tenants.models import Project

    eng = create_engine(os.environ["UF_TEST_DATABASE_ADMIN_URL"])
    with eng.begin() as conn:
        conn.execute(text("SELECT set_config('app.scope', 'platform', true)"))
        conn.execute(
            text(
                "UPDATE units SET publication_status = 'published' "
                "WHERE project_id = :p AND unit_type = 'apartment'"
            ),
            {"p": world["project"]["id"]},
        )
    eng.dispose()

    async def build():
        async with tenant_session(uuid.UUID(world["tenant"]["id"]), scope="tenant") as db:
            project = (
                await db.execute(
                    select(Project).where(Project.id == uuid.UUID(world["project"]["id"]))
                )
            ).scalar_one()
            pub, doc = await snapshot.build(db, project, status="preview", actor_id=None)
            await db.rollback()  # inspect only
            return doc

    doc = client.portal.call(build)
    ground = {b["code"]: next(f for f in b["floors"] if f["level"] == 0) for b in doc["buildings"]}
    assert set(ground) == {"A", "B", "C"}
    assets = {g["plan"]["asset"] for g in ground.values()}
    assert len(assets) == 3  # one crop per block, not the whole sheet three times
    for g in ground.values():
        assert g["plan"]["width"] < 2400 and len(g["units"]) == 2
        for u in g["units"]:
            xs = [p[0] for p in u["ring"]]
            ys = [p[1] for p in u["ring"]]
            assert 0.0 <= min(xs) and max(xs) <= 1.0 and 0.0 <= min(ys) and max(ys) <= 1.0
            assert max(xs) - min(xs) > 0.3  # the unit fills a good part of its crop
