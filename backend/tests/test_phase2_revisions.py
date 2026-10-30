"""Phase 2 completion (plan §14 exit criteria): vector suggestions map a building, a new
revision produces a diff proposal with relabel, split, merge, new and missing items, accepting
them preserves unit ids, the massing GLB is generated, and buildings are placed on the site."""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.fake_kratos import FakeKratos, cookie
from tests.pdf_fixture import make_plan_pdf_rev_a, make_plan_pdf_rev_b, make_site_plan_pdf

pytestmark = pytest.mark.skipif(
    not (os.environ.get("UF_TEST_DATABASE_ADMIN_URL") and os.environ.get("UF_TEST_DATABASE_URL")),
    reason="needs the PostgreSQL test database",
)

W, H = 842.0, 595.0


def nx(x_pt: float) -> float:
    return x_pt / W


def ny(y_pt: float) -> float:
    return 1 - y_pt / H


def rect(x0, y0, x1, y1):
    return [[nx(x0), ny(y1)], [nx(x1), ny(y1)], [nx(x1), ny(y0)], [nx(x0), ny(y0)]]


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
    kratos.add("root3", f"root3-{s}@unitforma.example.com", aal="aal2")
    assert client.get("/api/v1/admin/me", headers=cookie("root3")).status_code == 200
    eng = create_engine(os.environ["UF_TEST_DATABASE_ADMIN_URL"])
    with eng.begin() as conn:
        conn.execute(
            text("UPDATE users SET is_platform_admin = true WHERE email = :e"),
            {"e": f"root3-{s}@unitforma.example.com"},
        )
    eng.dispose()
    from unitforma.identity.deps import clear_whoami_cache

    clear_whoami_cache()
    root = cookie("root3")
    kratos.add("rev3", f"rev3-{s}@a.example.com")
    kratos.add("sales3", f"sales3-{s}@a.example.com")
    t = client.post(
        "/api/v1/platform/tenants", headers=root, json={"slug": f"rev{s}", "name": "Rev Co"}
    ).json()
    base = f"/api/v1/admin/tenants/{t['id']}"
    inv = client.post(
        f"/api/v1/platform/tenants/{t['id']}/invitations",
        headers=root,
        params={"email": f"rev3-{s}@a.example.com"},
    ).json()
    client.post(
        "/api/v1/admin/invitations/accept",
        headers=cookie("rev3"),
        json={"token": inv["accept_url"].rsplit("/", 1)[1]},
    )
    # the tenant admin is "rev3"; add an architectural reviewer and a sales user
    for who, role in (("arch3", "architectural_reviewer"), ("sales3", "sales")):
        kratos.add(who, f"{who}-{s}@a.example.com")
        inv2 = client.post(
            f"{base}/invitations",
            headers=cookie("rev3"),
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
            json={"token": inv2["accept_url"].rsplit("/", 1)[1]},
        )
    arch = cookie("arch3")
    p = client.post(
        f"{base}/projects", headers=cookie("rev3"), json={"slug": "hills", "name": "Hills"}
    ).json()
    b = client.post(
        f"{base}/projects/{p['id']}/buildings",
        headers=cookie("rev3"),
        json={"code": "A", "name": "Block A"},
    ).json()
    floors = client.put(
        f"{base}/buildings/{b['id']}/floors",
        headers=cookie("rev3"),
        json={
            "floors": [
                {"level": 0, "display_name": "Ground", "height_m": "3.0"},
                {"level": 1, "display_name": "1", "height_m": "3.0"},
            ]
        },
    ).json()
    return {
        "root": root,
        "arch": arch,
        "sales": cookie("sales3"),
        "base": base,
        "tenant": t,
        "project": p,
        "building": b,
        "floors": {f["level"]: f for f in floors},
    }


def _upload_revision(
    client: TestClient, world: dict, headers: dict, document_id: str, data: bytes, note: str
) -> dict:
    base = world["base"]
    intent = client.post(
        f"{base}/documents/{document_id}/uploads",
        headers=headers,
        json={
            "file_name": "plans.pdf",
            "content_type": "application/pdf",
            "byte_size": len(data),
            "source_note": note,
        },
    )
    assert intent.status_code == 201, intent.text
    up = intent.json()
    assert (
        client.put(
            up["upload_url"], content=data, headers={"Content-Type": "application/pdf"}
        ).status_code
        == 200
    )
    done = client.post(f"{base}/revisions/{up['revision']['id']}/complete", headers=headers)
    assert done.status_code == 200, done.text
    from unitforma.documents.jobs import process_revision

    result = client.portal.call(
        process_revision, uuid.UUID(world["tenant"]["id"]), uuid.UUID(up["revision"]["id"])
    )
    sheets = client.get(f"{base}/revisions/{up['revision']['id']}/sheets", headers=headers).json()
    return {"revision": done.json(), "sheets": sheets, "result": result}


def _calibrate(client, world, sheet, headers):
    # the 300 pt wide apartment 1 is declared 15 m → 0.05 m/pt everywhere
    r = client.patch(
        f"{world['base']}/sheets/{sheet['id']}/calibration",
        headers=headers,
        json={
            "calibration": {"p1": [nx(100), ny(200)], "p2": [nx(400), ny(200)], "distance_m": 15},
            "version": sheet["version"],
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def rev_a(client: TestClient, world: dict) -> dict:
    base, p, arch = world["base"], world["project"], world["arch"]
    doc = client.post(
        f"{base}/projects/{p['id']}/documents",
        headers=arch,
        json={
            "kind": "floor_plan",
            "title": "Floor plans A",
            "building_id": world["building"]["id"],
        },
    ).json()
    up = _upload_revision(client, world, arch, doc["id"], make_plan_pdf_rev_a(), "Rev A")
    assert up["result"]["pages"] == 2 and "diff" not in up["result"]  # first revision: no diff
    s1, s2 = up["sheets"]
    units: dict[str, dict] = {}
    for sheet, level in ((s1, 0), (s2, 1)):
        sheet = client.patch(
            f"{base}/sheets/{sheet['id']}/floor",
            headers=arch,
            json={"floor_id": world["floors"][level]["id"], "version": sheet["version"]},
        ).json()
        sheet = _calibrate(client, world, sheet, arch)
        # vector suggestions: every rectangle is a closed loop, labels come from the text inside
        sug = client.post(f"{base}/sheets/{sheet['id']}/suggestions", headers=arch)
        assert sug.status_code == 200, sug.text
        cands = sug.json()
        assert len(cands) == (2 if level == 0 else 4)
        for c in sorted(cands, key=lambda c: (c["label"] is None, c["label"] or "")):
            r = client.post(
                f"{base}/sheets/{sheet['id']}/boundaries",
                headers=arch,
                json={"ring": c["ring"], "label": c["label"], "source": "vector_suggest"},
            )
            assert r.status_code == 201, r.text
            units[c["label"] or f"unlabelled-{level}"] = r.json()["unit"]
            assert r.json()["boundary"]["source"] == "vector_suggest"
        if level == 0:
            # a manually drawn storage unit that revision B will drop
            r = client.post(
                f"{base}/sheets/{sheet['id']}/boundaries",
                headers=arch,
                json={
                    "ring": [[0.8, 0.1], [0.9, 0.1], [0.9, 0.2], [0.8, 0.2]],
                    "unit_type": "storage",
                    "code": "A-00-S1",
                },
            )
            assert r.status_code == 201, r.text
            units["storage"] = r.json()["unit"]
        ap = client.post(f"{base}/sheets/{sheet['id']}/approve", headers=arch)
        assert ap.status_code == 200, ap.text
        assert ap.json()["approved_units"] == (3 if level == 0 else 4)
        assert "massing_queued" in ap.json()
    return {"document": doc, **up, "units": units}


def test_rev_a_units_codes_and_areas(client: TestClient, world: dict, rev_a: dict):
    u = rev_a["units"]
    assert u["bina #1"]["code"] == "A-00-01" and u["bina #2"]["code"] == "A-00-02"
    assert u["bina #3"]["code"] == "A-01-01" and u["unlabelled-1"]["code"] == "A-01-04"
    # 300 pt × 200 pt at 0.05 m/pt → 15 m × 10 m
    assert abs(float(u["bina #1"]["areas"][0]["value_m2"]) - 150.0) < 0.5
    live = client.get(
        f"{world['base']}/projects/{world['project']['id']}/units", headers=world["arch"]
    ).json()
    assert len(live) == 7 and {x["lifecycle_status"] for x in live} == {"active"}


@pytest.fixture(scope="module")
def massing_a(client: TestClient, world: dict, rev_a: dict) -> dict:
    from unitforma.geometry.jobs import build_massing

    res = client.portal.call(
        build_massing, uuid.UUID(world["tenant"]["id"]), uuid.UUID(world["project"]["id"])
    )
    assert res["status"] == "ready", res
    return res


def test_massing_glb_generated_from_approved_boundaries(
    client: TestClient, world: dict, massing_a: dict
):
    from unitforma.geometry.massing import parse_glb

    base = world["base"]
    m = client.get(f"{base}/projects/{world['project']['id']}/massing", headers=world["arch"])
    assert m.status_code == 200, m.text
    body = m.json()
    assert body["status"] == "ready" and body["stats"]["units"] == 7
    assert body["stats"]["buildings_unplaced"] == ["A"] and body["glb_url"]
    glb = client.get(body["glb_url"])
    assert glb.status_code == 200 and glb.content[:4] == b"glTF"
    gltf, _ = parse_glb(glb.content)
    names = {n["name"] for n in gltf["nodes"]}
    assert {"A", "A-00-01", "A-00-02", "A-01-01", "A-00-S1"} <= names
    unit_nodes = [n for n in gltf["nodes"] if "mesh" in n and "unit_id" in n["extras"]]
    assert len(unit_nodes) == 7
    # ADR-0037 Decision 5: each floor also has its infill and slab band, the top one a parapet
    structure = {n["extras"].get("structure") for n in gltf["nodes"] if "mesh" in n} - {None}
    assert {"slab", "parapet"} <= structure
    first_floor = [n for n in unit_nodes if n["extras"]["floor_level"] == 1]
    assert first_floor and all(
        gltf["accessors"][gltf["meshes"][n["mesh"]]["primitives"][0]["attributes"]["POSITION"]][
            "min"
        ][1]
        == 3.0
        for n in first_floor
    )
    # sales can read the model, not regenerate it
    assert (
        client.get(
            f"{base}/projects/{world['project']['id']}/massing", headers=world["sales"]
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{base}/projects/{world['project']['id']}/massing", headers=world["sales"]
        ).status_code
        == 403
    )


def test_footprints_and_placement(client: TestClient, world: dict, rev_a: dict):
    base, p, b = world["base"], world["project"], world["building"]
    fp = client.get(f"{base}/projects/{p['id']}/footprints", headers=world["arch"])
    assert fp.status_code == 200, fp.text
    [f] = fp.json()
    assert f["code"] == "A" and f["source_floor_level"] == 0 and f["floors"] == 2
    assert f["height_m"] == 6.0 and len(f["ring_m"]) >= 4
    xs = [pt[0] for pt in f["ring_m"]]
    assert min(xs) == 5.0 and max(xs) >= 35.0  # 100 pt → 5 m; apartments end at 700 pt = 35 m
    # the reviewer places the building (mapping work) although they cannot edit the project
    r = client.patch(
        f"{base}/buildings/{b['id']}",
        headers=world["arch"],
        json={
            "site_transform": {"tx": 12.5, "ty": 40, "rotation_deg": 90},
            "version": f["version"],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["placement_status"] == "draft"
    assert r.json()["site_transform"]["tx"] == 12.5 and r.json()["site_transform"]["scale"] == 1.0
    # ...but not rename it
    assert (
        client.patch(
            f"{base}/buildings/{b['id']}",
            headers=world["arch"],
            json={"name": "x", "version": r.json()["version"]},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"{base}/buildings/{b['id']}",
            headers=world["sales"],
            json={"site_transform": {"tx": 0}, "version": r.json()["version"]},
        ).status_code
        == 403
    )
    r2 = client.patch(
        f"{base}/buildings/{b['id']}",
        headers=world["arch"],
        json={"placement_status": "confirmed", "version": r.json()["version"]},
    )
    assert r2.status_code == 200 and r2.json()["placement_status"] == "confirmed"
    # the site frame is the calibrated site plan sheet
    site_doc = client.post(
        f"{base}/projects/{p['id']}/documents",
        headers=world["arch"],
        json={"kind": "site_plan", "title": "Site plan"},
    ).json()
    up = _upload_revision(client, world, world["arch"], site_doc["id"], make_site_plan_pdf(), "S")
    [site_sheet] = up["sheets"]
    proj = client.get(f"{base}/projects/{p['id']}", headers=world["root"]).json()
    pr = client.patch(
        f"{base}/projects/{p['id']}",
        headers=world["root"],
        json={
            "site_frame": {"sheet_id": site_sheet["id"], "north_deg": 0},
            "version": proj["version"],
        },
    )
    assert pr.status_code == 200 and pr.json()["site_frame"]["sheet_id"] == site_sheet["id"]


@pytest.fixture(scope="module")
def rev_b(client: TestClient, world: dict, rev_a: dict, massing_a: dict) -> dict:
    up = _upload_revision(
        client, world, world["arch"], rev_a["document"]["id"], make_plan_pdf_rev_b(), "Rev B"
    )
    assert up["result"]["pages"] == 2
    assert up["result"]["diff"]["proposal"], up["result"]
    return up


def test_new_revision_inherits_setup_and_proposes_diff(
    client: TestClient, world: dict, rev_a: dict, rev_b: dict
):
    base = world["base"]
    s1, s2 = rev_b["sheets"]
    assert s1["floor_id"] is None and s1["suggested_floor_id"] == world["floors"][0]["id"]
    assert s1["assignment_status"] == "suggested" and s1["calibration_status"] == "inherited"
    assert s1["calibration"]["distance_m"] == 15
    props = client.get(
        f"{base}/projects/{world['project']['id']}/proposals", headers=world["arch"]
    ).json()
    assert len(props) == 1 and props[0]["status"] == "open"
    prop = client.get(f"{base}/proposals/{props[0]['id']}", headers=world["arch"]).json()
    summary = prop["summary"]
    assert summary["pages_compared"] == 2
    kinds = sorted(i["kind"] for i in prop["items"])
    assert kinds == ["matched", "matched", "merged", "missing", "new", "relabelled", "split"]
    u = rev_a["units"]
    by_kind: dict[str, list[dict]] = {}
    for it in prop["items"]:
        by_kind.setdefault(it["kind"], []).append(it)
    assert {i["old_unit_ids"][0] for i in by_kind["matched"]} == {
        u["bina #1"]["id"],
        u["unlabelled-1"]["id"],
    }
    assert by_kind["split"][0]["old_unit_ids"] == [u["bina #2"]["id"]]
    assert sorted(by_kind["split"][0]["labels"]) == ["bina #2", "bina #2B"]
    assert set(by_kind["merged"][0]["old_unit_ids"]) == {u["bina #5"]["id"], u["bina #6"]["id"]}
    assert by_kind["relabelled"][0]["old_unit_ids"] == [u["bina #3"]["id"]]
    assert by_kind["relabelled"][0]["labels"] == ["bina #3A"]
    assert by_kind["missing"][0]["old_unit_ids"] == [u["storage"]["id"]]
    assert (
        by_kind["new"][0]["labels"] == ["bina #9"] and by_kind["new"][0]["new_sheet_id"] == s1["id"]
    )
    # the diff never wrote to units
    live = client.get(
        f"{base}/projects/{world['project']['id']}/units", headers=world["arch"]
    ).json()
    assert len(live) == 7
    # re-running the diff dismisses the previous open proposal
    again = client.post(
        f"{base}/revisions/{rev_b['revision']['id']}/proposals", headers=world["arch"]
    )
    assert again.status_code == 201, again.text
    props = client.get(
        f"{base}/projects/{world['project']['id']}/proposals", headers=world["arch"]
    ).json()
    assert sorted(p["status"] for p in props) == ["dismissed", "open"]
    world["proposal"] = again.json()


def _items(prop: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for it in prop["items"]:
        out.setdefault(it["kind"], []).append(it)
    return out


def test_accepting_proposal_items_preserves_identities(
    client: TestClient, world: dict, rev_a: dict, rev_b: dict
):
    base, arch, u = world["base"], world["arch"], rev_a["units"]
    prop = world["proposal"]
    pid = prop["id"]
    items = _items(prop)
    # sales cannot decide
    assert (
        client.post(
            f"{base}/proposals/{pid}/items/{items['matched'][0]['id']}",
            headers=world["sales"],
            json={"decision": "accept"},
        ).status_code
        == 403
    )
    # 1) all confident matches at once: units keep id + code, geometry moves to the new sheet
    r = client.post(f"{base}/proposals/{pid}/accept-all", headers=arch, json={"kinds": ["matched"]})
    assert r.status_code == 200, r.text
    assert all(i["decision"] == "accepted" for i in _items(r.json())["matched"])
    u1 = client.get(f"{base}/units/{u['bina #1']['id']}", headers=arch).json()
    assert u1["code"] == "A-00-01" and u1["verification_status"] == "in_review"
    assert len(u1["boundaries"]) == 1
    assert u1["boundaries"][0]["sheet_id"] == rev_b["sheets"][0]["id"]
    assert (
        u1["boundaries"][0]["status"] == "draft"
        and u1["boundaries"][0]["source"] == "vector_suggest"
    )
    s1 = client.get(f"{base}/sheets/{rev_b['sheets'][0]['id']}", headers=arch).json()
    assert s1["floor_id"] == world["floors"][0]["id"] and s1["assignment_status"] == "confirmed"
    # 2) split: apartment 2 keeps its id on the part with the larger overlap; 2B is new
    sp = items["split"][0]
    idx_2b = sp["labels"].index("bina #2B")
    codes = [None] * len(sp["labels"])
    codes[idx_2b] = "A-00-02B"
    r = client.post(
        f"{base}/proposals/{pid}/items/{sp['id']}",
        headers=arch,
        json={"decision": "accept", "codes": codes, "inherit_index": 1 - idx_2b},
    )
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    assert res["unit_ids"][0] == u["bina #2"]["id"]
    u2b = client.get(f"{base}/units/{res['unit_ids'][1]}", headers=arch).json()
    assert u2b["code"] == "A-00-02B" and u2b["lifecycle_status"] == "draft"
    u2 = client.get(f"{base}/units/{u['bina #2']['id']}", headers=arch).json()
    assert abs(float(u2["areas"][0]["value_m2"]) - 75.0) < 0.5  # 150 pt × 200 pt → 7.5 × 10 m
    # 3) merge: reviewer picks apartment 6 as the survivor (default would be 5)
    mg = items["merged"][0]
    r = client.post(
        f"{base}/proposals/{pid}/items/{mg['id']}",
        headers=arch,
        json={"decision": "accept", "survivor_id": u["bina #6"]["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["result"]["survivor_id"] == u["bina #6"]["id"]
    u5 = client.get(f"{base}/units/{u['bina #5']['id']}", headers=arch).json()
    assert u5["lifecycle_status"] == "removed"
    u6 = client.get(f"{base}/units/{u['bina #6']['id']}", headers=arch).json()
    assert u6["lifecycle_status"] == "active" and abs(float(u6["areas"][0]["value_m2"]) - 100) < 1
    # 4) relabel: the drawing label changed to 3A; the reviewer also renumbers the code
    rl = items["relabelled"][0]
    r = client.post(
        f"{base}/proposals/{pid}/items/{rl['id']}",
        headers=arch,
        json={"decision": "accept", "code": "A-01-03A"},
    )
    assert r.status_code == 200, r.text
    u3 = client.get(f"{base}/units/{u['bina #3']['id']}", headers=arch).json()
    assert u3["code"] == "A-01-03A" and u3["id"] == u["bina #3"]["id"]
    assert u3["boundaries"][0]["label"] == "bina #3A"
    hist = client.get(f"{base}/units/{u3['id']}/history", headers=arch).json()
    assert [c["new_code"] for c in hist["codes"]] == ["A-01-01", "A-01-03A"]
    assert "geometry_updated" in [e["event_type"] for e in hist["lineage"]]
    # 5) new unit gets the next free code on the ground floor; 6) missing storage is removed
    nw = items["new"][0]
    r = client.post(
        f"{base}/proposals/{pid}/items/{nw['id']}", headers=arch, json={"decision": "accept"}
    )
    assert r.status_code == 200, r.text
    new_unit = client.get(f"{base}/units/{r.json()['result']['unit_id']}", headers=arch).json()
    assert new_unit["code"].startswith("A-00-") and new_unit["boundaries"][0]["label"] == "bina #9"
    ms = items["missing"][0]
    r = client.post(
        f"{base}/proposals/{pid}/items/{ms['id']}", headers=arch, json={"decision": "accept"}
    )
    assert r.status_code == 200, r.text
    storage = client.get(f"{base}/units/{u['storage']['id']}", headers=arch).json()
    assert storage["lifecycle_status"] == "removed"
    # deciding twice is refused; the proposal is resolved once nothing is pending
    assert (
        client.post(
            f"{base}/proposals/{pid}/items/{ms['id']}", headers=arch, json={"decision": "reject"}
        ).status_code
        == 409
    )
    prop = client.get(f"{base}/proposals/{pid}", headers=arch).json()
    assert prop["status"] == "resolved" and prop["resolved_at"]
    assert {i["decision"] for i in prop["items"]} == {"accepted"}
    # identities: every unit of revision A still exists (live or removed), none was deleted
    allu = client.get(
        f"{base}/projects/{world['project']['id']}/units",
        headers=arch,
        params={"include_removed": "true"},
    ).json()
    ids = {x["id"] for x in allu}
    assert {x["id"] for x in u.values()} <= ids
    lineage = client.get(f"{base}/projects/{world['project']['id']}/lineage", headers=arch).json()
    assert {"split", "merged", "removed", "relabelled", "geometry_updated", "created"} <= {
        e["event_type"] for e in lineage
    }
    assert all(
        e["revision_id"] == rev_b["revision"]["id"]
        for e in lineage
        if e["event_type"] in ("split", "merged", "removed")
    )


def test_approve_new_revision_and_rebuild_massing(
    client: TestClient, world: dict, rev_a: dict, rev_b: dict
):
    from unitforma.geometry.jobs import build_massing

    base, arch = world["base"], world["arch"]
    n = 0
    for s in rev_b["sheets"]:
        r = client.post(f"{base}/sheets/{s['id']}/approve", headers=arch)
        assert r.status_code == 200, r.text
        n += r.json()["approved_units"]
    assert n == 7  # 1, 2, 2B, 9 on the ground floor; 3A, unlabelled, 6 on the first
    live = client.get(f"{base}/projects/{world['project']['id']}/units", headers=arch).json()
    assert len(live) == 7 and {x["verification_status"] for x in live} == {"verified"}
    res = client.portal.call(
        build_massing, uuid.UUID(world["tenant"]["id"]), uuid.UUID(world["project"]["id"])
    )
    assert res["status"] == "ready" and res["stats"]["units"] == 7
    assert res["stats"]["buildings_unplaced"] == []  # placed in test_footprints_and_placement
    m = client.get(f"{base}/projects/{world['project']['id']}/massing", headers=arch).json()
    assert m["id"] == res["model_id"]  # the new model replaced the old one
