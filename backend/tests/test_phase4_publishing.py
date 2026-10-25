"""Phase 4 exit criteria (plan §14): publish → portal reachable at {tenant}.<domain> with
filters, plans and massing; internal fields absent from every public response (contract test);
unpublish hides the project immediately. Plus preview tokens, hidden units, a project-scoped
custom domain, the Caddy ``ask`` decision and branding allow-lists (plan §6.6, §9)."""

from __future__ import annotations

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.fake_kratos import FakeKratos, cookie
from tests.pdf_fixture import make_plan_pdf, make_section_pdf, make_site_plan_pdf

pytestmark = pytest.mark.skipif(
    not (os.environ.get("UF_TEST_DATABASE_ADMIN_URL") and os.environ.get("UF_TEST_DATABASE_URL")),
    reason="needs the PostgreSQL test database",
)

W, H = 842.0, 595.0
SECRETS = [
    "SECRET-NOTE-7f3",
    "SECRET-REASON-91a",
    "SECRET-PLAN-c22",
    "SECRET-PROMO-e5d",
    "SECRET-MEDIA-0b9",
    "SECRET-BRAND-44f",
]


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
    from unitforma.publishing import portal
    from unitforma.storage.service import reset_storage

    get_settings.cache_clear()
    reset_storage()
    clear_whoami_cache()
    portal.invalidate()
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
    return client.get(f"{base}/revisions/{rev['id']}/sheets", headers=headers).json()


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
    from unitforma.core.settings import get_settings
    from unitforma.geometry.jobs import build_massing
    from unitforma.identity.deps import clear_whoami_cache

    s = uuid.uuid4().hex[:6]
    kratos.add("root5", f"root5-{s}@unitforma.example.com", aal="aal2")
    assert client.get("/api/v1/admin/me", headers=cookie("root5")).status_code == 200
    _admin_sql(
        "UPDATE users SET is_platform_admin = true WHERE email = :e",
        {"e": f"root5-{s}@unitforma.example.com"},
    )
    clear_whoami_cache()
    root = cookie("root5")
    slug = f"pub{s}"
    t = client.post(
        "/api/v1/platform/tenants", headers=root, json={"slug": slug, "name": "Riverside Homes"}
    ).json()
    base = f"/api/v1/admin/tenants/{t['id']}"
    kratos.add("adm5", f"adm5-{s}@a.example.com")
    inv = client.post(
        f"/api/v1/platform/tenants/{t['id']}/invitations",
        headers=root,
        params={"email": f"adm5-{s}@a.example.com"},
    ).json()
    client.post(
        "/api/v1/admin/invitations/accept",
        headers=cookie("adm5"),
        json={"token": inv["accept_url"].rsplit("/", 1)[1]},
    )
    adm = cookie("adm5")
    for who, role in (("pm5", "project_manager"), ("sales5", "sales")):
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
    pm, sales = cookie("pm5"), cookie("sales5")
    p = client.post(
        f"{base}/projects",
        headers=adm,
        json={
            "slug": "riverside",
            "name": "Riverside",
            "currency": "EUR",
            "description": "Homes by the river",
        },
    ).json()
    other = client.post(
        f"{base}/projects", headers=adm, json={"slug": "hilltop", "name": "Hilltop"}
    ).json()
    b = client.post(
        f"{base}/projects/{p['id']}/buildings", headers=adm, json={"code": "A", "name": "Block A"}
    ).json()
    floors = client.put(
        f"{base}/buildings/{b['id']}/floors",
        headers=adm,
        json={
            "floors": [
                {"level": 0, "display_name": "Ground", "height_m": "3.0"},
                {"level": 1, "display_name": "First", "height_m": "3.0"},
            ]
        },
    ).json()
    floors = {f["level"]: f for f in floors}
    sheets = _upload(
        client, base, adm, p["id"], "floor_plan", "Plans A", make_plan_pdf(), t["id"], b["id"]
    )
    units = {}
    for sheet, level in ((sheets[0], 0), (sheets[1], 1)):
        sheet = client.patch(
            f"{base}/sheets/{sheet['id']}/floor",
            headers=adm,
            json={"floor_id": floors[level]["id"], "version": sheet["version"]},
        ).json()
        sheet = _calibrate(client, base, adm, sheet, (100, 200), (400, 200), 15)
        for r in (rect(100, 200, 400, 400), rect(400, 200, 700, 400)):
            res = client.post(
                f"{base}/sheets/{sheet['id']}/boundaries", headers=adm, json={"ring": r}
            )
            assert res.status_code == 201, res.text
            units[res.json()["unit"]["code"]] = res.json()["unit"]
        assert client.post(f"{base}/sheets/{sheet['id']}/approve", headers=adm).status_code == 200
    # site plan, calibrated, building placed on it
    [site_sheet] = _upload(
        client, base, adm, p["id"], "site_plan", "Site", make_site_plan_pdf(), t["id"]
    )
    site_sheet = _calibrate(client, base, adm, site_sheet, (100, 80), (600, 80), 100)
    proj = client.get(f"{base}/projects/{p['id']}", headers=adm).json()
    client.patch(
        f"{base}/projects/{p['id']}",
        headers=adm,
        json={
            "site_frame": {"sheet_id": site_sheet["id"]},
            "portal_settings": {
                "hero_text": "Twelve minutes to the old town",
                "construction_stage": "Frame complete",
            },
            "version": proj["version"],
        },
    )
    bb = client.get(f"{base}/projects/{p['id']}/buildings", headers=adm).json()[0]
    client.patch(
        f"{base}/buildings/{bb['id']}",
        headers=adm,
        json={
            "site_transform": {"tx": 30, "ty": 40},
            "placement_status": "confirmed",
            "version": bb["version"],
        },
    )
    res = client.portal.call(build_massing, uuid.UUID(t["id"]), uuid.UUID(p["id"]))
    assert res["status"] == "ready" and res["stats"]["units"] == 4

    # commercial data with deliberate internal-only values (the contract test looks for them)
    plan_pub = client.post(
        f"{base}/projects/{p['id']}/payment-plans",
        headers=sales,
        json={
            "name": "30/70",
            "schedule": [{"label": "Deposit", "percent": "30"}, {"label": "Keys", "percent": "70"}],
        },
    ).json()
    plan_priv = client.post(
        f"{base}/projects/{p['id']}/payment-plans",
        headers=sales,
        json={"name": "Insider SECRET-PLAN-c22", "is_public": False},
    ).json()
    client.post(
        f"{base}/projects/{p['id']}/promotions",
        headers=sales,
        json={"name": "Old SECRET-PROMO-e5d", "is_active": False},
    )
    st = client.get(f"{base}/projects/{p['id']}/sales-settings", headers=sales).json()
    client.put(
        f"{base}/projects/{p['id']}/sales-settings",
        headers=sales,
        json={"price_area_type": "net_internal", "version": st["project_version"]},
    )
    edits = {
        "A-00-01": {
            "list_price": "180000",
            "rooms": 2,
            "bedrooms": 1,
            "payment_plan_id": plan_pub["id"],
            "internal_notes": "SECRET-NOTE-7f3",
            "public_description": "Garden flat",
        },
        "A-00-02": {
            "list_price": "260000",
            "rooms": 3,
            "bedrooms": 2,
            "payment_plan_id": plan_priv["id"],
        },
        "A-01-01": {
            "availability": "sold",
            "availability_reason": "SECRET-REASON-91a",
            "list_price": "190000",
            "rooms": 2,
        },
        "A-01-02": {"price_on_request": True, "rooms": 4},
    }
    for code, body in edits.items():
        r = client.patch(
            f"{base}/units/{units[code]['id']}/sales", headers=sales, json={**body, "version": 0}
        )
        assert r.status_code == 200, r.text
    uid = units["A-00-01"]["id"]
    media = {}
    for name, public, ai in (("public.png", True, True), ("SECRET-MEDIA-0b9.png", False, False)):
        m = client.post(
            f"{base}/units/{uid}/media",
            headers=sales,
            json={
                "file_name": name,
                "content_type": "image/png",
                "byte_size": 8,
                "is_public": public,
                "is_ai_generated": ai,
                "kind": "interior_render",
            },
        ).json()
        client.put(
            m["upload_url"], content=b"\x89PNG\r\n\x1a\n", headers={"Content-Type": "image/png"}
        )
        client.post(f"{base}/media/{m['media']['id']}/complete", headers=sales)
        media[name] = m["media"]
    # tenant branding with an unknown key and an invalid colour (dropped by the allow-list)
    client.patch(
        f"{base}",
        headers=adm,
        json={
            "branding": {
                "primary_color": "#0F766E",
                "accent_color": "red;}</style>",
                "SECRET-BRAND-44f": "x",
                "contact_email": "sales@riverside.example.com",
            }
        },
    )
    host = f"{slug}.{get_settings().platform_domain}"
    return {
        "base": base,
        "tenant": t,
        "project": p,
        "other": other,
        "units": units,
        "adm": adm,
        "pm": pm,
        "sales": sales,
        "host": host,
        "media": media,
        "plan_priv": plan_priv,
    }


def H_(world) -> dict:
    return {"Host": world["host"]}


def test_unknown_host_and_coming_soon(client, world):
    r = client.get("/api/v1/portal/site", headers={"Host": "nobody.example.net"})
    assert r.status_code == 404 and r.json()["type"].endswith("portal-not-configured")
    site = client.get("/api/v1/portal/site", headers=H_(world))
    assert site.status_code == 200, site.text
    assert site.json()["status"] == "coming_soon" and site.json()["projects"] == []
    assert site.json()["tenant"]["name"] == "Riverside Homes"
    r = client.get("/api/v1/portal/projects/riverside", headers=H_(world))
    assert r.status_code == 404 and r.json()["type"].endswith("project-not-published")


def test_readiness_and_unit_publication(client, world):
    base, pid = world["base"], world["project"]["id"]
    rd = client.get(f"{base}/projects/{pid}/publish/readiness", headers=world["pm"]).json()
    assert rd["ok"] is False and rd["items"][0]["key"] == "units"
    assert rd["portal_url"] == f"https://{world['host']}/projects/riverside"
    assert (
        client.put(
            f"{base}/projects/{pid}/units/publication",
            headers=world["sales"],
            json={"status": "published", "all_active": True},
        ).status_code
        == 403
    )
    r = client.put(
        f"{base}/projects/{pid}/units/publication",
        headers=world["pm"],
        json={"status": "published", "all_active": True},
    )
    assert (
        r.status_code == 200
        and r.json()["changed"] == 4
        and r.json()["unit_counts"] == {"published": 4}
    )
    rd = client.get(f"{base}/projects/{pid}/publish/readiness", headers=world["pm"]).json()
    assert rd["ok"] is True
    # plans, placement, massing all present; no public render document yet, so the gallery
    # warning stays (ADR-0016 Decision 1) and does not block publishing
    assert {i["key"] for i in rd["items"]} == {"units", "gallery"}
    assert {i["level"] for i in rd["items"] if i["key"] == "gallery"} == {"warning"}


def test_preview_is_private_until_published(client, world):
    base, pid = world["base"], world["project"]["id"]
    r = client.post(
        f"{base}/projects/{pid}/publications", headers=world["pm"], json={"mode": "preview"}
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["publication"]["status"] == "preview" and out["preview_url"].startswith(
        f"https://{world['host']}/projects/riverside?preview="
    )
    tok = out["preview_token"]
    ok = client.get("/api/v1/portal/projects/riverside", headers=H_(world), params={"preview": tok})
    assert ok.status_code == 200 and ok.json()["preview"] is True
    assert ok.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/portal/projects/riverside", headers=H_(world)).status_code == 404
    bad = client.get(
        "/api/v1/portal/projects/riverside", headers=H_(world), params={"preview": tok[:-2] + "xx"}
    )
    assert bad.status_code == 403
    # a preview token does not open another project
    assert (
        client.get(
            "/api/v1/portal/projects/hilltop", headers=H_(world), params={"preview": tok}
        ).status_code
        == 403
    )
    assert client.get("/api/v1/portal/site", headers=H_(world)).json()["status"] == "coming_soon"


@pytest.fixture(scope="module")
def published(client, world) -> dict:
    base, pid = world["base"], world["project"]["id"]
    r = client.post(
        f"{base}/projects/{pid}/publications", headers=world["pm"], json={"mode": "publish"}
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_portal_serves_project_with_plans_site_and_massing(client, world, published):
    site = client.get("/api/v1/portal/site", headers=H_(world)).json()
    assert site["status"] == "live" and site["mode"] == "tenant"
    [proj] = site["projects"]
    assert (
        proj["slug"] == "riverside"
        and proj["stats"]["units"] == 4
        and proj["stats"]["available"] == 3
    )
    assert proj["stats"]["price_from"] == {"amount": "180000.00", "currency": "EUR"}
    doc = client.get("/api/v1/portal/projects/riverside", headers=H_(world))
    assert doc.status_code == 200 and doc.headers["cache-control"] == "public, max-age=5"
    d = doc.json()
    assert d["project"]["hero_text"] == "Twelve minutes to the old town"
    assert d["project"]["construction_stage"] == "Frame complete"
    [bld] = d["buildings"]
    assert [f["level"] for f in bld["floors"]] == [0, 1]
    f0 = bld["floors"][0]
    assert (
        f0["plan"]["url"].startswith("/api/v1/portal/projects/riverside/assets/")
        and f0["plan"]["width"] == 2400
    )
    assert [u["code"] for u in f0["units"]] == ["A-00-01", "A-00-02"] and len(
        f0["units"][0]["ring"]
    ) == 4
    assert (
        d["site"]["plan"]["url"]
        and d["site"]["buildings"][0]["ring"]
        and len(d["site"]["buildings"][0]["ring"]) >= 4
    )
    assert d["massing"]["units"] == 4 and d["massing"]["disclaimer"].startswith("Schematic")
    assert d["branding"] == {
        "primary_color": "#0f766e",
        "contact_email": "sales@riverside.example.com",
    }
    # assets resolve through the publication only
    img = client.get(f0["plan"]["url"], headers=H_(world), follow_redirects=False)
    assert img.status_code == 302
    got = client.get(img.headers["location"])
    assert (
        got.status_code == 200
        and got.content[:4] == b"RIFF"
        and got.headers["content-type"] == "image/webp"
    )
    assert (
        client.get(
            "/api/v1/portal/projects/riverside/assets/deadbeef.webp", headers=H_(world)
        ).status_code
        == 404
    )


def test_unit_filters_and_detail(client, world, published):
    def u(**p):
        return client.get(
            "/api/v1/portal/projects/riverside/units", headers=H_(world), params=p
        ).json()

    assert u()["total"] == 4
    assert [x["code"] for x in u(availability="available")["items"]] == [
        "A-00-01",
        "A-00-02",
        "A-01-02",
    ]
    assert [x["code"] for x in u(min_price=185000)["items"]] == ["A-00-02", "A-01-01"]
    assert [x["code"] for x in u(sort="price_desc")["items"]] == [
        "A-00-02",
        "A-01-01",
        "A-00-01",
        "A-01-02",
    ]
    assert [x["code"] for x in u(rooms=[4, 5])["items"]] == ["A-01-02"]
    assert [x["code"] for x in u(floor=1)["items"]] == ["A-01-01", "A-01-02"]
    a = client.get("/api/v1/portal/projects/riverside/units/a-00-01", headers=H_(world)).json()
    assert (
        a["price"]["amount"] == "180000.00"
        and a["price"]["currency"] == "EUR"
        and a["price"]["per_m2"]
    )
    assert a["payment_plan"]["name"] == "30/70" and a["description"] == "Garden flat"
    assert a["plan"]["ring"] and a["plan"]["url"] and a["indicative"] is False
    [m] = a["media"]
    assert m["is_ai_generated"] is True and m["ai_disclosure_text"] and m["url"].endswith(".png")
    por = client.get("/api/v1/portal/projects/riverside/units/A-01-02", headers=H_(world)).json()
    assert por["price"] is None  # price on request
    priv = client.get("/api/v1/portal/projects/riverside/units/A-00-02", headers=H_(world)).json()
    assert "payment_plan" not in priv  # internal plan stays internal


def _crawl(client, world) -> list[tuple[str, bytes]]:
    from unitforma.publishing import portal

    bodies = []
    for path in (
        "/api/v1/portal/site",
        "/api/v1/portal/branding",
        "/api/v1/portal/projects/riverside",
    ):
        bodies.append((path, client.get(path, headers=H_(world)).content))
    units = client.get(
        "/api/v1/portal/projects/riverside/units", headers=H_(world), params={"limit": 500}
    ).json()
    bodies.append(("units", json.dumps(units).encode()))
    for code in world["units"]:
        r = client.get(f"/api/v1/portal/projects/riverside/units/{code}", headers=H_(world))
        bodies.append((code, r.content))
    for pub in portal._docs.values():  # the stored snapshot documents themselves
        bodies.append(("snapshot", json.dumps(pub).encode()))
    return bodies


def test_contract_no_internal_fields_in_any_public_response(client, world, published):
    """Plan §6.6 / §18: crawl every portal response and the stored snapshot."""
    from unitforma.geometry.massing import parse_glb

    bodies = _crawl(client, world)
    assert len(bodies) >= 8
    forbidden_keys = [
        '"internal_notes"',
        '"availability_reason"',
        '"lifecycle_status"',
        '"verification_status"',
        '"version"',
        '"updated_by"',
        '"object_key"',
        '"snapshot_key"',
        '"tenant_id"',
    ]
    for where, body in bodies:
        text_ = body.decode()
        for s in SECRETS:
            assert s not in text_, (where, s)
        for k in forbidden_keys:
            assert k not in text_, (where, k)
    # the public GLB carries only public unit attributes
    d = client.get("/api/v1/portal/projects/riverside", headers=H_(world)).json()
    loc = client.get(d["massing"]["url"], headers=H_(world), follow_redirects=False).headers[
        "location"
    ]
    gltf, _ = parse_glb(client.get(loc).content)
    for n in gltf["nodes"]:
        if "mesh" in n:
            assert set(n["extras"]) <= {
                "unit_id",
                "code",
                "unit_type",
                "building_code",
                "floor_level",
            }
    assert "SECRET" not in json.dumps(gltf)
    # the non-public media object was never copied into the publication
    assets = _admin_sql(
        "SELECT assets FROM publications WHERE id = :i", {"i": published["publication"]["id"]}
    )[0][0]
    assert not any("SECRET" in k or "SECRET" in v for k, v in assets.items())
    assert len([k for k in assets if k.startswith("m-")]) == 1


def test_hidden_unit_is_linkable_but_not_listed(client, world, published):
    base, pid = world["base"], world["project"]["id"]
    uid = world["units"]["A-01-02"]["id"]
    client.put(
        f"{base}/projects/{pid}/units/publication",
        headers=world["pm"],
        json={"status": "hidden", "unit_ids": [uid]},
    )
    # not live until republished: the snapshot is immutable
    assert (
        client.get("/api/v1/portal/projects/riverside/units", headers=H_(world)).json()["total"]
        == 4
    )
    r = client.post(
        f"{base}/projects/{pid}/publications", headers=world["pm"], json={"mode": "publish"}
    )
    assert r.status_code == 201 and r.json()["publication"]["version_no"] == 3
    lst = client.get("/api/v1/portal/projects/riverside/units", headers=H_(world)).json()
    assert lst["total"] == 3 and "A-01-02" not in [x["code"] for x in lst["items"]]
    assert (
        client.get("/api/v1/portal/projects/riverside/units/A-01-02", headers=H_(world)).status_code
        == 200
    )
    d = client.get("/api/v1/portal/projects/riverside", headers=H_(world)).json()
    assert "A-01-02" not in [u["code"] for f in d["buildings"][0]["floors"] for u in f["units"]]
    pubs = client.get(f"{base}/projects/{pid}/publications", headers=world["sales"]).json()
    assert [p["status"] for p in pubs] == ["published", "retired", "preview"]


def test_unpublish_hides_project_immediately(client, world, published):
    base, pid = world["base"], world["project"]["id"]
    assert client.get("/api/v1/portal/projects/riverside", headers=H_(world)).status_code == 200
    assert (
        client.post(f"{base}/projects/{pid}/unpublish", headers=world["sales"]).status_code == 403
    )
    r = client.post(f"{base}/projects/{pid}/unpublish", headers=world["pm"])
    assert r.status_code == 200 and r.json()["status"] == "retired"
    assert client.get("/api/v1/portal/projects/riverside", headers=H_(world)).status_code == 404
    assert (
        client.get("/api/v1/portal/projects/riverside/units", headers=H_(world)).status_code == 404
    )
    assert client.get("/api/v1/portal/site", headers=H_(world)).json()["status"] == "coming_soon"
    assert client.post(f"{base}/projects/{pid}/unpublish", headers=world["pm"]).status_code == 409
    again = client.post(
        f"{base}/projects/{pid}/publications", headers=world["pm"], json={"mode": "publish"}
    )
    assert again.status_code == 201
    assert client.get("/api/v1/portal/site", headers=H_(world)).json()["status"] == "live"


def test_project_scoped_custom_domain_and_caddy_ask(client, world, published):
    host = f"homes-{uuid.uuid4().hex[:6]}.example.org"
    pending = f"pending-{uuid.uuid4().hex[:6]}.example.org"
    _admin_sql(
        "INSERT INTO portal_domains (id, tenant_id, project_id, hostname, kind, "
        "verification_status, status, is_primary) "
        "VALUES (:i, :t, :p, :h, 'custom', 'verified', 'active', false), "
        "(:i2, :t, :p, :h2, 'custom', 'pending', 'active', false)",
        {
            "i": str(uuid.uuid4()),
            "i2": str(uuid.uuid4()),
            "t": world["tenant"]["id"],
            "p": world["project"]["id"],
            "h": host,
            "h2": pending,
        },
    )
    # the on-demand TLS ask endpoint sees verified custom domains despite forced RLS
    assert client.get("/internal/domains/ask", params={"domain": host}).status_code == 200
    assert client.get("/internal/domains/ask", params={"domain": pending}).status_code == 403
    assert (
        client.get("/internal/domains/ask", params={"domain": "nobody.example.net"}).status_code
        == 403
    )
    site = client.get("/api/v1/portal/site", headers={"Host": host.upper()}).json()
    assert site["mode"] == "project" and [p["slug"] for p in site["projects"]] == ["riverside"]
    assert (
        client.get("/api/v1/portal/projects/riverside", headers={"Host": host}).status_code == 200
    )
    # other projects of the tenant are not reachable on a project domain
    assert client.get("/api/v1/portal/projects/hilltop", headers={"Host": host}).status_code == 404
    # X-Forwarded-Host (set by Caddy) wins over the upstream Host
    fw = client.get(
        "/api/v1/portal/site", headers={"Host": "api:8000", "X-Forwarded-Host": world["host"]}
    )
    assert fw.status_code == 200 and fw.json()["mode"] == "tenant"


def test_resolver_function_does_not_leak_scope(client, world):
    eng = create_engine(os.environ["UF_TEST_DATABASE_URL"].replace("+asyncpg", "+psycopg"))
    with eng.begin() as conn:
        row = conn.execute(
            text("SELECT tenant_slug FROM portal_resolve_host(:h)"), {"h": world["host"]}
        ).first()
        assert row and row[0] == world["tenant"]["slug"]
        assert (
            conn.execute(
                text("SELECT coalesce(current_setting('app.scope', true), '')")
            ).scalar_one()
            == ""
        )
        assert conn.execute(text("SELECT count(*) FROM portal_domains")).scalar_one() == 0
    eng.dispose()


# --- ADR-0014: entrance, building status and terms, price note, elevation floor picker ---------


def test_portal_content_entrance_building_fields_price_note_and_elevation(client, world):
    """A section sheet becomes the building's elevation picker, the entrance travels from the
    sales PATCH to the read model, per-building status and terms and the project's price note
    land in the snapshot (ADR-0014 Decisions 1 to 4)."""
    base, pid, tid = world["base"], world["project"]["id"], world["tenant"]["id"]
    adm, sales = world["adm"], world["sales"]
    b = next(
        x
        for x in client.get(f"{base}/projects/{pid}/buildings", headers=adm).json()
        if x["code"] == "A"
    )
    # the floors learn their elevations (ADR-0010 would propose them; here set by hand)
    client.put(
        f"{base}/buildings/{b['id']}/floors",
        headers=adm,
        json={
            "floors": [
                {"level": 0, "display_name": "Ground", "height_m": "3.0", "elevation_m": "0"},
                {"level": 1, "display_name": "First", "height_m": "3.0", "elevation_m": "3.0"},
            ]
        },
    )
    assert client.get(f"{base}/buildings/{b['id']}/elevation-candidates", headers=adm).json() == []
    [section] = _upload(
        client, base, adm, pid, "section", "Section A-A", make_section_pdf(), tid, b["id"]
    )
    [cand] = client.get(f"{base}/buildings/{b['id']}/elevation-candidates", headers=adm).json()
    assert cand["sheet_id"] == section["id"] and cand["document_title"] == "Section A-A"
    assert cand["markers"] == 3 and cand["matched_floors"] == 2 and cand["floors"] == 2
    assert cand["raster_url"]
    # a sheet of another project is refused
    bad = client.patch(
        f"{base}/buildings/{b['id']}",
        headers=adm,
        json={"elevation_sheet_id": str(uuid.uuid4()), "version": b["version"]},
    )
    assert bad.status_code == 422 and bad.json()["type"].endswith("elevation-sheet-unknown")
    b = client.patch(
        f"{base}/buildings/{b['id']}",
        headers=adm,
        json={
            "elevation_sheet_id": section["id"],
            "construction_status": "under_construction",
            "completion": "December 2026",
            "terms": "White shell; TBC and Bank of Georgia mortgages",
            "version": b["version"],
        },
    ).json()
    assert b["construction_status"] == "under_construction" and b["completion"] == "December 2026"
    for code, entrance in (("A-00-01", "1"), ("A-01-01", "2")):
        u = world["units"][code]
        row = client.get(f"{base}/units/{u['id']}/sales", headers=sales).json()
        r = client.patch(
            f"{base}/units/{u['id']}/sales",
            headers=sales,
            json={"entrance": entrance, "version": row["version"]},
        )
        assert r.status_code == 200 and r.json()["entrance"] == entrance, r.text
    proj = client.get(f"{base}/projects/{pid}", headers=adm).json()
    client.patch(
        f"{base}/projects/{pid}",
        headers=adm,
        json={
            "portal_settings": {
                **proj["portal_settings"],
                "price_note": "Settled in GEL at the NBG rate of the payment day",
                "terms": "Default terms SECRET-FREE",
            },
            "version": proj["version"],
        },
    )
    r = client.post(
        f"{base}/projects/{pid}/publications", headers=world["pm"], json={"mode": "publish"}
    )
    assert r.status_code == 201, r.text
    doc = client.get("/api/v1/portal/projects/riverside", headers=H_(world)).json()
    assert doc["project"]["price_note"].startswith("Settled in GEL")
    [bd] = doc["buildings"]
    assert bd["entrances"] == ["1", "2"]
    assert bd["construction_status"] == "under_construction" and bd["completion"] == "December 2026"
    assert bd["terms"].startswith("White shell")  # the building's own terms win over the default
    assert doc["site"]["buildings"][0]["construction_status"] == "under_construction"
    el = bd["elevation"]
    assert el["plan"]["url"].endswith(".webp") and el["plan"]["width"] > 0
    assert [(x["level"], x["published"]) for x in el["bands"]] == [(0, True), (1, True)]
    y_ground = el["bands"][0]["ring"][2][1]
    y_first = el["bands"][1]["ring"][2][1]
    assert 0 < y_first < y_ground <= 1  # the first floor's band sits above the ground band
    assert all(x["ring"][0] == [0.0, x["ring"][1][1]] for x in el["bands"])  # full-width bands
    ground = next(f for f in bd["floors"] if f["level"] == 0)
    assert next(u["entrance"] for u in ground["units"] if u["code"] == "A-00-01") == "1"

    def units(**p):
        return client.get(
            "/api/v1/portal/projects/riverside/units", headers=H_(world), params=p
        ).json()

    listed = units()["total"]  # one unit was hidden by an earlier test
    assert units(entrance="1")["total"] == listed  # meaningless without a building: ignored
    assert [x["code"] for x in units(building="A", entrance="1")["items"]] == ["A-00-01"]
    one = client.get("/api/v1/portal/projects/riverside/units/A-00-01", headers=H_(world)).json()
    assert one["entrance"] == "1"
    # an explicit null clears the building's terms; the default terms then apply
    b = client.patch(
        f"{base}/buildings/{b['id']}",
        headers=adm,
        json={"terms": None, "version": b["version"]},
    ).json()
    assert b["terms"] is None and b["completion"] == "December 2026"
    r = client.post(
        f"{base}/projects/{pid}/publications", headers=world["pm"], json={"mode": "publish"}
    )
    assert r.status_code == 201
    [bd] = client.get("/api/v1/portal/projects/riverside", headers=H_(world)).json()["buildings"]
    assert bd["terms"] == "Default terms SECRET-FREE"


def test_portal_gallery_site_features_map_and_shared_layout_media(client, world):
    """ADR-0016: pages of ``public`` render documents become the gallery and the project card
    cover (Decision 1), public site features reach the snapshot in sheet and metre coordinates
    (Decision 3), a unit without media borrows the renders of its layout (Decision 4) and the
    map position travels with the address (Decision 5); internal values stay out."""
    base, pid, tid = world["base"], world["project"]["id"], world["tenant"]["id"]
    adm, sales, pm = world["adm"], world["sales"], world["pm"]
    units = world["units"]
    portal = "/api/v1/portal/projects/riverside"

    # a render document is internal by default: readiness warns and the gallery stays empty
    _upload(client, base, adm, pid, "render", "Renders", make_plan_pdf(), tid)
    render = next(
        d
        for d in client.get(f"{base}/projects/{pid}/documents", headers=adm).json()
        if d["title"] == "Renders"
    )
    assert render["visibility"] == "internal"
    rd = client.get(f"{base}/projects/{pid}/publish/readiness", headers=pm).json()
    assert "gallery" in {i["key"] for i in rd["items"]}
    r = client.patch(f"{base}/documents/{render['id']}", headers=adm, json={"visibility": "public"})
    assert r.status_code == 200 and r.json()["visibility"] == "public", r.text
    rd = client.get(f"{base}/projects/{pid}/publish/readiness", headers=pm).json()
    assert "gallery" not in {i["key"] for i in rd["items"]}

    # site features: one public, one internal, one without a polygon
    garden = client.post(
        f"{base}/projects/{pid}/site-features",
        headers=adm,
        json={
            "kind": "garden",
            "name": "Courtyard",
            "polygon": {"ring": [[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]]},
        },
    )
    assert garden.status_code == 201, garden.text
    garden = garden.json()
    assert (
        client.post(
            f"{base}/projects/{pid}/site-features",
            headers=adm,
            json={
                "kind": "parking_zone",
                "name": "Staff SECRET-FEATURE-3c1",
                "is_public": False,
                "polygon": {"ring": [[0.5, 0.5], [0.6, 0.5], [0.6, 0.6]]},
            },
        ).status_code
        == 201
    )
    gym = client.post(
        f"{base}/projects/{pid}/site-features",
        headers=adm,
        json={"kind": "amenity", "name": "Gym"},
    ).json()
    r = client.patch(f"{base}/site-features/{garden['id']}", headers=adm, json={"name": "Garden"})
    assert r.status_code == 200 and r.json()["name"] == "Garden", r.text
    assert client.delete(f"{base}/site-features/{gym['id']}", headers=adm).status_code == 204
    assert (
        client.get(f"{base}/site-features/{gym['id']}", headers=adm).status_code == 404
        or len(client.get(f"{base}/projects/{pid}/site-features", headers=adm).json()) == 2
    )

    # the map position is part of the address; unknown keys never reach the portal
    proj = client.get(f"{base}/projects/{pid}", headers=adm).json()
    r = client.patch(
        f"{base}/projects/{pid}",
        headers=adm,
        json={
            "address": {
                "line1": "Riverside 1",
                "city": "Tbilisi",
                "lat": "41.7151",
                "lng": 44.8271,
                "cadastral": "SECRET-CAD-1",
            },
            "version": proj["version"],
        },
    )
    assert r.status_code == 200, r.text

    # layout L1 on the unit with media and on one without
    for code in ("A-00-01", "A-00-02"):
        row = client.get(f"{base}/units/{units[code]['id']}/sales", headers=sales).json()
        r = client.patch(
            f"{base}/units/{units[code]['id']}/sales",
            headers=sales,
            json={"layout": "L1", "version": row["version"]},
        )
        assert r.status_code == 200 and r.json()["layout"] == "L1", r.text

    r = client.post(f"{base}/projects/{pid}/publications", headers=pm, json={"mode": "publish"})
    assert r.status_code == 201, r.text
    doc = client.get(portal, headers=H_(world)).json()
    for marker in ("SECRET-FEATURE-3c1", "SECRET-CAD-1", "SECRET-MEDIA"):
        assert marker not in json.dumps(doc)

    gallery = doc["gallery"]
    assert [(g["document"], g["page"], g["caption"]) for g in gallery] == [
        ("Renders", 1, "Renders · 1"),
        ("Renders", 2, "Renders · 2"),
    ]
    assert all(g["url"].endswith(".webp") and g["width"] > 0 and g["height"] > 0 for g in gallery)
    site = client.get("/api/v1/portal/site", headers=H_(world)).json()
    card = next(c for c in site["projects"] if c["slug"] == "riverside")
    assert card["cover"] == gallery[0]["url"]

    [feature] = doc["site"]["features"]
    assert feature["kind"] == "garden" and feature["name"] == "Garden"
    assert feature["ring"] == [[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]]
    sheet = client.get(f"{base}/sheets/{proj['site_frame']['sheet_id']}", headers=adm).json()
    m = float(sheet["calibration"]["m_per_px"])
    assert len(feature["ring_m"]) == 4
    assert feature["ring_m"][1][0] - feature["ring_m"][0][0] == pytest.approx(
        0.2 * m * sheet["raster_width"], abs=0.01
    )
    assert feature["ring_m"][2][1] - feature["ring_m"][1][1] == pytest.approx(
        0.2 * m * sheet["raster_height"], abs=0.01
    )

    assert doc["project"]["address"] == {
        "line1": "Riverside 1",
        "city": "Tbilisi",
        "lat": 41.7151,
        "lng": 44.8271,
    }

    own = client.get(f"{portal}/units/A-00-01", headers=H_(world)).json()
    borrowed = client.get(f"{portal}/units/A-00-02", headers=H_(world)).json()
    assert own["layout"] == "L1" and borrowed["layout"] == "L1"
    assert len(own["media"]) == 1 and "shared_from" not in own["media"][0]
    assert len(borrowed["media"]) == 1 and borrowed["media"][0]["shared_from"] == "A-00-01"
    assert borrowed["media"][0]["url"] == own["media"][0]["url"]
    assert "SECRET-MEDIA" not in json.dumps(borrowed)  # the donor's internal media stays internal
