"""Drawing text and sheet sets (plan §13.2), from the first pilot drawing bundle:

4. Georgian lettered in legacy CAD fonts (Latin codes) is decoded by font;
5. unit labels stay on one line (a legend line is not a unit) and "№" wins over stray digits;
6. the area printed with a label becomes the unit's documented area, at creation, on a
   revision-diff accept and on demand for units already drawn;
7. parking stalls (code + P mark, or the sheet's code family) and numbered rooms are units
   too, numbered rooms below ground suggested as storage;
8. reprinted plans are detected and pages can be excluded from mapping, singly or by range.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.fake_kratos import cookie
from tests.pdf_fixture import (
    BUNDLE_APT,
    BUNDLE_STALL,
    BUNDLE_STORE,
    bundle_area,
    make_bundle_pdf,
)
from tests.test_split_level_sheets import _upload
from unitforma.documents import labels
from unitforma.documents.jobs import duplicate_pages
from unitforma.documents.processing import hints_from_text

needs_db = pytest.mark.skipif(
    not (os.environ.get("UF_TEST_DATABASE_ADMIN_URL") and os.environ.get("UF_TEST_DATABASE_URL")),
    reason="needs the PostgreSQL test database",
)


# --- pure ----------------------------------------------------------------------------------
def test_legacy_georgian_fonts_decode_by_font_name():
    assert labels.is_legacy_font("AcadNusx") and labels.is_legacy_font("ABCDEF+AcadMtavr")
    assert labels.is_legacy_font("AvazaMtavruli") and labels.is_legacy_font("Sanet")
    assert not labels.is_legacy_font("FBBJLJ+Sylfaen") and not labels.is_legacy_font("ArialMT")
    assert (
        labels.decode_legacy("mravalbiniani sacxovrebeli saxli")
        == "მრავალბინიანი საცხოვრებელი სახლი"
    )
    assert labels.decode_legacy("q. Tbilisi, bina #12") == "ქ. თბილისი, ბინა №12"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ბინა №22\n79.3 m2", [("apartment", "22")]),
        ("bina 5 #3 40.1 m2", [("apartment", "3")]),  # a callout digit between word and №
        ("5. საცხოვრებელი ბინა\n6. აივანი", []),  # a legend line is not apartment 6
        ("Apt 12B", [("apartment", "12B")]),
        ("სათავსო №4\n6.0 მ²", [("storage", "4")]),
        ("Office 2", [("commercial", "2")]),
        ("A9/10-1\nP\n12.5 m2", [("parking", "A9/10-1")]),
        ("A9/10-1\n12.5 m2", []),  # a code alone is not a stall
        ("№30\n12.5 m2", [(None, "30")]),
        ("6.90 2.50 0.40", []),  # dimensions
    ],
)
def test_unit_labels(text, expected):
    assert [(lb.kind, lb.key) for lb in labels.find_labels(text)] == expected


def test_parking_family_covers_a_stall_whose_p_mark_is_hidden():
    sheet = "A9/10-1 P 12.5 m2\nA9/10-2 P 12.5 m2\nA9/10-3 P 12.5 m2"
    fam = labels.parking_families(sheet)
    assert fam == {"A9/10-"}
    hidden = "A9/10-4\nP6\n12.5 m2"  # the P fused with a dimension crossing the stall
    assert labels.find_labels(hidden) == []
    assert [(lb.kind, lb.key) for lb in labels.find_labels(hidden, fam)] == [("parking", "A9/10-4")]


def test_hints_split_labels_by_kind():
    h = hints_from_text(
        "ბინა №2\nბინა №10\nA1-1 P\nA1-2 P\n№7 6.0 m2\n5. საცხოვრებელი ბინა\n6. აივანი",
        {"lines": 900},
    )
    assert h["apartment_labels"] == ["2", "10"]
    assert h["unit_labels"] == {
        "apartment": ["2", "10"],
        "numbered": ["7"],
        "parking": ["A1-1", "A1-2"],
    }
    assert h["kind"] == "floor_plan"


def test_reprints_point_at_the_first_page():
    def hp(**kinds):
        return {"unit_labels": kinds}

    hints = {
        1: hp(apartment=["1", "2", "3", "4"]),
        2: hp(apartment=["5", "6", "7", "8"]),
        3: hp(apartment=["1", "2", "3", "4"], parking=["A1-1"]),
        4: hp(apartment=["1", "2"]),  # too few labels to judge
        5: hp(apartment=["5", "6", "7"]),  # a reprint that lost a label drawn as outlines
        6: hp(numbered=["19", "20", "21"]),  # title-block numbers are not unit labels
    }
    assert duplicate_pages(hints) == {3: 1, 5: 2}


def test_floors_numbered_alike_are_not_reprints():
    from unitforma.documents.levels import Marker

    def m(v):
        return [Marker(f"{v:+.2f}", v, 0.5, 0.4)]

    same = {"unit_labels": {"apartment": ["1", "2", "3", "4"]}}
    hints = {1: same, 2: same, 3: same}
    markers = {1: m(3.2), 2: m(6.4), 3: m(3.2)}  # floors 1 and 2, then a reprint of floor 1
    assert duplicate_pages(hints, markers) == {3: 1}


# --- API -----------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def world(client: TestClient, kratos) -> dict:
    s = uuid.uuid4().hex[:6]
    kratos.add("rootdt", f"rootdt-{s}@unitforma.example.com", aal="aal2")
    assert client.get("/api/v1/admin/me", headers=cookie("rootdt")).status_code == 200
    from sqlalchemy import create_engine, text

    eng = create_engine(os.environ["UF_TEST_DATABASE_ADMIN_URL"])
    with eng.begin() as conn:
        conn.execute(
            text("UPDATE users SET is_platform_admin = true WHERE email = :e"),
            {"e": f"rootdt-{s}@unitforma.example.com"},
        )
    eng.dispose()
    from unitforma.identity.deps import clear_whoami_cache

    clear_whoami_cache()
    root = cookie("rootdt")
    kratos.add("archdt", f"archdt-{s}@a.example.com")
    t = client.post(
        "/api/v1/platform/tenants", headers=root, json={"slug": f"bnd{s}", "name": "Bundle Co"}
    ).json()
    base = f"/api/v1/admin/tenants/{t['id']}"
    inv = client.post(
        f"/api/v1/platform/tenants/{t['id']}/invitations",
        headers=root,
        params={"email": f"archdt-{s}@a.example.com"},
    ).json()
    client.post(
        "/api/v1/admin/invitations/accept",
        headers=cookie("archdt"),
        json={"token": inv["accept_url"].rsplit("/", 1)[1]},
    )
    arch = cookie("archdt")
    p = client.post(
        f"{base}/projects", headers=arch, json={"slug": "bundle", "name": "Bundle"}
    ).json()
    b = client.post(
        f"{base}/projects/{p['id']}/buildings", headers=arch, json={"code": "A", "name": "A"}
    ).json()
    fl = client.put(
        f"{base}/buildings/{b['id']}/floors",
        headers=arch,
        json={
            "floors": [
                {"level": -1, "display_name": "Basement", "elevation_m": -2.55},
                {"level": 0, "display_name": "Ground", "elevation_m": 0.0},
            ]
        },
    ).json()
    return {
        "base": base,
        "tenant": t,
        "project": p,
        "arch": arch,
        "b": {"A": b},
        "f": {f["level"]: f for f in fl},
    }


@pytest.fixture(scope="module")
def bundle(client: TestClient, world: dict) -> dict:
    return _upload(client, world, make_bundle_pdf())


@needs_db
def test_processing_decodes_flags_reprints_and_suggests_floors(world: dict, bundle: dict):
    p1, p2, p3, p4 = bundle["sheets"]
    assert p1["hints"]["legacy_font_chars"] > 0
    assert p1["hints"]["unit_labels"] == {
        "apartment": ["1", "2", "3"],
        "parking": ["A1-1", "A1-2", "A1-3"],
    }
    assert [f["floor_id"] for f in p1["floors"]] == [world["f"][0]["id"]]
    # the fire-safety reprint: same units, flagged, no floor guess
    assert p2["hints"]["duplicate_of"] == 1 and p2["floors"] == []
    # code-compliance text mentions floors but has no drawing: no floor guess
    assert p3["hints"]["kind"] == "text_sheet" and p3["floors"] == []
    assert [f["floor_id"] for f in p4["floors"]] == [world["f"][-1]["id"]]
    assert p4["hints"]["unit_labels"] == {"numbered": ["1", "2", "3"]}


def _confirm(api, world, sheet):
    r = api.put(
        f"{world['base']}/sheets/{sheet['id']}/floors",
        headers=world["arch"],
        json={
            "floors": [{"floor_id": f["floor_id"], "region": f["region"]} for f in sheet["floors"]],
            "version": sheet["version"],
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


@needs_db
def test_suggestions_are_typed_and_printed_areas_become_documented_areas(
    client: TestClient,
    world: dict,
    bundle: dict,
):
    base, arch = world["base"], world["arch"]
    p1 = _confirm(client, world, bundle["sheets"][0])
    sug = client.post(f"{base}/sheets/{p1['id']}/suggestions", headers=arch).json()
    sure = [c for c in sug if c["confidence"] >= 0.85]
    assert sorted((c["label"], c["unit_type"]) for c in sure) == [
        ("A1-1", "parking"),
        ("A1-2", "parking"),
        ("A1-3", "parking"),
        ("ბინა №1", "apartment"),
        ("ბინა №2", "apartment"),
        ("ბინა №3", "apartment"),
    ]
    assert not any(c["label"] and c["label"].endswith("6") for c in sug if c["unit_type"])
    created = {}
    for c in sure:
        r = client.post(
            f"{base}/sheets/{p1['id']}/boundaries",
            headers=arch,
            json={
                "ring": c["ring"],
                "label": c["label"],
                "unit_type": c["unit_type"],
                "source": "vector_suggest",
                "printed_area_m2": c["printed_area_m2"],
            },
        )
        assert r.status_code == 201, r.text
        created[c["label"]] = r.json()["unit"]
    apt = created["ბინა №1"]
    doc = [a for a in apt["areas"] if a["source"] == "drawing_schedule"]
    assert len(doc) == 1 and float(doc[0]["value_m2"]) == bundle_area(BUNDLE_APT)
    assert doc[0]["verification_status"] == "unverified"
    stall = created["A1-2"]
    assert stall["unit_type"] == "parking"
    assert float(
        next(a for a in stall["areas"] if a["source"] == "drawing_schedule")["value_m2"]
    ) == bundle_area(BUNDLE_STALL)

    # reading the sheet again changes nothing; a hand-drawn unit gets its area on demand
    r = client.post(f"{base}/sheets/{p1['id']}/printed-areas", headers=arch)
    assert r.status_code == 200 and r.json() == {"updated": 0, "unchanged": 6, "unmatched": 0}


@needs_db
def test_numbered_rooms_below_ground_are_storage_and_catch_up_areas(
    client: TestClient,
    world: dict,
    bundle: dict,
):
    base, arch = world["base"], world["arch"]
    p4 = _confirm(client, world, bundle["sheets"][3])
    sug = client.post(f"{base}/sheets/{p4['id']}/suggestions", headers=arch).json()
    rooms = [c for c in sug if c["confidence"] >= 0.85]
    assert sorted(c["label"] for c in rooms) == ["№1", "№2", "№3"]
    assert {c["unit_type"] for c in rooms} == {"storage"}
    for c in rooms:  # drawn without passing the printed area (as a hand-drawn unit would be)
        r = client.post(
            f"{base}/sheets/{p4['id']}/boundaries",
            headers=arch,
            json={"ring": c["ring"], "label": c["label"], "unit_type": "storage"},
        )
        assert r.status_code == 201, r.text
    r = client.post(f"{base}/sheets/{p4['id']}/printed-areas", headers=arch)
    assert r.json() == {"updated": 3, "unchanged": 0, "unmatched": 0}
    units = client.get(f"{base}/projects/{world['project']['id']}/units", headers=arch).json()
    stores = [u for u in units if u["unit_type"] == "storage"]
    assert len(stores) == 3
    for u in stores:
        doc = [a for a in u["areas"] if a["source"] == "drawing_schedule" and a["is_current"]]
        assert [float(a["value_m2"]) for a in doc] == [bundle_area(BUNDLE_STORE)]


@needs_db
def test_excluding_reprints_and_pages(client: TestClient, world: dict, bundle: dict):
    base, arch = world["base"], world["arch"]
    rev_id = bundle["sheets"][0]["revision_id"]
    # pages with units cannot be excluded
    r = client.post(
        f"{base}/revisions/{rev_id}/exclusions",
        headers=arch,
        json={"pages": [1, 2], "excluded": True, "reason": "fire-safety set"},
    )
    assert r.status_code == 409 and "Pages 1" in r.json()["detail"]
    r = client.post(
        f"{base}/revisions/{rev_id}/exclusions",
        headers=arch,
        json={"pages": [2, 3], "excluded": True, "reason": "fire-safety set"},
    )
    assert r.status_code == 200, r.text
    by_page = {s["page_no"]: s for s in r.json()}
    assert by_page[2]["excluded"] and by_page[2]["exclusion_reason"] == "fire-safety set"
    assert not by_page[1]["excluded"]
    p2 = by_page[2]
    assert client.post(f"{base}/sheets/{p2['id']}/suggestions", headers=arch).status_code == 409
    ring = [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]]
    r = client.post(f"{base}/sheets/{p2['id']}/boundaries", headers=arch, json={"ring": ring})
    assert r.status_code == 409
    r = client.put(
        f"{base}/sheets/{p2['id']}/floors",
        headers=arch,
        json={"floors": [{"floor_id": world["f"][0]["id"]}], "version": p2["version"]},
    )
    assert r.status_code == 409
    assert (
        client.post(
            f"{base}/revisions/{rev_id}/exclusions",
            headers=arch,
            json={"pages": [99], "excluded": True},
        ).status_code
        == 422
    )

    # a new revision keeps the reviewer's exclusions
    nxt = _upload(client, world, make_bundle_pdf(), document_id=bundle["document_id"])
    new = {s["page_no"]: s for s in nxt["sheets"]}
    assert new[2]["excluded"] and "previous revision" in new[2]["exclusion_reason"]
    assert new[2]["floors"] == []
    assert not new[1]["excluded"]

    # and a single sheet comes back
    r = client.patch(
        f"{base}/sheets/{p2['id']}/exclusion",
        headers=arch,
        json={"excluded": False, "version": p2["version"]},
    )
    assert (
        r.status_code == 200 and not r.json()["excluded"] and r.json()["exclusion_reason"] is None
    )
