"""ADR-0007: project bootstrap from a tas.ge permit. The registry is never called: a synthetic
DWR reply stands in for the remote call and a fake fetcher serves the attachments."""

from __future__ import annotations

import io
import json
import os
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, text

from tests.fake_kratos import FakeKratos, cookie
from tests.pdf_fixture import make_plan_pdf
from unitforma.core.errors import ProblemError
from unitforma.regulatory import service, tasge

DOC_ID = 4242
PERSONAL_NUMBER = "01001099999"
PHONE = "+995 500 00 00 00"


def _wrapper() -> dict[str, Any]:
    """A made-up permit with the structures the normaliser reads."""
    return {
        "document": {
            "documentId": DOC_ID,
            "documentNo": f"AR1{DOC_ID}",
            "createDateStr": "01/03/2026",
            "registrationDate": {"$date_ms": 1772323200000},
            "address": "Test city, Example street 7",
            "cachedInfo": (
                "<root><nomenklature><categoryName>Test category</categoryName>"
                "<categoryId>33</categoryId><className>III</className><classId>3</classId>"
                "<actionName>New building</actionName><stadiums>approval</stadiums>"
                "<stadiums>permit</stadiums></nomenklature></root>"
            ),
            "responseText": "<p>Decision naming Test Person</p>",
        },
        "archDocMeta": {"responseDate": {"$date_ms": 1772928000000}},
        "fieldsetPojos": [
            {
                "fieldsetId": 10,
                "fieldsetTitle": "სატიტულო ინფორმაცია",
                "fields": [{"documentFieldId": 1, "fieldLabel": tasge.FUNCTIONAL_PURPOSE_LABEL}],
            },
            {
                "fieldsetId": 20,
                "fieldsetTitle": "დამკვეთის ინფორმაცია",
                "fields": [
                    {"documentFieldId": 2, "fieldLabel": "პირადი ნომერი"},
                    {"documentFieldId": 3, "fieldLabel": "ტელეფონის ნომერი"},
                    {"documentFieldId": 4, "fieldLabel": "ორგანიზაცია"},
                ],
            },
            {
                "fieldsetId": 30,
                "fieldsetTitle": (
                    "შენობა-ნაგებობის ყველა სართულისა და სახურავის გეგმები, მასშტაბი 1:100."
                ),
                "fields": [],
            },
            {
                "fieldsetId": 40,
                "fieldsetTitle": "შენობა-ნაგებობის ფასადები, მასშტაბი 1:100",
                "fields": [],
            },
            {
                "fieldsetId": 50,
                "fieldsetTitle": "საპროექტო შენობა-ნაგებობის ვექტორული CAD ფაილი",
                "fields": [],
            },
            {
                "fieldsetId": 60,
                "fieldsetTitle": "ტექნიკურ - ეკონომიკური მაჩვენებლები",
                "fields": [{"documentFieldId": 5, "fieldLabel": "საერთო ფართობი (კვ.მ)"}],
            },
        ],
        "docValues": [
            {
                "documentFieldId": 1,
                "documentValueId": 1,
                "isActive": 1,
                "stringValue": "Residential house B-7",
            },
            {
                "documentFieldId": 2,
                "documentValueId": 2,
                "isActive": 1,
                "stringValue": PERSONAL_NUMBER,
            },
            {"documentFieldId": 3, "documentValueId": 3, "isActive": 1, "stringValue": PHONE},
            {
                "documentFieldId": 4,
                "documentValueId": 4,
                "isActive": 1,
                "stringValue": "Example Ltd",
            },
            {"documentFieldId": 5, "documentValueId": 5, "isActive": 1, "numberValue": 1234.5},
            {"documentFieldId": 5, "documentValueId": 6, "isActive": 0, "numberValue": 999.0},
        ],
        "docClassCalculatorValues": [
            {"fieldName": "შენობის სიმაღლე (მ)", "numberValue": 14.7},
            {"fieldName": "შენობის ჩაღრმავება მიწის ზედაპირიდან ქვემოთ (მ)", "numberValue": 4.05},
            {"fieldName": "შენობის საძირკვლის ტიპები", "comboValue": "point"},
        ],
        "mapInfos": [
            {
                "naprCadCode": "00.00.00.000.001",
                "naprAddress": "Test city, Example street 7",
                "naprArea": 1000.0,
                "naprPurpose": "non-agricultural",
                "naprOwner": "Test Person",
            }
        ],
        "attachedFiles": [
            {"attachedFileId": 900, "fieldsetId": 30, "fileName": "plans-old.pdf", "isActive": 1},
            {"attachedFileId": 901, "fieldsetId": 30, "fileName": "გეგმები.pdf", "isActive": 1},
            {"attachedFileId": 902, "fieldsetId": 40, "fileName": "facades.png", "isActive": 1},
            {"attachedFileId": 903, "fieldsetId": 50, "fileName": "model.pla", "isActive": 1},
            {"attachedFileId": 904, "fieldsetId": 20, "fileName": "id-card.pdf", "isActive": 1},
        ],
        "oldResponseMotions": [
            {"motionId": 77, "documentStatusId": 3, "motionDate": {"$date_ms": 0}}
        ],
    }


def _js(value: Any) -> str:
    """JSON is a subset of the data-only JavaScript DWR emits; dates become ``new Date(n)``."""
    if isinstance(value, dict) and set(value) == {"$date_ms"}:
        return f"new Date({value['$date_ms']})"
    if isinstance(value, dict):
        return "{" + ",".join(f"{k}:{_js(v)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ",".join(_js(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def dwr_body(wrapper: dict[str, Any] | None = None, *, success: bool = True) -> str:
    w = wrapper or _wrapper()
    return (
        "throw 'allowScriptTagRemoting is false.';\n//#DWR-INSERT\n//#DWR-REPLY\n"
        'var s0={};s0.documentStatusId=3;s0.note="last motion";\n'
        "var s1={};" + "".join(f"s1.{k}={_js(v)};" for k, v in w.items()) + "\n"
        'dwr.engine.remote.handleCallback("1","0",'
        f"{{isSuccess:{'true' if success else 'false'},errorMessage:null,"
        "source:s0,sources:[null,s1]});"
    )


def _record() -> dict[str, Any]:
    return tasge.normalise(tasge.record_from_dwr(dwr_body()))


# --------------------------------------------------------------------------- pure functions
def test_reference_accepts_url_or_id_and_refuses_other_hosts():
    assert tasge.extract_document_id("1127975") == 1127975
    assert tasge.extract_document_id("https://tas.ge/?p=publicpage&documentId=1127975") == 1127975
    assert tasge.extract_document_id("tas.ge/?documentId=5&p=publicpage") == 5
    assert (
        tasge.extract_document_id("https://docs.tbilisi.gov.ge/architect/public.html?docId=9") == 9
    )
    for bad in ("https://evil.example/?documentId=1", "http://169.254.169.254/latest", "abc"):
        with pytest.raises(ProblemError) as e:
            tasge.extract_document_id(bad)
        assert e.value.status == 422


def test_download_refuses_unknown_hosts_before_any_request():
    client = tasge.TasgeClient()
    for url in (
        "https://evil.example/DownloadServlet?attachedFileId=1",
        "http://docs.tbilisi.gov.ge/DownloadServlet?attachedFileId=1",  # plain http
        "https://169.254.169.254/latest/meta-data",
    ):
        with pytest.raises(ProblemError) as e:
            import asyncio

            asyncio.run(client.download(url))
        assert e.value.status == 422


def test_dwr_reply_parses_and_failure_is_an_error():
    rec = tasge.record_from_dwr(dwr_body())
    assert rec["last_motion"]["documentStatusId"] == 3
    assert rec["wrapper"]["document"]["documentId"] == DOC_ID
    assert rec["wrapper"]["document"]["registrationDate"] == {"$date_ms": 1772323200000}
    with pytest.raises(ProblemError) as e:
        tasge.record_from_dwr(dwr_body(success=False))
    assert e.value.status == 502


def test_normalised_record_has_no_personal_data():
    record = _record()
    flat = json.dumps(record, ensure_ascii=False)
    assert PERSONAL_NUMBER not in flat
    assert PHONE not in flat
    assert "Test Person" not in flat  # parcel owner that is not a company is redacted
    assert "Decision naming" not in flat  # decision text is not stored
    assert "id-card.pdf" not in flat  # attachments of a personal-data fieldset are dropped
    assert record["parcels"][0]["owner"] == "<redacted person>"
    assert record["permit"]["application_no"] == f"AR1{DOC_ID}"
    assert record["permit"]["status"] == "approved"
    assert record["permit"]["registered_at"].startswith("2026-03-01")
    assert record["nomenclature"]["class"] == "III"
    assert record["nomenclature"]["stages"] == ["approval", "permit"]
    labels = {f["label"]: f["value"] for f in record["fields"]}
    assert labels[tasge.FUNCTIONAL_PURPOSE_LABEL] == "Residential house B-7"
    assert labels["ორგანიზაცია"] == "Example Ltd"
    assert record["technical_indicators"] == [
        {
            "fieldset": "ტექნიკურ - ეკონომიკური მაჩვენებლები",
            "label": "საერთო ფართობი (კვ.მ)",
            "value": 1234.5,
            "field_id": 5,
        }
    ]


def test_attachment_classification_and_suggestions():
    record = _record()
    latest = {a["attached_file_id"]: a["latest_in_fieldset"] for a in record["attachments"]}
    assert latest == {900: False, 901: True, 902: True, 903: True}
    plan = {a["attached_file_id"]: a for a in tasge.classify_attachments(record)}
    assert plan[901]["kind"] == "floor_plan" and plan[901]["skip_reason"] is None
    assert plan[902]["kind"] == "elevation" and plan[902]["skip_reason"] is None
    assert plan[903]["skip_reason"].startswith("ArchiCAD")
    assert (
        tasge.kind_for_fieldset("საპროექტო ტერიტორიის გენერალური გეგმა, მასშტაბი 1:500")
        == "site_plan"
    )
    assert tasge.kind_for_fieldset("შენობა-ნაგებობის ჭრილები") == "section"
    assert tasge.kind_for_fieldset("ფოტომონტაჟი და აქსონომეტრიული ხედები") == "render"
    assert tasge.kind_for_fieldset("ენერგოეფექტურობის დეკლარაცია") == "permit"
    assert tasge.suggest_name(record) == "Residential house B-7"
    assert tasge.suggest_building_code(record) == "B-7"
    assert tasge.suggest_slug(record) == f"permit-{DOC_ID}"
    assert tasge.heights(record) == {"above_zero_m": 14.7, "below_zero_m": 4.05}
    summary = tasge.summary(record, uuid.UUID(int=1))
    assert summary["external_id"] == str(DOC_ID)
    assert summary["cadastral_codes"] == ["00.00.00.000.001"]
    assert PERSONAL_NUMBER not in json.dumps(summary)


# --------------------------------------------------------------------------- API + worker
pytestmark_db = pytest.mark.skipif(
    not (os.environ.get("UF_TEST_DATABASE_ADMIN_URL") and os.environ.get("UF_TEST_DATABASE_URL")),
    reason="needs the PostgreSQL test database",
)


class FakeFetcher:
    def __init__(self) -> None:
        self.records = 0
        self.downloads: list[str] = []

    async def fetch_record(self, doc_id: int) -> dict[str, Any]:
        assert doc_id == DOC_ID
        self.records += 1
        return tasge.record_from_dwr(dwr_body())

    async def download(self, url: str) -> bytes:
        self.downloads.append(url)
        if "attachedFileId=901" in url:
            return make_plan_pdf()
        if "attachedFileId=902" in url:
            buf = io.BytesIO()
            Image.new("RGB", (40, 30), (200, 200, 200)).save(buf, format="PNG")
            return buf.getvalue()
        raise AssertionError(f"unexpected download {url}")


@pytest.fixture(scope="module")
def kratos() -> FakeKratos:
    return FakeKratos()


@pytest.fixture(scope="module")
def client(kratos: FakeKratos, tmp_path_factory):
    from unitforma.core.settings import get_settings
    from unitforma.identity.deps import clear_whoami_cache, get_kratos
    from unitforma.main import create_app
    from unitforma.storage.service import reset_storage

    os.environ["UF_STORAGE_BACKEND"] = "local"
    os.environ["UF_STORAGE_LOCAL_ROOT"] = str(tmp_path_factory.mktemp("storage"))
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
    kratos.add("rootr", f"rootr-{s}@unitforma.example.com", aal="aal2")
    assert client.get("/api/v1/admin/me", headers=cookie("rootr")).status_code == 200
    eng = create_engine(os.environ["UF_TEST_DATABASE_ADMIN_URL"])
    with eng.begin() as conn:
        conn.execute(
            text("UPDATE users SET is_platform_admin = true WHERE email = :e"),
            {"e": f"rootr-{s}@unitforma.example.com"},
        )
    eng.dispose()
    from unitforma.identity.deps import clear_whoami_cache

    clear_whoami_cache()
    root = cookie("rootr")
    kratos.add("pm", f"pm-{s}@a.example.com")
    kratos.add("salesr", f"salesr-{s}@a.example.com")
    t = client.post(
        "/api/v1/platform/tenants", headers=root, json={"slug": f"reg{s}", "name": "Reg Co"}
    ).json()
    other = client.post(
        "/api/v1/platform/tenants", headers=root, json={"slug": f"oth{s}", "name": "Other Co"}
    ).json()
    base = f"/api/v1/admin/tenants/{t['id']}"
    inv = client.post(
        f"/api/v1/platform/tenants/{t['id']}/invitations",
        headers=root,
        params={"email": f"pm-{s}@a.example.com"},
    ).json()
    client.post(
        "/api/v1/admin/invitations/accept",
        headers=cookie("pm"),
        json={"token": inv["accept_url"].rsplit("/", 1)[1]},
    )
    inv2 = client.post(
        f"{base}/invitations",
        headers=cookie("pm"),
        json={
            "email": f"salesr-{s}@a.example.com",
            "role": "sales",
            "all_projects": True,
            "project_ids": [],
        },
    ).json()
    client.post(
        "/api/v1/admin/invitations/accept",
        headers=cookie("salesr"),
        json={"token": inv2["accept_url"].rsplit("/", 1)[1]},
    )
    fetcher = FakeFetcher()
    service.set_fetcher(fetcher)
    yield {"root": root, "base": base, "tenant": t, "other": other, "fetcher": fetcher, "s": s}
    service.set_fetcher(None)


@pytestmark_db
def test_preview_shows_what_an_import_will_do(client: TestClient, world: dict):
    r = client.post(
        f"{world['base']}/regulatory/tasge/preview",
        headers=cookie("pm"),
        json={"reference": f"https://tas.ge/?p=publicpage&documentId={DOC_ID}"},
    )
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["suggestions"] == {
        "name": "Residential house B-7",
        "slug": f"permit-{DOC_ID}",
        "building_code": "B-7",
    }
    assert p["heights"] == {"above_zero_m": 14.7, "below_zero_m": 4.05}
    assert p["counts"] == {"import": 2, "skip": 1}
    assert PERSONAL_NUMBER not in r.text and PHONE not in r.text
    # sales may not bootstrap projects
    assert (
        client.post(
            f"{world['base']}/regulatory/tasge/preview",
            headers=cookie("salesr"),
            json={"reference": str(DOC_ID)},
        ).status_code
        == 403
    )


@pytestmark_db
def test_import_creates_project_building_and_documents(client: TestClient, world: dict):
    from unitforma.regulatory.service import import_attachments

    base, fetcher = world["base"], world["fetcher"]
    r = client.post(
        f"{base}/regulatory/tasge/import",
        headers=cookie("pm"),
        json={"reference": str(DOC_ID), "slug": f"permit-{world['s']}"},
    )
    assert r.status_code == 201, r.text
    res = r.json()
    project, building, job = res["project"], res["building"], res["job"]
    assert project["name"] == "Residential house B-7"
    assert project["address"] == {"line1": "Test city, Example street 7"}
    assert project["regulatory"]["external_id"] == str(DOC_ID)
    assert project["regulatory"]["import_id"] == job["id"]
    assert building["code"] == "B-7"
    assert job["status"] == "importing" and job["permit"]["application_no"] == f"AR1{DOC_ID}"
    # floors are the user's (Decision 5)
    assert building["floors"] == []
    # a refresh while the import runs is refused
    assert (
        client.post(
            f"{base}/projects/{project['id']}/regulatory/tasge/refresh", headers=cookie("pm")
        ).status_code
        == 409
    )

    # the worker: downloads the two importable files, skips the ArchiCAD one
    result = client.portal.call(
        import_attachments, uuid.UUID(world["tenant"]["id"]), uuid.UUID(job["id"])
    )
    assert result == {"imported": 2, "existing": 0, "skipped": 1, "failed": 0}, result
    assert sorted(fetcher.downloads) == [
        tasge.ATTACHMENT_URL.format(id=901),
        tasge.ATTACHMENT_URL.format(id=902),
    ]
    docs = client.get(f"{base}/projects/{project['id']}/documents", headers=cookie("pm")).json()
    by_file = {
        d["source"]["attached_file_id"]: d for d in docs if d["source"].get("system") == "tasge"
    }
    assert set(by_file) == {901, 902}
    assert by_file[901]["kind"] == "floor_plan" and by_file[902]["kind"] == "elevation"
    assert by_file[901]["current_revision"]["file_name"] == "გეგმები.pdf"
    assert by_file[901]["current_revision"]["processing_status"] in ("queued", "processing", "done")
    imports = client.get(
        f"{base}/projects/{project['id']}/regulatory/imports", headers=cookie("pm")
    ).json()
    assert imports[0]["status"] == "done"
    assert imports[0]["counts"] == {"imported": 2, "existing": 0, "skipped": 1, "failed": 0}
    assert imports[0]["stats"]["skipped"][0]["file_name"] == "model.pla"

    # refresh: nothing new on the registry → nothing imported twice (Decision 7)
    r = client.post(
        f"{base}/projects/{project['id']}/regulatory/tasge/refresh", headers=cookie("pm")
    )
    assert r.status_code == 200, r.text
    result = client.portal.call(
        import_attachments, uuid.UUID(world["tenant"]["id"]), uuid.UUID(r.json()["id"])
    )
    assert result == {"imported": 0, "existing": 2, "skipped": 1, "failed": 0}
    assert (
        len(client.get(f"{base}/projects/{project['id']}/documents", headers=cookie("pm")).json())
        == 2
    )
    assert fetcher.records == 3  # preview, import, refresh: one fetch per user action

    # another tenant cannot see the imports; sales cannot refresh
    other_base = f"/api/v1/admin/tenants/{world['other']['id']}"
    assert (
        client.get(
            f"{other_base}/projects/{project['id']}/regulatory/imports", headers=world["root"]
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{base}/projects/{project['id']}/regulatory/tasge/refresh", headers=cookie("salesr")
        ).status_code
        == 403
    )


@pytestmark_db
def test_feature_flag_hides_the_endpoints(client: TestClient, world: dict):
    from unitforma.core.settings import get_settings

    settings = get_settings()
    settings.regulatory_tasge_enabled = False
    try:
        r = client.post(
            f"{world['base']}/regulatory/tasge/preview",
            headers=cookie("pm"),
            json={"reference": str(DOC_ID)},
        )
        assert r.status_code == 404
    finally:
        settings.regulatory_tasge_enabled = True
