import json

from tests.pdf_fixture import make_plan_pdf
from unitforma.documents import processing
from unitforma.inventory import geometry
from unitforma.inventory.codes import normalise_code, render_code


def test_inspect_pdf_pages_and_mime():
    data = make_plan_pdf()
    info = processing.inspect(data, "application/octet-stream")
    assert info.mime == "application/pdf"
    assert info.page_count == 2
    assert round(info.pages[0].width_pt) == 842 and round(info.pages[0].height_pt) == 595
    assert len(info.sha256) == 64


def test_rasterize_and_extract():
    data = make_plan_pdf()
    png, thumb, w, h = processing.rasterize_page(
        data, "application/pdf", 1, long_edge=800, thumb_edge=100
    )
    assert png[:4] == b"\x89PNG" and thumb[:4] == b"\x89PNG"
    assert w == 800 and 560 <= h <= 570
    ex = processing.extract_page(data, "application/pdf", 1)
    assert "GROUND FLOOR" in ex["text"]
    assert ex["vectors"]["lines"] >= 2 and ex["vectors"]["rects"] >= 2
    assert ex["hints"]["levels"] == ["+0.00"]
    assert ex["hints"]["scales"] == [100]
    assert ex["hints"]["apartment_labels"] == ["1", "2"]
    assert ex["hints"]["area_values"] == [42.7, 61.0]
    assert ex["hints"]["kind"] in ("floor_plan", "drawing", "unknown")
    json.dumps(ex)  # serialisable for storage
    assert processing.suggest_floor_level(ex["hints"]) == 0
    ex2 = processing.extract_page(data, "application/pdf", 2)
    assert processing.suggest_floor_level(ex2["hints"]) is None  # +3.20 alone is not a floor number


def test_sniff_mime_variants():
    assert processing.sniff_mime(b"\x89PNG\r\n", None) == "image/png"
    assert processing.sniff_mime(b"\xff\xd8\xff\xe0", None) == "image/jpeg"
    assert processing.sniff_mime(b"ISO-10303-21;", None) == "application/x-step"
    assert processing.sniff_mime(b"????", "text/plain") == "text/plain"


def test_codes():
    assert render_code("{building}-{floor:02}-{seq:02}", building="A", floor=2, seq=3) == "A-02-03"
    assert render_code("{building}-{floor:02}-{seq:02}", building="A", floor=-1, seq=7) == "A-B1-07"
    assert render_code("P-{seq:03}", building="SITE", floor=0, seq=12) == "P-012"
    assert normalise_code(" a-02-03 ") == "A-02-03"


def test_calibration_and_area():
    ring = [[0.1, 0.1], [0.5, 0.1], [0.5, 0.4], [0.1, 0.4]]
    geometry.validate_ring(ring)
    # raster 1000x500 px; two points 400 px apart = 10 m → 0.025 m/px
    cal = geometry.calibration_from_points([0.1, 0.5], [0.5, 0.5], 10.0, 1000, 500)
    assert abs(cal["m_per_px"] - 0.025) < 1e-9
    ring_m = geometry.ring_to_metres(ring, cal)
    # 400 px × 150 px → 10 m × 3.75 m = 37.5 m²
    assert geometry.area_m2(ring_m) == 37.5
    assert geometry.overlap_ratio(ring, [[0.1, 0.1], [0.3, 0.1], [0.3, 0.4], [0.1, 0.4]]) == 1.0
