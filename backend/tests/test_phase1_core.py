"""Phase 1 exit criteria (plan §14): tenant creation, invitations, project restriction, audit.

Runs against the migrated PostgreSQL test database (UF_TEST_DATABASE_URL / _ADMIN_URL).
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.fake_kratos import FakeKratos, cookie

pytestmark = pytest.mark.skipif(
    not (os.environ.get("UF_TEST_DATABASE_ADMIN_URL") and os.environ.get("UF_TEST_DATABASE_URL")),
    reason="needs the PostgreSQL test database",
)


@pytest.fixture(scope="module")
def kratos() -> FakeKratos:
    return FakeKratos()


@pytest.fixture(scope="module")
def client(kratos: FakeKratos):
    from unitforma.identity.deps import clear_whoami_cache, get_kratos
    from unitforma.main import create_app

    clear_whoami_cache()
    app = create_app()
    app.dependency_overrides[get_kratos] = lambda: kratos
    with TestClient(app, headers={"X-Requested-With": "unitforma"}) as c:
        yield c


@pytest.fixture(scope="module")
def platform_admin(kratos: FakeKratos, client: TestClient) -> dict:
    """A platform admin exists once a user row is flagged; the row appears on first login."""
    suffix = uuid.uuid4().hex[:6]
    kratos.add("root", f"root-{suffix}@unitforma.example.com", aal="aal2")
    assert client.get("/api/v1/admin/me", headers=cookie("root")).status_code == 200
    eng = create_engine(os.environ["UF_TEST_DATABASE_ADMIN_URL"])
    with eng.begin() as conn:
        conn.execute(
            text("UPDATE users SET is_platform_admin = true WHERE email = :e"),
            {"e": f"root-{suffix}@unitforma.example.com"},
        )
    eng.dispose()
    from unitforma.identity.deps import clear_whoami_cache

    clear_whoami_cache()
    return cookie("root")


@pytest.fixture(scope="module")
def world(kratos: FakeKratos, client: TestClient, platform_admin: dict) -> dict:
    """Two tenants, an admin and a restricted sales user in tenant A, two projects in A."""
    s = uuid.uuid4().hex[:6]
    admin_email = f"admin-{s}@a.example.com"
    sales_email = f"sales-{s}@a.example.com"
    kratos.add("admin_a", admin_email)
    kratos.add("sales_a", sales_email)
    kratos.add("admin_b", f"admin-{s}@b.example.com")

    r = client.post(
        "/api/v1/platform/tenants",
        headers=platform_admin,
        json={"slug": f"acme{s}", "name": "Acme Homes"},
    )
    assert r.status_code == 201, r.text
    tenant_a = r.json()
    r = client.post(
        "/api/v1/platform/tenants",
        headers=platform_admin,
        json={"slug": f"beta{s}", "name": "Beta Dev", "admin_email": f"admin-{s}@b.example.com"},
    )
    assert r.status_code == 201, r.text
    tenant_b = r.json()

    # invite + accept the tenant admin of A
    r = client.post(
        f"/api/v1/platform/tenants/{tenant_a['id']}/invitations",
        headers=platform_admin,
        params={"email": admin_email},
    )
    assert r.status_code == 201, r.text
    token = r.json()["accept_url"].rsplit("/", 1)[1]
    r = client.post(
        "/api/v1/admin/invitations/accept", headers=cookie("admin_a"), json={"token": token}
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "tenant_admin"

    # projects in A
    base = f"/api/v1/admin/tenants/{tenant_a['id']}"
    p1 = client.post(
        f"{base}/projects",
        headers=cookie("admin_a"),
        json={"slug": "riverside", "name": "Riverside"},
    ).json()
    p2 = client.post(
        f"{base}/projects", headers=cookie("admin_a"), json={"slug": "hilltop", "name": "Hilltop"}
    ).json()
    assert "id" in p1 and "id" in p2
    b = client.post(
        f"{base}/projects/{p1['id']}/buildings",
        headers=cookie("admin_a"),
        json={"code": "A", "name": "Block A"},
    )
    assert b.status_code == 201, b.text
    floors = client.put(
        f"{base}/buildings/{b.json()['id']}/floors",
        headers=cookie("admin_a"),
        json={
            "floors": [
                {"level": lvl, "display_name": name, "height_m": "3.0"}
                for lvl, name in [(-1, "Parking"), (0, "Ground"), (1, "1"), (2, "2")]
            ]
        },
    )
    assert floors.status_code == 200, floors.text
    assert [f["level"] for f in floors.json()] == [-1, 0, 1, 2]

    # invite sales restricted to P1 and accept
    r = client.post(
        f"{base}/invitations",
        headers=cookie("admin_a"),
        json={
            "email": sales_email,
            "role": "sales",
            "all_projects": False,
            "project_ids": [p1["id"]],
        },
    )
    assert r.status_code == 201, r.text
    token = r.json()["accept_url"].rsplit("/", 1)[1]
    r = client.post(
        "/api/v1/admin/invitations/accept", headers=cookie("sales_a"), json={"token": token}
    )
    assert r.status_code == 200, r.text
    assert r.json()["all_projects"] is False
    return {"a": tenant_a, "b": tenant_b, "p1": p1, "p2": p2, "building": b.json(), "base": base}


def test_unauthenticated_is_401(client: TestClient):
    assert client.get("/api/v1/admin/me").status_code == 401


def test_state_change_without_requested_with_header_is_rejected(
    client: TestClient, platform_admin: dict
):
    r = client.post(
        "/api/v1/platform/tenants",
        headers={**platform_admin, "X-Requested-With": "other"},
        json={"slug": "csrf-x", "name": "x"},
    )
    assert r.status_code == 403


def test_non_platform_admin_cannot_create_tenants(client: TestClient, world: dict):
    r = client.post(
        "/api/v1/platform/tenants", headers=cookie("admin_a"), json={"slug": "nope-x", "name": "x"}
    )
    assert r.status_code == 403


def test_reserved_slug_rejected(client: TestClient, platform_admin: dict):
    r = client.post(
        "/api/v1/platform/tenants", headers=platform_admin, json={"slug": "app", "name": "x"}
    )
    assert r.status_code == 422


def test_restricted_sales_sees_only_project_a(client: TestClient, world: dict):
    base = world["base"]
    r = client.get(f"{base}/projects", headers=cookie("sales_a"))
    assert r.status_code == 200
    assert [p["id"] for p in r.json()] == [world["p1"]["id"]]
    assert (
        client.get(f"{base}/projects/{world['p1']['id']}", headers=cookie("sales_a")).status_code
        == 200
    )
    # project B of the same tenant is invisible (404, not 403, to avoid probing)
    assert (
        client.get(f"{base}/projects/{world['p2']['id']}", headers=cookie("sales_a")).status_code
        == 404
    )
    assert (
        client.get(
            f"{base}/projects/{world['p2']['id']}/buildings", headers=cookie("sales_a")
        ).status_code
        == 404
    )


def test_sales_cannot_manage_users_or_create_projects(client: TestClient, world: dict):
    base = world["base"]
    assert client.get(f"{base}/members", headers=cookie("sales_a")).status_code == 403
    r = client.post(
        f"{base}/projects", headers=cookie("sales_a"), json={"slug": "new-one", "name": "New"}
    )
    assert r.status_code == 403


def test_cross_tenant_access_is_404(client: TestClient, world: dict):
    other = f"/api/v1/admin/tenants/{world['b']['id']}"
    assert client.get(other, headers=cookie("admin_a")).status_code == 404
    assert client.get(f"{other}/projects", headers=cookie("sales_a")).status_code == 404
    # and a project id of tenant A cannot be reached through tenant B's path by its own admin
    # (admin_b has an invitation but has not accepted it → no membership)
    assert client.get(f"{other}/projects", headers=cookie("admin_b")).status_code == 404


def test_platform_admin_sees_all_tenants(client: TestClient, platform_admin: dict, world: dict):
    ids = {t["id"] for t in client.get("/api/v1/platform/tenants", headers=platform_admin).json()}
    assert {world["a"]["id"], world["b"]["id"]} <= ids
    r = client.get(f"/api/v1/admin/tenants/{world['b']['id']}/projects", headers=platform_admin)
    assert r.status_code == 200


def test_optimistic_concurrency_on_project(client: TestClient, world: dict):
    base = world["base"]
    p = client.get(f"{base}/projects/{world['p1']['id']}", headers=cookie("admin_a")).json()
    r = client.patch(
        f"{base}/projects/{p['id']}",
        headers=cookie("admin_a"),
        json={"name": "Riverside Park", "version": p["version"]},
    )
    assert r.status_code == 200 and r.json()["version"] == p["version"] + 1
    stale = client.patch(
        f"{base}/projects/{p['id']}",
        headers=cookie("admin_a"),
        json={"name": "Stale", "version": p["version"]},
    )
    assert stale.status_code == 409


def test_last_admin_cannot_be_demoted(client: TestClient, world: dict):
    base = world["base"]
    members = client.get(f"{base}/members", headers=cookie("admin_a")).json()
    admin = next(m for m in members if m["role"] == "tenant_admin")
    r = client.patch(
        f"{base}/members/{admin['id']}", headers=cookie("admin_a"), json={"role": "sales"}
    )
    assert r.status_code == 409


def test_audit_trail(client: TestClient, world: dict):
    base = world["base"]
    r = client.get(f"{base}/audit", headers=cookie("admin_a"))
    assert r.status_code == 200
    actions = {(a["entity_type"], a["action"]) for a in r.json()["items"]}
    assert {
        ("tenant", "create"),
        ("project", "create"),
        ("building", "create"),
        ("building", "set_floors"),
        ("membership", "accept_invitation"),
        ("staff_invitation", "create"),
        ("project", "update"),
    } <= actions
    # a sales user is not allowed to read the audit log
    assert client.get(f"{base}/audit", headers=cookie("sales_a")).status_code == 403


def test_me_lists_memberships(client: TestClient, world: dict):
    me = client.get("/api/v1/admin/me", headers=cookie("sales_a")).json()
    assert [m["tenant_id"] for m in me["memberships"]] == [world["a"]["id"]]
    assert me["memberships"][0]["role"] == "sales"
