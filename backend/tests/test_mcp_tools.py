"""The tools ADR-0028 Decision 6 added to the MCP server (#C2, #C3), through the ASGI app on the
publishing world: four outlined units on two floors, documents, an admin and a sales member.

What they prove: units are found by the codes a person types; a list pages; documents come
without page text; a render request keeps the service's rules (same floor) and a read token
cannot request one; a proposed plan type is confirmed with the token's audit origin; the setup
checklist, the switch and "Run now" keep the admin API's rights.
"""

from __future__ import annotations

import uuid

import pytest

from tests import test_phase4_publishing as phase4
from tests.test_mcp_server import call
from tests.test_phase4_publishing import world  # noqa: F401 - module-scoped fixture, rebuilt here
from unitforma.api.schemas import DocumentOut
from unitforma.core.settings import get_settings

pytestmark = phase4.pytestmark


def _token(client, world, who: str, scope: str) -> str:  # noqa: F811
    r = client.post(
        f"{world['base']}/tokens",
        headers=world[who],
        json={"name": f"{who}-{scope}", "scope": scope, "expires_in_days": 1},
    )
    assert r.status_code == 201, r.text
    return r.json()["secret"]


@pytest.fixture(scope="module")
def tokens(client, world) -> dict:  # noqa: F811
    return {
        "adm": _token(client, world, "adm", "write"),
        "sales": _token(client, world, "sales", "write"),
        "sales_read": _token(client, world, "sales", "read"),
    }


def _ok(res: dict) -> dict:
    assert res.get("isError") is not True, res
    return res["structuredContent"]


def _error(res: dict) -> str:
    assert res["isError"] is True, res
    return res["content"][0]["text"]


def test_find_units_by_typed_codes_and_by_query(client, world, tokens):  # noqa: F811
    pid = world["project"]["id"]
    res = _ok(
        call(
            client,
            tokens["sales"],
            "find_units",
            {"project_id": pid, "codes": ["a 00 01", "A-01-02", "Z9"]},
        )
    )
    assert sorted(u["code"] for u in res["items"]) == ["A-00-01", "A-01-02"]
    assert res["not_found"] == ["Z9"]
    a1 = next(u for u in res["items"] if u["code"] == "A-00-01")
    assert a1["building_code"] == "A" and a1["floor_level"] == 0
    assert a1["list_price"] == "180000.00" and a1["currency"] == "EUR"
    res = _ok(call(client, tokens["sales"], "find_units", {"project_id": pid, "query": "a01"}))
    assert sorted(u["code"] for u in res["items"]) == ["A-01-01", "A-01-02"]
    assert "codes" in _error(call(client, tokens["sales"], "find_units", {"project_id": pid}))


def test_list_units_pages_and_filters(client, world, tokens):  # noqa: F811
    pid = world["project"]["id"]
    page = _ok(call(client, tokens["sales_read"], "list_units", {"project_id": pid, "limit": 3}))
    assert page["total"] == 4 and len(page["items"]) == 3
    rest = _ok(
        call(
            client,
            tokens["sales_read"],
            "list_units",
            {"project_id": pid, "limit": 3, "offset": 3},
        )
    )
    assert len(rest["items"]) == 1
    codes = [u["code"] for u in page["items"] + rest["items"]]
    assert sorted(codes) == ["A-00-01", "A-00-02", "A-01-01", "A-01-02"]
    sold = _ok(
        call(
            client,
            tokens["sales_read"],
            "list_units",
            {"project_id": pid, "availability": "sold"},
        )
    )
    assert [u["code"] for u in sold["items"]] == ["A-01-01"]
    floor0 = next(u["floor_id"] for u in page["items"] + rest["items"] if u["floor_level"] == 0)
    on_floor = _ok(
        call(
            client,
            tokens["sales_read"],
            "list_units",
            {"project_id": pid, "floor_id": floor0},
        )
    )
    assert on_floor["total"] == 2
    unit = _ok(
        call(client, tokens["sales_read"], "get_unit", {"unit_id": world["units"]["A-00-02"]["id"]})
    )
    assert unit["code"] == "A-00-02" and unit["list_price"] == "260000.00"
    # a foreign project id is refused like the admin API refuses it
    assert "not found" in _error(
        call(client, tokens["sales_read"], "list_units", {"project_id": str(uuid.uuid4())})
    )


def test_list_documents_carries_metadata_never_page_text(client, world, tokens):  # noqa: F811
    docs = _ok(
        call(client, tokens["sales_read"], "list_documents", {"project_id": world["project"]["id"]})
    )["result"]
    assert {d["kind"] for d in docs} >= {"floor_plan", "site_plan"}
    for d in docs:
        assert set(d) == set(DocumentOut.model_fields)
        assert not any("text" in k for k in d) and not any(
            "text" in k for k in d["current_revision"]
        )


def test_render_request_keeps_the_service_rules(client, world, tokens, monkeypatch):  # noqa: F811
    units = world["units"]
    ground_a, ground_b, first = units["A-00-01"], units["A-00-02"], units["A-01-01"]
    # off by default: the service's 409 reaches the assistant as a tool error
    msg = _error(call(client, tokens["sales"], "request_render", {"unit_id": ground_a["id"]}))
    assert "not configured" in msg
    monkeypatch.setattr(get_settings(), "ai_image_provider", "gemini")
    monkeypatch.setattr(get_settings(), "ai_image_daily_limit", 5)
    msg = _error(
        call(
            client,
            tokens["sales"],
            "request_render",
            {"unit_id": ground_a["id"], "with_unit_id": first["id"]},
        )
    )
    assert msg.endswith(": The joined unit must be on the same floor")  # the service's 422 text
    assert "read-only" in _error(
        call(client, tokens["sales_read"], "request_render", {"unit_id": ground_a["id"]})
    )
    r = _ok(
        call(
            client,
            tokens["sales"],
            "request_render",
            {"unit_id": ground_a["id"], "with_unit_id": ground_b["id"], "note": "oak floors"},
        )
    )
    assert r["status"] == "queued" and r["partner_code"] == "A-00-02" and r["note"] == "oak floors"
    got = _ok(call(client, tokens["sales_read"], "get_render", {"render_id": r["id"]}))
    assert got["id"] == r["id"] and got["partner_code"] == "A-00-02" and got["url"] is None
    listed = _ok(call(client, tokens["sales_read"], "list_renders", {"unit_id": ground_a["id"]}))
    assert listed["enabled"] is True and [i["id"] for i in listed["items"]] == [r["id"]]
    audit = phase4._admin_sql(
        "SELECT request_id FROM audit_log WHERE entity_id = :id AND action = 'request'",
        {"id": r["id"]},
    )
    assert audit and audit[0][0].startswith("mcp:ufm_")


def test_confirm_a_proposed_layout(client, world, tokens):  # noqa: F811
    pid, tid = world["project"]["id"], world["tenant"]["id"]
    [(lid,)] = phase4._admin_sql(
        "INSERT INTO unit_layouts (id, tenant_id, project_id, code, name, status, source, version)"
        " VALUES (gen_random_uuid(), :t, :p, 'MCP1', NULL, 'proposed', 'autopilot', 1)"
        " RETURNING id",
        {"t": tid, "p": pid},
    )
    lays = _ok(call(client, tokens["sales_read"], "list_layouts", {"project_id": pid}))["result"]
    assert next(x for x in lays if x["code"] == "MCP1")["status"] == "proposed"
    assert "read-only" in _error(
        call(client, tokens["sales_read"], "confirm_layout", {"layout_id": str(lid)})
    )
    done = _ok(call(client, tokens["sales"], "confirm_layout", {"layout_id": str(lid)}))
    assert done["status"] == "confirmed" and done["version"] == 2
    again = _ok(call(client, tokens["sales"], "confirm_layout", {"layout_id": str(lid)}))
    assert again["version"] == 2  # idempotent, as the annotation says
    audit = phase4._admin_sql(
        "SELECT request_id FROM audit_log WHERE entity_type = 'unit_layout' AND entity_id = :id"
        " AND action = 'confirm'",
        {"id": str(lid)},
    )
    assert len(audit) == 1 and audit[0][0].startswith("mcp:ufm_")


def test_setup_tools_keep_the_admin_api_rights(client, world, tokens):  # noqa: F811
    pid = world["project"]["id"]
    setup = _ok(call(client, tokens["sales_read"], "get_setup_checklist", {"project_id": pid}))
    assert setup["steps"] and "auto" in setup and "decisions" in setup
    # sales may read a project but not change it: the role matrix applies unchanged
    assert "Not allowed" in _error(
        call(client, tokens["sales"], "set_setup_auto", {"project_id": pid, "enabled": True})
    )
    assert "Not allowed" in _error(call(client, tokens["sales"], "run_setup", {"project_id": pid}))
    assert "read-only" in _error(
        call(client, tokens["sales_read"], "run_setup", {"project_id": pid})
    )
    auto = _ok(
        call(
            client,
            tokens["adm"],
            "set_setup_auto",
            {"project_id": pid, "enabled": True, "approve_sheets": False},
        )
    )
    assert auto["enabled"] is True and auto["approve_sheets"] is False
    assert auto["publish_defaults"] is False  # not touched by the tool
    run = _ok(call(client, tokens["adm"], "run_setup", {"project_id": pid}))
    assert run["status"] == "queued"
    off = _ok(
        call(
            client,
            tokens["adm"],
            "set_setup_auto",
            {"project_id": pid, "enabled": False, "approve_sheets": False},
        )
    )
    assert off["enabled"] is False
