"""Build small vector PDFs by hand: lines, rectangles and text with level markers.

Avoids a PDF-writing dependency; the files are valid for pypdfium2 and pdfplumber.
"""

from __future__ import annotations


def _obj(n: int, body: str) -> str:
    return f"{n} 0 obj\n{body}\nendobj\n"


def build_pdf(streams: list[str], width: float = 842, height: float = 595) -> bytes:
    """One page per content stream (PDF operators, Helvetica available as /F1)."""
    objs: list[str] = []
    objs.append(_obj(1, "<< /Type /Catalog /Pages 2 0 R >>"))
    first_page_obj = 4
    page_objs = [first_page_obj + 2 * i for i in range(len(streams))]
    kids = " ".join(f"{n} 0 R" for n in page_objs)
    objs.append(_obj(2, f"<< /Type /Pages /Kids [{kids}] /Count {len(streams)} >>"))
    objs.append(_obj(3, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
    pages: list[str] = []
    contents: list[str] = []
    for page_obj, stream in zip(page_objs, streams, strict=True):
        content_obj = page_obj + 1
        pages.append(
            _obj(
                page_obj,
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >>",
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
