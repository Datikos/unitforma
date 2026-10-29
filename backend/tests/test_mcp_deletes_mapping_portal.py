"""ADR-0034 through the MCP endpoint on the publishing world: the mapping tools do what the
sheet editor does with its rights, the delete tools need the confirmation argument and keep the
services' guards, and the portal hosts answer an anonymous read-only server."""

from __future__ import annotations

import pytest

from tests import test_phase4_publishing as phase4
from tests.pdf_fixture import make_plan_pdf
from tests.test_mcp_server import call, rpc
from tests.test_phase4_publishing import world  # noqa: F401 - module-scoped fixture, rebuilt here

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
    }


def _ok(res: dict) -> dict:
    assert res.get("isError") is not True, res
    return res["structuredContent"]


def _list(res: dict) -> list:
    """A list-returning tool comes back wrapped as ``{"result": [...]}``."""
    sc = _ok(res)
    return sc["result"] if isinstance(sc, dict) and "result" in sc else sc


def _error(res: dict) -> str:
    assert res["isError"] is True, res
    return res["content"][0]["text"]


# --------------------------------------------------------------------------- mapping tools
@pytest.fixture(scope="module")
def plan_sheets(client, world) -> list[dict]:  # noqa: F811
    """A fresh two-page plan set under building A, processed, not yet mapped."""
    b = client.get(
        f"{world['base']}/projects/{world['project']['id']}/buildings", headers=world["adm"]
    ).json()
    bid = next(x["id"] for x in b if x["code"] == "A")
    return phase4._upload(
        client,
        world["base"],
        world["adm"],
        world["project"]["id"],
        "floor_plan",
        "Plans MCP",
        make_plan_pdf(),
        world["tenant"]["id"],
        bid,
    )


def test_mapping_tools_map_a_sheet_end_to_end(client, world, tokens, plan_sheets):  # noqa: F811
    base, adm = world["base"], tokens["adm"]
    bid = client.get(
        f"{base}/projects/{world['project']['id']}/buildings", headers=world["adm"]
    ).json()
    building = next(x for x in bid if x["code"] == "A")
    floors = {f["level"]: f for f in building["floors"]}
    rev = plan_sheets[0]["revision_id"]

    sheets = _list(call(client, adm, "list_sheets", {"revision_id": rev}))
    assert [s["page_no"] for s in sheets] == [1, 2]
    s1 = sheets[0]
    assert s1["calibration_status"] == "none"
    assert all(a["status"] == "suggested" for a in s1["floors"])  # level marker +0.00 → Ground
    assert s1["raster_url"] and s1["thumbnail_url"]

    out = _ok(
        call(
            client,
            adm,
            "set_sheet_floors",
            {
                "sheet_id": s1["id"],
                "floors": [{"floor_id": floors[0]["id"]}],
                "version": s1["version"],
            },
        )
    )
    assert [a["floor_id"] for a in out["floors"]] == [floors[0]["id"]]
    assert out["floors"][0]["status"] == "confirmed"

    out = _ok(
        call(
            client,
            adm,
            "calibrate_sheet",
            {
                "sheet_id": s1["id"],
                "p1": [100 / phase4.W, 1 - 200 / phase4.H],
                "p2": [400 / phase4.W, 1 - 200 / phase4.H],
                "distance_m": 15,
                "version": out["version"],
            },
        )
    )
    assert out["calibration_status"] == "calibrated" and out["calibration"]["m_per_px"] > 0

    sugg = _list(call(client, adm, "suggest_outlines", {"sheet_id": s1["id"]}))
    assert isinstance(sugg, list) and sugg, sugg
    best = max(sugg, key=lambda c: c["confidence"])
    assert best["floor_id"] == floors[0]["id"]

    created = _ok(
        call(
            client,
            adm,
            "create_outline",
            {
                "sheet_id": s1["id"],
                "ring": best["ring"],
                "label": best["label"],
                "printed_area_m2": best["printed_area_m2"],
                "unit_type": "apartment",
            },
        )
    )
    assert (
        created["unit"]["lifecycle_status"] == "draft"
        and created["boundary"]["sheet_id"] == s1["id"]
    )
    assert created["unit"]["floor_id"] == floors[0]["id"]

    # sales holds mapping read only: no approval through a token either
    assert "Not allowed" in _error(
        call(client, tokens["sales"], "approve_sheet", {"sheet_id": s1["id"]})
    )
    approved = _ok(call(client, adm, "approve_sheet", {"sheet_id": s1["id"]}))
    assert approved["approved_units"] == 1
    unit = client.get(f"{base}/units/{created['unit']['id']}", headers=world["adm"]).json()
    assert unit["lifecycle_status"] == "active" and unit["verification_status"] == "verified"

    out = _list(
        call(client, adm, "exclude_pages", {"revision_id": rev, "pages": [2], "reason": "reprint"})
    )
    assert next(s for s in out if s["page_no"] == 2)["excluded"] is True
    assert "No such pages" in _error(
        call(client, adm, "exclude_pages", {"revision_id": rev, "pages": [9]})
    )


def _building(client, world, code: str) -> dict | None:  # noqa: F811
    rows = client.get(
        f"{world['base']}/projects/{world['project']['id']}/buildings", headers=world["adm"]
    ).json()
    return next((b for b in rows if b["code"] == code), None)


# --------------------------------------------------------------------------- delete tools
def test_delete_tools_need_the_confirmation_and_keep_the_guards(client, world, tokens):  # noqa: F811
    base, adm = world["base"], tokens["adm"]
    pid = world["project"]["id"]
    z = client.post(
        f"{base}/projects/{pid}/buildings",
        headers=world["adm"],
        json={"code": "Z", "name": "Spare"},
    ).json()
    floors = client.put(
        f"{base}/buildings/{z['id']}/floors",
        headers=world["adm"],
        json={
            "floors": [{"level": 0, "display_name": "Ground"}, {"level": 1, "display_name": "1"}]
        },
    ).json()
    ground = next(f for f in floors if f["level"] == 0)

    # wrong confirmation: nothing happens, the expected value is named
    msg = _error(
        call(
            client,
            adm,
            "delete_floor",
            {"building_id": z["id"], "floor_id": ground["id"], "confirm": "0"},
        )
    )
    assert "confirm='Ground'" in msg
    assert len(_building(client, world, "Z")["floors"]) == 2
    out = _ok(
        call(
            client,
            adm,
            "delete_floor",
            {"building_id": z["id"], "floor_id": ground["id"], "confirm": "Ground"},
        )
    )
    assert out == {
        "kind": "floor",
        "id": ground["id"],
        "name": "Ground",
        "detached_units": 0,
        "note": None,
    }
    assert [f["level"] for f in _building(client, world, "Z")["floors"]] == [1]

    # a building with units keeps ADR-0012's guard; the empty one goes with its code
    a = next(
        b
        for b in client.get(f"{base}/projects/{pid}/buildings", headers=world["adm"]).json()
        if b["code"] == "A"
    )
    assert (
        "units"
        in _error(
            call(client, adm, "delete_building", {"building_id": a["id"], "confirm": "A"})
        ).lower()
    )
    assert "confirm='Z'" in _error(
        call(client, adm, "delete_building", {"building_id": z["id"], "confirm": "z "})
    )
    out = _ok(call(client, adm, "delete_building", {"building_id": z["id"], "confirm": "Z"}))
    assert out["kind"] == "building" and out["name"] == "Z"
    assert _building(client, world, "Z") is None

    # a document: the title confirms; a mapped one needs detach_units
    docs = client.get(f"{base}/projects/{pid}/documents", headers=world["adm"]).json()
    mapped = next(d for d in docs if d["title"] == "Plans MCP")
    assert (
        "detach"
        in _error(
            call(
                client,
                adm,
                "delete_document",
                {"document_id": mapped["id"], "confirm": "Plans MCP"},
            )
        ).lower()
    )
    spare = client.post(
        f"{base}/projects/{pid}/documents",
        headers=world["adm"],
        json={"kind": "other", "title": "Spare letter"},
    ).json()
    assert "confirm='Spare letter'" in _error(
        call(client, adm, "delete_document", {"document_id": spare["id"], "confirm": "spare"})
    )
    out = _ok(
        call(
            client, adm, "delete_document", {"document_id": spare["id"], "confirm": "Spare letter"}
        )
    )
    assert out["kind"] == "document" and out["detached_units"] == 0
    assert all(
        d["id"] != spare["id"]
        for d in client.get(f"{base}/projects/{pid}/documents", headers=world["adm"]).json()
    )
    # delete_project is deliberately not a tool
    assert "delete_project" not in {
        t["name"] for t in rpc(client, adm, "tools/list").json()["result"]["tools"]
    }


# --------------------------------------------------------------------------- the portal server
@pytest.fixture(scope="module")
def published(client, world) -> dict:  # noqa: F811
    """The world prepares riverside; marking the units and publishing are test steps there,
    so they happen here (every approved unit, as the project manager)."""
    r = client.put(
        f"{world['base']}/projects/{world['project']['id']}/units/publication",
        headers=world["pm"],
        json={"status": "published", "all_active": True},
    )
    assert r.status_code == 200, r.text
    r = client.post(
        f"{world['base']}/projects/{world['project']['id']}/publications",
        headers=world["pm"],
        json={"mode": "publish"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_portal_host_answers_a_read_only_server_without_a_token(client, world, published):  # noqa: F811
    host = world["host"]
    r = rpc(client, None, "tools/list", **{"Host": host})
    assert r.status_code == 200, r.text
    tools = {t["name"]: t for t in r.json()["result"]["tools"]}
    assert set(tools) == {"site", "get_project", "list_units", "get_unit", "list_layouts"}
    assert all(t["annotations"]["readOnlyHint"] is True for t in tools.values())

    def pcall(tool: str, args: dict | None = None) -> dict:
        res = rpc(
            client, None, "tools/call", {"name": tool, "arguments": args or {}}, **{"Host": host}
        )
        assert res.status_code == 200, res.text
        return res.json()["result"]

    site = _ok(pcall("site"))
    assert site["tenant"]["name"] == "Riverside Homes"
    assert any(p["slug"] == "riverside" for p in site["projects"]), site
    doc = _ok(pcall("get_project", {"slug": "riverside"}))
    assert doc["project"]["slug"] == "riverside" and doc["buildings"]
    units = _ok(
        pcall("list_units", {"slug": "riverside", "availability": ["available"], "limit": 10})
    )
    assert units["total"] >= 1 and all(u["availability"] == "available" for u in units["items"])
    one = _ok(pcall("get_unit", {"slug": "riverside", "code": "a-00-01"}))
    assert one["code"] == "A-00-01"
    assert "SECRET" not in str(one) and "SECRET" not in str(doc)
    layouts = _ok(pcall("list_layouts", {"slug": "riverside"}))
    assert "items" in layouts
    # an unpublished project is not there, and the preview path does not exist here
    assert "not published" in _error(pcall("get_project", {"slug": "hilltop"})).lower()


def test_portal_server_refuses_unknown_hosts_and_foreign_origins(client, world, published):  # noqa: F811
    r = rpc(
        client,
        None,
        "tools/call",
        {"name": "site", "arguments": {}},
        **{"Host": "nobody.example.net"},
    )
    assert r.status_code == 200 and "not configured" in _error(r.json()["result"]).lower()
    r = rpc(client, None, "tools/list", **{"Host": world["host"], "Origin": "https://evil.example"})
    assert r.status_code == 403
    r = rpc(
        client, None, "tools/list", **{"Host": world["host"], "Origin": f"https://{world['host']}"}
    )
    assert r.status_code == 200
    # X-Forwarded-Host (set by Caddy) wins over the upstream Host, as for the portal API
    r = rpc(client, None, "tools/list", **{"Host": "api:8000", "X-Forwarded-Host": world["host"]})
    assert r.status_code == 200 and "site" in {t["name"] for t in r.json()["result"]["tools"]}
    # the staff server on the default (admin-side) host still wants a bearer
    assert rpc(client, None, "tools/list").status_code == 401
