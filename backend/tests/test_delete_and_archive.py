"""ADR-0012: archive a project, delete a document or an empty building, and the tenant admin's
permanent project delete. Role matrix, refusals (published, mapped, has units, wrong slug), the
cascade including units, the kept audit row, and the guarded storage job."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.fake_kratos import FakeKratos, cookie
from tests.pdf_fixture import make_plan_pdf

pytestmark = pytest.mark.skipif(
    not (os.environ.get("UF_TEST_DATABASE_ADMIN_URL") and os.environ.get("UF_TEST_DATABASE_URL")),
    reason="needs the PostgreSQL test database",
)

W, H = 842.0, 595.0


def rect(x0, y0, x1, y1):
    return [[x0 / W, 1 - y1 / H], [x1 / W, 1 - y1 / H], [x1 / W, 1 - y0 / H], [x0 / W, 1 - y0 / H]]


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


def _admin_sql(sql: str, params: dict | None = None):
    eng = create_engine(os.environ["UF_TEST_DATABASE_ADMIN_URL"])
    with eng.begin() as conn:
        conn.execute(text("SELECT set_config('app.scope', 'platform', true)"))
        res = conn.execute(text(sql), params or {})
        rows = res.fetchall() if res.returns_rows else None
    eng.dispose()
    return rows


def _count(table: str, where: str, params: dict) -> int:
    return _admin_sql(f"SELECT count(*) FROM {table} WHERE {where}", params)[0][0]  # noqa: S608


def _upload(client, base, headers, project_id, kind, title, data, tenant_id, building_id=None):
    from unitforma.documents.jobs import process_revision

    doc = client.post(
        f"{base}/projects/{project_id}/documents",
        headers=headers,
        json={"kind": kind, "title": title, "building_id": building_id},
    ).json()
    up = client.post(
        f"{base}/documents/{doc['id']}/uploads",
        headers=headers,
        json={"file_name": "f.pdf", "content_type": "application/pdf", "byte_size": len(data)},
    ).json()
    assert (
        client.put(
            up["upload_url"], content=data, headers={"Content-Type": "application/pdf"}
        ).status_code
        == 200
    )
    rev = client.post(f"{base}/revisions/{up['revision']['id']}/complete", headers=headers).json()
    client.portal.call(process_revision, uuid.UUID(tenant_id), uuid.UUID(rev["id"]))
    sheets = client.get(f"{base}/revisions/{rev['id']}/sheets", headers=headers).json()
    return doc, sheets


def _calibrate(client, base, headers, sheet, p1, p2, metres):
    r = client.patch(
        f"{base}/sheets/{sheet['id']}/calibration",
        headers=headers,
        json={
            "calibration": {
                "p1": [p1[0] / W, 1 - p1[1] / H],
                "p2": [p2[0] / W, 1 - p2[1] / H],
                "distance_m": metres,
            },
            "version": sheet["version"],
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def world(kratos: FakeKratos, client: TestClient) -> dict:
    from unitforma.identity.deps import clear_whoami_cache
    from unitforma.storage.service import get_storage

    s = uuid.uuid4().hex[:6]
    kratos.add("root12", f"root12-{s}@unitforma.example.com", aal="aal2")
    assert client.get("/api/v1/admin/me", headers=cookie("root12")).status_code == 200
    _admin_sql(
        "UPDATE users SET is_platform_admin = true WHERE email = :e",
        {"e": f"root12-{s}@unitforma.example.com"},
    )
    clear_whoami_cache()
    root = cookie("root12")
    t = client.post(
        "/api/v1/platform/tenants", headers=root, json={"slug": f"del{s}", "name": "Del Co"}
    ).json()
    base = f"/api/v1/admin/tenants/{t['id']}"
    kratos.add("adm12", f"adm12-{s}@a.example.com")
    inv = client.post(
        f"/api/v1/platform/tenants/{t['id']}/invitations",
        headers=root,
        params={"email": f"adm12-{s}@a.example.com"},
    ).json()
    client.post(
        "/api/v1/admin/invitations/accept",
        headers=cookie("adm12"),
        json={"token": inv["accept_url"].rsplit("/", 1)[1]},
    )
    adm = cookie("adm12")
    for who, role in (("pm12", "project_manager"), ("sales12", "sales")):
        kratos.add(who, f"{who}-{s}@a.example.com")
        i2 = client.post(
            f"{base}/invitations",
            headers=adm,
            json={
                "email": f"{who}-{s}@a.example.com",
                "role": role,
                "all_projects": True,
                "project_ids": [],
            },
        ).json()
        client.post(
            "/api/v1/admin/invitations/accept",
            headers=cookie(who),
            json={"token": i2["accept_url"].rsplit("/", 1)[1]},
        )
    p = client.post(
        f"{base}/projects", headers=adm, json={"slug": "doomed", "name": "Doomed Towers"}
    ).json()
    a = client.post(
        f"{base}/projects/{p['id']}/buildings", headers=adm, json={"code": "A", "name": "Block A"}
    ).json()
    b = client.post(
        f"{base}/projects/{p['id']}/buildings", headers=adm, json={"code": "B", "name": "Block B"}
    ).json()
    floors = {}
    for bld in (a, b):
        fl = client.put(
            f"{base}/buildings/{bld['id']}/floors",
            headers=adm,
            json={
                "floors": [
                    {"level": 0, "display_name": "Ground", "height_m": "3.0"},
                    {"level": 1, "display_name": "First", "height_m": "3.0"},
                ]
            },
        ).json()
        floors[bld["code"]] = {f["level"]: f for f in fl}
    # a plan filed under A: sheet 1 mapped with two units and approved, sheet 2 assigned to B
    plans, sheets = _upload(
        client, base, adm, p["id"], "floor_plan", "Plans", make_plan_pdf(), t["id"], a["id"]
    )
    s1 = client.patch(
        f"{base}/sheets/{sheets[0]['id']}/floor",
        headers=adm,
        json={"floor_id": floors["A"][0]["id"], "version": sheets[0]["version"]},
    ).json()
    s1 = _calibrate(client, base, adm, s1, (100, 200), (400, 200), 15)
    units = []
    for r in (rect(100, 200, 400, 400), rect(400, 200, 700, 400)):
        res = client.post(f"{base}/sheets/{s1['id']}/boundaries", headers=adm, json={"ring": r})
        assert res.status_code == 201, res.text
        units.append(res.json()["unit"])
    assert client.post(f"{base}/sheets/{s1['id']}/approve", headers=adm).status_code == 200
    s2 = client.patch(
        f"{base}/sheets/{sheets[1]['id']}/floor",
        headers=adm,
        json={"floor_id": floors["B"][1]["id"], "version": sheets[1]["version"]},
    ).json()
    assert s2["assignment_status"] == "confirmed"
    # a document filed under B, and an IFC model of B with a GLB object
    render, _ = _upload(
        client, base, adm, p["id"], "render", "Render B", make_plan_pdf(), t["id"], b["id"]
    )
    glb_key = f"t/{t['id']}/p/{p['id']}/geometry/ifc-test.glb"
    get_storage().put_bytes(glb_key, b"glb", "model/gltf-binary")
    model_id = uuid.uuid4()
    _admin_sql(
        "INSERT INTO geometry_models (id, tenant_id, project_id, building_id, kind, glb_key, "
        "model_transform, units_scale, status, stats, is_current) VALUES "
        "(:id, :t, :p, :b, 'ifc', :k, '{}', 1, 'ready', '{}', true)",
        {"id": model_id, "t": t["id"], "p": p["id"], "b": b["id"], "k": glb_key},
    )
    return {
        "root": root,
        "adm": adm,
        "pm": cookie("pm12"),
        "sales": cookie("sales12"),
        "base": base,
        "tenant": t,
        "project": p,
        "a": a,
        "b": b,
        "floors": floors,
        "plans": plans,
        "sheet2": s2,
        "render": render,
        "units": units,
        "glb_key": glb_key,
        "model_id": model_id,
        "root_dir": Path(os.environ["UF_STORAGE_LOCAL_ROOT"]),
    }


def _prefix_dir(world, *parts) -> Path:
    return world["root_dir"].joinpath(
        "t", world["tenant"]["id"], "p", world["project"]["id"], *parts
    )


def test_role_matrix(client, world):
    base, pid = world["base"], world["project"]["id"]
    assert (
        client.delete(
            f"{base}/projects/{pid}", headers=world["pm"], params={"confirm": "doomed"}
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"{base}/documents/{world['render']['id']}", headers=world["sales"]
        ).status_code
        == 403
    )
    assert (
        client.delete(f"{base}/buildings/{world['b']['id']}", headers=world["sales"]).status_code
        == 403
    )


def test_job_guard_refuses_while_owner_exists(client, world):
    from unitforma.storage.jobs import OwnerStillExists, delete_prefix

    t, p = uuid.UUID(world["tenant"]["id"]), uuid.UUID(world["project"]["id"])
    with pytest.raises(OwnerStillExists):
        client.portal.call(delete_prefix, t, f"t/{t}/p/{p}/", "projects", p)
    with pytest.raises(ValueError, match="not under"):
        client.portal.call(delete_prefix, t, f"t/{uuid.uuid4()}/p/{p}/", "projects", p)
    with pytest.raises(ValueError, match="not under"):
        client.portal.call(delete_prefix, t, f"t/{t}/p/", "projects", p)
    assert _prefix_dir(world).is_dir()


def test_delete_unmapped_document_removes_rows_files_and_keeps_audit(client, world):
    from unitforma.storage.jobs import delete_prefix

    base, doc = world["base"], world["render"]
    doc_dir = _prefix_dir(world, "documents", doc["id"])
    assert doc_dir.is_dir() and any(doc_dir.rglob("*.png"))
    r = client.delete(f"{base}/documents/{doc['id']}", headers=world["pm"])
    assert r.status_code == 204, r.text
    assert (
        client.get(f"{base}/documents/{doc['id']}/revisions", headers=world["adm"]).status_code
        == 404
    )
    assert (
        _count(
            "sheets",
            "revision_id IN (SELECT id FROM document_revisions WHERE document_id = :d)",
            {"d": doc["id"]},
        )
        == 0
    )
    t, p = uuid.UUID(world["tenant"]["id"]), uuid.UUID(world["project"]["id"])
    out = client.portal.call(
        delete_prefix, t, f"t/{t}/p/{p}/documents/{doc['id']}/", "documents", uuid.UUID(doc["id"])
    )
    assert out["deleted"] >= 3 and not doc_dir.exists()
    assert _prefix_dir(world, "documents", world["plans"]["id"]).is_dir()
    rows = _admin_sql(
        "SELECT action, before FROM audit_log WHERE entity_type = 'document' AND entity_id = :id",
        {"id": doc["id"]},
    )
    deletes = [b for a, b in rows if a == "delete"]
    assert len(deletes) == 1 and deletes[0]["title"] == "Render B" and deletes[0]["revisions"] == 1


def test_building_with_units_is_refused(client, world):
    r = client.delete(f"{world['base']}/buildings/{world['a']['id']}", headers=world["adm"])
    assert r.status_code == 409, r.text
    assert r.json()["type"].endswith("building-has-units") and r.json()["units"] == 2
    assert (
        client.get(
            f"{world['base']}/buildings/{world['a']['id']}/floor-proposal", headers=world["adm"]
        ).status_code
        == 200
    )


def test_empty_building_deleted_with_models_and_assignments(client, world):
    base, b = world["base"], world["b"]
    r = client.delete(f"{base}/buildings/{b['id']}", headers=world["pm"])
    assert r.status_code == 204, r.text
    bl = client.get(
        f"{base}/projects/{world['project']['id']}/buildings", headers=world["adm"]
    ).json()
    assert [x["code"] for x in bl if x["kind"] == "building"] == ["A"]
    assert _count("floors", "building_id = :b", {"b": b["id"]}) == 0
    assert _count("geometry_models", "id = :m", {"m": world["model_id"]}) == 0
    assert not (world["root_dir"] / world["glb_key"]).exists()
    s2 = client.get(f"{base}/sheets/{world['sheet2']['id']}", headers=world["adm"]).json()
    assert s2["floor_id"] is None and s2["assignment_status"] == "unassigned"
    rows = _admin_sql(
        "SELECT before FROM audit_log WHERE entity_type = 'building' AND entity_id = :id "
        "AND action = 'delete'",
        {"id": b["id"]},
    )
    assert rows[0][0]["floors"] == 2 and rows[0][0]["models"] == 1


def test_mapped_document_refused_then_detached(client, world):
    base, doc, pid = world["base"], world["plans"], world["project"]["id"]
    r = client.delete(f"{base}/documents/{doc['id']}", headers=world["adm"])
    assert r.status_code == 409, r.text
    assert r.json()["type"].endswith("document-mapped") and r.json()["units"] == 2
    r = client.delete(
        f"{base}/documents/{doc['id']}", headers=world["adm"], params={"detach_units": "true"}
    )
    assert r.status_code == 204, r.text
    assert _count("units", "project_id = :p", {"p": pid}) == 2
    assert (
        _count(
            "unit_boundaries", "unit_id IN (SELECT id FROM units WHERE project_id = :p)", {"p": pid}
        )
        == 0
    )
    rows = _admin_sql(
        "SELECT before FROM audit_log WHERE entity_type = 'document' AND entity_id = :id "
        "AND action = 'delete'",
        {"id": doc["id"]},
    )
    assert sorted(rows[0][0]["detached_units"]) == sorted(u["id"] for u in world["units"])


def _publish_by_sql(world, status: str):
    _admin_sql(
        "INSERT INTO publications (id, tenant_id, project_id, version_no, status, snapshot_key, "
        "summary, assets) VALUES (:id, :t, :p, 1, :s, 'x', '{}', '{}')",
        {"id": uuid.uuid4(), "t": world["tenant"]["id"], "p": world["project"]["id"], "s": status},
    )


def test_archive_and_delete_refused_while_published(client, world):
    base, p = world["base"], world["project"]
    _publish_by_sql(world, "published")
    cur = client.get(f"{base}/projects/{p['id']}", headers=world["adm"]).json()
    r = client.patch(
        f"{base}/projects/{p['id']}",
        headers=world["pm"],
        json={"status": "archived", "version": cur["version"]},
    )
    assert r.status_code == 409 and r.json()["type"].endswith("project-published"), r.text
    r = client.delete(
        f"{base}/projects/{p['id']}", headers=world["adm"], params={"confirm": "doomed"}
    )
    assert r.status_code == 409 and r.json()["type"].endswith("project-published"), r.text
    _admin_sql("UPDATE publications SET status = 'retired' WHERE project_id = :p", {"p": p["id"]})


def test_archive_then_reactivate(client, world):
    base, p = world["base"], world["project"]
    cur = client.get(f"{base}/projects/{p['id']}", headers=world["adm"]).json()
    r = client.patch(
        f"{base}/projects/{p['id']}",
        headers=world["pm"],
        json={"status": "archived", "version": cur["version"]},
    )
    assert r.status_code == 200 and r.json()["status"] == "archived", r.text
    r = client.patch(
        f"{base}/projects/{p['id']}",
        headers=world["pm"],
        json={"status": "active", "version": r.json()["version"]},
    )
    assert r.status_code == 200 and r.json()["status"] == "active", r.text


def test_project_delete_needs_the_slug(client, world):
    base, p = world["base"], world["project"]
    r = client.delete(
        f"{base}/projects/{p['id']}", headers=world["adm"], params={"confirm": "Doomed"}
    )
    assert r.status_code == 400 and r.json()["type"].endswith("confirm-mismatch"), r.text
    assert client.delete(f"{base}/projects/{p['id']}", headers=world["adm"]).status_code == 422


def test_project_delete_cascades_units_and_keeps_audit(client, world):
    from unitforma.storage.jobs import delete_prefix

    base, p, t = world["base"], world["project"], world["tenant"]
    _admin_sql(
        "INSERT INTO portal_domains (id, tenant_id, project_id, hostname, kind, "
        "verification_status, status, is_primary) "
        "VALUES (:id, :t, :p, :h, 'custom', 'verified', 'active', false)",
        {
            "id": uuid.uuid4(),
            "t": t["id"],
            "p": p["id"],
            "h": f"doomed-{uuid.uuid4().hex[:8]}.example.net",
        },
    )
    assert _count("units", "project_id = :p", {"p": p["id"]}) == 2
    r = client.delete(
        f"{base}/projects/{p['id']}", headers=world["adm"], params={"confirm": "doomed"}
    )
    assert r.status_code == 204, r.text
    assert client.get(f"{base}/projects/{p['id']}", headers=world["adm"]).status_code == 404
    for table in (
        "units",
        "buildings",
        "documents",
        "publications",
        "geometry_models",
        "membership_project_access",
    ):
        assert _count(table, "project_id = :p", {"p": p["id"]}) == 0, table
    assert _count("floors", "building_id = :b", {"b": world["a"]["id"]}) == 0
    assert _count("document_revisions", "document_id = :d", {"d": world["plans"]["id"]}) == 0
    assert _admin_sql(
        "SELECT status FROM portal_domains WHERE project_id = :p", {"p": p["id"]}
    ) == [("removed",)]
    rows = _admin_sql(
        "SELECT before FROM audit_log WHERE entity_type = 'project' AND entity_id = :id "
        "AND action = 'delete'",
        {"id": p["id"]},
    )
    assert rows[0][0] == {
        "slug": "doomed",
        "name": "Doomed Towers",
        "buildings": 1,
        "units": 2,
        "documents": 0,
    }
    out = client.portal.call(
        delete_prefix,
        uuid.UUID(t["id"]),
        f"t/{t['id']}/p/{p['id']}/",
        "projects",
        uuid.UUID(p["id"]),
    )
    assert out["deleted"] >= 0 and not _prefix_dir(world).exists()
    # the tenant's other objects are untouched
    assert (world["root_dir"] / "t" / t["id"]).is_dir()
