"""ADR-0008: documents classify themselves from the file name and from page content; a kind
set by a person is never replaced; uploads without a kind stay ``unclassified`` until set."""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.fake_kratos import FakeKratos, cookie
from tests.pdf_fixture import make_plan_pdf
from unitforma.documents import classify


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("9.10 გეგმები 20.02.pdf", "floor_plan"),
        ("A-9-10 გენგეგმა 11.02.pdf", "site_plan"),
        ("ფასადები.pdf", "elevation"),
        ("ჭრილები 1-1, 2-2.pdf", "section"),
        ("rendering_final.jpg", "render"),
        ("3D views.pdf", "render"),
        ("Floor plans rev C.dxf", "floor_plan"),
        ("plan_01.dxf", "floor_plan"),
        ("fasadi-chrdiloeti.pdf", "elevation"),
        ("gegma sartuli 2.pdf", "floor_plan"),
        ("area schedule.xlsx", "schedule"),
        ("ბინების ექსპლიკაცია.pdf", "schedule"),
        ("მშენებლობის ნებართვა.pdf", "permit"),
        ("site plan 1-500.pdf", "site_plan"),
        ("planning permit.pdf", "permit"),
        ("scan0001.pdf", None),
        ("project.pdf", None),
        ("", None),
    ],
)
def test_kind_from_name(name: str, kind: str | None):
    assert classify.kind_from_name(name) == kind


def test_kind_from_name_reads_title_and_file_name_together():
    assert classify.kind_from_name("Rev C", "ფასადები.pdf") == "elevation"
    assert classify.kind_from_name(None, None) is None


def test_kind_from_pages():
    fp = {"kind": "floor_plan", "apartment_labels": ["1"], "has_text_layer": True}
    dr = {"kind": "drawing", "has_text_layer": True}
    ts = {"kind": "text_sheet", "has_text_layer": True, "area_values": [42.7]}
    tn = {"kind": "text_sheet", "has_text_layer": True}
    assert classify.kind_from_pages([fp, fp, dr]) == "floor_plan"  # 2 of 3
    assert classify.kind_from_pages([fp, dr]) == "floor_plan"  # a plan and its section sheet
    assert classify.kind_from_pages([fp, dr, dr]) is None  # 1 of 3 is not enough
    labelled = {"kind": "unknown", "unit_labels": {"apartment": ["1", "2"]}, "vector_lines": 12}
    listed = {"kind": "text_sheet", "unit_labels": {"apartment": ["1", "2"]}, "vector_lines": 0}
    assert classify.kind_from_pages([labelled, labelled]) == "floor_plan"  # labels on line work
    assert classify.kind_from_pages([listed, listed]) is None  # the same labels in a table
    assert classify.kind_from_pages([ts, tn]) == "schedule"
    assert classify.kind_from_pages([tn, tn]) is None  # text without areas: a letter, a permit
    img = {"kind": "unknown", "has_text_layer": False}
    assert classify.kind_from_pages([img], "image/jpeg") == "render"
    assert classify.kind_from_pages([img], "application/pdf") is None
    assert classify.kind_from_pages([]) is None


# --------------------------------------------------------------------------- through the API
pytestmark_db = pytest.mark.skipif(
    not (os.environ.get("UF_TEST_DATABASE_ADMIN_URL") and os.environ.get("UF_TEST_DATABASE_URL")),
    reason="needs the PostgreSQL test database",
)


@pytest.fixture(scope="module")
def kratos() -> FakeKratos:
    return FakeKratos()


@pytest.fixture(scope="module")
def client(kratos: FakeKratos, tmp_path_factory):
    from unitforma.core.settings import get_settings
    from unitforma.identity.deps import clear_whoami_cache, get_kratos
    from unitforma.main import create_app
    from unitforma.storage.service import reset_storage

    os.environ["UF_STORAGE_BACKEND"] = "local"
    os.environ["UF_STORAGE_LOCAL_ROOT"] = str(tmp_path_factory.mktemp("storage"))
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
    client: TestClient, base: str, doc_id: str, headers: dict, data: bytes, name: str
) -> dict:
    intent = client.post(
        f"{base}/documents/{doc_id}/uploads",
        headers=headers,
        json={
            "file_name": name,
            "content_type": "application/pdf",
            "byte_size": len(data),
            "source_note": None,
        },
    )
    assert intent.status_code == 201, intent.text
    client.put(
        intent.json()["upload_url"], content=data, headers={"Content-Type": "application/pdf"}
    )
    rev = client.post(
        f"{base}/revisions/{intent.json()['revision']['id']}/complete", headers=headers
    )
    assert rev.status_code == 200, rev.text
    return rev.json()


@pytestmark_db
def test_classification_through_upload_processing_and_confirmation(
    kratos: FakeKratos, client: TestClient
):
    from unitforma.documents.jobs import process_revision

    s = uuid.uuid4().hex[:6]
    kratos.add("rootc", f"rootc-{s}@unitforma.example.com", aal="aal2")
    assert client.get("/api/v1/admin/me", headers=cookie("rootc")).status_code == 200
    eng = create_engine(os.environ["UF_TEST_DATABASE_ADMIN_URL"])
    with eng.begin() as conn:
        conn.execute(
            text("UPDATE users SET is_platform_admin = true WHERE email = :e"),
            {"e": f"rootc-{s}@unitforma.example.com"},
        )
    eng.dispose()
    from unitforma.identity.deps import clear_whoami_cache

    clear_whoami_cache()
    root = cookie("rootc")
    t = client.post(
        "/api/v1/platform/tenants", headers=root, json={"slug": f"cls{s}", "name": "Cls"}
    ).json()
    base = f"/api/v1/admin/tenants/{t['id']}"
    p = client.post(f"{base}/projects", headers=root, json={"slug": "cls", "name": "Cls"}).json()
    tid = uuid.UUID(t["id"])

    # 1. a kind from the file name, at creation, without a kind in the request
    d = client.post(
        f"{base}/projects/{p['id']}/documents", headers=root, json={"title": "ფასადები.pdf"}
    )
    assert d.status_code == 201, d.text
    assert (d.json()["kind"], d.json()["kind_source"]) == ("elevation", "filename")

    # 2. nothing in the name → unclassified and pending; the content then says floor plan
    d2 = client.post(
        f"{base}/projects/{p['id']}/documents", headers=root, json={"title": "scan0001.pdf"}
    ).json()
    assert (d2["kind"], d2["kind_source"]) == ("unclassified", "pending")
    rev = _upload(client, base, d2["id"], root, make_plan_pdf(), "scan0001.pdf")
    result = client.portal.call(process_revision, tid, uuid.UUID(rev["id"]))
    assert result["pages"] == 2
    docs = {
        x["id"]: x for x in client.get(f"{base}/projects/{p['id']}/documents", headers=root).json()
    }
    assert (docs[d2["id"]]["kind"], docs[d2["id"]]["kind_source"]) == ("floor_plan", "content")

    # 3. a person confirms or changes the kind: manual, and a later revision keeps it
    r = client.patch(f"{base}/documents/{d2['id']}", headers=root, json={"kind": "section"})
    assert r.status_code == 200, r.text
    assert (r.json()["kind"], r.json()["kind_source"]) == ("section", "manual")
    rev2 = _upload(client, base, d2["id"], root, make_plan_pdf(), "scan0002.pdf")
    client.portal.call(process_revision, tid, uuid.UUID(rev2["id"]))
    docs = {
        x["id"]: x for x in client.get(f"{base}/projects/{p['id']}/documents", headers=root).json()
    }
    assert (docs[d2["id"]]["kind"], docs[d2["id"]]["kind_source"]) == ("section", "manual")

    # 4. an explicit kind in the request is manual from the start
    d3 = client.post(
        f"{base}/projects/{p['id']}/documents",
        headers=root,
        json={"title": "x.pdf", "kind": "render"},
    ).json()
    assert (d3["kind"], d3["kind_source"]) == ("render", "manual")
    # rename and file under no building
    r = client.patch(
        f"{base}/documents/{d3['id']}",
        headers=root,
        json={"title": "Street view", "clear_building": True},
    )
    assert r.json()["title"] == "Street view" and r.json()["building_id"] is None
    assert (
        client.patch(
            f"{base}/documents/{d3['id']}", headers=root, json={"building_id": str(uuid.uuid4())}
        ).status_code
        == 422
    )
