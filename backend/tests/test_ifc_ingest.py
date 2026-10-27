"""ADR-0006 Phase C with IfcOpenShell: a synthetic IFC4 building (two storeys, three spaces, a
wall and a slab) is read, tessellated into a GLB with one node per space, its spaces are matched
to existing units, and a reviewer confirms a link, which writes the IFC areas on the unit."""

from __future__ import annotations

import os
import shutil
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.fake_kratos import FakeKratos, cookie

ifcopenshell = pytest.importorskip("ifcopenshell", reason="IFC extra not installed")

from unitforma.geometry import ifc  # noqa: E402
from unitforma.geometry.massing import parse_glb  # noqa: E402


def make_ifc(*, long_names: bool = True) -> bytes:
    """IFC4: building A, storeys at 0.00 and 3.20, spaces 1 and 2 on the ground floor and 3 above,
    one wall and one slab; space 1 carries base quantities."""
    import ifcopenshell.api
    import ifcopenshell.util.shape_builder as sb
    import numpy as np

    f = ifcopenshell.api.run("project.create_file", version="IFC4")
    proj = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="Test")
    # metres, like the exports we expect (the api default is millimetres)
    ifcopenshell.api.run("unit.assign_unit", f, length={"is_metric": True, "raw": "METERS"})
    ctx = ifcopenshell.api.run("context.add_context", f, context_type="Model")
    body = ifcopenshell.api.run(
        "context.add_context",
        f,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=ctx,
    )
    site = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite", name="Site")
    bld = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuilding", name="A")
    st0 = ifcopenshell.api.run(
        "root.create_entity", f, ifc_class="IfcBuildingStorey", name="Ground"
    )
    st0.Elevation = 0.0
    st1 = ifcopenshell.api.run(
        "root.create_entity", f, ifc_class="IfcBuildingStorey", name="Level 1"
    )
    st1.Elevation = 3.2
    ifcopenshell.api.run("aggregate.assign_object", f, products=[site], relating_object=proj)
    ifcopenshell.api.run("aggregate.assign_object", f, products=[bld], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", f, products=[st0, st1], relating_object=bld)
    builder = sb.ShapeBuilder(f)

    def box(cls, name, x, y, z, dx, dy, dz, storey):
        e = ifcopenshell.api.run("root.create_entity", f, ifc_class=cls, name=name)
        rect = builder.rectangle(size=np.array([dx, dy]))
        solid = builder.extrude(rect, magnitude=dz)
        rep = builder.get_representation(body, [solid])
        ifcopenshell.api.run("geometry.assign_representation", f, product=e, representation=rep)
        mat = np.eye(4)
        mat[:3, 3] = [x, y, z]
        ifcopenshell.api.run("geometry.edit_object_placement", f, product=e, matrix=mat)
        if cls == "IfcSpace":
            # spaces are spatial elements: aggregated under the storey, not "contained" like walls
            ifcopenshell.api.run("aggregate.assign_object", f, products=[e], relating_object=storey)
        else:
            ifcopenshell.api.run(
                "spatial.assign_container", f, products=[e], relating_structure=storey
            )
        return e

    sp1 = box("IfcSpace", "1", 0, 0, 0, 8, 6, 3.2, st0)
    if long_names:
        sp1.LongName = "ბინა 1"
    box("IfcSpace", "2", 8, 0, 0, 8, 6, 3.2, st0)
    box("IfcSpace", "3", 0, 0, 3.2, 16, 6, 3.2, st1)
    box("IfcWall", "W1", 0, -0.3, 0, 16, 0.3, 6.4, st0)
    box("IfcSlab", "S1", 0, 0, -0.3, 16, 6, 0.3, st0)
    qto = ifcopenshell.api.run("pset.add_qto", f, product=sp1, name="Qto_SpaceBaseQuantities")
    ifcopenshell.api.run(
        "pset.edit_qto", f, qto=qto, properties={"NetFloorArea": 47.5, "GrossFloorArea": 48.0}
    )
    return f.to_string().encode("utf-8")


def test_read_ifc_storeys_spaces_footprints_and_glb():
    model = ifc.read_ifc(make_ifc())
    assert model.schema.startswith("IFC4") and model.building_name == "A"
    assert [(s.name, s.elevation_m) for s in model.storeys] == [("Ground", 0.0), ("Level 1", 3.2)]
    by_name = {s.name: s for s in model.spaces}
    assert set(by_name) == {"1", "2", "3"}
    assert by_name["1"].long_name == "ბინა 1" and by_name["1"].storey.name == "Ground"
    assert by_name["3"].storey.index == 1
    assert by_name["1"].areas == {"net_floor_area": 47.5, "gross_floor_area": 48.0}
    ring = by_name["2"].footprint_m
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    assert (round(min(xs), 1), round(max(xs), 1), round(min(ys), 1), round(max(ys), 1)) == (
        8.0,
        16.0,
        0.0,
        6.0,
    )
    gltf, blob = parse_glb(model.glb)
    names = {n["name"] for n in gltf["nodes"]}
    assert {"1", "2", "3", "IfcWall", "IfcSlab", "A"} <= names
    space_nodes = [n for n in gltf["nodes"] if n.get("extras", {}).get("ifc_global_id")]
    assert len(space_nodes) == 3 and all(
        n["extras"]["unit_id"].startswith("space:") for n in space_nodes
    )
    wall = next(n for n in gltf["nodes"] if n["name"] == "IfcWall")
    assert "unit_id" not in wall["extras"] and wall["extras"]["elements"] == 1
    assert gltf["extras"]["unitforma"]["kind"] == "ifc"
    assert model.stats["spaces"] == 3 and model.stats["bytes"] == len(model.glb)
    assert model.stats["compression"] == "none"
    # Y is up in the GLB: the first storey's space spans 0..3.2 in Y
    acc = gltf["accessors"][gltf["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    assert round(acc["min"][1], 2) >= -0.31 and round(acc["max"][1], 1) in (3.2, 3.5)


def test_compress_glb_without_the_cli_returns_the_input(monkeypatch):
    monkeypatch.setattr(ifc.shutil, "which", lambda _name: None)
    glb = ifc.read_ifc(make_ifc()).glb
    assert ifc.compress_glb(glb) == (glb, "none")


@pytest.mark.skipif(
    shutil.which("gltf-transform") is None, reason="gltf-transform CLI not installed"
)
def test_compress_glb_draco_keeps_extras_and_relinks():
    model = ifc.read_ifc(make_ifc())
    small, how = ifc.compress_glb(model.glb)
    assert how == "draco" and len(small) < len(model.glb)
    gltf, _ = parse_glb(small)
    assert "KHR_draco_mesh_compression" in gltf["extensionsRequired"]
    gids = {s.global_id for s in model.spaces}
    nodes = [n for n in gltf["nodes"] if (n.get("extras") or {}).get("ifc_global_id") in gids]
    assert len(nodes) == len(gids)
    gid = next(iter(gids))
    relinked, _ = parse_glb(ifc.relink_glb(small, {gid: "unit-1"}))
    assert "KHR_draco_mesh_compression" in relinked["extensionsRequired"]
    node = next(n for n in relinked["nodes"] if n["extras"].get("ifc_global_id") == gid)
    assert node["extras"]["unit_id"] == "unit-1"


def test_read_ifc_refuses_other_files_and_respects_the_budget():
    with pytest.raises(ifc.IfcError):
        ifc.read_ifc(b"%PDF-1.4")
    with pytest.raises(ifc.IfcError) as e:
        ifc.read_ifc(make_ifc(), budget=200)
    assert "budget" in str(e.value)


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


def _document(client: TestClient, base: str, project_id: str, doc_id: str, headers: dict) -> dict:
    docs = client.get(f"{base}/projects/{project_id}/documents", headers=headers).json()
    return next(d for d in docs if d["id"] == doc_id)


@pytestmark_db
def test_ifc_upload_links_spaces_to_units_and_confirmation_writes_areas(
    kratos: FakeKratos, client: TestClient
):
    from unitforma.documents.jobs import process_revision
    from unitforma.geometry.ifc_service import ingest_ifc

    s = uuid.uuid4().hex[:6]
    kratos.add("rooti", f"rooti-{s}@unitforma.example.com", aal="aal2")
    assert client.get("/api/v1/admin/me", headers=cookie("rooti")).status_code == 200
    eng = create_engine(os.environ["UF_TEST_DATABASE_ADMIN_URL"])
    with eng.begin() as conn:
        conn.execute(
            text("UPDATE users SET is_platform_admin = true WHERE email = :e"),
            {"e": f"rooti-{s}@unitforma.example.com"},
        )
    eng.dispose()
    from unitforma.identity.deps import clear_whoami_cache

    clear_whoami_cache()
    root = cookie("rooti")
    t = client.post(
        "/api/v1/platform/tenants", headers=root, json={"slug": f"ifc{s}", "name": "I"}
    ).json()
    base = f"/api/v1/admin/tenants/{t['id']}"
    tid = uuid.UUID(t["id"])
    p = client.post(f"{base}/projects", headers=root, json={"slug": "ifc", "name": "IFC"}).json()
    b = client.post(f"{base}/projects/{p['id']}/buildings", headers=root, json={"code": "A"}).json()
    floors = client.put(
        f"{base}/buildings/{b['id']}/floors",
        headers=root,
        json={
            "floors": [
                {"level": 0, "display_name": "Ground", "elevation_m": "0"},
                {"level": 1, "display_name": "1", "elevation_m": "3.2"},
            ]
        },
    ).json()
    # two units exist on the ground floor from an earlier plan mapping (labels 1 and 2)
    from tests.pdf_fixture import make_plan_pdf

    doc = client.post(
        f"{base}/projects/{p['id']}/documents",
        headers=root,
        json={"kind": "floor_plan", "title": "Plans", "building_id": b["id"]},
    ).json()
    pdf = make_plan_pdf()
    intent = client.post(
        f"{base}/documents/{doc['id']}/uploads",
        headers=root,
        json={
            "file_name": "plans.pdf",
            "content_type": "application/pdf",
            "byte_size": len(pdf),
            "source_note": None,
        },
    ).json()
    client.put(intent["upload_url"], content=pdf, headers={"Content-Type": "application/pdf"})
    rev = client.post(f"{base}/revisions/{intent['revision']['id']}/complete", headers=root).json()
    client.portal.call(process_revision, tid, uuid.UUID(rev["id"]))
    sheets = client.get(f"{base}/revisions/{rev['id']}/sheets", headers=root).json()
    ground = next(sh for sh in sheets if sh["page_no"] == 1)
    client.patch(
        f"{base}/sheets/{ground['id']}/floor",
        headers=root,
        json={"floor_id": floors[0]["id"], "version": ground["version"]},
    )
    ground = client.get(f"{base}/revisions/{rev['id']}/sheets", headers=root).json()[0]
    client.patch(
        f"{base}/sheets/{ground['id']}/calibration",
        headers=root,
        json={
            "calibration": {"p1": [0.1, 0.5], "p2": [0.9, 0.5], "distance_m": 16.0},
            "version": ground["version"],
        },
    )
    units = []
    for ring, label in (
        ([[0.1, 0.3], [0.5, 0.3], [0.5, 0.7], [0.1, 0.7]], "ბინა №1"),
        ([[0.5, 0.3], [0.9, 0.3], [0.9, 0.7], [0.5, 0.7]], "ბინა №2"),
    ):
        r = client.post(
            f"{base}/sheets/{ground['id']}/boundaries",
            headers=root,
            json={"ring": ring, "unit_type": "apartment", "label": label, "source": "manual"},
        )
        assert r.status_code == 201, r.text
        units.append(r.json()["unit"])

    # the IFC upload, filed under the building, without a kind: the file type fixes it
    # (ADR-0008 amendment) at the upload intent, and the worker keeps it
    ifc_doc = client.post(
        f"{base}/projects/{p['id']}/documents",
        headers=root,
        json={"title": "Model", "building_id": b["id"]},
    ).json()
    assert (ifc_doc["kind"], ifc_doc["kind_source"]) == ("unclassified", "pending")
    data = make_ifc()
    intent = client.post(
        f"{base}/documents/{ifc_doc['id']}/uploads",
        headers=root,
        json={
            "file_name": "a.ifc",
            "content_type": "application/x-step",
            "byte_size": len(data),
            "source_note": None,
        },
    ).json()
    got = _document(client, base, p["id"], ifc_doc["id"], root)
    assert (got["kind"], got["kind_source"]) == ("model_ifc", "type")
    client.put(intent["upload_url"], content=data, headers={"Content-Type": "application/x-step"})
    rev2 = client.post(f"{base}/revisions/{intent['revision']['id']}/complete", headers=root).json()
    out = client.portal.call(process_revision, tid, uuid.UUID(rev2["id"]))
    assert out["ifc"] is True
    got = _document(client, base, p["id"], ifc_doc["id"], root)
    assert (got["kind"], got["kind_source"]) == ("model_ifc", "type")
    result = client.portal.call(ingest_ifc, tid, uuid.UUID(rev2["id"]))
    assert result["status"] == "ready", result
    assert result["stats"]["spaces"] == 3 and result["stats"]["spaces_suggested"] >= 2
    assert "application" in result["stats"]

    # the same bytes declared as a generic binary under a misleading name: the worker fixes the
    # kind from the sniffed content, and a person's kind is never replaced
    other = client.post(
        f"{base}/projects/{p['id']}/documents",
        headers=root,
        json={"title": "Scan", "building_id": b["id"]},
    ).json()
    intent = client.post(
        f"{base}/documents/{other['id']}/uploads",
        headers=root,
        json={
            "file_name": "scan0001.bin",
            "content_type": "application/octet-stream",
            "byte_size": len(data),
            "source_note": None,
        },
    ).json()
    got = _document(client, base, p["id"], other["id"], root)
    assert (got["kind"], got["kind_source"]) == ("unclassified", "pending")
    client.put(
        intent["upload_url"], content=data, headers={"Content-Type": "application/octet-stream"}
    )
    rev3 = client.post(f"{base}/revisions/{intent['revision']['id']}/complete", headers=root).json()
    assert client.portal.call(process_revision, tid, uuid.UUID(rev3["id"]))["ifc"] is True
    got = _document(client, base, p["id"], other["id"], root)
    assert (got["kind"], got["kind_source"]) == ("model_ifc", "type")
    manual = client.post(
        f"{base}/projects/{p['id']}/documents",
        headers=root,
        json={"kind": "other", "title": "Kept", "building_id": b["id"]},
    ).json()
    client.post(
        f"{base}/documents/{manual['id']}/uploads",
        headers=root,
        json={
            "file_name": "kept.ifc",
            "content_type": "application/x-step",
            "byte_size": len(data),
            "source_note": None,
        },
    )
    got = _document(client, base, p["id"], manual["id"], root)
    assert (got["kind"], got["kind_source"]) == ("other", "manual")

    model = client.get(f"{base}/buildings/{b['id']}/model", headers=root).json()
    assert model["kind"] == "ifc" and model["glb_url"] and model["links"]["suggested"] >= 2
    links = {
        lk["name"]: lk
        for lk in client.get(f"{base}/buildings/{b['id']}/ifc-links", headers=root).json()
    }
    assert links["1"]["unit_code"] == units[0]["code"] and float(links["1"]["confidence"]) == 0.9
    assert links["2"]["unit_code"] == units[1]["code"]
    assert links["3"]["status"] == "unmatched" and links["3"]["floor_level"] == 1
    # the reviewer confirms space 1: the unit gets the IFC quantities as areas
    r = client.post(
        f"{base}/ifc-links/{links['1']['id']}", headers=root, json={"decision": "confirm"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "confirmed"
    areas = client.get(f"{base}/units/{units[0]['id']}", headers=root).json()["areas"]
    ifc_areas = {a["area_type"]: a for a in areas if a["source"] == "ifc_quantity"}
    assert set(ifc_areas) == {"net_internal", "gross_internal"}
    assert ifc_areas["net_internal"]["value_m2"] in ("47.50", "47.5")
    # another space cannot be confirmed as the same unit
    r = client.post(
        f"{base}/ifc-links/{links['2']['id']}",
        headers=root,
        json={"decision": "confirm", "unit_id": units[0]["id"]},
    )
    assert r.status_code == 409
    # the model's GLB now picks space 1 as the unit
    model = client.get(f"{base}/buildings/{b['id']}/model", headers=root).json()
    glb = client.get(model["glb_url"]).content
    gltf, _ = parse_glb(glb)
    space1 = next(
        n
        for n in gltf["nodes"]
        if n.get("extras", {}).get("ifc_global_id") == links["1"]["ifc_global_id"]
    )
    assert space1["extras"]["unit_id"] == units[0]["id"]
    # an unconfirmed space keeps its space id but already carries the matched floor's level
    space3 = next(
        n
        for n in gltf["nodes"]
        if n.get("extras", {}).get("ifc_global_id") == links["3"]["ifc_global_id"]
    )
    assert space3["extras"]["unit_id"] == f"space:{links['3']['ifc_global_id']}"
    assert space3["extras"]["floor_level"] == 1
