"""ADR-0006 #E2: the DXF preview raster draws Georgian labels in a font that has the glyphs,
and the symbols printed next to them (№, ², ±, −, ×) in one that has those."""

from __future__ import annotations

import io

from unitforma.documents import cad_dxf, preview_text

MISSING = ""  # private use: in neither font, so it draws the font's empty box


def _mask(georgian: bool, ch: str) -> bytes:
    return bytes(preview_text.font(georgian, 40).getmask(ch))


def test_a_label_is_cut_into_georgian_and_other_runs():
    runs = preview_text.script_runs("ბინა №12 48.5 მ²")
    assert runs == [(True, "ბინა"), (False, " №12 48.5 "), (True, "მ"), (False, "²")]
    assert "".join(r for _, r in runs) == "ბინა №12 48.5 მ²"
    assert preview_text.script_runs("") == []
    assert preview_text.script_runs("ᲑᲘᲜᲐ") == [(True, "ᲑᲘᲜᲐ")]  # Mtavruli capitals


def test_every_character_of_a_plan_label_has_a_glyph_in_its_font():
    for ch in "აბგდევზთიკლმნოპჟრსტუფქღყშჩცძწჭხჯჰᲑᲘᲜᲐ":
        assert preview_text.is_georgian(ch)
        assert _mask(True, ch) != _mask(True, MISSING), ch
    for ch in "0123456789ABCabcm.,-+:/()%№²±−×°":
        assert not preview_text.is_georgian(ch)
        assert _mask(False, ch) != _mask(False, MISSING), ch


def _sheet_with_label(label: str) -> bytes:
    import ezdxf

    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (10, 0), (10, 5), (0, 5)], close=True)
    msp.add_text(label, dxfattribs={"insert": (1, 2), "height": 0.6})
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def test_the_dxf_preview_draws_georgian_letters_not_empty_boxes():
    # Before #E2 both labels came out as the same row of boxes (Pillow's default font).
    word = "ბინა"
    georgian, _, w, h = cad_dxf.DxfDrawing(_sheet_with_label(word)).rasterize(1, long_edge=1200)
    boxes, _, w2, h2 = cad_dxf.DxfDrawing(_sheet_with_label(MISSING * len(word))).rasterize(
        1, long_edge=1200
    )
    assert (w, h) == (w2, h2)
    assert georgian != boxes
    # the label itself is drawn: dark pixels where the word sits
    from PIL import Image

    im = Image.open(io.BytesIO(georgian)).convert("L")
    ex = cad_dxf.DxfDrawing(_sheet_with_label(word)).extract(1)
    wd = next(x for x in ex["words"] if x["t"] == word)
    box = (
        int(wd["x0"] * w),
        int(wd["y0"] * h),
        int(wd["x1"] * w) + 1,
        int(wd["y1"] * h) + 1,
    )
    assert im.crop(box).getextrema()[0] < 80
