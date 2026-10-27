"""Drawing sets without a printed scale, lettered small (ADR-0031), from the N4 set of
2026-10-27 ("NTS" title blocks, "ბინა / 221 / 43.9 მ2" in three 3.3 pt rows, a yellow hatch
over every apartment, red dimension chains in centimetres):

1. text is read in the order the file draws it, so stacked label rows stay separate rows;
2. coloured and light strokes are marked as annotation and do not cut rooms into pieces;
3. the page width comes from the drawing's own dimensions when no scale is printed;
4. two labels in one face and a symbol inside a labelled zone are not units of their own.
"""

from __future__ import annotations

import uuid

from shapely.geometry import box

from tests.pdf_fixture import NTS_APTS, NTS_CM_PER_PT, build_pdf, make_nts_stacked_pdf
from unitforma.autopilot.passes import calibration
from unitforma.documents import processing
from unitforma.mapping import suggest
from unitforma.tenants.models import Sheet

PAGE_WIDTH_M = 842 * NTS_CM_PER_PT / 100


def _extract() -> dict:
    return processing.extract_page(make_nts_stacked_pdf(), "application/pdf", 1)


def test_stacked_label_rows_stay_rows_and_name_the_units():
    ex = _extract()
    words = [w["t"] for w in ex["words"]]
    assert words[:8] == ["ბინა", "101", "16.0", "მ2", "ბინა", "102", "16.0", "მ2"]
    assert ex["hints"]["unit_labels"] == {"apartment": [code for code, _, _ in NTS_APTS]}


def test_the_page_width_comes_from_the_dimensions():
    dim = _extract()["hints"]["dimension_scale"]
    assert dim["unit"] == "cm" and dim["agree"] == dim["pairs"] == 7
    assert abs(dim["page_width_m"] - PAGE_WIDTH_M) < 0.01


def test_annotation_is_marked_and_the_apartments_grow_to_their_printed_areas():
    ex = _extract()
    marked = [s for s in ex["segments"] if len(s) > 4]
    # 8 hatch lines, the grid axis and 7 dimension lines; the 2 partitions are line work
    assert len(marked) == 16 and all(s[4] == 1 for s in marked)
    assert len(ex["segments"]) - len(marked) == 2
    page_m = suggest.dimension_metres(ex, ex["hints"]["dimension_scale"])
    units = [c for c in suggest.closed_loops(ex, page_m=page_m) if c.unit_type == "apartment"]
    assert sorted(c.label for c in units) == ["ბინა 101", "ბინა 102"]
    for c in units:
        assert c.method == "grown" and c.printed_area_m2 == 16.0
        assert abs(c.measured_area_m2 - 16.0) < 0.2


def test_an_extract_written_before_the_annotation_mark_still_reads():
    """Extracts stored before ADR-0031 hold four numbers per segment: all of them line work."""
    ex = {
        "words": [
            {"t": "ბინა", "x0": 0.2, "y0": 0.3, "x1": 0.22, "y1": 0.31},
            {"t": "№1", "x0": 0.23, "y0": 0.3, "x1": 0.25, "y1": 0.31},
        ],
        "segments": [list(b) for b in ([0.1, 0.1, 0.5, 0.1], [0.5, 0.1, 0.5, 0.5])]
        + [[0.5, 0.5, 0.1, 0.5], [0.1, 0.5, 0.1, 0.1]],
    }
    found = suggest.closed_loops(ex)
    assert [(c.label, c.confidence) for c in found] == [("ბინა №1", 0.9)]


def test_dimensions_need_agreement_and_tell_millimetres_from_centimetres():
    def page(values: list[str], span: float = 100.0) -> tuple[list[dict], list[dict]]:
        words, lines = [], []
        for i, v in enumerate(values):
            x0 = 20 + i * (span + 10)
            words.append({"text": v, "x0": x0 + 40, "x1": x0 + 52, "top": 90, "bottom": 96})
            lines.append({"x0": x0, "x1": x0 + span, "top": 97, "bottom": 97})
        return words, lines

    assert processing.dimension_page_width(*page(["620"] * 4), 842) is None  # 4 < 5 pairs
    cm = processing.dimension_page_width(*page(["620"] * 5), 842)
    assert cm == {"page_width_m": 52.204, "unit": "cm", "agree": 5, "pairs": 5}
    mm = processing.dimension_page_width(*page(["6200"] * 5), 842)
    assert mm is not None and mm["unit"] == "mm" and mm["page_width_m"] == 52.204
    # five dimensions against five unrelated numbers that each disagree: still the dimensions
    words, lines = page(["620"] * 5 + ["12", "45", "230", "77", "5"])
    assert processing.dimension_page_width(words, lines, 842)["agree"] == 5


def test_two_labels_in_one_face_are_not_one_unit():
    """No drawn wall between two apartments: one face holds both labels (N4's x23 and x24)."""
    ex = {
        "words": [
            {"t": t, "x0": x, "y0": y, "x1": x + 0.02, "y1": y + 0.01}
            for t, x, y in (("ბინა", 0.2, 0.2), ("№1", 0.23, 0.2), ("ბინა", 0.2, 0.4))
        ]
        + [{"t": "№2", "x0": 0.23, "y0": 0.4, "x1": 0.25, "y1": 0.41}],
        "rects": [[0.1, 0.1, 0.5, 0.5]],
    }
    found = suggest.closed_loops(ex)
    assert [(c.label, c.confidence) for c in found] == [("ბინა №1", 0.5)]


def test_a_symbol_drawn_inside_a_labelled_zone_is_not_a_second_unit():
    """A parking stall fill with the car drawn over it as a smaller fill (N4's basement)."""
    stall, car = box(0.1, 0.1, 0.2, 0.3), box(0.12, 0.12, 0.18, 0.28)
    ex = {
        "words": [
            {"t": t, "x0": 0.14, "y0": y, "x1": 0.16, "y1": y + 0.005}
            for t, y in (("P", 0.18), ("01", 0.19), ("13.3", 0.2), ("m2", 0.2))
        ],
        "fills": [
            {"ring": [list(p) for p in poly.exterior.coords[:-1]], "rgb": [0.5, 0.5, 0.5]}
            for poly in (stall, car)
        ],
    }
    found = [c for c in suggest.closed_loops(ex) if c.method == "fill"]
    assert [(c.label, c.unit_type) for c in found] == [("P 01", "parking")]
    assert abs(found[0].area_norm - stall.area) < 1e-6


def test_calibration_takes_a_printed_scale_only_when_the_dimensions_agree():
    """N4 page 11 (A3, 1190.55 pt wide) prints a ramp's "1:12", which reads as the only scale."""
    dims = {"page_width_m": 108.187, "unit": "cm", "agree": 27}
    sheet = Sheet(
        id=uuid.uuid4(),
        width_pt=1190.55,
        height_pt=841.89,
        raster_width=4000,
        raster_height=2829,
        hints={"scales": [], "dimension_scale": dims},
    )
    cal = calibration.from_dimensions(sheet)
    assert calibration.from_printed_scale(sheet) is None
    assert cal["source"] == "dimensions" and cal["dimensions_agreeing"] == 27
    assert abs(cal["m_per_px"] * 4000 - 108.187) < 1e-9
    sheet.hints = {"scales": [12], "dimension_scale": dims}  # 5.04 m against 108.19 m
    assert calibration.from_printed_scale(sheet) is None
    assert calibration.from_dimensions(sheet)["printed_scale_ignored"] == 12
    sheet.hints = {"scales": [257], "dimension_scale": dims}  # 107.94 m: within 5 %
    assert calibration.from_dimensions(sheet) is None
    assert calibration.from_printed_scale(sheet)["scale"] == 257
    sheet.hints = {"scales": [100]}  # no dimensions: the printed scale as before
    assert calibration.from_printed_scale(sheet)["scale"] == 100


def test_the_fixture_without_dimensions_has_no_dimension_scale():
    assert (
        "dimension_scale"
        not in processing.extract_page(
            build_pdf(["100 100 m 700 100 l S\n"]), "application/pdf", 1
        )["hints"]
    )


def test_a_labelled_room_measured_at_zero_is_still_a_room_of_the_unit():
    """A wrong scale (N4 page 11 read a ramp's "1:12") rounds every face to 0.0 m²: that is a
    measurement far below the printed area, not a missing one, so the face stays at 0.5."""
    ex = {
        "words": [
            {"t": t, "x0": x, "y0": 0.3, "x1": x + 0.02, "y1": 0.31}
            for t, x in (("ბინა", 0.2), ("№1", 0.23), ("43.9", 0.26), ("m2", 0.29))
        ],
        "rects": [[0.1, 0.1, 0.5, 0.5]],
    }
    (found,) = suggest.closed_loops(ex, page_m=(0.1, 0.07))
    assert found.measured_area_m2 == 0.0 and found.confidence == 0.5
