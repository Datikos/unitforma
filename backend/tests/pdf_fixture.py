"""Build small vector PDFs by hand: lines, rectangles and text with level markers.

Avoids a PDF-writing dependency; the files are valid for pypdfium2 and pdfplumber.
"""

from __future__ import annotations


def _obj(n: int, body: str) -> str:
    return f"{n} 0 obj\n{body}\nendobj\n"


def build_pdf(streams: list[str], width: float = 842, height: float = 595) -> bytes:
    """One page per content stream (PDF operators).

    Fonts: /F1 Helvetica, /F2 a font named AcadNusx (the legacy Georgian CAD font: Latin
    codes drawn as Georgian; the viewer substitutes a standard font, the name is what counts).
    """
    objs: list[str] = []
    objs.append(_obj(1, "<< /Type /Catalog /Pages 2 0 R >>"))
    first_page_obj = 6
    page_objs = [first_page_obj + 2 * i for i in range(len(streams))]
    kids = " ".join(f"{n} 0 R" for n in page_objs)
    objs.append(_obj(2, f"<< /Type /Pages /Kids [{kids}] /Count {len(streams)} >>"))
    objs.append(_obj(3, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
    objs.append(
        _obj(
            4,
            "<< /Type /Font /Subtype /Type1 /BaseFont /AcadNusx /Encoding /WinAnsiEncoding "
            "/FirstChar 32 /LastChar 126 /Widths [" + " ".join(["556"] * 95) + "] "
            "/FontDescriptor 5 0 R >>",
        )
    )
    objs.append(
        _obj(
            5,
            "<< /Type /FontDescriptor /FontName /AcadNusx /Flags 32 "
            "/FontBBox [0 -200 1000 900] /ItalicAngle 0 /Ascent 900 /Descent -200 "
            "/CapHeight 700 /StemV 80 >>",
        )
    )
    pages: list[str] = []
    contents: list[str] = []
    for page_obj, stream in zip(page_objs, streams, strict=True):
        content_obj = page_obj + 1
        pages.append(
            _obj(
                page_obj,
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_obj} 0 R >>",
            )
        )
        contents.append(
            _obj(content_obj, f"<< /Length {len(stream.encode())} >>\nstream\n{stream}endstream")
        )
    chunks = objs + pages + contents
    body = "%PDF-1.4\n" + "".join(chunks)
    offsets = {}
    pos = len("%PDF-1.4\n")
    for chunk in chunks:
        num = int(chunk.split(" ", 1)[0])
        offsets[num] = pos
        pos += len(chunk.encode())
    max_obj = max(offsets)
    xref = ["xref", f"0 {max_obj + 1}", "0000000000 65535 f "]
    for i in range(1, max_obj + 1):
        xref.append(f"{offsets.get(i, 0):010d} 00000 n ")
    trailer = f"trailer\n<< /Size {max_obj + 1} /Root 1 0 R >>\nstartxref\n{pos}\n%%EOF\n"
    return (body + "\n".join(xref) + "\n" + trailer).encode("latin-1")


def _text(x: float, y: float, s: str, size: int = 10) -> str:
    return f"BT /F1 {size} Tf {x} {y} Td ({s}) Tj ET\n"


def _rect(x0: float, y0: float, x1: float, y1: float) -> str:
    return f"{x0} {y0} {x1 - x0} {y1 - y0} re S\n"


def make_plan_pdf(width: float = 842, height: float = 595) -> bytes:
    """Two pages: ground floor with two apartments and a 600 pt dimension line; first floor."""
    p1 = (
        _text(40, 560, "GROUND FLOOR PLAN +0.00 scale 1:100", 14)
        + _text(120, 300, "bina #1 42.7 m2")
        + _text(420, 300, "bina #2 61.0 m2")
        + "2 w 100 100 m 700 100 l S\n"  # dimension line: 600 pt
        + _rect(100, 200, 400, 400)
        + _rect(400, 200, 700, 400)
        + "100 150 m 700 150 l S\n"
    )
    p2 = (
        _text(40, 560, "FIRST FLOOR PLAN +3.20 scale 1:100", 14)
        + _text(120, 300, "bina #3 42.7 m2")
        + _rect(100, 200, 400, 400)
        + _rect(400, 200, 700, 400)
    )
    return build_pdf([p1, p2], width, height)


# --- revision pair for the diff tests (plan §13.3) ----------------------------------------
def make_plan_pdf_rev_a() -> bytes:
    """Revision A. Page 1: apartments 1 and 2. Page 2: 3, an unlabelled flat, 5 and 6."""
    p1 = (
        _text(40, 560, "GROUND FLOOR PLAN +0.00 scale 1:100", 14)
        + _text(120, 300, "bina #1")
        + _text(420, 300, "bina #2")
        + "2 w 100 100 m 700 100 l S\n"
        + _rect(100, 200, 400, 400)
        + _rect(400, 200, 700, 400)
    )
    p2 = (
        _text(40, 560, "FIRST FLOOR PLAN +3.20 scale 1:100", 14)
        + _text(120, 300, "bina #3")
        + _text(120, 470, "bina #5")
        + _text(320, 470, "bina #6")
        + _rect(100, 200, 400, 400)
        + _rect(400, 200, 700, 400)
        + _rect(100, 420, 300, 520)
        + _rect(300, 420, 500, 520)
    )
    return build_pdf([p1, p2])


def make_plan_pdf_rev_b() -> bytes:
    """Revision B. Page 1: 1 unchanged, 2 split into 2 and 2B, new 9. Page 2: 3 relabelled to
    3A, the unlabelled flat unchanged, 5 and 6 merged into one flat labelled 5."""
    p1 = (
        _text(40, 560, "GROUND FLOOR PLAN +0.00 scale 1:100", 14)
        + _text(120, 300, "bina #1")
        + _text(420, 300, "bina #2")
        + _text(570, 300, "bina #2B")
        + _text(120, 480, "bina #9")
        + "2 w 100 100 m 700 100 l S\n"
        + _rect(100, 200, 400, 400)
        + _rect(400, 200, 550, 400)
        + _rect(550, 200, 700, 400)
        + _rect(100, 430, 300, 530)
    )
    p2 = (
        _text(40, 560, "FIRST FLOOR PLAN +3.20 scale 1:100", 14)
        + _text(120, 300, "bina #3A")
        + _text(120, 470, "bina #5")
        + _rect(100, 200, 400, 400)
        + _rect(400, 200, 700, 400)
        + _rect(100, 420, 500, 520)
    )
    return build_pdf([p1, p2])


def make_site_plan_pdf() -> bytes:
    """A one-page site plan: a plot outline and a 500 pt dimension line (used for placement)."""
    p = (
        _text(40, 560, "SITE PLAN scale 1:500", 14)
        + "2 w 100 80 m 600 80 l S\n"
        + _rect(80, 120, 760, 540)
    )
    return build_pdf([p])


def make_section_pdf() -> bytes:
    """A one-page section: three stacked level markers (ground, first, roof) on floor lines, so
    the sheet is "stacked" for floor suggestions and a candidate for the elevation picker
    (ADR-0014 Decision 1)."""
    p = (
        _text(40, 560, "SECTION A-A scale 1:100", 14)
        + _text(60, 100, "+0.00")
        + _text(60, 300, "+3.00")
        + _text(60, 500, "+6.00")
        + "2 w 150 100 m 700 100 l S\n150 300 m 700 300 l S\n150 500 m 700 500 l S\n"
        + _rect(150, 100, 700, 500)
    )
    return build_pdf([p])


# --- split-level sheets (one sheet, three blocks at three levels) -----------------------------
PT_M_AT_100 = 0.0254 / 72 * 100  # metres per PDF point at 1:100

SPLIT_BLOCKS = [("A", 60.0), ("B", 300.0), ("C", 540.0)]  # block code, left edge (pt)
SPLIT_APT = (110.0, 140.0)  # apartment width × height (pt)
SPLIT_LEVELS = [  # per page: (level marker, absolute) for blocks A, B, C
    [("+0.00", "649.0"), ("+1.00", "650.0"), ("+2.00", "651.0")],
    [("+3.20", "652.2"), ("+4.20", "653.2"), ("+5.20", "654.2")],
]


def split_apartment_area() -> float:
    w, h = SPLIT_APT
    return round(w * PT_M_AT_100 * h * PT_M_AT_100, 1)


def split_apartment_rects(page_index: int) -> list[tuple[str, str, float, float, float, float]]:
    """(block, label number, x0, y0, x1, y1) in PDF points for each apartment on a page."""
    out = []
    n = page_index * 6
    w, h = SPLIT_APT
    for code, left in SPLIT_BLOCKS:
        for dx in (0.0, w + 10):
            n += 1
            out.append((code, str(n), left + dx, 160.0, left + dx + w, 160.0 + h))
    return out


def make_split_level_pdf() -> bytes:
    """Three blocks per sheet at stepped levels, ArchiCAD-style zone fills and stamps.

    Page 1: +0.00 / +1.00 / +2.00; page 2: +3.20 / +4.20 / +5.20; page 3: a section with
    stacked markers. Every page repeats the title block's level range ("-2.55 ... +9.60") at
    the same place and a caption listing its levels; neither is a level marker of the plan.
    """
    area = split_apartment_area()
    pages = []
    for pi, page_levels in enumerate(SPLIT_LEVELS):
        s = _text(40, 560, "TYPICAL PLAN scale 1:100", 12)
        s += _text(60, 30, "plan at " + ", ".join(m for m, _ in page_levels), 9)
        s += _text(600, 30, "levels -2.55 to +9.60", 9)
        for (code, left), (marker, absolute) in zip(SPLIT_BLOCKS, page_levels, strict=True):
            s += _rect(left, 150, left + 240, 310)  # block outline
            s += _text(left + 80, 330, f"{marker} ({absolute})")
            s += _text(left + 100, 360, f"block {code}", 8)
        for _code, num, x0, y0, x1, y1 in split_apartment_rects(pi):
            s += f"0.5 0.75 1 rg {x0} {y0} {x1 - x0} {y1 - y0} re f\n"  # zone fill
            s += _rect(x0, y0, x1, y1)
            mid = (x0 + x1) / 2
            s += f"{mid} {y0} m {mid} {y0 + 60} l S\n"  # a partition: the loop is a room
            s += _text(x0 + 15, y0 + 90, f"bina #{num}")
            s += _text(x0 + 15, y0 + 75, f"{area} m2")
        pages.append(s)
    section = _text(40, 560, "SECTION 1-1 scale 1:100", 12)
    section += _text(60, 30, "section", 9)
    section += _text(600, 30, "levels -2.55 to +9.60", 9)
    for y, m in ((150, "+0.00"), (250, "+3.20"), (350, "+6.40")):
        section += _text(100, y, m)
        section += f"60 {y} m 760 {y} l S\n"
    pages.append(section)
    return build_pdf(pages)


# --- a drawing bundle: legacy-font labels, parking, a reprint, a text page, a basement ------
def _geo(x: float, y: float, s: str, size: int = 10) -> str:
    """Text in the legacy Georgian CAD font (/F2): "bina #3" reads as "ბინა №3" on paper."""
    return f"BT /F2 {size} Tf {x} {y} Td ({s}) Tj ET\n"


BUNDLE_APT = (120.0, 120.0)  # apartment fill (pt) → printed area at 1:100
BUNDLE_STALL = (2.5 / PT_M_AT_100, 5.0 / PT_M_AT_100)  # a 2.5 × 5 m parking stall
BUNDLE_STORE = (2.0 / PT_M_AT_100, 3.0 / PT_M_AT_100)  # a 2 × 3 m store room


def bundle_area(size: tuple[float, float]) -> float:
    return round(size[0] * PT_M_AT_100 * size[1] * PT_M_AT_100, 1)


def _ground_plan(dx: float = 0.0, dy: float = 0.0, title: str = "TYPICAL PLAN") -> str:
    s = _text(40, 560, f"{title} scale 1:100", 12)
    s += _text(60 + dx, 470 + dy, "+0.00 (649.0)")
    w, h = BUNDLE_APT
    area = bundle_area(BUNDLE_APT)
    for i in range(3):
        x0, y0 = 60 + dx + i * (w + 10), 300 + dy
        s += f"0.5 0.75 1 rg {x0} {y0} {w} {h} re f\n" + _rect(x0, y0, x0 + w, y0 + h)
        s += _geo(x0 + 20, y0 + 70, f"bina #{i + 1}")
        s += _text(x0 + 20, y0 + 55, f"{area} m2")
    sw, sh = BUNDLE_STALL
    for i in range(3):
        x0, y0 = 520 + dx + i * (sw + 4), 300 + dy
        s += f"0.886 0.875 0.867 rg {x0} {y0} {sw} {sh} re f\n" + _rect(x0, y0, x0 + sw, y0 + sh)
        s += _text(x0 + 8, y0 + 100, f"A1-{i + 1}", 8)
        s += _text(x0 + 30, y0 + 70, "P", 12)
        s += _text(x0 + 8, y0 + 40, f"{bundle_area(BUNDLE_STALL)} m2", 8)
    # the legend: item 5 ends with "apartment", item 6 starts the next line
    s += _geo(60, 120, "5. sacxovrebeli bina")
    s += _geo(60, 105, "6. aivani")
    return s


def make_bundle_pdf() -> bytes:
    """Page 1 ground plan, 2 its fire-safety reprint, 3 a text page, 4 the basement."""
    p1 = _ground_plan()
    p2 = _ground_plan(15, -10, "FIRE SAFETY PLAN") + _geo(400, 560, "xanZarsawinaaRmdego")
    p3 = "".join(_geo(60, 520 - 14 * i, "SeniSvnebi: sarTuli 1 da sarTuli 2") for i in range(30))
    p4 = _text(40, 560, "BASEMENT PLAN scale 1:100", 12) + _text(60, 470, "-2.55 (646.45)")
    w, h = BUNDLE_STORE
    for i in range(3):
        x0, y0 = 60 + i * (w + 6), 300
        s = f"0.5 0.5 0.5 rg {x0} {y0} {w} {h} re f\n" + _rect(x0, y0, x0 + w, y0 + h)
        s += _geo(x0 + 10, y0 + 50, f"#{i + 1}")
        s += _text(x0 + 10, y0 + 35, f"{bundle_area(BUNDLE_STORE)} m2", 8)
        p4 += s
    return build_pdf([p1, p2, p3, p4])
