"""Build a small vector PDF (two pages) by hand: lines, rectangles and text with level markers.

Avoids a PDF-writing dependency; the file is valid for pypdfium2 and pdfplumber.
"""

from __future__ import annotations


def _obj(n: int, body: str) -> str:
    return f"{n} 0 obj\n{body}\nendobj\n"


def make_plan_pdf(width: float = 842, height: float = 595) -> bytes:
    pages = []
    contents = []
    # page 1: ground floor, two rooms (rectangles) and a dimension line of known length
    p1 = (
        "BT /F1 14 Tf 40 560 Td (GROUND FLOOR PLAN +0.00 scale 1:100) Tj ET\n"
        "BT /F1 10 Tf 120 300 Td (bina #1 42.7 m2) Tj ET\n"
        "BT /F1 10 Tf 420 300 Td (bina #2 61.0 m2) Tj ET\n"
        "2 w 100 100 m 700 100 l S\n"  # dimension line: 600 pt
        "100 200 300 200 re S\n"
        "400 200 300 200 re S\n"
        "100 150 m 700 150 l S\n"
    )
    # page 2: first floor
    p2 = (
        "BT /F1 14 Tf 40 560 Td (FIRST FLOOR PLAN +3.20 scale 1:100) Tj ET\n"
        "BT /F1 10 Tf 120 300 Td (bina #3 42.7 m2) Tj ET\n"
        "100 200 300 200 re S\n400 200 300 200 re S\n"
    )
    objs: list[str] = []
    objs.append(_obj(1, "<< /Type /Catalog /Pages 2 0 R >>"))
    objs.append(_obj(2, "<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>"))
    objs.append(_obj(7, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
    for page_obj, content_obj, stream in ((3, 4, p1), (5, 6, p2)):
        pages.append(
            _obj(
                page_obj,
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
                f"/Resources << /Font << /F1 7 0 R >> >> /Contents {content_obj} 0 R >>",
            )
        )
        contents.append(
            _obj(content_obj, f"<< /Length {len(stream.encode())} >>\nstream\n{stream}endstream")
        )
    body = "%PDF-1.4\n" + "".join(objs + pages + contents)
    # xref table
    offsets = {}
    pos = len("%PDF-1.4\n")
    for chunk in objs + pages + contents:
        num = int(chunk.split(" ", 1)[0])
        offsets[num] = pos
        pos += len(chunk.encode())
    max_obj = max(offsets)
    xref = ["xref", f"0 {max_obj + 1}", "0000000000 65535 f "]
    for i in range(1, max_obj + 1):
        xref.append(f"{offsets.get(i, 0):010d} 00000 n ")
    trailer = f"trailer\n<< /Size {max_obj + 1} /Root 1 0 R >>\nstartxref\n{pos}\n%%EOF\n"
    return (body + "\n".join(xref) + "\n" + trailer).encode("latin-1")
