"""The layout registry (ADR-0022): codes unique per project without case, units linked by code
and refused for unknown codes, a rename that follows into every member, delete refused then forced,
media owned by the layout, a generated render cropped from a member and owned by the layout, and
the snapshot merge (own media first, then the layout's, the hero rule, internal items kept out)."""

from __future__ import annotations

import json
import uuid

from tests import test_phase4_publishing as phase4
from tests.test_phase4_publishing import H_, world  # noqa: F401 - module-scoped fixture
from tests.test_unit_renders import _Stub
from unitforma.core.settings import get_settings
from unitforma.renders import jobs as render_jobs

pytestmark = phase4.pytestmark


def _link(client, base, headers, unit_id: str, code: str | None):
    row = client.get(f"{base}/units/{unit_id}/sales", headers=headers).json()
    return client.patch(
        f"{base}/units/{unit_id}/sales",
        headers=headers,
        json={"layout": code, "version": row["version"]},
    )


def _upload(client, base, headers, layout_id: str, name: str, public: bool, kind="photo"):
    m = client.post(
        f"{base}/layouts/{layout_id}/media",
        headers=headers,
        json={
            "file_name": name,
            "content_type": "image/png",
            "byte_size": 8,
            "is_public": public,
            "kind": kind,
        },
    )
    assert m.status_code == 201, m.text
    m = m.json()
    client.put(m["upload_url"], content=b"\x89PNG\r\n\x1a\n", headers={"Content-Type": "image/png"})
    r = client.post(f"{base}/media/{m['media']['id']}/complete", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_registry_codes_links_rename_and_delete(client, world):  # noqa: F811
    base, pid, sales = world["base"], world["project"]["id"], world["sales"]
    units = world["units"]
    a, b = units["A-01-01"]["id"], units["A-01-02"]["id"]

    r = client.post(f"{base}/projects/{pid}/layouts", headers=sales, json={"code": " T3 "})
    assert r.status_code == 201, r.text
    lay = r.json()
    assert lay["code"] == "T3" and lay["name"] is None and lay["units"] == []
    assert lay["media_count"] == 0 and lay["cover_url"] is None
    # unique without case; blank refused
    assert (
        client.post(
            f"{base}/projects/{pid}/layouts", headers=sales, json={"code": "t3"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{base}/projects/{pid}/layouts", headers=sales, json={"code": "  "}
        ).status_code
        == 422
    )

    # a unit links by code in any case and reads the registry's spelling; unknown codes are refused
    r = _link(client, base, sales, a, "t3")
    assert r.status_code == 200 and r.json()["layout"] == "T3", r.text
    assert r.json()["layout_id"] == lay["id"]
    r = _link(client, base, sales, b, "T9")
    assert r.status_code == 422 and "registry" in r.json()["detail"], r.text
    listed = client.get(f"{base}/projects/{pid}/layouts", headers=sales).json()
    t3 = next(x for x in listed if x["id"] == lay["id"])
    assert [u["code"] for u in t3["units"]] == ["A-01-01"]
    assert t3["units"][0]["availability"] in ("available", "reserved", "sold", "withdrawn")

    # a rename follows into the member (the mirror and the inventory row)
    r = client.patch(
        f"{base}/layouts/{lay['id']}",
        headers=sales,
        json={"code": "T3b", "name": "Three rooms", "version": lay["version"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["code"] == "T3b" and r.json()["name"] == "Three rooms"
    row = client.get(f"{base}/units/{a}/sales", headers=sales).json()
    assert row["layout"] == "T3b" and row["layout_name"] == "Three rooms"
    assert (
        client.patch(
            f"{base}/layouts/{lay['id']}",
            headers=sales,
            json={"name": "x", "version": lay["version"]},
        ).status_code
        == 409
    )  # stale version

    # delete refuses while a unit links to it; forced, the unit is unlinked and the code is gone
    r = client.delete(f"{base}/layouts/{lay['id']}", headers=sales)
    assert r.status_code == 409 and r.json()["units"] == ["A-01-01"], r.text
    assert r.json()["type"].endswith("layout-in-use")
    r = client.delete(f"{base}/layouts/{lay['id']}?unlink_units=true", headers=sales)
    assert r.status_code == 204, r.text
    row = client.get(f"{base}/units/{a}/sales", headers=sales).json()
    assert row["layout"] is None and row["layout_id"] is None
    assert client.get(f"{base}/layouts/{lay['id']}", headers=sales).status_code == 404


def test_layout_media_and_a_layout_render_from_a_member(client, world, monkeypatch):  # noqa: F811
    base, pid, tid, sales = (
        world["base"],
        world["project"]["id"],
        world["tenant"]["id"],
        world["sales"],
    )
    units = world["units"]
    lay = client.post(
        f"{base}/projects/{pid}/layouts", headers=sales, json={"code": "R2", "name": "Corner"}
    ).json()
    # A-01-02 is a member without an outline on a processed sheet; A-01-01 has one
    for code in ("A-01-02", "A-01-01"):
        assert _link(client, base, sales, units[code]["id"], "R2").status_code == 200

    pub = _upload(client, base, sales, lay["id"], "r2-public.png", True, kind="interior_render")
    priv = _upload(client, base, sales, lay["id"], "SECRET-LAYOUT-7a1.png", False)
    assert pub["layout_id"] == lay["id"] and pub["unit_id"] is None
    items = client.get(f"{base}/layouts/{lay['id']}/media", headers=sales).json()
    assert [m["file_name"] for m in items] == ["r2-public.png", "SECRET-LAYOUT-7a1.png"]
    r = client.put(
        f"{base}/layouts/{lay['id']}/media/order",
        headers=sales,
        json={"ids": [priv["id"], pub["id"]]},
    )
    assert r.status_code == 200 and [m["id"] for m in r.json()] == [priv["id"], pub["id"]]
    got = client.get(f"{base}/layouts/{lay['id']}", headers=sales).json()
    assert got["media_count"] == 2 and got["public_media_count"] == 1 and got["cover_url"]
    # unit media lists never show layout rows, and the inventory count is the unit's own
    for code in ("A-01-01", "A-01-02"):
        own = client.get(f"{base}/units/{units[code]['id']}/media", headers=sales).json()
        assert all(m["layout_id"] is None for m in own)
    row = client.get(f"{base}/units/{units[code]['id']}/sales", headers=sales).json()
    assert row["media_count"] == 0

    # a render for the layout: the default member is the first by code with an outline
    settings = get_settings()
    stub = _Stub()
    monkeypatch.setattr(settings, "ai_image_provider", "gemini")
    monkeypatch.setattr(settings, "ai_image_daily_limit", 5)
    monkeypatch.setattr(render_jobs, "get_provider", lambda: stub)
    url = f"{base}/layouts/{lay['id']}/renders"
    r = client.post(url, headers=sales, json={"unit_id": units["A-00-01"]["id"]})
    assert r.status_code == 422, r.text  # not a member
    r = client.post(url, headers=sales, json={"note": "walnut floors"})
    assert r.status_code == 202, r.text
    assert r.json()["layout_id"] == lay["id"] and r.json()["source_code"] == "A-01-01"
    rid = r.json()["id"]
    assert client.post(url, headers=sales, json={}).status_code == 409  # one at a time per layout
    out = client.portal.call(render_jobs.generate, uuid.UUID(tid), uuid.UUID(rid))
    assert out["status"] == "review", out
    data = client.get(url, headers=sales).json()
    [item] = data["items"]
    assert item["status"] == "review" and item["source_code"] == "A-01-01" and item["url"]
    gen = next(
        m
        for m in client.get(f"{base}/layouts/{lay['id']}/media", headers=sales).json()
        if m["kind"] == "plan_render"
    )
    assert gen["layout_id"] == lay["id"] and gen["is_public"] is False
    assert gen["alt_text"] == "Generated 3D view of layout R2 (Corner)"
    # the source unit's own render list does not claim it
    own_renders = client.get(f"{base}/units/{units['A-01-01']['id']}/renders", headers=sales).json()
    assert all(i["id"] != rid for i in own_renders["items"])
    r = client.post(f"{base}/renders/{rid}/approve", headers=sales)
    assert r.status_code == 200 and r.json()["status"] == "approved"

    # published: both members show the layout's public items in their sort order and the
    # private one stays out
    pm = world["pm"]
    r = client.put(
        f"{base}/projects/{pid}/units/publication",
        headers=pm,
        json={"status": "published", "all_active": True},
    )
    assert r.status_code == 200, r.text
    r = client.post(f"{base}/projects/{pid}/publications", headers=pm, json={"mode": "publish"})
    assert r.status_code == 201, r.text
    portal = "/api/v1/portal/projects/riverside"
    for code in ("A-01-01", "A-01-02"):
        doc = client.get(f"{portal}/units/{code}", headers=H_(world)).json()
        assert doc["layout"] == "R2" and doc["layout_name"] == "Corner"
        assert [m["from_layout"] for m in doc["media"]] == ["R2", "R2"]
        assert {m["kind"] for m in doc["media"]} == {"interior_render", "plan_render"}
        assert "SECRET-LAYOUT" not in json.dumps(doc)

    # the layout's render stays with the layout when the source unit is unlinked
    assert _link(client, base, sales, units["A-01-01"]["id"], None).status_code == 200
    got = client.get(f"{base}/layouts/{lay['id']}", headers=sales).json()
    assert [u["code"] for u in got["units"]] == ["A-01-02"] and got["media_count"] == 3


def test_a_mirror_without_a_link_still_publishes(client, world):  # noqa: F811
    """A unit written by the previous release carries ``attributes.layout`` but no ``layout_id``
    (the rolling-update window): the inventory shows the code, nothing is shared, and a write
    resolves it against the registry."""
    base, pid, sales = world["base"], world["project"]["id"], world["sales"]
    uid = world["units"]["A-01-02"]["id"]
    phase4._admin_sql(
        'UPDATE units SET layout_id = NULL, attributes = attributes || \'{"layout": "OLD"}\' '
        "WHERE id = :id",
        {"id": uid},
    )
    row = client.get(f"{base}/units/{uid}/sales", headers=sales).json()
    assert row["layout"] == "OLD" and row["layout_id"] is None
    r = client.patch(
        f"{base}/units/{uid}/sales",
        headers=sales,
        json={"layout": "OLD", "version": row["version"]},
    )
    assert r.status_code == 200 and r.json()["layout"] == "OLD"  # no diff, no write
    r = client.patch(
        f"{base}/units/{uid}/sales", headers=sales, json={"layout": "R2", "version": row["version"]}
    )
    assert r.status_code == 200 and r.json()["layout"] == "R2", r.text
    assert r.json()["layout_id"] is not None
    assert (
        client.post(
            f"{base}/projects/{pid}/layouts", headers=sales, json={"code": "old"}
        ).status_code
        == 201
    )
