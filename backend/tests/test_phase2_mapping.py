"""Phase 2 exit criteria (plan §14): upload → sheets → assignment → calibration → boundaries →
draft units with codes → approve; relabel/split/merge/remove preserve identities and lineage."""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.fake_kratos import FakeKratos, cookie
from tests.pdf_fixture import make_plan_pdf

pytestmark = pytest.mark.skipif(
    not (os.environ.get("UF_TEST_DATABASE_ADMIN_URL") and os.environ.get("UF_TEST_DATABASE_URL")),
    reason="needs the PostgreSQL test database",
)


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


@pytest.fixture(scope="module")
def world(kratos: FakeKratos, client: TestClient) -> dict:
    s = uuid.uuid4().hex[:6]
    kratos.add("root2", f"root2-{s}@unitforma.example.com", aal="aal2")
    assert client.get("/api/v1/admin/me", headers=cookie("root2")).status_code == 200
    eng = create_engine(os.environ["UF_TEST_DATABASE_ADMIN_URL"])
    with eng.begin() as conn:
        conn.execute(
            text("UPDATE users SET is_platform_admin = true WHERE email = :e"),
            {"e": f"root2-{s}@unitforma.example.com"},
        )
    eng.dispose()
    from unitforma.identity.deps import clear_whoami_cache

    clear_whoami_cache()
    root = cookie("root2")
    kratos.add("reviewer", f"rev-{s}@a.example.com")
    kratos.add("sales2", f"sales2-{s}@a.example.com")

    t = client.post(
        "/api/v1/platform/tenants", headers=root, json={"slug": f"map{s}", "name": "Map Co"}
    ).json()
    base = f"/api/v1/admin/tenants/{t['id']}"
    inv = client.post(
        f"/api/v1/platform/tenants/{t['id']}/invitations",
        headers=root,
        params={"email": f"rev-{s}@a.example.com"},
    ).json()
    client.post(
        "/api/v1/admin/invitations/accept",
        headers=cookie("reviewer"),
        json={"token": inv["accept_url"].rsplit("/", 1)[1]},
    )
    # a sales member exercises the role matrix (read-only on mapping)
    inv2 = client.post(
        f"{base}/invitations",
        headers=cookie("reviewer"),
        json={
            "email": f"sales2-{s}@a.example.com",
            "role": "sales",
            "all_projects": True,
            "project_ids": [],
        },
    ).json()
    client.post(
        "/api/v1/admin/invitations/accept",
        headers=cookie("sales2"),
        json={"token": inv2["accept_url"].rsplit("/", 1)[1]},
    )

    p = client.post(
        f"{base}/projects", headers=cookie("reviewer"), json={"slug": "tower", "name": "Tower"}
    ).json()
    b = client.post(
        f"{base}/projects/{p['id']}/buildings",
        headers=cookie("reviewer"),
        json={"code": "A", "name": "Block A"},
    ).json()
    floors = client.put(
        f"{base}/buildings/{b['id']}/floors",
        headers=cookie("reviewer"),
        json={
            "floors": [{"level": 0, "display_name": "Ground"}, {"level": 1, "display_name": "1"}]
        },
    ).json()
    return {
        "root": root,
        "base": base,
        "tenant": t,
        "project": p,
        "building": b,
        "floors": {f["level"]: f for f in floors},
    }


def _upload(
    client: TestClient, world: dict, headers: dict, data: bytes, title: str = "Floor plans A"
) -> dict:
    base, p = world["base"], world["project"]
    doc = client.post(
        f"{base}/projects/{p['id']}/documents",
        headers=headers,
        json={"kind": "floor_plan", "title": title, "building_id": world["building"]["id"]},
    )
    assert doc.status_code == 201, doc.text
    intent = client.post(
        f"{base}/documents/{doc.json()['id']}/uploads",
        headers=headers,
        json={
            "file_name": "plans.pdf",
            "content_type": "application/pdf",
            "byte_size": len(data),
            "source_note": "Rev A",
        },
    )
    assert intent.status_code == 201, intent.text
    up = intent.json()
    put = client.put(up["upload_url"], content=data, headers={"Content-Type": "application/pdf"})
    assert put.status_code == 200, put.text
    done = client.post(f"{base}/revisions/{up['revision']['id']}/complete", headers=headers)
    assert done.status_code == 200, done.text
    return {"document": doc.json(), "revision": done.json()}


@pytest.fixture(scope="module")
def uploaded(client: TestClient, world: dict) -> dict:
    from unitforma.documents.jobs import process_revision

    r = _upload(client, world, cookie("reviewer"), make_plan_pdf())
    assert r["revision"]["processing_status"] in ("queued", "processing", "done")
    # run the worker job inline on the app's event loop (no worker process in tests)
    result = client.portal.call(
        process_revision, uuid.UUID(world["tenant"]["id"]), uuid.UUID(r["revision"]["id"])
    )
    assert result == {"pages": 2, "page_count": 2}, result
    sheets = client.get(
        f"{world['base']}/revisions/{r['revision']['id']}/sheets", headers=cookie("reviewer")
    ).json()
    assert len(sheets) == 2
    return {**r, "sheets": sheets}


def test_upload_requires_object_before_complete(client: TestClient, world: dict):
    base, p = world["base"], world["project"]
    doc = client.post(
        f"{base}/projects/{p['id']}/documents",
        headers=cookie("reviewer"),
        json={"kind": "render", "title": "Render"},
    ).json()
    up = client.post(
        f"{base}/documents/{doc['id']}/uploads",
        headers=cookie("reviewer"),
        json={"file_name": "x.png", "content_type": "image/png", "byte_size": 10},
    ).json()
    r = client.post(f"{base}/revisions/{up['revision']['id']}/complete", headers=cookie("reviewer"))
    assert r.status_code == 409
    bad = client.post(
        f"{base}/documents/{doc['id']}/uploads",
        headers=cookie("reviewer"),
        json={"file_name": "x.exe", "content_type": "application/x-msdownload", "byte_size": 10},
    )
    assert bad.status_code == 415


def test_processing_produced_rasters_hints_and_suggestion(
    client: TestClient, world: dict, uploaded: dict
):
    s1, s2 = uploaded["sheets"]
    assert s1["raster_url"] and s1["thumbnail_url"] and s1["extract_url"]
    assert s1["raster_width"] == 4000
    assert s1["hints"]["levels"] == ["+0.00"] and s1["hints"]["apartment_labels"] == ["1", "2"]
    assert (
        s1["suggested_floor_id"] == world["floors"][0]["id"]
        and s1["assignment_status"] == "suggested"
    )
    assert s2["assignment_status"] == "unassigned"
    rev = client.get(
        f"{world['base']}/documents/{uploaded['document']['id']}/revisions",
        headers=cookie("reviewer"),
    ).json()[0]
    assert rev["processing_status"] == "done" and rev["page_count"] == 2 and rev["sha256"]
    # the signed raster URL serves the PNG (local backend)
    png = client.get(s1["raster_url"])
    assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
    assert client.get(s1["raster_url"].replace("sig=", "sig=0")).status_code == 403


def test_sales_cannot_map_but_can_read(client: TestClient, world: dict, uploaded: dict):
    s1 = uploaded["sheets"][0]
    assert (
        client.get(f"{world['base']}/sheets/{s1['id']}", headers=cookie("sales2")).status_code
        == 200
    )
    r = client.patch(
        f"{world['base']}/sheets/{s1['id']}/floor",
        headers=cookie("sales2"),
        json={"floor_id": world["floors"][0]["id"], "version": s1["version"]},
    )
    assert r.status_code == 403


@pytest.fixture(scope="module")
def mapped(client: TestClient, world: dict, uploaded: dict) -> dict:
    base = world["base"]
    s1 = uploaded["sheets"][0]
    # drawing before assignment is refused
    r = client.post(
        f"{base}/sheets/{s1['id']}/boundaries",
        headers=cookie("reviewer"),
        json={"ring": [[0.1, 0.3], [0.4, 0.3], [0.4, 0.6], [0.1, 0.6]]},
    )
    assert r.status_code == 409
    s1 = client.patch(
        f"{base}/sheets/{s1['id']}/floor",
        headers=cookie("reviewer"),
        json={"floor_id": world["floors"][0]["id"], "version": s1["version"]},
    ).json()
    assert s1["assignment_status"] == "confirmed"
    # calibrate on the 600 pt dimension line (x 100..700 of 842 pt); declare it 30 m
    s1 = client.patch(
        f"{base}/sheets/{s1['id']}/calibration",
        headers=cookie("reviewer"),
        json={
            "calibration": {
                "p1": [100 / 842, 1 - 100 / 595],
                "p2": [700 / 842, 1 - 100 / 595],
                "distance_m": 30,
            },
            "version": s1["version"],
        },
    ).json()
    assert s1["calibration_status"] == "calibrated" and s1["calibration"]["m_per_px"] > 0

    # two apartments: 100..400 x 200..400 pt and 400..700 x 200..400 pt (PDF y up)
    def ring(x0, x1, y0, y1):
        return [
            [x0 / 842, 1 - y1 / 595],
            [x1 / 842, 1 - y1 / 595],
            [x1 / 842, 1 - y0 / 595],
            [x0 / 842, 1 - y0 / 595],
        ]

    u1 = client.post(
        f"{base}/sheets/{s1['id']}/boundaries",
        headers=cookie("reviewer"),
        json={"ring": ring(100, 400, 200, 400), "label": "bina #1"},
    )
    assert u1.status_code == 201, u1.text
    u2 = client.post(
        f"{base}/sheets/{s1['id']}/boundaries",
        headers=cookie("reviewer"),
        json={"ring": ring(400, 700, 200, 400), "label": "bina #2"},
    )
    assert u2.status_code == 201, u2.text
    return {"sheet": s1, "u1": u1.json(), "u2": u2.json(), "ring": ring}


def test_draft_units_have_codes_and_measured_areas(client: TestClient, world: dict, mapped: dict):
    u1, u2 = mapped["u1"]["unit"], mapped["u2"]["unit"]
    assert u1["code"] == "A-00-01" and u2["code"] == "A-00-02"
    assert u1["lifecycle_status"] == "draft" and u1["verification_status"] == "unverified"
    # 300 pt × 200 pt at 30 m / 600 pt = 0.05 m/pt → 15 m × 10 m = 150 m²
    a = u1["areas"][0]
    assert a["source"] == "drawing_measured" and a["verification_status"] == "unverified"
    assert abs(float(a["value_m2"]) - 150.0) < 0.5
    assert mapped["u1"]["boundary"]["polygon_m"] is not None


def test_duplicate_code_rejected_and_relabel_keeps_identity(
    client: TestClient, world: dict, mapped: dict
):
    base, s1 = world["base"], mapped["sheet"]
    dup = client.post(
        f"{base}/sheets/{s1['id']}/boundaries",
        headers=cookie("reviewer"),
        json={"ring": [[0.6, 0.1], [0.7, 0.1], [0.7, 0.2], [0.6, 0.2]], "code": "a-00-01"},
    )
    assert dup.status_code == 409
    u1 = mapped["u1"]["unit"]
    r = client.post(
        f"{base}/units/{u1['id']}/relabel",
        headers=cookie("reviewer"),
        json={"code": "A-00-11", "version": u1["version"], "reason": "architect renumbered"},
    )
    assert r.status_code == 200 and r.json()["code"] == "A-00-11" and r.json()["id"] == u1["id"]
    hist = client.get(f"{base}/units/{u1['id']}/history", headers=cookie("reviewer")).json()
    assert [c["new_code"] for c in hist["codes"]] == ["A-00-01", "A-00-11"]
    assert [e["event_type"] for e in hist["lineage"]] == ["created", "relabelled"]
    # the old code can be reused by a new unit now
    again = client.post(
        f"{base}/sheets/{s1['id']}/boundaries",
        headers=cookie("reviewer"),
        json={
            "ring": [[0.6, 0.1], [0.7, 0.1], [0.7, 0.2], [0.6, 0.2]],
            "code": "A-00-01",
            "unit_type": "storage",
        },
    )
    assert again.status_code == 201
    mapped["u3"] = again.json()


def test_approve_sheet_activates_and_verifies(client: TestClient, world: dict, mapped: dict):
    base, s1 = world["base"], mapped["sheet"]
    # sales cannot approve
    assert (
        client.post(f"{base}/sheets/{s1['id']}/approve", headers=cookie("sales2")).status_code
        == 403
    )
    r = client.post(f"{base}/sheets/{s1['id']}/approve", headers=cookie("reviewer"))
    assert r.status_code == 200 and r.json()["approved_units"] == 3
    units = client.get(
        f"{base}/projects/{world['project']['id']}/units", headers=cookie("reviewer")
    ).json()
    assert {u["lifecycle_status"] for u in units} == {"active"} and {
        u["verification_status"] for u in units
    } == {"verified"}
    assert all(b["status"] == "approved" for u in units for b in u["boundaries"])


def test_editing_approved_boundary_supersedes_not_overwrites(
    client: TestClient, world: dict, mapped: dict
):
    base = world["base"]
    u1 = client.get(f"{base}/units/{mapped['u1']['unit']['id']}", headers=cookie("reviewer")).json()
    b = u1["boundaries"][0]
    smaller = mapped["ring"](100, 400, 200, 300)
    r = client.patch(
        f"{base}/boundaries/{b['id']}",
        headers=cookie("reviewer"),
        json={"ring": smaller, "version": b["version"]},
    )
    assert r.status_code == 200 and r.json()["id"] != b["id"] and r.json()["status"] == "draft"
    u1b = client.get(f"{base}/units/{u1['id']}", headers=cookie("reviewer")).json()
    assert len(u1b["boundaries"]) == 1 and u1b["boundaries"][0]["id"] == r.json()["id"]
    assert (
        abs(float(u1b["areas"][0]["value_m2"]) - 75.0) < 0.5
    )  # measured area follows the new geometry
    hist = client.get(f"{base}/units/{u1['id']}/history", headers=cookie("reviewer")).json()
    assert "geometry_updated" in [e["event_type"] for e in hist["lineage"]]


def test_split_and_merge_preserve_ids_and_sales_references(
    client: TestClient, world: dict, mapped: dict
):
    base, s1, ring = world["base"], mapped["sheet"], mapped["ring"]
    u2 = client.get(f"{base}/units/{mapped['u2']['unit']['id']}", headers=cookie("reviewer")).json()
    r = client.post(
        f"{base}/units/{u2['id']}/split",
        headers=cookie("reviewer"),
        json={
            "sheet_id": s1["id"],
            "rings": [ring(400, 550, 200, 400), ring(550, 700, 200, 400)],
            "codes": [None, "A-00-02B"],
            "note": "two smaller flats",
        },
    )
    assert r.status_code == 200, r.text
    parts = r.json()
    assert parts[0]["id"] == u2["id"] and parts[0]["code"] == "A-00-02"
    assert parts[1]["id"] != u2["id"] and parts[1]["code"] == "A-00-02B"
    assert abs(float(parts[0]["areas"][0]["value_m2"]) - 75.0) < 0.5
    # merge them back: survivor keeps id, absorbed becomes removed and leaves the live code space
    m = client.post(
        f"{base}/projects/{world['project']['id']}/units/merge",
        headers=cookie("reviewer"),
        json={
            "survivor_id": u2["id"],
            "absorbed_ids": [parts[1]["id"]],
            "sheet_id": s1["id"],
            "ring": ring(400, 700, 200, 400),
            "note": "merged again",
        },
    )
    assert m.status_code == 200, m.text
    assert m.json()["id"] == u2["id"] and m.json()["verification_status"] == "in_review"
    removed = client.get(f"{base}/units/{parts[1]['id']}", headers=cookie("reviewer")).json()
    assert removed["lifecycle_status"] == "removed"
    live = client.get(
        f"{base}/projects/{world['project']['id']}/units", headers=cookie("reviewer")
    ).json()
    assert parts[1]["id"] not in {u["id"] for u in live}
    allu = client.get(
        f"{base}/projects/{world['project']['id']}/units",
        headers=cookie("reviewer"),
        params={"include_removed": "true"},
    ).json()
    assert parts[1]["id"] in {u["id"] for u in allu}  # never deleted
    lineage = client.get(
        f"{base}/projects/{world['project']['id']}/lineage", headers=cookie("reviewer")
    ).json()
    assert {"split", "merged"} <= {e["event_type"] for e in lineage}
    # a removed unit's code becomes reusable
    reuse = client.post(
        f"{base}/sheets/{s1['id']}/boundaries",
        headers=cookie("reviewer"),
        json={"ring": [[0.8, 0.1], [0.9, 0.1], [0.9, 0.2], [0.8, 0.2]], "code": "A-00-02B"},
    )
    assert reuse.status_code == 201


def test_manual_area_and_verification(client: TestClient, world: dict, mapped: dict):
    base = world["base"]
    u1 = mapped["u1"]["unit"]
    r = client.put(
        f"{base}/units/{u1['id']}/areas",
        headers=cookie("reviewer"),
        json={"area_type": "net_internal", "value_m2": "74.30", "verified": True},
    )
    assert r.status_code == 200 and r.json()["verification_status"] == "verified"
    u = client.get(f"{base}/units/{u1['id']}", headers=cookie("reviewer")).json()
    sources = {a["source"]: a for a in u["areas"]}
    assert set(sources) == {"drawing_measured", "manual"}
    assert (
        sources["manual"]["value_m2"] == "74.30"
        and sources["drawing_measured"]["verification_status"] == "unverified"
    )
    # zero stays an explicit value; negative is rejected
    assert (
        client.put(
            f"{base}/units/{u1['id']}/areas",
            headers=cookie("reviewer"),
            json={"area_type": "balcony", "value_m2": "-1"},
        ).status_code
        == 422
    )
