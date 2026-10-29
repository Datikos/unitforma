"""ADR-0015 Phase 2: the MCP endpoint at /mcp. JSON-RPC over stateless Streamable HTTP with a
bearer API token: initialize, tools/list, the project and building tools, the read-only
refusal, the foreign-tenant 404, the audit origin, the 401 and 421 doors."""

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

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    "MCP-Protocol-Version": "2025-06-18",
}

TOOLS = {
    "whoami",
    "list_projects",
    "get_project",
    "create_project",
    "update_project",
    "list_buildings",
    "create_building",
    "update_building",
    "set_floors",
    "get_floor_proposal",
    "accept_floor_proposal_blocks",
    "list_site_features",
    "create_site_feature",
    # ADR-0028 Decision 6
    "find_units",
    "list_units",
    "get_unit",
    "list_documents",
    "request_render",
    "get_render",
    "list_renders",
    "list_layouts",
    "confirm_layout",
    "get_setup_checklist",
    "run_setup",
    "set_setup_auto",
    # ADR-0034: mapping and deletes
    "list_sheets",
    "set_sheet_floors",
    "calibrate_sheet",
    "exclude_pages",
    "suggest_outlines",
    "create_outline",
    "approve_sheet",
    "delete_floor",
    "delete_building",
    "delete_document",
}


def _admin_sql(sql: str, params: dict | None = None):
    eng = create_engine(os.environ["UF_TEST_DATABASE_ADMIN_URL"])
    with eng.begin() as conn:
        conn.execute(text("SELECT set_config('app.scope', 'platform', true)"))
        res = conn.execute(text(sql), params or {})
        rows = res.fetchall() if res.returns_rows else None
    eng.dispose()
    return rows


def rpc(client: TestClient, secret: str | None, method: str, params: dict | None = None, **extra):
    headers = dict(MCP_HEADERS)
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    headers.update(extra)
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return client.post("/mcp", headers=headers, json=body)


def call(client: TestClient, secret: str, tool: str, arguments: dict | None = None) -> dict:
    r = rpc(client, secret, "tools/call", {"name": tool, "arguments": arguments or {}})
    assert r.status_code == 200, r.text
    return r.json()["result"]


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


def _tenant(client, kratos, platform_admin, who: str, slug: str) -> tuple[dict, str]:
    s = uuid.uuid4().hex[:6]
    email = f"{who}-{s}@example.com"
    kratos.add(who, email)
    r = client.post(
        "/api/v1/platform/tenants",
        headers=platform_admin,
        json={"slug": f"{slug}{s}", "name": slug},
    )
    assert r.status_code == 201, r.text
    tenant = r.json()
    r = client.post(
        f"/api/v1/platform/tenants/{tenant['id']}/invitations",
        headers=platform_admin,
        params={"email": email},
    )
    token = r.json()["accept_url"].rsplit("/", 1)[1]
    r = client.post("/api/v1/admin/invitations/accept", headers=cookie(who), json={"token": token})
    assert r.status_code == 200, r.text
    return tenant, f"/api/v1/admin/tenants/{tenant['id']}"


@pytest.fixture(scope="module")
def world(kratos: FakeKratos, client: TestClient, platform_admin: dict) -> dict:
    """Tenant A: admin with a write token and a read token, a sales member restricted to one
    project with a write token; tenant B with one project."""
    tenant_a, base_a = _tenant(client, kratos, platform_admin, "admin_a", "mcpa")
    tenant_b, base_b = _tenant(client, kratos, platform_admin, "admin_b", "mcpb")
    p1 = client.post(
        f"{base_a}/projects",
        headers=cookie("admin_a"),
        json={"slug": "riverside", "name": "Riverside"},
    ).json()
    p2 = client.post(
        f"{base_a}/projects", headers=cookie("admin_a"), json={"slug": "hilltop", "name": "Hilltop"}
    ).json()
    pb = client.post(
        f"{base_b}/projects", headers=cookie("admin_b"), json={"slug": "other", "name": "Other"}
    ).json()
    s = uuid.uuid4().hex[:6]
    sales_email = f"sales-{s}@example.com"
    kratos.add("sales_a", sales_email)
    r = client.post(
        f"{base_a}/invitations",
        headers=cookie("admin_a"),
        json={
            "email": sales_email,
            "role": "sales",
            "all_projects": False,
            "project_ids": [p1["id"]],
        },
    )
    token = r.json()["accept_url"].rsplit("/", 1)[1]
    assert (
        client.post(
            "/api/v1/admin/invitations/accept", headers=cookie("sales_a"), json={"token": token}
        ).status_code
        == 200
    )

    def mk(who: str, scope: str) -> dict:
        r = client.post(
            f"{base_a}/tokens", headers=cookie(who), json={"name": f"{who}-{scope}", "scope": scope}
        )
        assert r.status_code == 201, r.text
        return r.json()

    return {
        "a": tenant_a,
        "base": base_a,
        "p1": p1,
        "p2": p2,
        "pb": pb,
        "write": mk("admin_a", "write"),
        "read": mk("admin_a", "read"),
        "sales": mk("sales_a", "write"),
    }


def test_no_bearer_is_401_with_challenge(client: TestClient, world: dict):
    r = rpc(client, None, "initialize")
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith("Bearer")
    assert rpc(client, "ufm_not-a-token", "initialize").status_code == 401


def test_wrong_host_never_reaches_the_staff_server(client: TestClient, world: dict):
    """ADR-0034 Decision 5: a host that is not the admin host is a portal host; the staff
    server (and the token) are not consulted there, the anonymous read-only portal server is."""
    r = rpc(client, world["write"]["secret"], "tools/list", Host="evil.example")
    assert r.status_code == 200, r.text
    assert "whoami" not in {t["name"] for t in r.json()["result"]["tools"]}
    r = rpc(
        client,
        world["write"]["secret"],
        "tools/call",
        {"name": "site", "arguments": {}},
        Host="evil.example",
    )
    assert r.status_code == 200 and r.json()["result"]["isError"] is True
    assert "not configured" in r.json()["result"]["content"][0]["text"].lower()


def test_initialize_and_tools_list(client: TestClient, world: dict):
    r = rpc(
        client,
        world["read"]["secret"],
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["result"]["serverInfo"]["name"] == "Unitforma"
    r = rpc(client, world["read"]["secret"], "tools/list")
    assert r.status_code == 200, r.text
    tools = {t["name"]: t for t in r.json()["result"]["tools"]}
    assert set(tools) == TOOLS
    assert (
        "version" in tools["update_project"]["inputSchema"]["$defs"]["ProjectUpdate"]["properties"]
    )


def test_whoami_and_project_restriction(client: TestClient, world: dict):
    me = call(client, world["sales"]["secret"], "whoami")["structuredContent"]
    assert me["tenant_slug"] == world["a"]["slug"]
    assert me["role"] == "sales" and me["token_scope"] == "write"  # noqa: S105 - not a secret
    assert me["all_projects"] is False and me["project_ids"] == [world["p1"]["id"]]
    listed = call(client, world["sales"]["secret"], "list_projects")["structuredContent"]["result"]
    assert [p["slug"] for p in listed] == ["riverside"]
    admin_listed = call(client, world["write"]["secret"], "list_projects")["structuredContent"][
        "result"
    ]
    assert {p["slug"] for p in admin_listed} == {"riverside", "hilltop"}


def test_read_token_cannot_write(client: TestClient, world: dict):
    res = call(
        client,
        world["read"]["secret"],
        "create_project",
        {"project": {"slug": "nope", "name": "Nope"}},
    )
    assert res["isError"] is True
    assert "read-only" in res["content"][0]["text"]
    assert not _admin_sql("SELECT 1 FROM projects WHERE slug = 'nope'")


def test_role_matrix_applies(client: TestClient, world: dict):
    """A sales member's write token still cannot create projects (project WRITE is not theirs)."""
    res = call(
        client,
        world["sales"]["secret"],
        "create_project",
        {"project": {"slug": "sales-made", "name": "x"}},
    )
    assert res["isError"] is True and "Not allowed" in res["content"][0]["text"]


def test_create_project_building_floors_with_audit_origin(client: TestClient, world: dict):
    secret = world["write"]["secret"]
    created = call(
        client,
        secret,
        "create_project",
        {"project": {"slug": "mcp-made", "name": "Made by MCP", "address": {"city": "Tbilisi"}}},
    )
    assert created.get("isError") is not True, created
    project = created["structuredContent"]
    assert project["slug"] == "mcp-made" and project["version"] == 1
    audit = _admin_sql(
        "SELECT request_id, actor_role FROM audit_log WHERE entity_type = 'project' "
        "AND entity_id = :id AND action = 'create'",
        {"id": project["id"]},
    )
    assert audit == [(f"mcp:{world['write']['token_prefix']}", "tenant_admin")]

    building = call(
        client,
        secret,
        "create_building",
        {"project_id": project["id"], "building": {"code": "A", "name": "Block A"}},
    )["structuredContent"]
    assert building["code"] == "A" and building["floors"] == []
    floors = call(
        client,
        secret,
        "set_floors",
        {
            "building_id": building["id"],
            "floors": [
                {"level": 0, "display_name": "Ground", "height_m": "3.2"},
                {"level": 1, "display_name": "1", "height_m": None},
            ],
        },
    )["structuredContent"]["result"]
    assert [f["level"] for f in floors] == [0, 1]
    assert float(floors[0]["height_m"]) == 3.2 and floors[1]["height_m"] is None
    buildings = call(client, secret, "list_buildings", {"project_id": project["id"]})
    codes = {b["code"]: b for b in buildings["structuredContent"]["result"]}
    assert set(codes) == {"SITE", "A"} and len(codes["A"]["floors"]) == 2

    updated = call(
        client,
        secret,
        "update_building",
        {
            "building_id": building["id"],
            "changes": {"construction_status": "planned", "version": codes["A"]["version"]},
        },
    )["structuredContent"]
    assert updated["construction_status"] == "planned"
    stale = call(
        client,
        secret,
        "update_project",
        {"project_id": project["id"], "changes": {"name": "Renamed", "version": 99}},
    )
    assert stale["isError"] is True and "version" in stale["content"][0]["text"]
    # through the admin API the same project is visible with the same version
    r = client.get(f"{world['base']}/projects/{project['id']}", headers=cookie("admin_a"))
    assert r.status_code == 200 and r.json()["name"] == "Made by MCP"


def test_foreign_tenant_project_is_not_found(client: TestClient, world: dict):
    res = call(client, world["write"]["secret"], "get_project", {"project_id": world["pb"]["id"]})
    assert res["isError"] is True and "Project not found" in res["content"][0]["text"]
    res = call(client, world["sales"]["secret"], "get_project", {"project_id": world["p2"]["id"]})
    assert res["isError"] is True and "Project not found" in res["content"][0]["text"]


def test_revoked_and_expired_tokens_are_refused_on_the_next_call(client: TestClient, world: dict):
    r = client.post(f"{world['base']}/tokens", headers=cookie("admin_a"), json={"name": "short"})
    t = r.json()
    assert call(client, t["secret"], "whoami")["structuredContent"]["role"] == "tenant_admin"
    assert (
        client.delete(f"{world['base']}/tokens/{t['id']}", headers=cookie("admin_a")).status_code
        == 204
    )
    assert rpc(client, t["secret"], "tools/list").status_code == 401
    r = client.post(f"{world['base']}/tokens", headers=cookie("admin_a"), json={"name": "old"})
    t = r.json()
    _admin_sql(
        "UPDATE api_tokens SET expires_at = now() - interval '1 minute' WHERE id = :id",
        {"id": t["id"]},
    )
    assert rpc(client, t["secret"], "tools/list").status_code == 401
    listed = client.get(f"{world['base']}/tokens", headers=cookie("admin_a")).json()
    assert next(x for x in listed if x["id"] == t["id"])["status"] == "expired"


def test_suspended_member_is_refused(client: TestClient, world: dict):
    members = client.get(f"{world['base']}/members", headers=cookie("admin_a")).json()
    sales = next(m for m in members if m["role"] == "sales")
    client.patch(
        f"{world['base']}/members/{sales['id']}",
        headers=cookie("admin_a"),
        json={"status": "suspended"},
    )
    res = call(client, world["sales"]["secret"], "whoami")
    assert res["isError"] is True and "Tenant not found" in res["content"][0]["text"]
    client.patch(
        f"{world['base']}/members/{sales['id']}",
        headers=cookie("admin_a"),
        json={"status": "active"},
    )
    assert call(client, world["sales"]["secret"], "whoami")["structuredContent"]["role"] == "sales"


def test_mcp_path_is_outside_the_cookie_csrf_regime(client: TestClient, world: dict):
    """No X-Requested-With needed: the endpoint never accepts a cookie."""
    headers = {
        **MCP_HEADERS,
        "Authorization": f"Bearer {world['read']['secret']}",
        "X-Requested-With": "other",
    }
    r = client.post(
        "/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    )
    assert r.status_code == 200
    r = client.post(
        "/mcp",
        headers={**MCP_HEADERS, "Cookie": "ory_kratos_session=admin_a"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert r.status_code == 401
