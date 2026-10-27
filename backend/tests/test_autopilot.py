"""The setup solver (ADR-0025): a project created with "Set up automatically" runs from the
uploaded drawings to floors, confirmed sheets, draft and approved units, a calibrated site frame,
a placed building, a public gallery, a map position and a proposed plan type; what it cannot
decide is listed as "needs you"; a person's own work is never touched; a proposed layout shares
nothing until confirmed; the switches respect the role matrix."""

from __future__ import annotations

import io
import os
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.fake_kratos import FakeKratos, cookie
from tests.pdf_fixture import (
    SPLIT_LEVELS_STOREY,
    _rect,
    _text,
    build_pdf,
    make_plan_pdf,
    make_split_level_pdf,
)
from tests.test_phase4_publishing import _admin_sql
from unitforma.autopilot import rules
from unitforma.autopilot.passes import classify, facades, floors, geocode, layouts, placement
from unitforma.renders.gemini import _find_text

pytestmark = pytest.mark.skipif(
    not (os.environ.get("UF_TEST_DATABASE_ADMIN_URL") and os.environ.get("UF_TEST_DATABASE_URL")),
    reason="needs the PostgreSQL test database",
)

PT_M_100 = 0.0254 / 72 * 100  # metres per point at 1:100
PT_M_500 = 0.0254 / 72 * 500


# --------------------------------------------------------------------------- pure functions
def _l_shape(mirror: bool = False) -> list[list[float]]:
    ring = [[0, 0], [8, 0], [8, 3], [4, 3], [4, 7], [0, 7]]
    return [[-x, y] for x, y in ring] if mirror else ring


def test_layout_matcher_clusters_rotations_and_tells_mirrors_apart():
    a = layouts.normalise(_l_shape())
    b = layouts.normalise([[x + 20, y + 5] for x, y in _l_shape()])  # moved
    c = layouts.normalise([[-y + 3, x + 40] for x, y in _l_shape()])  # turned 90°
    m = layouts.normalise(_l_shape(mirror=True))
    assert a and b and c and m
    shapes = [
        layouts.Shape(uuid.uuid4(), "A-00-01", a[0].area, a),
        layouts.Shape(uuid.uuid4(), "A-00-02", b[0].area, b),
        layouts.Shape(uuid.uuid4(), "A-01-01", c[0].area, c),
        layouts.Shape(uuid.uuid4(), "A-01-02", m[0].area, m),
    ]
    iou, mirrored = layouts.match(shapes[0], shapes[2])
    assert iou > rules.LAYOUT_MIN_IOU and not mirrored
    iou, mirrored = layouts.match(shapes[0], shapes[3])
    assert iou > rules.LAYOUT_MIN_IOU and mirrored
    groups, mirror_of, lowest = layouts.cluster(shapes)
    assert sorted(len(g) for g in groups) == [1, 3]
    big = next(g for g in groups if len(g) == 3)
    small = next(g for g in groups if len(g) == 1)
    assert mirror_of == {small[0]: big[0]}
    assert lowest[big[0]] > rules.LAYOUT_MIN_IOU
    # a different flat is not the same plan type
    other = layouts.normalise([[0, 0], [8, 0], [8, 7], [0, 7]])
    assert other is not None
    iou, _ = layouts.match(shapes[0], layouts.Shape(uuid.uuid4(), "x", other[0].area, other))
    assert iou < rules.LAYOUT_MIN_IOU


def test_placement_finds_rotation_and_translation():
    from shapely.geometry import Polygon

    foot = Polygon([[0, 0], [21, 0], [21, 7], [21, 7], [0, 7]])
    placed = placement._placed(foot, 37.0, 120.0, 80.0)
    faces = [Polygon([[0, 0], [300, 0], [300, 200], [0, 200]]), placed]
    fit = placement.best_fit(foot, faces)
    assert fit is not None and fit["iou"] >= rules.PLACEMENT_CONFIRM_IOU
    # a rectangle fits at its angle or turned by 180°
    assert min(abs(fit["rotation_deg"] - 37.0), abs(fit["rotation_deg"] - 217.0)) <= 1.0
    again = placement._placed(foot, fit["rotation_deg"], fit["tx"], fit["ty"])
    assert again.symmetric_difference(placed).area / placed.area < 0.05


def test_facade_assignment_needs_distinct_widths_and_one_drawing_per_width():
    sides = [
        {"index": 0, "length_m": 30.0},
        {"index": 1, "length_m": 12.0},
        {"index": 2, "length_m": 30.0},
        {"index": 3, "length_m": 12.0},
    ]
    s1, s2, s3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    items = facades.assign(sides, [(s1, 1, 29.6), (s2, 2, 12.3), (s3, 3, 30.4)])
    assert items is not None
    assert {(i["side"], i["sheet_id"]) for i in items} == {(0, str(s1)), (2, str(s3)), (1, str(s2))}
    assert facades.assign(sides, [(s1, 1, 20.0)]) is None  # matches neither length
    square = [{"index": k, "length_m": 20.0} for k in range(4)]
    assert facades.assign(square, [(s1, 1, 20.0)]) is None  # sides cannot be told apart


def test_geocoder_queries_follow_the_permit_address_form_and_agree_within_a_radius():
    # the tas.ge form (D1, 2026-10-27): the city first with its word, "N" and a letter on the number
    assert geocode.address_queries({"line1": "ქალაქი თბილისი, ლეო კვაჭაძის ქუჩა, N 19გ"}) == [
        "ქალაქი თბილისი, ლეო კვაჭაძის ქუჩა, N 19გ",
        "ლეო კვაჭაძის ქუჩა 19, თბილისი",
        "ლეო კვაჭაძის ქუჩა, თბილისი",
    ]
    # a plain line has one query; nothing is repeated
    assert geocode.address_queries({"line1": "19 Chavchavadze Avenue", "city": "Tbilisi"}) == [
        "19 Chavchavadze Avenue, Tbilisi"
    ]
    assert geocode.address_queries({}) == []
    # entrances 19/4 and 19/5 of one number are one address; two streets of one name are not
    near = [{"lat": 41.7433757, "lng": 44.7223641}, {"lat": 41.7436963, "lng": 44.7227069}]
    far = [{"lat": 41.7491125, "lng": 44.7026684}, {"lat": 41.7475218, "lng": 44.7083756}]
    assert geocode.places_agree(near, 150.0) and not geocode.places_agree(far, 150.0)
    assert not geocode.places_agree([], 150.0)


def test_storeys_of_split_level_blocks_are_the_main_blocks_storeys():
    """The five blocks the markers of permit 1127975 give (2026-10-27): three real blocks at
    offsets of 1 m and two stamp columns; the owner's storey list is B1, Ground, 1, 2, 3."""

    def fl(level, name, elev, h):
        return {"level": level, "display_name": name, "elevation_m": elev, "height_m": h}

    blocks = [
        {
            "code": "A-A",
            "sheets": 6,
            "floors": [fl(0, "Ground", 0.0, 13.2), fl(1, "1", 13.2, 3.25), fl(2, "2", 16.45, 8.22)],
        },
        {
            "code": "B",
            "sheets": 5,
            "floors": [
                fl(-1, "B1", -2.55, 2.55),
                fl(0, "Ground", 0.0, 3.2),
                fl(1, "1", 3.2, 3.2),
                fl(2, "2", 6.4, 3.2),
                fl(3, "3", 9.6, 3.2),
            ],
        },
        {
            "code": "C",
            "sheets": 5,
            "floors": [
                fl(-1, "B1", -1.55, 2.55),
                fl(0, "Ground", 1.0, 3.2),
                fl(1, "1", 4.2, 3.2),
                fl(2, "2", 7.4, 3.2),
                fl(3, "3", 10.6, 3.2),
            ],
        },
        {
            "code": "D",
            "sheets": 4,
            "floors": [
                fl(0, "Ground", 2.0, 3.2),
                fl(1, "1", 5.2, 3.2),
                fl(2, "2", 8.4, 3.2),
                fl(3, "3", 11.6, 3.2),
            ],
        },
        {
            "code": "E",
            "sheets": 5,
            "floors": [fl(-1, "B1", -5.0, 5.0), fl(0, "Ground", 0.0, 3.2), fl(1, "1", 3.2, 4.1)],
        },
    ]
    out = floors.storeys_from_blocks(blocks)
    assert [(f["level"], f["display_name"], f["elevation_m"], f["height_m"]) for f in out] == [
        (-1, "B1", -2.55, 2.55),
        (0, "Ground", 0.0, 3.2),
        (1, "1", 3.2, 3.2),
        (2, "2", 6.4, 3.2),
        (3, "3", 9.6, 3.2),
    ]
    # a level only another block has is added from that block
    blocks[3]["floors"].append(fl(4, "4", 14.8, 3.2))
    assert [f["level"] for f in floors.storeys_from_blocks(blocks)] == [-1, 0, 1, 2, 3, 4]


def test_host_kind_files_a_set_with_floor_plan_pages_as_floor_plans():
    plan, other = {"kind": "floor_plan"}, {"kind": "drawing"}
    assert classify.host_kind([plan, plan] + [other] * 49) == "floor_plan"  # 2 in 51, like "4"
    assert classify.host_kind([plan, other]) == "floor_plan"  # one plan in a short set
    assert classify.host_kind([plan] + [other] * 5) is None  # one plan page in a longer set
    assert classify.host_kind([other] * 9) is None  # elevations: a person's call
    assert classify.host_kind([]) is None


def test_classifier_sends_drawings_only():
    # a real elevation sheet (permit 1127975, D2 on 2026-10-27): long text, far more line work
    assert classify.page_is_drawing(64444, 4676)
    assert classify.page_is_drawing(60, 100)  # a small plan page
    assert not classify.page_is_drawing(20, 2300)  # table rules and a paragraph
    assert not classify.page_is_drawing(300, 3000)  # an area schedule: rules, but text-heavy
    assert not classify.page_is_drawing(0, 10)  # a scan without a vector layer


def test_classifier_parses_one_word_answers_and_gemini_text_blocks():
    assert classify.parse_kind(" Floor_plan. ") == "floor_plan"
    assert classify.parse_kind("site plan") == "site_plan"
    assert classify.parse_kind("other") is None
    assert classify.parse_kind("I think this is a section") is None
    assert _find_text({"steps": [{"type": "text", "text": "elevation"}]}) == "elevation"
    echo = {"output_text": "render", "input": [{"type": "text", "text": "q"}]}
    assert _find_text(echo) == "render"
    legacy = {"candidates": [{"content": {"parts": [{"text": "schedule"}]}}]}
    assert _find_text(legacy) == "schedule"
    assert _find_text({"steps": [{"type": "image", "data": "x"}]}) is None


# --------------------------------------------------------------------------- fixtures
def _plan_pdf(filler: int = 0, scale: bool = True) -> bytes:
    """Page 1 as make_plan_pdf: apartments 1 and 2 (typed labels, 0.9). Page 2: apartment 3, a
    filled zone "#12" with its printed area (a numbered fill, 0.85: a unit since 2026-10-27) and a
    zone labelled only "7" (a bare number, 0.65): it stays a candidate and blocks the approval."""
    base = make_plan_pdf()
    sc = " scale 1:100" if scale else ""
    p1 = (
        _text(40, 560, f"GROUND FLOOR PLAN +0.00{sc}", 14)
        + _text(120, 300, "bina #1 42.7 m2")
        + _text(420, 300, "bina #2 61.0 m2")
        + "2 w 100 100 m 700 100 l S\n"
        + _rect(100, 200, 400, 400)
        + _rect(400, 200, 700, 400)
        + "100 150 m 700 150 l S\n"
        + _axis_marks(100, 600)
    )
    p2 = (
        _text(40, 560, f"FIRST FLOOR PLAN +3.20{sc}", 14)
        + _text(120, 300, "bina #3 42.7 m2")
        + _text(540, 470, "7")
        + _rect(100, 200, 400, 400)
        + _rect(400, 200, 700, 400)
        + _rect(450, 420, 650, 520)
        + "0.5 0.75 1 rg 100 420 200 100 re f\n"  # zone fill: 200 × 100 pt at 1:100 = 24.9 m²
        + _rect(100, 420, 300, 520)
        + _text(110, 470, "#12 24.9 m2")
        + _axis_marks(320, 660)
    )
    assert base  # the shared fixture still builds
    # detail pages without labels or markers: with enough of them the plans are under half the
    # set and ADR-0008's content rule leaves the document pending (the real set: 6 plans in 51)
    detail = "".join(_rect(60 + 30 * i, 100, 80 + 30 * i, 500) for i in range(24))
    return build_pdf([p1, p2] + [detail] * filler)


def _axis_marks(x_left: float, x_right: float) -> str:
    """Two small boxes labelled "4" on one page: an axis mark printed at both ends. Repeated on
    every page of the set it is not a unit label (D4) and must not be listed as "needs you"."""
    return (
        _rect(x_left, 430, x_left + 100, 490)
        + _text(x_left + 40, 455, "4")
        + _rect(x_right, 430, x_right + 100, 490)
        + _text(x_right + 40, 455, "4")
    )


def _site_pdf() -> bytes:
    """A site plan at 1:500 with the plot outline and one rectangle the size of building A's
    footprint (600 × 200 pt at 1:100 → 120 × 40 pt at 1:500)."""
    p = (
        _text(40, 560, "SITE PLAN scale 1:500", 14)
        + _rect(80, 120, 760, 540)
        + _rect(300, 250, 420, 290)
    )
    return build_pdf([p])


def _document_pdf() -> bytes:
    """Table rules and a paragraph: line work, but a page that reads like a document (a permit
    decision, an area schedule). It must never leave the host."""
    rules_ = "".join(_rect(60, 100 + j * 20, 780, 120 + j * 20) for j in range(20))
    text = "".join(
        _text(
            70, 540 - i * 12, "Applicant Giorgi Beridze personal number 01011234567 address " * 2, 8
        )
        for i in range(16)
    )
    return build_pdf([_text(40, 560, "decision", 12) + rules_ + text])


def _unknown_pdf() -> bytes:
    """Line work without labels or floor words: neither the name nor the content says the kind."""
    p = _text(40, 560, "drawing", 12) + "".join(
        _rect(60 + i * 40, 100 + j * 40, 90 + i * 40, 130 + j * 40)
        for i in range(12)
        for j in range(8)
    )
    return build_pdf([p])


def _png() -> bytes:
    from PIL import Image

    im = Image.new("RGB", (64, 48), (120, 160, 200))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def kratos() -> FakeKratos:
    return FakeKratos()


@pytest.fixture(scope="module")
def client(kratos: FakeKratos, tmp_path_factory):
    os.environ["UF_STORAGE_BACKEND"] = "local"
    os.environ["UF_STORAGE_LOCAL_ROOT"] = str(tmp_path_factory.mktemp("storage"))
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


def _upload(
    client, base, headers, project_id, kind, title, data, tenant_id, building_id=None, *, png=False
):
    from unitforma.documents.jobs import process_revision

    doc = client.post(
        f"{base}/projects/{project_id}/documents",
        headers=headers,
        json={"kind": kind, "title": title, "building_id": building_id},
    )
    assert doc.status_code == 201, doc.text
    doc = doc.json()
    ct = "image/png" if png else "application/pdf"
    up = client.post(
        f"{base}/documents/{doc['id']}/uploads",
        headers=headers,
        json={"file_name": "f.png" if png else "f.pdf", "content_type": ct, "byte_size": len(data)},
    ).json()
    put = client.put(up["upload_url"], content=data, headers={"Content-Type": ct})
    assert put.status_code == 200
    rev = client.post(f"{base}/revisions/{up['revision']['id']}/complete", headers=headers).json()
    result = client.portal.call(process_revision, uuid.UUID(tenant_id), uuid.UUID(rev["id"]))
    return doc, result


def _run(client, tenant_id: str, run_id: str) -> dict[str, Any]:
    from unitforma.autopilot.service import run_autopilot

    return client.portal.call(run_autopilot, uuid.UUID(tenant_id), uuid.UUID(run_id))


def _units(client, base, headers, project_id) -> dict[str, Any]:
    rows = client.get(f"{base}/projects/{project_id}/units", headers=headers).json()
    return {u["code"]: u for u in rows}


def _setup(client, base, headers, project_id) -> dict[str, Any]:
    r = client.get(f"{base}/projects/{project_id}/setup", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _runs(client, base, headers, project_id) -> list[dict[str, Any]]:
    return client.get(f"{base}/projects/{project_id}/setup/runs", headers=headers).json()


@pytest.fixture(scope="module")
def world(kratos: FakeKratos, client: TestClient) -> dict:
    from unitforma.identity.deps import clear_whoami_cache

    s = uuid.uuid4().hex[:6]
    kratos.add("root25", f"root25-{s}@unitforma.example.com", aal="aal2")
    assert client.get("/api/v1/admin/me", headers=cookie("root25")).status_code == 200
    _admin_sql(
        "UPDATE users SET is_platform_admin = true WHERE email = :e",
        {"e": f"root25-{s}@unitforma.example.com"},
    )
    clear_whoami_cache()
    root = cookie("root25")
    t = client.post(
        "/api/v1/platform/tenants", headers=root, json={"slug": f"auto{s}", "name": "Autopilot"}
    ).json()
    base = f"/api/v1/admin/tenants/{t['id']}"
    kratos.add("adm25", f"adm25-{s}@a.example.com")
    inv = client.post(
        f"/api/v1/platform/tenants/{t['id']}/invitations",
        headers=root,
        params={"email": f"adm25-{s}@a.example.com"},
    ).json()
    client.post(
        "/api/v1/admin/invitations/accept",
        headers=cookie("adm25"),
        json={"token": inv["accept_url"].rsplit("/", 1)[1]},
    )
    adm = cookie("adm25")
    kratos.add("pm25", f"pm25-{s}@a.example.com")
    i2 = client.post(
        f"{base}/invitations",
        headers=adm,
        json={
            "email": f"pm25-{s}@a.example.com",
            "role": "project_manager",
            "all_projects": True,
            "project_ids": [],
        },
    ).json()
    client.post(
        "/api/v1/admin/invitations/accept",
        headers=cookie("pm25"),
        json={"token": i2["accept_url"].rsplit("/", 1)[1]},
    )
    return {"base": base, "tenant": t, "adm": adm, "pm": cookie("pm25")}


# --------------------------------------------------------------------------- the intake
def test_intake_creates_the_building_and_the_switches_and_respects_the_role_matrix(client, world):
    base, adm, pm = world["base"], world["adm"], world["pm"]
    # a project manager may switch the solver on but not ask it to approve sheets
    r = client.post(
        f"{base}/projects",
        headers=pm,
        json={
            "slug": "pm-tries",
            "name": "PM tries",
            "building_code": "A",
            "setup_auto": {"enabled": True, "approve_sheets": True},
        },
    )
    assert r.status_code == 403, r.text
    r = client.post(
        f"{base}/projects",
        headers=pm,
        json={
            "slug": "pm-drafts",
            "name": "PM drafts",
            "building_code": "B",
            "setup_auto": {"enabled": True, "approve_sheets": False},
        },
    )
    assert r.status_code == 201, r.text
    p = r.json()
    buildings = client.get(f"{base}/projects/{p['id']}/buildings", headers=pm).json()
    assert [b["code"] for b in buildings if b["kind"] == "building"] == ["B"]
    setup = _setup(client, base, pm, p["id"])
    assert setup["auto"]["enabled"] is True and setup["auto"]["approve_sheets"] is False
    assert setup["auto"]["running"] is False and setup["auto"]["last_run"] is None
    # the switches: approval needs the mapping approve right
    r = client.put(
        f"{base}/projects/{p['id']}/setup/auto",
        headers=pm,
        json={"enabled": True, "approve_sheets": True},
    )
    assert r.status_code == 403
    r = client.put(
        f"{base}/projects/{p['id']}/setup/auto",
        headers=adm,
        json={"enabled": True, "approve_sheets": True},
    )
    assert r.status_code == 200 and r.json()["approve_sheets"] is True, r.text
    assert r.json()["running"] is True  # switching on queued a run
    runs = _runs(client, base, adm, p["id"])
    assert [x["status"] for x in runs] == ["queued"] and runs[0]["trigger"] == "switched_on"
    # off again; a manual run is still possible and acts as the caller
    r = client.put(
        f"{base}/projects/{p['id']}/setup/auto",
        headers=adm,
        json={"enabled": False, "approve_sheets": False},
    )
    assert r.status_code == 200 and r.json()["enabled"] is False


# --------------------------------------------------------------------------- the solver run
@pytest.fixture(scope="module")
def solved(client, world) -> dict:
    """A project the solver set up from two drawings: the plan set and the site plan."""
    base, adm, tid = world["base"], world["adm"], world["tenant"]["id"]
    p = client.post(
        f"{base}/projects",
        headers=adm,
        json={
            "slug": "solved",
            "name": "Solved",
            "address": {"line1": "Chavchavadze Ave 19", "city": "Tbilisi"},
            "building_code": "A",
            "setup_auto": {"enabled": True, "approve_sheets": True},
        },
    ).json()
    building = next(
        b
        for b in client.get(f"{base}/projects/{p['id']}/buildings", headers=adm).json()
        if b["kind"] == "building"
    )
    assert building["floors"] == []
    geocode.set_geocoder(_OnePlace())
    try:
        _doc, result = _upload(
            client, base, adm, p["id"], "floor_plan", "Plans", _plan_pdf(), tid, building["id"]
        )
        assert result["pages"] == 2
        assert result.get("autopilot_run_id"), result  # processing queued a run
        _upload(client, base, adm, p["id"], "site_plan", "Site", _site_pdf(), tid)
        _upload(client, base, adm, p["id"], "render", "View", _png(), tid, png=True)
        runs = _runs(client, base, adm, p["id"])
        queued = [r for r in runs if r["status"] == "queued"]
        assert len(queued) == 1, runs  # one waiting run per project, however many uploads
        counts = _run(client, tid, queued[0]["id"])
    finally:
        geocode.set_geocoder(None, override=False)
    return {"project": p, "building": building, "counts": counts}


class _OnePlace:
    name = "fake"

    async def search(self, query: str, country: str | None):
        assert "Chavchavadze" in query
        return [{"lat": 41.7101, "lng": 44.7672, "display_name": "19 Chavchavadze Avenue, Tbilisi"}]


def test_run_sets_floors_sheets_units_site_placement_gallery_and_map(client, world, solved):
    base, adm = world["base"], world["adm"]
    p, b = solved["project"], solved["building"]
    assert solved["counts"]["errors"] == 0, solved["counts"]
    setup = _setup(client, base, adm, p["id"])
    steps = {s["key"]: s for s in setup["steps"]}
    # floors from the two level markers; no roof marker, so 0.8
    buildings = client.get(f"{base}/projects/{p['id']}/buildings", headers=adm).json()
    a = next(x for x in buildings if x["id"] == b["id"])
    assert [(f["level"], float(f["elevation_m"])) for f in a["floors"]] == [(0, 0.0), (1, 3.2)]
    assert steps["floors"]["status"] == "done" and "made for you" in steps["floors"]["auto_detail"]
    # units: 1 and 2 approved (every label on page 1 covered); 3 and the numbered fill #12 drafts
    # (page 2 keeps the bare "7")
    units = _units(client, base, adm, p["id"])
    assert sorted(units) == ["A-00-01", "A-00-02", "A-01-01", "A-01-02"]
    assert units["A-00-01"]["lifecycle_status"] == "active"
    assert units["A-00-02"]["lifecycle_status"] == "active"
    assert units["A-01-01"]["lifecycle_status"] == "draft"
    assert units["A-01-02"]["lifecycle_status"] == "draft"  # the numbered fill "#12"
    assert all(bd["source"] == "autopilot" for u in units.values() for bd in u["boundaries"])
    assert all(bd["polygon_m"] for u in units.values() for bd in u["boundaries"])  # calibrated
    decisions = setup["decisions"]
    kinds = {(d["step"], d["kind"]) for d in decisions}
    assert ("mapping", "accepted") in kinds and ("calibration", "accepted") in kinds
    left = [d for d in decisions if d["needs_you"] and d["step"] == "mapping"]
    assert len(left) == 1 and "7 (0.65)" in left[0]["detail"], left
    assert "printed twice" not in left[0]["detail"]  # the axis mark "4" of every page is not listed
    # needs-you items come first, then by confidence
    assert decisions[0]["needs_you"] is True
    assert "need" in steps["mapping"]["auto_detail"]
    # the only site plan is the frame, calibrated from 1:500; the building sits on its outline
    project = client.get(f"{base}/projects/{p['id']}", headers=adm).json()
    assert project["site_frame"].get("sheet_id")
    site_sheet = client.get(
        f"{base}/sheets/{project['site_frame']['sheet_id']}", headers=adm
    ).json()
    assert site_sheet["calibration_status"] == "calibrated"
    assert site_sheet["calibration"]["source"] == "printed_scale"
    assert a["placement_status"] == "confirmed", [d for d in decisions if d["step"] == "placement"]
    expected_w = 120 * PT_M_500
    assert abs(a["site_transform"]["rotation_deg"] % 180.0) < 1.5 or (
        abs(a["site_transform"]["rotation_deg"] % 180.0 - 180.0) < 1.5
    )
    assert abs(a["site_transform"]["tx"] - 360 * PT_M_500) < expected_w  # near the drawn centre
    assert steps["site_plan"]["status"] == "done" and steps["placement"]["status"] == "done"
    # the render document is public; the address is on the map
    docs = client.get(f"{base}/projects/{p['id']}/documents", headers=adm).json()
    view = next(d for d in docs if d["title"] == "View")
    assert view["visibility"] == "public" and steps["gallery"]["status"] == "done"
    assert project["address"]["lat"] == 41.7101
    assert project["address"]["geocoded"]["provider"] == "fake"
    assert steps["location"]["status"] == "done"
    assert setup["auto"]["last_run"]["status"] == "done"
    assert setup["auto"]["last_run"]["accepted"] >= 8


def test_proposed_layout_shares_nothing_until_confirmed(client, world, solved):
    base, adm = world["base"], world["adm"]
    p = solved["project"]
    lays = client.get(f"{base}/projects/{p['id']}/layouts", headers=adm).json()
    assert len(lays) == 1, lays
    lay = lays[0]
    assert lay["status"] == "proposed" and lay["source"] == "autopilot" and lay["code"] == "L1"
    assert sorted(u["code"] for u in lay["units"]) == ["A-00-01", "A-00-02", "A-01-01"]
    assert lay["match"]["members"] == 3 and lay["match"]["iou_min"] >= rules.LAYOUT_MIN_IOU
    # no media, no renders, no code on the inventory row, the rules refuse the code
    r = client.post(
        f"{base}/layouts/{lay['id']}/media",
        headers=adm,
        json={"file_name": "a.png", "content_type": "image/png", "byte_size": 8, "kind": "photo"},
    )
    assert r.status_code == 409 and r.json()["type"].endswith("layout-proposed"), r.text
    r = client.post(f"{base}/layouts/{lay['id']}/renders", headers=adm, json={})
    assert r.status_code == 409, r.text
    units = _units(client, base, adm, p["id"])
    row = client.get(f"{base}/units/{units['A-00-01']['id']}/sales", headers=adm).json()
    assert row["layout"] is None and row["layout_id"] == lay["id"]
    r = client.patch(
        f"{base}/units/{units['A-01-01']['id']}/sales",
        headers=adm,
        json={"layout": "L1", "version": 0},
    )
    assert r.status_code == 422, r.text
    # confirm: the code reaches the row and the mirror attribute; media are allowed
    r = client.post(f"{base}/layouts/{lay['id']}/confirm", headers=adm)
    assert r.status_code == 200 and r.json()["status"] == "confirmed", r.text
    row = client.get(f"{base}/units/{units['A-00-01']['id']}/sales", headers=adm).json()
    assert row["layout"] == "L1"
    r = client.post(
        f"{base}/layouts/{lay['id']}/media",
        headers=adm,
        json={"file_name": "a.png", "content_type": "image/png", "byte_size": 8, "kind": "photo"},
    )
    assert r.status_code == 201, r.text
    # a second run adds nothing: every unit is linked, every sheet decided
    r = client.post(f"{base}/projects/{p['id']}/setup/run", headers=adm)
    assert r.status_code == 202, r.text
    counts = _run(client, world["tenant"]["id"], r.json()["id"])
    assert counts["accepted"] == 0, counts


def test_split_level_blocks_stay_a_proposal(client, world):
    """Blocks drawn side by side (ADR-0013 Decision 4) are the owner's call since 2026-10-27: on
    permit 1127975 the markers showed five blocks where the owner kept one building. Steps of a
    whole storey give the one building its merged storey list; smaller steps set nothing."""
    base, adm, tid = world["base"], world["adm"], world["tenant"]["id"]
    outcomes = {}
    for slug, levels in (("steps-storey", SPLIT_LEVELS_STOREY), ("steps-metre", None)):
        p = client.post(
            f"{base}/projects",
            headers=adm,
            json={
                "slug": slug,
                "name": slug,
                "building_code": "A",
                "setup_auto": {"enabled": True, "approve_sheets": False},
            },
        ).json()
        b = next(
            x
            for x in client.get(f"{base}/projects/{p['id']}/buildings", headers=adm).json()
            if x["kind"] == "building"
        )
        _doc, result = _upload(
            client,
            base,
            adm,
            p["id"],
            "floor_plan",
            "Blocks",
            make_split_level_pdf(levels),
            tid,
            b["id"],
        )
        _run(client, tid, result["autopilot_run_id"])
        buildings = client.get(f"{base}/projects/{p['id']}/buildings", headers=adm).json()
        codes = sorted(x["code"] for x in buildings if x["kind"] == "building")
        assert codes == ["A"], codes  # never split by the solver
        floors = next(x for x in buildings if x["id"] == b["id"])["floors"]
        blocks = [
            d
            for d in _setup(client, base, adm, p["id"])["decisions"]
            if d["step"] == "floors" and "blocks drawn side by side" in d["title"]
        ]
        assert len(blocks) == 1 and blocks[0]["needs_you"], blocks
        outcomes[slug] = ([f["level"] for f in floors], blocks[0]["detail"])
    assert outcomes["steps-storey"][0] == [0, 1, 2, 3]
    assert "Kept as one building" in outcomes["steps-storey"][1]
    # steps of a metre: the storeys are the blocks' own (Ground, 1), not one per step
    assert outcomes["steps-metre"][0] == [0, 1]
    assert "Kept as one building" in outcomes["steps-metre"][1]


def test_an_unclassified_plan_set_is_filed_on_the_host_and_the_rest_is_listed(client, world):
    """Files named 1 to 4 (2026-10-27): nothing classified them and the solver stopped. A set with
    floor-plan pages is filed as floor plans on the host; what stays pending is one "needs you"."""
    base, adm, tid = world["base"], world["adm"], world["tenant"]["id"]
    p = client.post(
        f"{base}/projects",
        headers=adm,
        json={
            "slug": "named-1-to-4",
            "name": "Named",
            "building_code": "A",
            "setup_auto": {"enabled": True, "approve_sheets": False},
        },
    ).json()
    b = next(
        x
        for x in client.get(f"{base}/projects/{p['id']}/buildings", headers=adm).json()
        if x["kind"] == "building"
    )
    plan, result = _upload(
        client, base, adm, p["id"], "unclassified", "4", _plan_pdf(filler=3), tid, b["id"]
    )
    other, _ = _upload(client, base, adm, p["id"], "unclassified", "2", _document_pdf(), tid)
    assert plan["kind"] == "unclassified" and plan["kind_source"] == "pending"
    runs = _runs(client, base, adm, p["id"])
    _run(client, tid, next(r for r in runs if r["status"] == "queued")["id"])
    docs = {
        d["title"]: d
        for d in client.get(f"{base}/projects/{p['id']}/documents", headers=adm).json()
    }
    assert docs["4"]["kind"] == "floor_plan" and docs["4"]["kind_source"] == "content"
    assert docs["2"]["kind_source"] == "pending"
    decisions = _setup(client, base, adm, p["id"])["decisions"]
    kinds = [d for d in decisions if d["step"] == "classify"]
    assert any(d["kind"] == "accepted" and d["title"] == "4: floor_plan" for d in kinds), kinds
    left = [d for d in kinds if d["needs_you"]]
    assert len(left) == 1 and "2" in left[0]["detail"] and "UF_AI_CLASSIFY" in left[0]["detail"]
    # and the plan set went on to floors and units in the same run
    floors_ = next(
        x
        for x in client.get(f"{base}/projects/{p['id']}/buildings", headers=adm).json()
        if x["id"] == b["id"]
    )["floors"]
    assert [f["level"] for f in floors_] == [0, 1]
    assert len(_units(client, base, adm, p["id"])) >= 3


def _intake(client, base, adm, slug: str, setup_auto: dict) -> tuple[dict, dict]:
    p = client.post(
        f"{base}/projects",
        headers=adm,
        json={"slug": slug, "name": slug, "building_code": "A", "setup_auto": setup_auto},
    ).json()
    b = next(
        x
        for x in client.get(f"{base}/projects/{p['id']}/buildings", headers=adm).json()
        if x["kind"] == "building"
    )
    return p, b


def test_publish_with_defaults_makes_the_first_version_live(client, world):
    """ADR-0029 Decision 1: one action approves the solver's drafts, confirms its plan types,
    writes a first description, marks the units and publishes; the checklist's publish step is
    done and every needs-you line says what to do (Decision 5)."""
    base, adm, pm, tid = world["base"], world["adm"], world["pm"], world["tenant"]["id"]
    p, b = _intake(client, base, adm, "defaults-1", {"enabled": True, "approve_sheets": False})
    _upload(client, base, adm, p["id"], "floor_plan", "Plans", _plan_pdf(), tid, b["id"])
    _upload(client, base, adm, p["id"], "site_plan", "Site", _site_pdf(), tid)
    _upload(client, base, adm, p["id"], "render", "View", _png(), tid, png=True)
    queued = next(r for r in _runs(client, base, adm, p["id"]) if r["status"] == "queued")
    _run(client, tid, queued["id"])
    units = _units(client, base, adm, p["id"])
    assert all(u["lifecycle_status"] == "draft" for u in units.values())  # approval was off
    # a project manager without the publish right is refused
    assert (
        client.post(f"{base}/projects/{p['id']}/setup/publish-defaults", headers=pm).status_code
        == 403
    )
    r = client.post(f"{base}/projects/{p['id']}/setup/publish-defaults", headers=adm)
    assert r.status_code == 202, r.text
    counts = _run(client, tid, r.json()["id"])
    assert counts["errors"] == 0, counts
    units = _units(client, base, adm, p["id"])
    assert len(units) == 4 and all(u["lifecycle_status"] == "active" for u in units.values())
    assert all(u["publication_status"] == "published" for u in units.values())
    lays = client.get(f"{base}/projects/{p['id']}/layouts", headers=adm).json()
    assert lays and all(lay["status"] == "confirmed" for lay in lays)
    project = client.get(f"{base}/projects/{p['id']}", headers=adm).json()
    assert (
        project["description"].startswith("defaults-1")
        and "1 building(s): A (2 floors)" in (project["description"])
    )
    pubs = client.get(f"{base}/projects/{p['id']}/publications", headers=adm).json()
    assert [x["version_no"] for x in pubs if x["status"] == "published"] == [1]
    setup = _setup(client, base, adm, p["id"])
    steps = {s["key"]: s for s in setup["steps"]}
    assert steps["publish"]["status"] == "done" and "v1" in steps["publish"]["detail"]
    decisions = setup["decisions"]
    assert any(d["step"] == "defaults" and d["title"] == "Published v1" for d in decisions)
    for d in decisions:
        assert (d["todo"] is not None) == bool(d["needs_you"]), d
    described = next(d for d in decisions if "Description written" in d["title"])
    assert described["needs_you"] and "replace" in described["detail"]
    # pressing it again publishes a new version
    r = client.post(f"{base}/projects/{p['id']}/setup/publish-defaults", headers=adm)
    _run(client, tid, r.json()["id"])
    pubs = client.get(f"{base}/projects/{p['id']}/publications", headers=adm).json()
    assert [x["version_no"] for x in pubs if x["status"] == "published"] == [2]


def test_publish_with_defaults_goes_live_even_without_units(client, world):
    """A set without apartment labels outlines nothing (the Jan Homeri set, 2026-10-27): the
    portal still goes live with the project, and the run says how the units come."""
    base, adm, tid = world["base"], world["adm"], world["tenant"]["id"]
    p, _b = _intake(client, base, adm, "defaults-empty", {"enabled": True})
    _upload(client, base, adm, p["id"], "render", "View", _png(), tid, png=True)
    queued = next(r for r in _runs(client, base, adm, p["id"]) if r["status"] == "queued")
    _run(client, tid, queued["id"])
    r = client.post(f"{base}/projects/{p['id']}/setup/publish-defaults", headers=adm)
    assert r.status_code == 202, r.text
    counts = _run(client, tid, r.json()["id"])
    assert counts["errors"] == 0, counts
    pubs = client.get(f"{base}/projects/{p['id']}/publications", headers=adm).json()
    assert [x["version_no"] for x in pubs] == [1]
    setup = _setup(client, base, adm, p["id"])
    steps = {s["key"]: s for s in setup["steps"]}
    assert steps["publish"]["status"] == "done"
    assert steps["mapping"]["detail"].startswith("No units yet")
    titles = [d["title"] for d in setup["decisions"]]
    assert "Published v1 without units" in titles
    left = next(d for d in setup["decisions"] if d["title"] == "No units in the portal yet")
    assert left["needs_you"] and left["todo"].startswith("No units yet")
    # a person's own publish keeps the gate
    r = client.post(
        f"{base}/projects/{p['id']}/publications", headers=adm, json={"mode": "publish"}
    )
    assert r.status_code == 422, r.text


def test_the_intake_switch_publishes_the_first_version_once(client, world):
    """ADR-0029 Decision 2: with the intake switch on, the first settled run ends live; later runs
    leave publishing to the person."""
    base, adm, tid = world["base"], world["adm"], world["tenant"]["id"]
    p, b = _intake(
        client,
        base,
        adm,
        "defaults-2",
        {"enabled": True, "approve_sheets": False, "publish_defaults": True},
    )
    setup = _setup(client, base, adm, p["id"])
    assert setup["auto"]["publish_defaults"] is True
    _doc, result = _upload(
        client, base, adm, p["id"], "floor_plan", "Plans", _plan_pdf(), tid, b["id"]
    )
    counts = _run(client, tid, result["autopilot_run_id"])
    assert counts["errors"] == 0, counts
    pubs = client.get(f"{base}/projects/{p['id']}/publications", headers=adm).json()
    assert [x["version_no"] for x in pubs] == [1]
    units = _units(client, base, adm, p["id"])
    assert units and all(u["publication_status"] == "published" for u in units.values())
    # a second run: no second version
    r = client.post(f"{base}/projects/{p['id']}/setup/run", headers=adm)
    _run(client, tid, r.json()["id"])
    pubs = client.get(f"{base}/projects/{p['id']}/publications", headers=adm).json()
    assert [x["version_no"] for x in pubs] == [1]
    # the switch needs the publish right
    assert (
        client.put(
            f"{base}/projects/{p['id']}/setup/auto",
            headers=world["pm"],
            json={"enabled": True, "approve_sheets": False, "publish_defaults": True},
        ).status_code
        == 403
    )


def test_a_persons_calibration_serves_the_sibling_pages(client, world):
    """ADR-0029 Decision 3: a set without a printed scale (a legacy-font title block) needs two
    clicks on one page; the solver gives the same calibration to the pages of the same size."""
    base, adm, tid = world["base"], world["adm"], world["tenant"]["id"]
    p, b = _intake(client, base, adm, "siblings", {"enabled": True, "approve_sheets": False})
    doc, result = _upload(
        client, base, adm, p["id"], "floor_plan", "Plans", _plan_pdf(scale=False), tid, b["id"]
    )
    _run(client, tid, result["autopilot_run_id"])
    rev = next(
        d["current_revision_id"]
        for d in client.get(f"{base}/projects/{p['id']}/documents", headers=adm).json()
        if d["id"] == doc["id"]
    )
    sheets = client.get(f"{base}/revisions/{rev}/sheets", headers=adm).json()
    assert [s["calibration_status"] for s in sheets] == ["none", "none"]  # nothing printed
    first = sheets[0]
    # the person: the 600 pt dimension line of page 1 is 21.17 m at 1:100
    r = client.patch(
        f"{base}/sheets/{first['id']}/calibration",
        headers=adm,
        json={
            "version": first["version"],
            "calibration": {"p1": [100 / 842, 0.5], "p2": [700 / 842, 0.5], "distance_m": 21.1667},
        },
    )
    assert r.status_code == 200, r.text
    r = client.post(f"{base}/projects/{p['id']}/setup/run", headers=adm)
    _run(client, tid, r.json()["id"])
    sheets = {
        s["page_no"]: s for s in client.get(f"{base}/revisions/{rev}/sheets", headers=adm).json()
    }
    assert sheets[2]["calibration_status"] == "calibrated"
    assert sheets[2]["calibration"]["source"] == "sibling"
    assert sheets[2]["calibration"]["from_sheet_id"] == first["id"]
    assert abs(sheets[2]["calibration"]["m_per_px"] - sheets[1]["calibration"]["m_per_px"]) < 1e-9
    assert "source" not in sheets[1]["calibration"]  # the person's stays the person's
    decisions = _setup(client, base, adm, p["id"])["decisions"]
    assert any(
        d["step"] == "calibration" and "calibrated like page 1" in d["title"] for d in decisions
    )


def test_a_persons_work_is_never_touched_and_the_guard_waits(client, world):
    base, adm, tid = world["base"], world["adm"], world["tenant"]["id"]
    p = client.post(
        f"{base}/projects",
        headers=adm,
        json={
            "slug": "manual-first",
            "name": "Manual first",
            "building_code": "A",
            "setup_auto": {"enabled": True, "approve_sheets": True},
        },
    ).json()
    b = next(
        x
        for x in client.get(f"{base}/projects/{p['id']}/buildings", headers=adm).json()
        if x["kind"] == "building"
    )
    # the person sets one floor by hand before the drawings arrive
    r = client.put(
        f"{base}/buildings/{b['id']}/floors",
        headers=adm,
        json={"floors": [{"level": 5, "display_name": "Five", "height_m": "3.0"}]},
    )
    assert r.status_code == 200
    _doc, result = _upload(
        client, base, adm, p["id"], "floor_plan", "Plans", _plan_pdf(), tid, b["id"]
    )
    run_id = result["autopilot_run_id"]
    # a second document still processing makes the run wait
    doc = client.post(
        f"{base}/projects/{p['id']}/documents",
        headers=adm,
        json={"kind": "floor_plan", "title": "Late", "building_id": b["id"]},
    ).json()
    data = _plan_pdf()
    up = client.post(
        f"{base}/documents/{doc['id']}/uploads",
        headers=adm,
        json={"file_name": "late.pdf", "content_type": "application/pdf", "byte_size": len(data)},
    ).json()
    client.put(up["upload_url"], content=data, headers={"Content-Type": "application/pdf"})
    client.post(f"{base}/revisions/{up['revision']['id']}/complete", headers=adm)
    counts = _run(client, tid, run_id)
    assert counts == {"waiting": 1}
    runs = _runs(client, base, adm, p["id"])
    assert runs[0]["status"] == "waiting"
    # processed: the run that follows leaves the person's floor alone
    from unitforma.documents.jobs import process_revision

    result = client.portal.call(process_revision, uuid.UUID(tid), uuid.UUID(up["revision"]["id"]))
    counts = _run(client, tid, result["autopilot_run_id"])
    floors = next(
        x
        for x in client.get(f"{base}/projects/{p['id']}/buildings", headers=adm).json()
        if x["id"] == b["id"]
    )["floors"]
    assert [f["level"] for f in floors] == [5]
    setup = _setup(client, base, adm, p["id"])
    assert all(d["step"] != "floors" or d["kind"] != "accepted" for d in setup["decisions"])
    # no sheet matched the floor the person made, so nothing was outlined either
    assert client.get(f"{base}/projects/{p['id']}/units", headers=adm).json() == []


def test_vision_classifier_names_a_pending_kind_from_a_drawing_page(client, world, monkeypatch):
    from unitforma.core.settings import get_settings

    base, adm, tid = world["base"], world["adm"], world["tenant"]["id"]
    p = client.post(
        f"{base}/projects",
        headers=adm,
        json={"slug": "classify", "name": "Classify", "setup_auto": {"enabled": True}},
    ).json()
    _doc, result = _upload(
        client, base, adm, p["id"], "unclassified", "scan 0042", _unknown_pdf(), tid
    )
    docs = client.get(f"{base}/projects/{p['id']}/documents", headers=adm).json()
    assert docs[0]["kind"] == "unclassified" and docs[0]["kind_source"] == "pending"
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_classify", True)
    monkeypatch.setattr(settings, "ai_image_provider", "gemini")

    class _Stub:
        name = "stub"
        model = "stub"
        calls: list[str] = []

        async def describe(self, image: bytes, mime: str, prompt: str) -> str:
            self.calls.append(mime)
            return "Floor_plan"

    stub = _Stub()
    monkeypatch.setattr(classify, "get_provider", lambda: stub)
    counts = _run(client, tid, result["autopilot_run_id"])
    assert counts["errors"] == 0
    docs = client.get(f"{base}/projects/{p['id']}/documents", headers=adm).json()
    assert docs[0]["kind"] == "floor_plan" and docs[0]["kind_source"] == "ai"
    assert stub.calls == ["image/jpeg"]
    # a person's kind is final; the cap stops further calls
    monkeypatch.setattr(settings, "ai_classify_daily_limit", 1)
    _doc2, result2 = _upload(
        client, base, adm, p["id"], "unclassified", "scan 0043", _unknown_pdf(), tid
    )
    _run(client, tid, result2["autopilot_run_id"])
    setup = _setup(client, base, adm, p["id"])
    assert any("cap" in d["title"] for d in setup["decisions"] if d["step"] == "classify")
    assert stub.calls == ["image/jpeg"]


def test_what_a_person_undoes_stays_undone(client, world, solved):
    """The solver's memory (ADR-0025 Decision 4): a deleted proposed layout, a removed solver
    unit and a render set back to internal are not redone by the next run."""
    base, adm, tid = world["base"], world["adm"], world["tenant"]["id"]
    p = solved["project"]
    lays = client.get(f"{base}/projects/{p['id']}/layouts", headers=adm).json()
    for lay in lays:
        r = client.delete(f"{base}/layouts/{lay['id']}?unlink_units=true", headers=adm)
        assert r.status_code == 204, r.text
    units = _units(client, base, adm, p["id"])
    u = units["A-01-01"]
    r = client.post(
        f"{base}/units/{u['id']}/remove",
        headers=adm,
        json={"version": u["version"], "note": "not a flat"},
    )
    assert r.status_code == 200, r.text
    docs = client.get(f"{base}/projects/{p['id']}/documents", headers=adm).json()
    view = next(d for d in docs if d["title"] == "View")
    r = client.patch(f"{base}/documents/{view['id']}", headers=adm, json={"visibility": "internal"})
    assert r.status_code == 200, r.text

    r = client.post(f"{base}/projects/{p['id']}/setup/run", headers=adm)
    assert r.status_code == 202, r.text
    counts = _run(client, tid, r.json()["id"])
    assert counts["accepted"] == 0, counts
    assert client.get(f"{base}/projects/{p['id']}/layouts", headers=adm).json() == []
    assert "A-01-01" not in _units(client, base, adm, p["id"])
    docs = client.get(f"{base}/projects/{p['id']}/documents", headers=adm).json()
    assert next(d for d in docs if d["title"] == "View")["visibility"] == "internal"


def test_a_page_that_reads_like_a_document_never_reaches_the_classifier(client, world, monkeypatch):
    from unitforma.core.settings import get_settings

    base, adm, tid = world["base"], world["adm"], world["tenant"]["id"]
    p = client.post(
        f"{base}/projects",
        headers=adm,
        json={"slug": "classify-text", "name": "Classify text", "setup_auto": {"enabled": True}},
    ).json()
    _doc, result = _upload(
        client, base, adm, p["id"], "unclassified", "file 0099", _document_pdf(), tid
    )
    docs = client.get(f"{base}/projects/{p['id']}/documents", headers=adm).json()
    assert docs[0]["kind_source"] == "pending"
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_classify", True)
    monkeypatch.setattr(settings, "ai_image_provider", "gemini")
    calls: list[str] = []

    class _Stub:
        name = "stub"
        model = "stub"

        async def describe(self, image: bytes, mime: str, prompt: str) -> str:
            calls.append(mime)
            return "schedule"

    monkeypatch.setattr(classify, "get_provider", lambda: _Stub())
    _run(client, tid, result["autopilot_run_id"])
    assert calls == []
    docs = client.get(f"{base}/projects/{p['id']}/documents", headers=adm).json()
    assert docs[0]["kind"] == "unclassified" and docs[0]["kind_source"] == "pending"
