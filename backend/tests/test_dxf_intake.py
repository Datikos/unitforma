"""ADR-0006 Phase B: a DXF goes through the same pipeline as a PDF — sheets per layout, the
extract shape ``mapping/suggest.py`` reads, fills from zones and hatches, labels from TEXT with
the legacy Georgian font decoded, a calibration from ``$INSUNITS`` and a raster."""

from __future__ import annotations

import io
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.fake_kratos import FakeKratos, cookie
from unitforma.documents import cad_dxf, processing
from unitforma.mapping import suggest


def make_plan_dxf(*, insunits: int = 6, legacy: bool = True) -> bytes:
    """A 20 m × 12 m floor: two apartments as closed polylines on a zone layer, one as a
    hatch, a labelled stair hall, a level marker, and the walls as lines."""
    import ezdxf

    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = insunits
    doc.styles.new("ACADNUSX", dxfattribs={"font": "acadnusx.ttf"})
    msp = doc.modelspace()
    # outer walls
    for a, b in (((0, 0), (20, 0)), ((20, 0), (20, 12)), ((20, 12), (0, 12)), ((0, 12), (0, 0))):
        msp.add_line(a, b, dxfattribs={"layer": "WALLS"})
    # apartment 1: 8 m × 6 m = 48.0 m², apartment 2: 8 m × 6 m, hall 4 m × 12 m
    msp.add_lwpolyline([(0, 0), (8, 0), (8, 6), (0, 6)], close=True, dxfattribs={"layer": "ZONES"})
    msp.add_lwpolyline(
        [(0, 6), (8, 6), (8, 12), (0, 12)], close=True, dxfattribs={"layer": "ZONES"}
    )
    h = msp.add_hatch(color=4, dxfattribs={"layer": "ZONES"})
    h.paths.add_polyline_path([(12, 0), (20, 0), (20, 12), (12, 12)], is_closed=True)
    msp.add_lwpolyline(
        [(8, 0), (12, 0), (12, 12), (8, 12)], close=True, dxfattribs={"layer": "ZONES"}
    )
    style = "ACADNUSX" if legacy else "Standard"
    label = "bina #1 48.0 m2" if legacy else "ბინა №1 48.0 m²"
    msp.add_text(label, dxfattribs={"insert": (2, 2.5), "height": 0.4, "style": style})
    msp.add_text("ბინა №2 48.0 m²", dxfattribs={"insert": (2, 8.5), "height": 0.4})
    msp.add_text("ბინა №3 96.0 m²", dxfattribs={"insert": (14, 6), "height": 0.4})
    msp.add_mtext("+3.20", dxfattribs={"insert": (9, 6), "char_height": 0.3})
    msp.add_mtext("m.1:100", dxfattribs={"insert": (0.5, -0.5), "char_height": 0.3})
    # a block with a door symbol, referenced once
    blk = doc.blocks.new("DOOR")
    blk.add_arc((0, 0), 0.9, 0, 90)
    msp.add_blockref("DOOR", (8, 2))
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def test_sniff_and_inspect_dxf():
    data = make_plan_dxf()
    assert cad_dxf.is_dxf(data)
    assert processing.sniff_mime(data, "application/octet-stream") == "application/dxf"
    info = processing.inspect(data, "application/octet-stream")
    assert info.mime == "application/dxf"
    assert info.page_count == 1  # the empty paper layout is not a sheet
    # 20 m plus 2 % margin on each side, in points at 1:1
    assert round(info.pages[0].width_pt / cad_dxf.POINTS_PER_METRE, 2) == 20.8
    assert not cad_dxf.is_dxf(b"%PDF-1.4 ...")
    with pytest.raises(cad_dxf.DxfError):
        cad_dxf.DxfDrawing(b"AutoCAD Binary DXF\r\n\x1a\x00")


def test_extract_has_the_pdf_shape_and_decodes_legacy_text():
    cad = cad_dxf.DxfDrawing(make_plan_dxf())
    ex = cad.extract(1)
    assert set(ex) >= {"text", "words", "vectors", "segments", "rects", "fills", "page_pt", "hints"}
    assert ex["vectors"]["lines"] >= 20 and ex["vectors"]["curves"] == 1  # the door arc
    assert len(ex["fills"]) == 4 and all(len(f["ring"]) >= 4 for f in ex["fills"])
    assert sum(1 for f in ex["fills"] if f.get("rgb")) == 1  # the hatch carries its colour
    assert all(0 <= v <= 1 for s in ex["segments"] for v in s)
    words = [w["t"] for w in ex["words"]]
    assert "ბინა" in words and "№1" in words  # legacy font decoded by style
    assert "+3.20" in words
    hints = ex["hints"]
    assert hints["cad"] == "dxf" and hints["units"] == "m" and hints["layout"] == "Model"
    assert hints["layers"]["ZONES"] == 4 and hints["layers"]["WALLS"] == 4
    assert hints["levels"] == ["+3.20"] and hints["scales"] == [100]
    assert hints["apartment_labels"] == ["1", "2", "3"]
    assert hints["legacy_font_chars"] > 0
    import json

    json.dumps(ex)


def test_fills_become_unit_candidates_with_printed_areas():
    cad = cad_dxf.DxfDrawing(make_plan_dxf())
    ex = cad.extract(1)
    info = cad.layout(1)
    page_m = (
        (info.extent[2] - info.extent[0]) * cad.m_per_unit,
        (info.extent[3] - info.extent[1]) * cad.m_per_unit,
    )
    cands = suggest.closed_loops(ex, page_m=page_m)
    fills = {c.label: c for c in cands if c.method == "fill"}
    assert set(fills) >= {"ბინა №1", "ბინა №2", "ბინა №3"}
    for key, printed in (("ბინა №1", 48.0), ("ბინა №2", 48.0), ("ბინა №3", 96.0)):
        c = fills[key]
        assert c.confidence == 0.95, (key, c.confidence, c.measured_area_m2)
        assert c.printed_area_m2 == printed
        assert abs(c.measured_area_m2 - printed) <= printed * 0.02
        assert c.unit_type == "apartment"


def test_raster_and_calibration_from_units():
    cad = cad_dxf.DxfDrawing(make_plan_dxf())
    png, thumb, w, h = cad.rasterize(1, long_edge=1000, thumb_edge=100)
    assert png[:4] == b"\x89PNG" and thumb[:4] == b"\x89PNG"
    assert w == 1000 and 580 <= h <= 700  # 20.8 m wide; the scale note below the plan adds height
    cal = cad.calibration(1, w, h)
    assert cal["source"] == "dxf_insunits" and cal["unit"] == "m"
    assert round(cal["m_per_px"] * w, 2) == 20.8
    # millimetres scale the same drawing down a thousandfold; unitless gives no calibration
    mm = cad_dxf.DxfDrawing(make_plan_dxf(insunits=4))
    assert round(mm.calibration(1, 1000, 600)["distance_m"], 4) == 0.0208
    assert cad_dxf.DxfDrawing(make_plan_dxf(insunits=0)).calibration(1, 1000, 600) is None


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
def test_dxf_upload_arrives_calibrated_with_suggestions(kratos: FakeKratos, client: TestClient):
    from unitforma.documents.jobs import process_revision

    s = uuid.uuid4().hex[:6]
    kratos.add("rootd", f"rootd-{s}@unitforma.example.com", aal="aal2")
    assert client.get("/api/v1/admin/me", headers=cookie("rootd")).status_code == 200
    eng = create_engine(os.environ["UF_TEST_DATABASE_ADMIN_URL"])
    with eng.begin() as conn:
        conn.execute(
            text("UPDATE users SET is_platform_admin = true WHERE email = :e"),
            {"e": f"rootd-{s}@unitforma.example.com"},
        )
    eng.dispose()
    from unitforma.identity.deps import clear_whoami_cache

    clear_whoami_cache()
    root = cookie("rootd")
    t = client.post(
        "/api/v1/platform/tenants", headers=root, json={"slug": f"dxf{s}", "name": "DXF Co"}
    ).json()
    base = f"/api/v1/admin/tenants/{t['id']}"
    p = client.post(f"{base}/projects", headers=root, json={"slug": "dxf", "name": "DXF"}).json()
    b = client.post(f"{base}/projects/{p['id']}/buildings", headers=root, json={"code": "A"}).json()
    floors = client.put(
        f"{base}/buildings/{b['id']}/floors",
        headers=root,
        json={"floors": [{"level": 1, "display_name": "1", "elevation_m": "3.20"}]},
    )
    doc = client.post(
        f"{base}/projects/{p['id']}/documents",
        headers=root,
        json={"kind": "floor_plan", "title": "Plans A", "building_id": b["id"]},
    ).json()
    data = make_plan_dxf()
    intent = client.post(
        f"{base}/documents/{doc['id']}/uploads",
        headers=root,
        json={
            "file_name": "plans.dxf",
            "content_type": "application/dxf",
            "byte_size": len(data),
            "source_note": None,
        },
    )
    assert intent.status_code == 201, intent.text
    up = client.put(
        intent.json()["upload_url"], content=data, headers={"Content-Type": "application/dxf"}
    )
    assert up.status_code in (200, 201, 204), up.text
    rev = client.post(
        f"{base}/revisions/{intent.json()['revision']['id']}/complete", headers=root
    ).json()
    result = client.portal.call(process_revision, uuid.UUID(t["id"]), uuid.UUID(rev["id"]))
    assert result["pages"] == 1 and result["page_count"] == 1, result
    sheets = client.get(f"{base}/revisions/{rev['id']}/sheets", headers=root).json()
    assert len(sheets) == 1
    sh = sheets[0]
    assert sh["calibration_status"] == "calibrated"
    assert sh["calibration"]["source"] == "dxf_insunits"
    assert sh["hints"]["units"] == "m" and sh["hints"]["cad"] == "dxf"
    # the +3.20 marker matched the floor at 3.20 m
    assert [f["floor_id"] for f in sh["floors"]] == [floors.json()[0]["id"]]
    sugg = client.post(f"{base}/sheets/{sh['id']}/suggestions", headers=root)
    assert sugg.status_code == 200, sugg.text
    fills = {c["label"]: c for c in sugg.json() if c["method"] == "fill"}
    assert set(fills) >= {"ბინა №1", "ბინა №2", "ბინა №3"}
    assert all(fills[k]["confidence"] == 0.95 for k in ("ბინა №1", "ბინა №2", "ბინა №3"))
