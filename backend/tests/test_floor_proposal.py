"""ADR-0010: floors proposed from the drawings' level markers, accepted through PUT /floors."""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.fake_kratos import FakeKratos, cookie
from tests.pdf_fixture import make_plan_pdf
from unitforma.documents import storeys
from unitforma.documents.levels import Marker


def _m(text_: str, x: float = 0.1, y: float = 0.1) -> Marker:
    return Marker(text=text_, value=float(text_.replace("+", "")), x=x, y=y)


def _plan(text_: str) -> list[Marker]:
    return [_m(text_, x=0.2, y=0.9)]


def _section(*texts: str) -> list[Marker]:
    return [_m(t, x=0.05, y=0.9 - i * 0.15) for i, t in enumerate(texts)]


def test_pilot_like_stack_with_basement_and_roof():
    markers = {
        "p0": _plan("-4.05"),
        "p1": _plan("+0.00"),
        "p2": _plan("+3.20"),
        "p3": _plan("+6.40"),
        "p4": _plan("+9.60"),
        "s1": _section("-4.05", "+0.00", "+3.20", "+6.40", "+9.60", "+14.70"),
        "s2": _section("+0.00", "+3.20", "+6.40", "+9.60", "+14.70"),
    }
    floors, unmatched, roof = storeys.propose(markers, [])
    assert [(f.level, f.display_name, f.elevation_m) for f in floors] == [
        (-1, "B1", -4.05),
        (0, "Ground", 0.0),
        (1, "1", 3.2),
        (2, "2", 6.4),
        (3, "3", 9.6),
    ]
    assert [f.height_m for f in floors] == [4.05, 3.2, 3.2, 3.2, 5.1]  # top from the roof
    assert roof == {"elevation_m": 14.7, "sheets": 2}
    assert all(f.status == "new" for f in floors) and unmatched == []
    assert floors[1].sheets == 3  # plan + two sections print 0.00


def test_split_level_block_markers_stay_distinct_and_close_ones_merge():
    markers = {
        "a": _plan("+3.20"),
        "b": _plan("+4.20"),
        "c": _plan("+5.20"),
        "d": [_m("+3.22", x=0.6, y=0.5)],  # the same storey printed slightly off
    }
    floors, _, roof = storeys.propose(markers, [])
    assert [f.elevation_m for f in floors] == [3.21, 4.2, 5.2]  # median of +3.20 and +3.22
    assert floors[0].sheets == 2
    assert roof == {}
    # nothing near 0.00: the lowest storey at or above zero is the ground
    assert [f.level for f in floors] == [0, 1, 2]


def test_existing_floors_are_kept_updated_or_reported():
    existing = [
        storeys.ExistingFloor(
            id="g", level=0, display_name="Entrance", elevation_m=0.0, height_m=3.5
        ),
        storeys.ExistingFloor(id="one", level=1, display_name="1", elevation_m=None, height_m=None),
        storeys.ExistingFloor(
            id="nine", level=9, display_name="9", elevation_m=None, height_m=None
        ),
    ]
    markers = {"p1": _plan("+0.00"), "p2": _plan("+3.20"), "p3": _plan("+6.40")}
    floors, unmatched, _ = storeys.propose(markers, existing)
    assert [(f.status, f.level, f.display_name, f.height_m) for f in floors] == [
        ("existing", 0, "Entrance", 3.5),  # matched by elevation, its own name and height kept
        ("update", 1, "1", 3.2),  # matched by level number, elevation filled
        ("new", 2, "2", 3.2),
    ]
    assert [f.id for f in unmatched] == ["nine"]


def test_no_markers_or_only_sections_gives_nothing():
    assert storeys.propose({}, []) == ([], [], {})
    floors, _, roof = storeys.propose({"s": _section("+0.00", "+3.20", "+6.40")}, [])
    assert floors == [] and roof == {}


# --------------------------------------------------------------------------- through the API
pytestmark_db = pytest.mark.skipif(
    not (os.environ.get("UF_TEST_DATABASE_ADMIN_URL") and os.environ.get("UF_TEST_DATABASE_URL")),
    reason="needs the PostgreSQL test database",
)


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


@pytestmark_db
def test_proposal_from_an_uploaded_plan_set_and_acceptance(kratos: FakeKratos, client: TestClient):
    from unitforma.documents.jobs import process_revision

    s = uuid.uuid4().hex[:6]
    kratos.add("rootf", f"rootf-{s}@unitforma.example.com", aal="aal2")
    assert client.get("/api/v1/admin/me", headers=cookie("rootf")).status_code == 200
    eng = create_engine(os.environ["UF_TEST_DATABASE_ADMIN_URL"])
    with eng.begin() as conn:
        conn.execute(
            text("UPDATE users SET is_platform_admin = true WHERE email = :e"),
            {"e": f"rootf-{s}@unitforma.example.com"},
        )
    eng.dispose()
    from unitforma.identity.deps import clear_whoami_cache

    clear_whoami_cache()
    root = cookie("rootf")
    t = client.post(
        "/api/v1/platform/tenants", headers=root, json={"slug": f"flr{s}", "name": "F"}
    ).json()
    base = f"/api/v1/admin/tenants/{t['id']}"
    p = client.post(f"{base}/projects", headers=root, json={"slug": "flr", "name": "Floors"}).json()
    b = client.post(f"{base}/projects/{p['id']}/buildings", headers=root, json={"code": "A"}).json()
    # no floors yet: the proposal is empty until a drawing is processed
    r = client.get(f"{base}/buildings/{b['id']}/floor-proposal", headers=root)
    assert (
        r.status_code == 200 and r.json()["floors"] == [] and r.json()["sheets_with_markers"] == 0
    )

    doc = client.post(
        f"{base}/projects/{p['id']}/documents",
        headers=root,
        json={"kind": "floor_plan", "title": "Plans", "building_id": b["id"]},
    ).json()
    data = make_plan_pdf()
    intent = client.post(
        f"{base}/documents/{doc['id']}/uploads",
        headers=root,
        json={
            "file_name": "plans.pdf",
            "content_type": "application/pdf",
            "byte_size": len(data),
            "source_note": None,
        },
    ).json()
    client.put(intent["upload_url"], content=data, headers={"Content-Type": "application/pdf"})
    rev = client.post(f"{base}/revisions/{intent['revision']['id']}/complete", headers=root).json()
    client.portal.call(process_revision, uuid.UUID(t["id"]), uuid.UUID(rev["id"]))

    prop = client.get(f"{base}/buildings/{b['id']}/floor-proposal", headers=root).json()
    assert prop["sheets_with_markers"] == 2
    assert [
        (f["level"], f["display_name"], f["elevation_m"], f["height_m"], f["status"])
        for f in prop["floors"]
    ] == [
        (0, "Ground", 0.0, 3.2, "new"),
        (1, "1", 3.2, 3.2, "new"),
    ]
    assert prop["counts"] == {"new": 2, "update": 0, "existing": 0}

    # accept through the floors endpoint that exists
    r = client.put(
        f"{base}/buildings/{b['id']}/floors",
        headers=root,
        json={
            "floors": [
                {
                    "level": f["level"],
                    "display_name": f["display_name"],
                    "elevation_m": str(f["elevation_m"]),
                    "height_m": str(f["height_m"]),
                }
                for f in prop["floors"]
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert [(f["level"], f["elevation_m"]) for f in r.json()] == [(0, "0.000"), (1, "3.200")]
    prop2 = client.get(f"{base}/buildings/{b['id']}/floor-proposal", headers=root).json()
    assert prop2["counts"] == {"new": 0, "update": 0, "existing": 2}
    assert prop2["floors"][0]["floor_id"] == r.json()[0]["id"]
