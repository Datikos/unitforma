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

from unitforma.geometry import ifc, plan_spaces  # noqa: E402
from unitforma.geometry.massing import parse_glb  # noqa: E402


def make_ifc(*, long_names: bool = True, spaces: bool = True, millimetres: bool = False) -> bytes:
    """IFC4: building A, storeys at 0.00 and 3.20, spaces 1 and 2 on the ground floor and 3 above,
    one wall and one slab; space 1 carries base quantities. ``spaces=False`` is the zoneless
    export of ADR-0030: storeys, wall and slab only."""
    import ifcopenshell.api
    import ifcopenshell.util.shape_builder as sb
    import numpy as np

    f = ifcopenshell.api.run("project.create_file", version="IFC4")
    proj = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="Test")
    # metres, like the exports we expect (the api default is millimetres); ``millimetres`` is
    # the Archicad export of 2026-10-27, whose Elevation attributes read 3200 for 3.2 m
    k = 1000.0 if millimetres else 1.0
    ifcopenshell.api.run(
        "unit.assign_unit",
        f,
        length={"is_metric": True, "raw": "MILLIMETERS" if millimetres else "METERS"},
    )
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
    st0.Elevation = 0.0 * k
    st1 = ifcopenshell.api.run(
        "root.create_entity", f, ifc_class="IfcBuildingStorey", name="Level 1"
    )
    st1.Elevation = 3.2 * k
    ifcopenshell.api.run("aggregate.assign_object", f, products=[site], relating_object=proj)
    ifcopenshell.api.run("aggregate.assign_object", f, products=[bld], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", f, products=[st0, st1], relating_object=bld)
    builder = sb.ShapeBuilder(f)

    def box(cls, name, x, y, z, dx, dy, dz, storey):
        e = ifcopenshell.api.run("root.create_entity", f, ifc_class=cls, name=name)
        rect = builder.rectangle(size=np.array([dx * k, dy * k]))
        solid = builder.extrude(rect, magnitude=dz * k)
        rep = builder.get_representation(body, [solid])
        ifcopenshell.api.run("geometry.assign_representation", f, product=e, representation=rep)
        mat = np.eye(4)
        mat[:3, 3] = [x * k, y * k, z * k]
        ifcopenshell.api.run("geometry.edit_object_placement", f, product=e, matrix=mat)
        if cls == "IfcSpace":
            # spaces are spatial elements: aggregated under the storey, not "contained" like walls
            ifcopenshell.api.run("aggregate.assign_object", f, products=[e], relating_object=storey)
        else:
            ifcopenshell.api.run(
                "spatial.assign_container", f, products=[e], relating_structure=storey
            )
        return e

    box("IfcWall", "W1", 0, -0.3, 0, 16, 0.3, 6.4, st0)
    box("IfcSlab", "S1", 0, 0, -0.3, 16, 6, 0.3, st0)
    if not spaces:
        return f.to_string().encode("utf-8")
    sp1 = box("IfcSpace", "1", 0, 0, 0, 8, 6, 3.2, st0)
    if long_names:
        sp1.LongName = "ბინა 1"
    box("IfcSpace", "2", 8, 0, 0, 8, 6, 3.2, st0)
    box("IfcSpace", "3", 0, 0, 3.2, 16, 6, 3.2, st1)
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


ARCHICAD_HEADER = (
    "ViewDefinition [CoordinationView_V2.0, SurfaceGeometryAddOnView]",
    "Option [Elements to export: Visible elements (on all stories)]",
    "Option [Partial Structure Display: Entire Model]",
    "Option [IFC Domain: All]",
    "Option [Material Preservation: Explode all]",
    "Option [Space containment: Off]",
    "Option [IFC Base Quantities: Off]",
    "Option [IFC Space boundaries: Off]",
)


def test_parse_ifc_scales_storey_elevations_by_the_file_unit():
    """ADR-0030 amendment: a millimetre file says Elevation 3200; the storey is at 3.2 m and the
    geometry still spans 16 m (the tessellator already converts it)."""
    parsed = ifc.parse_ifc(make_ifc(millimetres=True, spaces=False))
    assert parsed.unit_scale == pytest.approx(0.001)
    assert [s.elevation_m for s in parsed.storeys] == [0.0, 3.2]
    x0, _y0, x1, _y1 = parsed.bounds
    assert x1 - x0 == pytest.approx(16.0, abs=0.01)
    target = plan_spaces.storey_target(parsed, parsed.storeys[0].global_id)
    assert (
        target is not None and target[1] == "slabs" and target[0].area == pytest.approx(96, abs=1)
    )


def _parsed_with_slabs(slabs: dict[str, list[list[list[float]]]], elevations: list[float]):
    """A hand-made ParsedIfc: storeys at the given elevations, slab rings per storey name."""
    storeys = [
        ifc.Storey(global_id=f"S{i}", name=f"st{i}", elevation_m=e, index=i)
        for i, e in enumerate(elevations)
    ]
    rings = {f"S{i}": slabs.get(f"st{i}", []) for i in range(len(elevations))}
    pts = [pt for rs in rings.values() for r in rs for pt in r]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return ifc.ParsedIfc(
        schema="IFC4",
        building_name="T",
        application=None,
        export_options={},
        storeys=storeys,
        spaces=[],
        space_geo=[],
        class_geo={},
        offset=(min(xs), min(ys), 0.0),
        elements_failed=0,
        storey_slabs=rings,
        bounds=(min(xs), min(ys), max(xs), max(ys)),
    )


def _rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def test_plan_spaces_fit_the_project_when_the_block_alone_does_not():
    """ADR-0030 amendment: block B holds the left half of a 40 × 10 slab, block C the right half.
    B's outlines alone fit anywhere inside the slab; with C's outlines on the same level the fit
    is pinned (scope project), B's spaces land on the left, and C gets no spaces here."""
    parsed = _parsed_with_slabs({"st0": [_rect(0, 0, 40, 10)]}, [0.0, 3.0])
    floors = [plan_spaces.PlanFloor(id="fB0", level=0, elevation_m=0.0, base_m=0.0, height_m=3.0)]
    # sheet frame (y down): B at x 0–20, C at x 20–40; the IFC frame flips y
    outlines = [
        plan_spaces.Outline(uuid.uuid4(), "B-1", "fB0", _rect(0, 0, 10, 10), "B", 0),
        plan_spaces.Outline(uuid.uuid4(), "B-2", "fB0", _rect(10, 0, 20, 10), "B", 0),
        plan_spaces.Outline(uuid.uuid4(), "C-1", "fC0", _rect(20, 0, 40, 10), "C", 0),
    ]
    spaces, info = plan_spaces.build(parsed, floors, outlines, building_id="B")
    assert "reason" not in info, info
    assert info["scope"] == "project" and info["face"] == "slabs" and info["iou"] > 0.95, info
    assert [sp.name for sp, _v, _f in spaces] == ["B-1", "B-2"]
    xs = [x for sp, _v, _f in spaces for x, _y in sp.footprint_m]
    assert max(xs) <= 20.5 and min(xs) >= -0.5, xs  # the left half of the slab
    assert all(sp.source == "plan" and sp.floor_level == 0 for sp, _v, _f in spaces)
    # the same building alone: accepted too (a 20 × 10 rectangle inside 40 × 10 is IoU 0.5)
    spaces_alone, info_alone = plan_spaces.build(parsed, floors, outlines[:2], building_id="B")
    assert len(spaces_alone) == 2 and info_alone["scope"] == "building"


def test_plan_spaces_use_the_hull_when_the_slabs_are_exploded():
    """Four small landings in the corners are all that is left as IfcSlab: the hull is the target
    and the reason names the overlap when the outlines are far too small for it."""
    corners = [_rect(0, 0, 1, 1), _rect(39, 0, 40, 1), _rect(0, 9, 1, 10), _rect(39, 9, 40, 10)]
    parsed = _parsed_with_slabs({"st0": corners}, [0.0])
    floors = [plan_spaces.PlanFloor(id="f0", level=0, elevation_m=0.0, base_m=0.0, height_m=3.0)]
    one = [plan_spaces.Outline(uuid.uuid4(), "A-1", "f0", _rect(0, 0, 4, 4), "A", 0)]
    spaces, info = plan_spaces.build(parsed, floors, one, building_id="A")
    assert info["face"] == "hull" and spaces == [] and "overlap" in info["reason"], info
    whole = [plan_spaces.Outline(uuid.uuid4(), "A-1", "f0", _rect(0, 0, 40, 10), "A", 0)]
    spaces, info = plan_spaces.build(parsed, floors, whole, building_id="A")
    assert len(spaces) == 1 and info["face"] == "hull" and info["iou"] > 0.95, info


def test_header_options_reads_the_archicad_translator_settings():
    """ADR-0030 Decision 1: the FILE_DESCRIPTION of the 2026-10-27 export, whitelisted keys only."""
    assert ifc.header_options(list(ARCHICAD_HEADER)) == {
        "elements_to_export": "Visible elements (on all stories)",
        "material_preservation": "Explode all",
        "space_containment": "Off",
        "base_quantities": "Off",
    }
    assert ifc.header_options(["ViewDefinition [CoordinationView]"]) == {}
    assert ifc.header_options([]) == {}


def test_plan_fit_recovers_a_known_rotation_and_translation():
    """ADR-0030 Decision 4: an L-shaped footprint turned 37° and moved is found within 1° and
    0.1 m; the sheet frame enters the IFC frame with y flipped."""
    from shapely.geometry import Polygon

    from unitforma.geometry import plan_fit

    foot = Polygon([(0, 0), (16, 0), (16, 6), (6, 6), (6, 10), (0, 10)]).buffer(0)
    target = plan_fit.placed(foot, 37.0, 12.5, -4.0)
    fit = plan_fit.best_rotation(foot, target)
    assert abs(fit["rotation_deg"] - 37.0) <= 1.0, fit
    assert abs(fit["tx"] - 12.5) <= 0.1 and abs(fit["ty"] + 4.0) <= 0.1, fit
    assert fit["iou"] > 0.98
    assert plan_fit.sheet_to_ifc([[1, 2], [3, -4]]) == [(1.0, -2.0), (3.0, 4.0)]
    moved = plan_fit.apply([(1.0, 0.0)], 90.0, 0.0, 0.0)
    assert abs(moved[0][0]) < 1e-9 and abs(moved[0][1] - 1.0) < 1e-9


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


def _building_with_two_units(kratos: FakeKratos, client: TestClient, who: str) -> dict:
    """A tenant, a project, building A with two floors, a calibrated ground-floor plan and two
    apartment outlines on it (units 1 and 2), as the earlier mapping phases leave them."""
    from unitforma.documents.jobs import process_revision

    s = uuid.uuid4().hex[:6]
    kratos.add(who, f"{who}-{s}@unitforma.example.com", aal="aal2")
    assert client.get("/api/v1/admin/me", headers=cookie(who)).status_code == 200
    eng = create_engine(os.environ["UF_TEST_DATABASE_ADMIN_URL"])
    with eng.begin() as conn:
        conn.execute(
            text("UPDATE users SET is_platform_admin = true WHERE email = :e"),
            {"e": f"{who}-{s}@unitforma.example.com"},
        )
    eng.dispose()
    from unitforma.identity.deps import clear_whoami_cache

    clear_whoami_cache()
    root = cookie(who)
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
    return {
        "base": base,
        "tid": tid,
        "root": root,
        "project": p,
        "building": b,
        "floors": floors,
        "units": units,
    }


@pytestmark_db
def test_ifc_upload_links_spaces_to_units_and_confirmation_writes_areas(
    kratos: FakeKratos, client: TestClient
):
    from unitforma.documents.jobs import process_revision
    from unitforma.geometry.ifc_service import ingest_ifc

    w = _building_with_two_units(kratos, client, "rooti")
    base, tid, root = w["base"], w["tid"], w["root"]
    p, b, units = w["project"], w["building"], w["units"]

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
    assert "application" in result["stats"] and "export_options" in result["stats"]

    # ADR-0030 Decision 2: the same bytes again under another document of the project: noted,
    # and not converted again because the building already shows this very file
    again = client.post(
        f"{base}/projects/{p['id']}/documents",
        headers=root,
        json={"title": "Model again", "building_id": b["id"]},
    ).json()
    intent = client.post(
        f"{base}/documents/{again['id']}/uploads",
        headers=root,
        json={
            "file_name": "a-copy.ifc",
            "content_type": "application/x-step",
            "byte_size": len(data),
            "source_note": None,
        },
    ).json()
    client.put(intent["upload_url"], content=data, headers={"Content-Type": "application/x-step"})
    rev_again = client.post(
        f"{base}/revisions/{intent['revision']['id']}/complete", headers=root
    ).json()
    out = client.portal.call(process_revision, tid, uuid.UUID(rev_again["id"]))
    assert out == {"ifc": True, "status": "done", "duplicate": True}
    revs = client.get(f"{base}/documents/{again['id']}/revisions", headers=root).json()
    assert revs[0]["processing_status"] == "done"
    assert revs[0]["processing_note"] == "Same file as Model rev 1"
    assert (
        client.get(f"{base}/buildings/{b['id']}/model", headers=root).json()["id"]
        == result["model_id"]
    )

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


def _upload_ifc(client: TestClient, base: str, headers: dict, doc_id: str, data: bytes) -> dict:
    intent = client.post(
        f"{base}/documents/{doc_id}/uploads",
        headers=headers,
        json={
            "file_name": "model.ifc",
            "content_type": "application/x-step",
            "byte_size": len(data),
            "source_note": None,
        },
    ).json()
    client.put(intent["upload_url"], content=data, headers={"Content-Type": "application/x-step"})
    return client.post(
        f"{base}/revisions/{intent['revision']['id']}/complete", headers=headers
    ).json()


@pytestmark_db
def test_ifc_without_spaces_takes_the_plan_outlines(kratos: FakeKratos, client: TestClient):
    """ADR-0030 Decisions 3 to 5: a zoneless export gets one space per approved outline, placed by
    the slab fit, suggested with the IoU; confirm-all makes them pickable as their units and copies
    no areas; the published copy keeps only listed units; a building without outlines says why."""
    from unitforma.documents.jobs import process_revision
    from unitforma.geometry.ifc_service import ingest_ifc

    w = _building_with_two_units(kratos, client, "rootp")
    base, tid, root = w["base"], w["tid"], w["root"]
    p, b, units = w["project"], w["building"], w["units"]
    doc = client.post(
        f"{base}/projects/{p['id']}/documents",
        headers=root,
        json={"title": "Zoneless", "building_id": b["id"]},
    ).json()
    rev = _upload_ifc(client, base, root, doc["id"], make_ifc(spaces=False))
    assert client.portal.call(process_revision, tid, uuid.UUID(rev["id"]))["ifc"] is True
    result = client.portal.call(ingest_ifc, tid, uuid.UUID(rev["id"]))
    assert result["status"] == "ready", result
    stats = result["stats"]
    assert stats["spaces"] == 2 and stats["spaces_plan"] == 2, stats
    fit = stats["plan_fit"]
    assert "reason" not in fit and fit["floor_level"] == 0 and fit["face"] == "slabs", fit
    assert fit["iou"] >= 0.3

    links = client.get(f"{base}/buildings/{b['id']}/ifc-links", headers=root).json()
    assert {lk["source"] for lk in links} == {"plan"}
    assert {lk["status"] for lk in links} == {"suggested"}
    assert {lk["unit_id"] for lk in links} == {u["id"] for u in units}
    assert {lk["floor_level"] for lk in links} == {0}
    assert all(float(lk["confidence"]) == round(fit["iou"], 2) for lk in links)
    model = client.get(f"{base}/buildings/{b['id']}/model", headers=root).json()
    gltf, _ = parse_glb(client.get(model["glb_url"]).content)
    plan_nodes = [n for n in gltf["nodes"] if (n.get("extras") or {}).get("source") == "plan"]
    assert len(plan_nodes) == 2
    assert all(n["extras"]["unit_id"].startswith("space:") for n in plan_nodes)
    assert {n["extras"]["code"] for n in plan_nodes} == {u["code"] for u in units}

    # confirm all: one call, one relink, pickable as the units, no ifc_quantity areas
    r = client.post(f"{base}/buildings/{b['id']}/ifc-links/confirm-plan", headers=root)
    assert r.status_code == 200 and r.json() == {"confirmed": 2}, r.text
    links = client.get(f"{base}/buildings/{b['id']}/ifc-links", headers=root).json()
    assert {lk["status"] for lk in links} == {"confirmed"}
    model = client.get(f"{base}/buildings/{b['id']}/model", headers=root).json()
    gltf, _ = parse_glb(client.get(model["glb_url"]).content)
    picked = {
        n["extras"]["unit_id"]
        for n in gltf["nodes"]
        if (n.get("extras") or {}).get("source") == "plan"
    }
    assert picked == {u["id"] for u in units}
    for u in units:
        areas = client.get(f"{base}/units/{u['id']}", headers=root).json()["areas"]
        assert not [a for a in areas if a["source"] == "ifc_quantity"]
    r = client.post(f"{base}/buildings/{b['id']}/ifc-links/confirm-plan", headers=root)
    assert r.json() == {"confirmed": 0}

    # a building with floors but no outlines: the model is built, the reason is written
    other = client.post(
        f"{base}/projects/{p['id']}/buildings", headers=root, json={"code": "B"}
    ).json()
    client.put(
        f"{base}/buildings/{other['id']}/floors",
        headers=root,
        json={"floors": [{"level": 0, "display_name": "Ground", "elevation_m": "0"}]},
    )
    doc_b = client.post(
        f"{base}/projects/{p['id']}/documents",
        headers=root,
        json={"title": "Zoneless B", "building_id": other["id"]},
    ).json()
    rev_b = _upload_ifc(client, base, root, doc_b["id"], make_ifc(spaces=False))
    client.portal.call(process_revision, tid, uuid.UUID(rev_b["id"]))
    result = client.portal.call(ingest_ifc, tid, uuid.UUID(rev_b["id"]))
    assert result["status"] == "ready" and result["stats"]["spaces"] == 0
    assert "no calibrated unit outline" in result["stats"]["plan_fit"]["reason"]
