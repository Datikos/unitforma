"""Phase 3 exit criteria (plan §14): a 500-row spreadsheet with deliberate errors produces a
correct dry-run report; applying it audits every change; two concurrent edits produce a 409
carrying the current row; a missing price stays NULL through an import/export round trip.
Plus pricing rules (§6.2), bulk edit (§6.3), public/internal separation (§6.6) and media."""

from __future__ import annotations

import csv
import io
import json
import os
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.fake_kratos import FakeKratos, cookie

pytestmark = pytest.mark.skipif(
    not (os.environ.get("UF_TEST_DATABASE_ADMIN_URL") and os.environ.get("UF_TEST_DATABASE_URL")),
    reason="needs the PostgreSQL test database",
)

FLOORS = range(1, 11)
PER_FLOOR = 50


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


async def _seed_units(tenant_id: uuid.UUID, project_id: uuid.UUID, building_id: uuid.UUID):
    """500 approved units with verified areas (mapping is Phase 2's job; here we need data)."""
    from sqlalchemy import select

    from unitforma.core.db import tenant_session
    from unitforma.core.ids import new_id
    from unitforma.tenants.models import Floor, Unit, UnitArea

    async with tenant_session(tenant_id, scope="tenant") as db:
        floors = {
            f.level: f
            for f in (
                await db.execute(select(Floor).where(Floor.building_id == building_id))
            ).scalars()
        }
        for level in FLOORS:
            for seq in range(1, PER_FLOOR + 1):
                u = Unit(
                    id=new_id(),
                    tenant_id=tenant_id,
                    project_id=project_id,
                    building_id=building_id,
                    floor_id=floors[level].id,
                    code=f"A-{level:02}-{seq:02}",
                    unit_type="apartment",
                    lifecycle_status="active",
                    verification_status="verified",
                )
                db.add(u)
                await db.flush()
                for area_type, value, source in (
                    ("net_internal", Decimal("50.00") + seq, "drawing_measured"),
                    ("total_sellable", Decimal("60.00") + seq, "manual"),
                ):
                    db.add(
                        UnitArea(
                            id=new_id(),
                            tenant_id=tenant_id,
                            unit_id=u.id,
                            area_type=area_type,
                            value_m2=value,
                            source=source,
                            verification_status="verified",
                            is_current=True,
                        )
                    )


@pytest.fixture(scope="module")
def world(kratos: FakeKratos, client: TestClient) -> dict:
    s = uuid.uuid4().hex[:6]
    kratos.add("root4", f"root4-{s}@unitforma.example.com", aal="aal2")
    assert client.get("/api/v1/admin/me", headers=cookie("root4")).status_code == 200
    eng = create_engine(os.environ["UF_TEST_DATABASE_ADMIN_URL"])
    with eng.begin() as conn:
        conn.execute(
            text("UPDATE users SET is_platform_admin = true WHERE email = :e"),
            {"e": f"root4-{s}@unitforma.example.com"},
        )
    eng.dispose()
    from unitforma.identity.deps import clear_whoami_cache

    clear_whoami_cache()
    root = cookie("root4")
    kratos.add("adm4", f"adm4-{s}@a.example.com")
    t = client.post(
        "/api/v1/platform/tenants", headers=root, json={"slug": f"sal{s}", "name": "Sales Co"}
    ).json()
    base = f"/api/v1/admin/tenants/{t['id']}"
    inv = client.post(
        f"/api/v1/platform/tenants/{t['id']}/invitations",
        headers=root,
        params={"email": f"adm4-{s}@a.example.com"},
    ).json()
    client.post(
        "/api/v1/admin/invitations/accept",
        headers=cookie("adm4"),
        json={"token": inv["accept_url"].rsplit("/", 1)[1]},
    )
    adm = cookie("adm4")
    p = client.post(
        f"{base}/projects",
        headers=adm,
        json={"slug": "river", "name": "River", "currency": "USD"},
    ).json()
    other = client.post(
        f"{base}/projects", headers=adm, json={"slug": "other", "name": "Other"}
    ).json()
    for who, role, all_projects, pids in (
        ("sales4", "sales", True, []),
        ("arch4", "architectural_reviewer", True, []),
        ("sales4b", "sales", False, [other["id"]]),
    ):
        kratos.add(who, f"{who}-{s}@a.example.com")
        inv2 = client.post(
            f"{base}/invitations",
            headers=adm,
            json={
                "email": f"{who}-{s}@a.example.com",
                "role": role,
                "all_projects": all_projects,
                "project_ids": pids,
            },
        ).json()
        r = client.post(
            "/api/v1/admin/invitations/accept",
            headers=cookie(who),
            json={"token": inv2["accept_url"].rsplit("/", 1)[1]},
        )
        assert r.status_code == 200, r.text
    b = client.post(
        f"{base}/projects/{p['id']}/buildings", headers=adm, json={"code": "A", "name": "A"}
    ).json()
    client.put(
        f"{base}/buildings/{b['id']}/floors",
        headers=adm,
        json={"floors": [{"level": lvl, "display_name": str(lvl)} for lvl in FLOORS]},
    )
    client.portal.call(_seed_units, uuid.UUID(t["id"]), uuid.UUID(p["id"]), uuid.UUID(b["id"]))
    sales = cookie("sales4")
    plan = client.post(
        f"{base}/projects/{p['id']}/payment-plans",
        headers=sales,
        json={
            "name": "Standard 30/70",
            "schedule": [
                {"label": "Deposit", "percent": "30", "due": "on signing"},
                {"label": "Balance", "percent": "70", "due": "on completion"},
            ],
        },
    )
    assert plan.status_code == 201, plan.text
    promo = client.post(
        f"{base}/projects/{p['id']}/promotions",
        headers=sales,
        json={"name": "Autumn", "kind": "discount_percent", "value": "5", "terms": "until Dec"},
    )
    assert promo.status_code == 201, promo.text
    inv_rows = client.get(f"{base}/projects/{p['id']}/inventory", headers=sales).json()
    return {
        "base": base,
        "tenant": t,
        "project": p,
        "other": other,
        "adm": adm,
        "sales": sales,
        "arch": cookie("arch4"),
        "sales_b": cookie("sales4b"),
        "plan": plan.json(),
        "promo": promo.json(),
        "units": {r["code"]: r for r in inv_rows},
    }


def _row(client, world, code) -> dict:
    uid = world["units"][code]["unit_id"]
    return client.get(f"{world['base']}/units/{uid}/sales", headers=world["sales"]).json()


def test_inventory_defaults_null_price_and_project_currency(client, world):
    rows = list(world["units"].values())
    assert len(rows) == 500
    r = world["units"]["A-01-01"]
    assert r["version"] == 0 and r["list_price"] is None and r["price_per_m2"] is None
    assert r["currency"] == "USD" and r["availability"] == "available"
    assert r["price_area_type"] == "total_sellable" and r["price_area_m2"] == "61.00"
    assert r["areas"] == {"net_internal": "51.00", "total_sellable": "61.00"}
    assert r["public_fields"]["list_price"] is True


def test_role_matrix_and_project_restriction(client, world):
    base, uid = world["base"], world["units"]["A-01-02"]["unit_id"]
    # the architectural reviewer reads sales data but cannot edit it
    assert client.get(f"{base}/units/{uid}/sales", headers=world["arch"]).status_code == 200
    r = client.patch(
        f"{base}/units/{uid}/sales", headers=world["arch"], json={"list_price": "1", "version": 0}
    )
    assert r.status_code == 403
    # a sales user restricted to another project does not see this one
    pid = world["project"]["id"]
    assert (
        client.get(f"{base}/projects/{pid}/inventory", headers=world["sales_b"]).status_code == 404
    )
    assert client.get(f"{base}/units/{uid}/sales", headers=world["sales_b"]).status_code == 404


def test_concurrent_edits_conflict_with_current_row(client, world):
    base, uid = world["base"], world["units"]["A-01-03"]["unit_id"]
    a = client.patch(
        f"{base}/units/{uid}/sales",
        headers=world["sales"],
        json={"list_price": "150000", "currency": "usd", "version": 0},
    )
    assert a.status_code == 200, a.text
    assert a.json()["version"] == 1 and a.json()["list_price"] == "150000.00"
    assert a.json()["price_per_m2"] == str(
        (Decimal(150000) / Decimal(63)).quantize(Decimal("0.01"))
    )
    # the second editor still holds version 0
    b = client.patch(
        f"{base}/units/{uid}/sales",
        headers=world["adm"],
        json={"list_price": "149000", "version": 0},
    )
    assert b.status_code == 409
    body = b.json()
    assert body["current"]["version"] == 1 and body["current"]["list_price"] == "150000.00"
    assert body["current"]["unit_id"] == uid
    # re-applying on the current version via If-Match succeeds
    c = client.patch(
        f"{base}/units/{uid}/sales",
        headers={**world["adm"], "If-Match": '"1"'},
        json={"list_price": "149000"},
    )
    assert c.status_code == 200 and c.json()["version"] == 2
    assert (
        client.patch(
            f"{base}/units/{uid}/sales", headers=world["adm"], json={"list_price": "1"}
        ).status_code
        == 428
    )
    hist = client.get(f"{base}/units/{uid}/sales/history", headers=world["sales"]).json()
    assert [(h["old_price"], h["new_price"]) for h in hist["prices"]] == [
        ("150000.00", "149000.00"),
        (None, "150000.00"),
    ]


def test_pricing_rules(client, world):
    base, uid = world["base"], world["units"]["A-01-04"]["unit_id"]
    s = world["sales"]
    zero = client.patch(
        f"{base}/units/{uid}/sales", headers=s, json={"list_price": "0", "version": 0}
    )
    assert zero.status_code == 422 and "price 0" in zero.json()["detail"]
    ok = client.patch(
        f"{base}/units/{uid}/sales",
        headers=s,
        json={"list_price": "0", "confirm_zero_price": True, "version": 0},
    )
    assert ok.status_code == 200 and ok.json()["list_price"] == "0.00"
    bad_ccy = client.patch(
        f"{base}/units/{uid}/sales", headers=s, json={"currency": "U$D", "version": 1}
    )
    assert bad_ccy.status_code == 422
    sold = client.patch(
        f"{base}/units/{uid}/sales", headers=s, json={"availability": "sold", "version": 1}
    )
    assert sold.status_code == 200
    back = client.patch(
        f"{base}/units/{uid}/sales", headers=s, json={"availability": "available", "version": 2}
    )
    assert back.status_code == 422 and "reason" in back.json()["detail"]
    back = client.patch(
        f"{base}/units/{uid}/sales",
        headers=s,
        json={"availability": "available", "reason": "contract cancelled", "version": 2},
    )
    assert back.status_code == 200 and back.json()["availability_reason"] == "contract cancelled"
    # clearing the price is an explicit null, and it stays null (not 0)
    cleared = client.patch(
        f"{base}/units/{uid}/sales", headers=s, json={"list_price": None, "version": 3}
    )
    assert cleared.status_code == 200 and cleared.json()["list_price"] is None
    hist = client.get(f"{base}/units/{uid}/sales/history", headers=s).json()
    assert [(h["old_availability"], h["new_availability"]) for h in hist["availability"]] == [
        ("sold", "available"),
        ("available", "sold"),
    ]
    assert hist["availability"][0]["reason"] == "contract cancelled"


def test_payment_plan_validation(client, world):
    base, pid = world["base"], world["project"]["id"]
    r = client.post(
        f"{base}/projects/{pid}/payment-plans",
        headers=world["sales"],
        json={"name": "Broken", "schedule": [{"label": "x", "percent": "40"}]},
    )
    assert r.status_code == 422 and "100" in r.json()["title"]
    dup = client.post(
        f"{base}/projects/{pid}/payment-plans",
        headers=world["sales"],
        json={"name": "standard 30/70"},
    )
    assert dup.status_code == 409


def test_bulk_edit_preview_apply_and_stale(client, world):
    base, pid, s = world["base"], world["project"]["id"], world["sales"]
    codes = [f"A-02-{i:02}" for i in range(1, 6)]
    rows = [_row(client, world, c) for c in codes]
    items = [{"unit_id": r["unit_id"], "version": r["version"]} for r in rows]
    set_price = client.post(
        f"{base}/projects/{pid}/inventory/bulk",
        headers=s,
        json={
            "items": items[:3],
            "changes": {"list_price": "200000", "currency": "USD"},
            "preview": False,
        },
    )
    assert set_price.status_code == 200, set_price.text
    rows = [_row(client, world, c) for c in codes]
    items = [{"unit_id": r["unit_id"], "version": r["version"]} for r in rows]
    body = {
        "items": items,
        "changes": {
            "payment_plan_id": world["plan"]["id"],
            "promotion_ids": [world["promo"]["id"]],
        },
        "price_adjust_percent": "5",
    }
    prev = client.post(f"{base}/projects/{pid}/inventory/bulk", headers=s, json=body)
    assert prev.status_code == 200 and prev.json()["preview"] is True
    first = prev.json()["units"][0]["changes"]
    assert {"field": "list_price", "old": "200000.00", "new": "210000.00"} in first
    # units without a price keep an empty price under a percentage change
    assert not any(c["field"] == "list_price" for c in prev.json()["units"][4]["changes"])
    assert _row(client, world, codes[0])["payment_plan_id"] is None  # preview wrote nothing
    applied = client.post(
        f"{base}/projects/{pid}/inventory/bulk", headers=s, json={**body, "preview": False}
    )
    assert applied.status_code == 200 and applied.json()["changed_units"] == 5
    after = [_row(client, world, c) for c in codes]
    assert [a["list_price"] for a in after] == ["210000.00"] * 3 + [None, None]
    assert {a["payment_plan_name"] for a in after} == {"Standard 30/70"}
    assert {tuple(a["promotion_names"]) for a in after} == {("Autumn",)}
    # the same request again is stale for every unit → 409, nothing changed
    stale = client.post(
        f"{base}/projects/{pid}/inventory/bulk", headers=s, json={**body, "preview": False}
    )
    assert stale.status_code == 409 and len(stale.json()["stale"]) == 5
    assert [_row(client, world, c)["list_price"] for c in codes[:3]] == ["210000.00"] * 3
    # all-or-nothing: one invalid unit (sold → available without reason) blocks the batch
    r0 = after[0]
    client.patch(
        f"{base}/units/{r0['unit_id']}/sales",
        headers=s,
        json={"availability": "sold", "version": r0["version"]},
    )
    rows = [_row(client, world, c) for c in codes]
    bad = client.post(
        f"{base}/projects/{pid}/inventory/bulk",
        headers=s,
        json={
            "items": [{"unit_id": r["unit_id"], "version": r["version"]} for r in rows],
            "changes": {"availability": "available"},
            "preview": False,
        },
    )
    assert bad.status_code == 422 and bad.json()["unit_errors"][0]["code"] == codes[0]
    assert _row(client, world, codes[1])["version"] == rows[1]["version"]


def _xlsx(rows: list[list]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


HEADER = [
    "Code",
    "Status",
    "Price",
    "Currency",
    "price_on_request",
    "payment_plan",
    "promotions",
    "rooms",
    "internal_notes",
]


@pytest.fixture(scope="module")
def big_import(client, world) -> dict:
    """502 rows: one per unit of floors 3–10 and 1–2, an unknown code and a duplicate row,
    with deliberate errors on specific rows."""
    codes = [f"A-{lvl:02}-{seq:02}" for lvl in FLOORS for seq in range(1, PER_FLOOR + 1)]
    rows: list[list] = [HEADER]
    expected_errors: dict[int, str] = {}
    sheet_row = 1
    for i, code in enumerate(codes):
        sheet_row += 1
        row = [
            code,
            "available",
            f"{100000 + i * 1000:,.2f}".replace(",", " "),  # "100 000.00" with ' ' thousands
            "USD",
            "false",
            "Standard 30/70",
            "Autumn",
            2,
            f"batch note {i}",
        ]
        if code == "A-03-01":
            row[2] = "12 5O0.00"
            expected_errors[sheet_row] = "not a number"
        elif code == "A-03-02":
            row[2] = "-5"
            expected_errors[sheet_row] = "negative"
        elif code == "A-03-03":
            row[2] = "0"
            expected_errors[sheet_row] = "price 0"
        elif code == "A-03-04":
            row[3] = "US"
            expected_errors[sheet_row] = "ISO 4217"
        elif code == "A-03-05":
            row[1] = "booked"
            expected_errors[sheet_row] = "is not one of"
        elif code == "A-03-06":
            row[5] = "Nope"
            expected_errors[sheet_row] = "unknown payment plan"
        elif code == "A-03-07":
            row[3] = None
            expected_errors[sheet_row] = "currency is required"
        elif code == "A-03-08":
            row[7] = 2.5
            expected_errors[sheet_row] = "whole number"
        elif code == "A-03-09":
            row[6] = "Autumn; Spring"
            expected_errors[sheet_row] = "unknown promotion"
        elif code == "A-03-10":
            row[2] = None  # missing price: valid, stays NULL
        elif code == "A-02-01":
            # test_bulk_edit_preview_apply_and_stale left this unit sold: "available" without
            # a reason must be refused by the import exactly as by the editor (plan §6.4)
            expected_errors[sheet_row] = "requires a reason"
        rows.append(row)
    sheet_row += 1
    rows.append(["A-99-99", "available", "1000.00", "USD", "false", None, None, 1, None])
    expected_errors[sheet_row] = "unknown code"
    sheet_row += 1
    rows.append(["a-04-01", "sold", "1.00", "USD", "false", None, None, 1, None])
    expected_errors[sheet_row] = "already appears in row"
    data = _xlsx(rows)
    base, pid = world["base"], world["project"]["id"]
    up = client.post(
        f"{base}/projects/{pid}/imports",
        params={"file_name": "prices.xlsx"},
        content=data,
        headers={**world["sales"], "Content-Type": "application/octet-stream"},
    )
    assert up.status_code == 201, up.text
    batch = up.json()
    assert batch["file_format"] == "xlsx" and batch["row_count"] == 502
    # auto-mapping found every column by name or synonym
    assert batch["mapping"] == {
        "code": "Code",
        "availability": "Status",
        "list_price": "Price",
        "currency": "Currency",
        "price_on_request": "price_on_request",
        "payment_plan": "payment_plan",
        "promotions": "promotions",
        "rooms": "rooms",
        "internal_notes": "internal_notes",
    }
    dry = client.post(
        f"{base}/imports/{batch['id']}/dry-run",
        headers=world["sales"],
        json={"mapping": batch["mapping"], "options": {"thousands_separator": " "}},
    )
    assert dry.status_code == 200, dry.text
    return {"batch": dry.json(), "expected_errors": expected_errors, "codes": codes}


def test_dry_run_report_is_correct(client, world, big_import):
    rep = big_import["batch"]["report"]
    summary = rep["summary"]
    assert summary["rows"] == 502
    assert summary["errors"] == len(big_import["expected_errors"]) == 12
    assert summary["unknown_codes"] == ["A-99-99"]
    by_row = {r["row"]: r for r in rep["rows"]}
    for row_no, needle in big_import["expected_errors"].items():
        r = by_row[row_no]
        assert r["status"] == "error", (row_no, r)
        assert any(needle in e for e in r["errors"]), (row_no, needle, r["errors"])
    errored_rows = set(big_import["expected_errors"])
    others = [r for r in rep["rows"] if r["row"] not in errored_rows]
    assert all(r["status"] in ("changed", "unchanged") for r in others)
    # dry run wrote nothing
    assert _row(client, world, "A-05-05")["list_price"] is None
    # the missing price is not a change to the price
    a0310 = next(r for r in rep["rows"] if r["code"] == "A-03-10")
    assert a0310["status"] == "changed"
    assert "list_price" not in {c["field"] for c in a0310["changes"]}
    assert summary["changes_by_field"]["list_price"] > 400
    assert big_import["batch"]["error_count"] == 12


def test_apply_import_audits_every_change(client, world, big_import):
    base, batch = world["base"], big_import["batch"]
    no = client.post(f"{base}/imports/{batch['id']}/apply", headers=world["sales"], json={})
    assert no.status_code == 422
    ok = client.post(
        f"{base}/imports/{batch['id']}/apply",
        headers=world["sales"],
        json={"skip_invalid_rows": True},
    )
    assert ok.status_code == 200, ok.text
    applied = ok.json()
    assert applied["status"] == "applied"
    assert applied["change_count"] == batch["report"]["summary"]["total_changes"]
    eng = create_engine(os.environ["UF_TEST_DATABASE_ADMIN_URL"])
    with eng.begin() as conn:
        conn.execute(text("SELECT set_config('app.scope', 'platform', true)"))
        audits = conn.execute(
            text(
                "SELECT count(*) FROM audit_log WHERE action = 'import' "
                "AND after->>'import_batch_id' = :b"
            ),
            {"b": batch["id"]},
        ).scalar_one()
        prices = conn.execute(
            text("SELECT count(*) FROM price_history WHERE import_batch_id = :b"),
            {"b": batch["id"]},
        ).scalar_one()
        null_price = conn.execute(
            text(
                "SELECT s.list_price FROM unit_sales s JOIN units u ON u.id = s.unit_id "
                "WHERE u.project_id = :p AND u.code = 'A-03-10'"
            ),
            {"p": world["project"]["id"]},
        ).scalar_one()
    eng.dispose()
    assert audits == applied["change_count"]
    assert prices == batch["report"]["summary"]["changes_by_field"]["list_price"]
    assert null_price is None
    r = _row(client, world, "A-05-05")
    assert r["list_price"] == f"{100000 + (4 * 50 + 4) * 1000}.00"
    assert r["payment_plan_name"] == "Standard 30/70" and r["rooms"] == 2
    assert _row(client, world, "A-03-01")["list_price"] is None  # errored row skipped
    again = client.post(f"{base}/imports/{batch['id']}/apply", headers=world["sales"], json={})
    assert again.status_code == 409


def test_apply_refuses_when_inventory_changed_after_dry_run(client, world, big_import):
    base, pid, s = world["base"], world["project"]["id"], world["sales"]
    data = _xlsx([["code", "list_price", "currency"], ["A-06-01", "333000", "USD"]])
    up = client.post(
        f"{base}/projects/{pid}/imports",
        params={"file_name": "one.xlsx"},
        content=data,
        headers={**s, "Content-Type": "application/octet-stream"},
    ).json()
    dry = client.post(
        f"{base}/imports/{up['id']}/dry-run", headers=s, json={"mapping": up["mapping"]}
    ).json()
    assert dry["report"]["summary"]["changed"] == 1
    r = _row(client, world, "A-06-01")
    client.patch(
        f"{base}/units/{r['unit_id']}/sales",
        headers=world["adm"],
        json={"internal_notes": "edited meanwhile", "version": r["version"]},
    )
    stale = client.post(f"{base}/imports/{up['id']}/apply", headers=s, json={})
    assert stale.status_code == 409 and stale.json()["stale_units"] == [r["unit_id"]]
    assert _row(client, world, "A-06-01")["list_price"] == r["list_price"]


@pytest.mark.parametrize("fmt", ["xlsx", "csv"])
def test_export_import_round_trip_keeps_null_prices(client, world, big_import, fmt):
    base, pid, s = world["base"], world["project"]["id"], world["sales"]
    exp = client.get(f"{base}/projects/{pid}/inventory/export", headers=s, params={"format": fmt})
    assert exp.status_code == 200 and "attachment" in exp.headers["content-disposition"]
    if fmt == "csv":
        rows = list(csv.DictReader(io.StringIO(exp.content.decode("utf-8-sig"))))
        assert len(rows) == 500
        a0310 = next(r for r in rows if r["code"] == "A-03-10")
        assert a0310["list_price"] == "" and a0310["currency"] == "USD"
        assert a0310["internal_notes"] == "batch note 109"
        assert set(rows[0]) >= {"unit_id", "area_net_internal", "price_per_m2"}
    up = client.post(
        f"{base}/projects/{pid}/imports",
        params={"file_name": f"export.{fmt}"},
        content=exp.content,
        headers={**s, "Content-Type": "application/octet-stream"},
    )
    assert up.status_code == 201, up.text
    batch = up.json()
    assert batch["mapping"]["unit_id"] == "unit_id" and "price_per_m2" not in batch["mapping"]
    dry = client.post(
        f"{base}/imports/{batch['id']}/dry-run", headers=s, json={"mapping": batch["mapping"]}
    )
    assert dry.status_code == 200, dry.text
    summary = dry.json()["report"]["summary"]
    assert summary["errors"] == 0, [r for r in dry.json()["report"]["rows"] if r["errors"]][:3]
    assert summary["changed"] == 0 and summary["unchanged"] == 500
    # public exports leave internal columns out
    pub = client.get(
        f"{base}/projects/{pid}/inventory/export",
        headers=s,
        params={"format": "csv", "columns": "public"},
    )
    assert b"internal_notes" not in pub.content and b"availability_reason" not in pub.content


def test_public_preview_never_contains_internal_fields(client, world, big_import):
    base, s = world["base"], world["sales"]
    r = _row(client, world, "A-07-07")
    assert r["internal_notes"]
    pv = client.get(f"{base}/units/{r['unit_id']}/sales/public-preview", headers=s)
    assert pv.status_code == 200
    body = pv.json()
    dumped = json.dumps(body)
    assert "internal_notes" not in dumped and r["internal_notes"] not in dumped
    assert body["price"]["amount"] == r["list_price"] and body["price"]["currency"] == "USD"
    assert body["payment_plan"]["name"] == "Standard 30/70"
    assert body["promotions"][0]["name"] == "Autumn"
    # unit-level override hides the price; price on request hides it as well
    upd = client.patch(
        f"{base}/units/{r['unit_id']}/sales",
        headers=s,
        json={"public_fields": {"list_price": False}, "version": r["version"]},
    )
    assert upd.status_code == 200 and upd.json()["public_fields"]["list_price"] is False
    assert (
        client.get(f"{base}/units/{r['unit_id']}/sales/public-preview", headers=s).json()["price"]
        is None
    )
    # project-level default: hide payment plans everywhere
    st = client.get(f"{base}/projects/{world['project']['id']}/sales-settings", headers=s).json()
    put = client.put(
        f"{base}/projects/{world['project']['id']}/sales-settings",
        headers=s,
        json={"public_fields": {"payment_plan": False}, "version": st["project_version"]},
    )
    assert put.status_code == 200 and put.json()["public_fields"]["payment_plan"] is False
    pv2 = client.get(f"{base}/units/{r['unit_id']}/sales/public-preview", headers=s).json()
    assert "payment_plan" not in pv2


def test_price_area_type_setting_changes_price_per_m2(client, world, big_import):
    base, pid, s = world["base"], world["project"]["id"], world["sales"]
    st = client.get(f"{base}/projects/{pid}/sales-settings", headers=s).json()
    bad = client.put(
        f"{base}/projects/{pid}/sales-settings",
        headers=s,
        json={"price_area_type": "garden", "version": st["project_version"]},
    )
    assert bad.status_code == 422
    ok = client.put(
        f"{base}/projects/{pid}/sales-settings",
        headers=s,
        json={"price_area_type": "net_internal", "version": st["project_version"]},
    )
    assert ok.status_code == 200 and ok.json()["price_area_type"] == "net_internal"
    r = _row(client, world, "A-08-10")
    assert r["price_area_type"] == "net_internal" and r["price_area_m2"] == "60.00"
    assert r["price_per_m2"] == str(
        (Decimal(r["list_price"]) / Decimal(60)).quantize(Decimal("0.01"))
    )


def test_media_upload_order_visibility_and_ai_flag(client, world):
    base, s = world["base"], world["sales"]
    uid = world["units"]["A-09-09"]["unit_id"]
    bad = client.post(
        f"{base}/units/{uid}/media",
        headers=s,
        json={"file_name": "x.exe", "content_type": "application/x-msdownload", "byte_size": 4},
    )
    assert bad.status_code == 415
    ids = []
    for name, public, ai in (
        ("plan.png", True, False),
        ("render.png", True, True),
        ("x.png", False, False),
    ):
        intent = client.post(
            f"{base}/units/{uid}/media",
            headers=s,
            json={
                "file_name": name,
                "content_type": "image/png",
                "byte_size": 8,
                "kind": "interior_render" if ai else "photo",
                "is_public": public,
                "is_ai_generated": ai,
            },
        )
        assert intent.status_code == 201, intent.text
        m = intent.json()
        if ai:
            assert m["media"]["ai_disclosure_text"].startswith("AI-generated")
        put = client.put(
            m["upload_url"], content=b"\x89PNG\r\n\x1a\n", headers={"Content-Type": "image/png"}
        )
        assert put.status_code == 200
        done = client.post(f"{base}/media/{m['media']['id']}/complete", headers=s)
        assert done.status_code == 200 and done.json()["status"] == "ready" and done.json()["url"]
        ids.append(m["media"]["id"])
    order = client.put(
        f"{base}/units/{uid}/media/order", headers=s, json={"ids": list(reversed(ids))}
    )
    assert order.status_code == 200 and [m["id"] for m in order.json()] == list(reversed(ids))
    assert (
        client.put(f"{base}/units/{uid}/media/order", headers=s, json={"ids": ids[:1]}).status_code
        == 422
    )
    pv = client.get(f"{base}/units/{uid}/sales/public-preview", headers=s).json()
    assert [m["id"] for m in pv["media"]] == [ids[1], ids[0]]  # public only, in order
    assert pv["media"][0]["is_ai_generated"] is True and pv["media"][0]["ai_disclosure_text"]
    # turning the AI flag off clears the disclosure; turning it on restores a default one
    m = client.get(f"{base}/units/{uid}/media", headers=s).json()
    render = next(x for x in m if x["id"] == ids[1])
    off = client.patch(
        f"{base}/media/{render['id']}",
        headers=s,
        json={"is_ai_generated": False, "version": render["version"]},
    )
    assert off.status_code == 200 and off.json()["ai_disclosure_text"] is None
    assert _row(client, world, "A-09-09")["media_count"] == 3
    assert client.delete(f"{base}/media/{ids[2]}", headers=s).status_code == 204
    assert _row(client, world, "A-09-09")["media_count"] == 2
    assert client.delete(f"{base}/media/{ids[0]}", headers=world["arch"]).status_code == 403
