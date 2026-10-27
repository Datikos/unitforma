"""ADR-0015 Phase 1: personal API tokens. Creation shows the secret once and stores only its
hash and prefix; members see their own tokens, the tenant admin every token of the tenant;
revocation and the input bounds; the audit rows."""

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


def _admin_sql(sql: str, params: dict | None = None):
    eng = create_engine(os.environ["UF_TEST_DATABASE_ADMIN_URL"])
    with eng.begin() as conn:
        conn.execute(text("SELECT set_config('app.scope', 'platform', true)"))
        res = conn.execute(text(sql), params or {})
        rows = res.fetchall() if res.returns_rows else None
    eng.dispose()
    return rows


@pytest.fixture(scope="module")
def platform_admin(kratos: FakeKratos, client: TestClient) -> dict:
    suffix = uuid.uuid4().hex[:6]
    email = f"root-{suffix}@unitforma.example.com"
    kratos.add("root", email, aal="aal2")
    assert client.get("/api/v1/admin/me", headers=cookie("root")).status_code == 200
    _admin_sql("UPDATE users SET is_platform_admin = true WHERE email = :e", {"e": email})
    from unitforma.identity.deps import clear_whoami_cache

    clear_whoami_cache()
    return cookie("root")


def _accept(client: TestClient, kratos: FakeKratos, who: str, email: str, base: str, body: dict):
    kratos.add(who, email)
    r = client.post(f"{base}/invitations", headers=cookie("admin_a"), json=body)
    assert r.status_code == 201, r.text
    token = r.json()["accept_url"].rsplit("/", 1)[1]
    r = client.post("/api/v1/admin/invitations/accept", headers=cookie(who), json={"token": token})
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module")
def world(kratos: FakeKratos, client: TestClient, platform_admin: dict) -> dict:
    """Tenant A with an admin and a project manager; tenant B with its own admin."""
    s = uuid.uuid4().hex[:6]
    kratos.add("admin_a", f"admin-{s}@a.example.com")
    r = client.post(
        "/api/v1/platform/tenants", headers=platform_admin, json={"slug": f"tok{s}", "name": "Tok"}
    )
    assert r.status_code == 201, r.text
    tenant_a = r.json()
    r = client.post(
        f"/api/v1/platform/tenants/{tenant_a['id']}/invitations",
        headers=platform_admin,
        params={"email": f"admin-{s}@a.example.com"},
    )
    token = r.json()["accept_url"].rsplit("/", 1)[1]
    r = client.post(
        "/api/v1/admin/invitations/accept", headers=cookie("admin_a"), json={"token": token}
    )
    assert r.status_code == 200, r.text
    base = f"/api/v1/admin/tenants/{tenant_a['id']}"
    _accept(
        client,
        kratos,
        "pm_a",
        f"pm-{s}@a.example.com",
        base,
        {
            "email": f"pm-{s}@a.example.com",
            "role": "project_manager",
            "all_projects": True,
            "project_ids": [],
        },
    )
    return {"a": tenant_a, "base": base}


def test_member_creates_a_token_and_sees_the_secret_once(client: TestClient, world: dict):
    r = client.post(
        f"{world['base']}/tokens",
        headers=cookie("pm_a"),
        json={"name": "Claude Code", "scope": "write", "expires_in_days": 30},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["secret"].startswith("ufm_") and len(body["secret"]) >= 40
    assert body["token_prefix"] == body["secret"][:12]
    assert body["scope"] == "write" and body["status"] == "active"
    # the row holds the hash and the prefix, never the secret
    rows = _admin_sql(
        "SELECT token_hash, token_prefix FROM api_tokens WHERE id = :id", {"id": body["id"]}
    )
    assert rows and rows[0][0] != body["secret"] and len(rows[0][0]) == 64
    assert rows[0][1] == body["token_prefix"]
    listed = client.get(f"{world['base']}/tokens", headers=cookie("pm_a")).json()
    assert [t["id"] for t in listed] == [body["id"]]
    assert "secret" not in listed[0]
    audit = _admin_sql(
        "SELECT action, after->>'token_prefix' FROM audit_log WHERE entity_type = 'api_token' "
        "AND entity_id = :id",
        {"id": body["id"]},
    )
    assert audit == [("create", body["token_prefix"])]


def test_admin_lists_every_token_members_only_their_own(client: TestClient, world: dict):
    r = client.post(
        f"{world['base']}/tokens", headers=cookie("admin_a"), json={"name": "Admin script"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["scope"] == "read"
    admin_view = client.get(f"{world['base']}/tokens", headers=cookie("admin_a")).json()
    pm_view = client.get(f"{world['base']}/tokens", headers=cookie("pm_a")).json()
    assert {t["name"] for t in admin_view} >= {"Claude Code", "Admin script"}
    assert {t["name"] for t in pm_view} == {"Claude Code"}
    assert all(t["user_email"] for t in admin_view)


def test_member_cannot_revoke_another_members_token_admin_can(client: TestClient, world: dict):
    admin_tokens = client.get(f"{world['base']}/tokens", headers=cookie("admin_a")).json()
    admins_own = next(t for t in admin_tokens if t["name"] == "Admin script")
    pms = next(t for t in admin_tokens if t["name"] == "Claude Code")
    r = client.delete(f"{world['base']}/tokens/{admins_own['id']}", headers=cookie("pm_a"))
    assert r.status_code == 404
    r = client.delete(f"{world['base']}/tokens/{pms['id']}", headers=cookie("admin_a"))
    assert r.status_code == 204
    after = client.get(f"{world['base']}/tokens", headers=cookie("pm_a")).json()
    assert after[0]["status"] == "revoked" and after[0]["revoked_at"]
    # revoking twice is idempotent and writes one audit row
    assert (
        client.delete(f"{world['base']}/tokens/{pms['id']}", headers=cookie("admin_a")).status_code
        == 204
    )
    audit = _admin_sql(
        "SELECT count(*) FROM audit_log WHERE entity_type = 'api_token' AND entity_id = :id "
        "AND action = 'revoke'",
        {"id": pms["id"]},
    )
    assert audit[0][0] == 1


def test_input_bounds(client: TestClient, world: dict):
    base = world["base"]
    assert (
        client.post(
            f"{base}/tokens", headers=cookie("pm_a"), json={"name": "x", "expires_in_days": 366}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{base}/tokens", headers=cookie("pm_a"), json={"name": "x", "scope": "admin"}
        ).status_code
        == 422
    )
    assert (
        client.post(f"{base}/tokens", headers=cookie("pm_a"), json={"name": "   "}).status_code
        == 422
    )


def test_platform_admin_holds_a_token_only_where_a_member(
    client: TestClient, world: dict, platform_admin: dict
):
    """ADR-0015 Decision 3: a token acts through a membership, so a platform admin without one
    is refused with the reason, and with one the token carries that membership's role."""
    base = world["base"]
    r = client.post(f"{base}/tokens", headers=platform_admin, json={"name": "root"})
    assert r.status_code == 403, r.text
    assert r.json()["title"] == "Not a member of this workspace"
    email = client.get("/api/v1/admin/me", headers=platform_admin).json()["email"]
    r = client.post(
        f"{base}/invitations",
        headers=cookie("admin_a"),
        json={"email": email, "role": "project_manager", "all_projects": True},
    )
    assert r.status_code == 201, r.text
    token = r.json()["accept_url"].rsplit("/", 1)[1]
    r = client.post(
        "/api/v1/admin/invitations/accept", headers=platform_admin, json={"token": token}
    )
    assert r.status_code == 200, r.text
    r = client.post(f"{base}/tokens", headers=platform_admin, json={"name": "root"})
    assert r.status_code == 201, r.text
    secret = r.json()["secret"]
    r = client.post(
        "/mcp",
        headers={
            "Authorization": f"Bearer {secret}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-06-18",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "whoami", "arguments": {}},
        },
    )
    assert r.status_code == 200, r.text
    me = r.json()["result"]["structuredContent"]
    assert me["role"] == "project_manager" and me["user_email"] == email


def test_tokens_are_tenant_scoped(client: TestClient, world: dict, platform_admin: dict, kratos):
    s = uuid.uuid4().hex[:6]
    kratos.add("admin_b", f"admin-{s}@b.example.com")
    r = client.post(
        "/api/v1/platform/tenants",
        headers=platform_admin,
        json={"slug": f"tokb{s}", "name": "B", "admin_email": f"admin-{s}@b.example.com"},
    )
    tenant_b = r.json()
    # tenant B's routes refuse tenant A's admin
    r = client.get(f"/api/v1/admin/tenants/{tenant_b['id']}/tokens", headers=cookie("admin_a"))
    assert r.status_code == 404
