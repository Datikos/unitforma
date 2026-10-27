"""Document processing used by the worker (plan §12.3, §13.2).

Pure functions over bytes so they are testable without storage or a database:
* ``inspect`` — sha256, mime sniffing, page count and page sizes
* ``rasterize_page`` — PNG at a target long edge plus a thumbnail (pypdfium2 / Pillow)
* ``extract_page`` — text with positions, vector segment statistics, hints (levels, scale,
  apartment labels) for floor suggestions (pdfplumber)

DXF files take the same route through ``documents.cad_dxf`` (ADR-0006): one sheet per layout,
the same extract shape, a raster drawn from the vectors.
"""

from __future__ import annotations

import bisect
import hashlib
import io
import re
from dataclasses import dataclass, field
from typing import Any

from unitforma.documents import labels

LEVEL_RE = re.compile(r"(?<![\d.])([+-]\d{1,2}\.\d{2})(?![\d.])")
SCALE_RE = re.compile(r"(?:\b|[mმ]\.?\s*)1\s*[:/]\s*(\d{2,4})\b")
# "61.3 m²", "61.3 მ²" (Georgian), "61,3 კვ.მ", "61.3 sq m"
AREA_RE = re.compile(r"(\d{1,4}[.,]\d{1,2})\s*(?:m\s*[²2]|მ\s*[²2]|კვ\.?\s*მ|sq\.?\s*m)", re.I)
FLOOR_WORD_RE = re.compile(
    r"\b(?:level|floor|storey|etage|этаж|სართული|sarTuli)\b\s*([+-]?\d{1,2})?", re.I
)
# a dimension in centimetres or millimetres: "620", "6,475", "6 475" (not "43.9", not "+3.20")
DIMENSION_RE = re.compile(r"^(?:\d{2,5}|\d{1,3}[, ]\d{3})$")
DIMENSION_AGREE = 0.005  # ±0.5 % around the agreeing ratio
DIMENSION_MIN_AGREE = 5
DIMENSION_MIN_SHARE = 0.3
DIMENSION_PAGE_WIDTH_M = (5.0, 2000.0)
# stroke colours that count as line work for room faces (ADR-0031 Decision 2)
LINE_WORK_MAX_CHROMA = 0.25
LINE_WORK_MAX_LIGHTNESS = 0.6
MAX_SEGMENTS = 20_000


@dataclass
class PageInfo:
    page_no: int
    width_pt: float
    height_pt: float


@dataclass
class FileInspection:
    sha256: str
    mime: str
    page_count: int
    pages: list[PageInfo] = field(default_factory=list)


def sniff_mime(data: bytes, declared: str | None) -> str:
    head = data[:16]
    if head.startswith(b"%PDF"):
        return "application/pdf"
    if head.startswith(b"\x89PNG"):
        return "image/png"
    if head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if head[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if head[:4] == b"glTF":
        return "model/gltf-binary"
    if data[:20].upper().startswith(b"ISO-10303-21"):
        return "application/x-step"
    from unitforma.documents import cad_dxf

    if cad_dxf.is_dxf(data):
        return cad_dxf.MIME
    return declared or "application/octet-stream"


def inspect(data: bytes, declared_mime: str | None = None) -> FileInspection:
    mime = sniff_mime(data, declared_mime)
    sha = hashlib.sha256(data).hexdigest()
    pages: list[PageInfo] = []
    if mime == "application/pdf":
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        for i in range(len(pdf)):
            w, h = pdf[i].get_size()
            pages.append(PageInfo(i + 1, float(w), float(h)))
    elif mime.startswith("image/"):
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            pages.append(PageInfo(1, float(im.width), float(im.height)))
    elif mime == "application/dxf":
        from unitforma.documents import cad_dxf

        for lay in cad_dxf.DxfDrawing(data).layouts:
            pages.append(PageInfo(lay.page_no, lay.width_pt, lay.height_pt))
    return FileInspection(sha256=sha, mime=mime, page_count=len(pages), pages=pages)


def rasterize_page(
    data: bytes, mime: str, page_no: int, long_edge: int = 4000, thumb_edge: int = 320
) -> tuple[bytes, bytes, int, int]:
    """Return (png, thumbnail_png, width, height) for a page/image."""
    from PIL import Image

    if mime == "application/pdf":
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        page = pdf[page_no - 1]
        w, h = page.get_size()
        scale = long_edge / max(w, h)
        im = page.render(scale=scale).to_pil().convert("RGB")
    else:
        im = Image.open(io.BytesIO(data)).convert("RGB")
        if max(im.size) > long_edge:
            im.thumbnail((long_edge, long_edge))
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    thumb = im.copy()
    thumb.thumbnail((thumb_edge, thumb_edge))
    tbuf = io.BytesIO()
    thumb.save(tbuf, format="PNG", optimize=True)
    return buf.getvalue(), tbuf.getvalue(), im.width, im.height


def extract_page(data: bytes, mime: str, page_no: int) -> dict[str, Any]:
    """Text, vector statistics and hints for one PDF page (empty for images)."""
    if mime != "application/pdf":
        return {
            "text": "",
            "words": [],
            "vectors": {"lines": 0, "rects": 0, "curves": 0},
            "segments": [],
            "rects": [],
            "fills": [],
            "hints": {},
        }
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        page = pdf.pages[page_no - 1]
        page_w, page_h = page.width, page.height
        # Georgian set in legacy CAD fonts sits at Latin code points: decode it in place so
        # text, words and labels read as Georgian (page.chars is the cached object list)
        legacy = 0
        for ch in page.chars:
            if labels.is_legacy_font(ch.get("fontname")):
                ch["text"] = labels.decode_legacy(ch["text"])
                legacy += 1
        # lines in the order the file draws them (ADR-0031 Decision 1): clustering the tops of
        # every character on the page chains the rows of small stacked labels into one line
        text = page.extract_text(use_text_flow=True) or ""
        raw_words = page.extract_words(use_text_flow=True)
        words = [
            {
                "t": w["text"],
                "x0": round(w["x0"] / page.width, 5),
                "y0": round(w["top"] / page.height, 5),
                "x1": round(w["x1"] / page.width, 5),
                "y1": round(w["bottom"] / page.height, 5),
            }
            for w in raw_words
        ]
        vectors = {"lines": len(page.lines), "rects": len(page.rects), "curves": len(page.curves)}
        # the raw line segments (normalised), line work first so the cap drops annotation; a
        # fifth element 1 marks annotation (hatching, grid axes, dimension and boundary lines)
        drawn = sorted(page.lines, key=lambda ln: not is_line_work(ln))[:MAX_SEGMENTS]
        segments = [
            [
                round(ln["x0"] / page.width, 5),
                round(ln["top"] / page.height, 5),
                round(ln["x1"] / page.width, 5),
                round(ln["bottom"] / page.height, 5),
                *(() if is_line_work(ln) else (1,)),
            ]
            for ln in drawn
        ]
        dimension_scale = dimension_page_width(raw_words, page.lines, float(page.width))
        fills = _fills(page)
        # rectangles are closed loops already; the suggestion engine turns them into faces
        rects = [
            [
                round(r["x0"] / page.width, 5),
                round(r["top"] / page.height, 5),
                round(r["x1"] / page.width, 5),
                round(r["bottom"] / page.height, 5),
            ]
            for r in page.rects[:MAX_SEGMENTS]
        ]
    hints = {**hints_from_text(text, vectors), "legacy_font_chars": legacy}
    if dimension_scale:
        hints["dimension_scale"] = dimension_scale
    return {
        "text": text,
        "words": words,
        "vectors": vectors,
        "segments": segments,
        "rects": rects,
        "fills": fills,
        "page_pt": [round(float(page_w), 3), round(float(page_h), 3)],
        "hints": hints,
    }


def is_line_work(obj: dict[str, Any]) -> bool:
    """Walls, partitions and furniture are drawn dark and grey; coloured or light strokes are
    annotation that crosses rooms (hatch lines, grid axes, dimension and boundary lines)."""
    rgb = _rgb(obj.get("stroking_color"))
    if rgb is None:
        return True
    return max(rgb) - min(rgb) <= LINE_WORK_MAX_CHROMA and sum(rgb) / 3 <= LINE_WORK_MAX_LIGHTNESS


def dimension_page_width(
    words: list[dict[str, Any]], lines: list[dict[str, Any]], page_width: float
) -> dict[str, Any] | None:
    """The page width in metres read from the drawing's own dimensions (ADR-0031 Decision 3).

    A dimension is an upright whole number ("620", "6,475") with a horizontal line just above or
    below it whose span covers the number; value ÷ span is the page width in the drawing's
    length unit. Numbers that are not dimensions (unit labels, axis bubbles, label boxes) give
    scattered ratios, dimensions give one: the densest ratio window is taken when it holds at
    least ``DIMENSION_MIN_AGREE`` pairs and ``DIMENSION_MIN_SHARE`` of all of them. Centimetres
    or millimetres are told apart by the agreeing values (a room is 300–900 cm, 3000–9000 mm).
    """
    rows = sorted(
        (ln["top"], ln["x0"], ln["x1"])
        for ln in lines
        if abs(ln["bottom"] - ln["top"]) < 0.05 and ln["x1"] - ln["x0"] > 1.0
    )
    tops = [r[0] for r in rows]
    pairs: list[tuple[float, float]] = []
    for w in words:
        if not w.get("upright", True) or not DIMENSION_RE.match(w["text"]):
            continue
        value = float(re.sub(r"[, ]", "", w["text"]))
        h = max(float(w["bottom"]) - float(w["top"]), 0.1)
        cx = (float(w["x0"]) + float(w["x1"])) / 2
        best: tuple[float, float] | None = None
        lo = bisect.bisect_left(tops, float(w["top"]) - 1.2 * h)
        hi = bisect.bisect_right(tops, float(w["bottom"]) + 1.2 * h)
        for top, x0, x1 in rows[lo:hi]:
            if not x0 <= cx <= x1 or x1 - x0 < float(w["x1"]) - float(w["x0"]):
                continue
            gap = min(abs(top - float(w["top"])), abs(top - float(w["bottom"])))
            if best is None or gap < best[0]:
                best = (gap, x1 - x0)
        if best is not None:
            pairs.append((value * page_width / best[1], value))
    if len(pairs) < DIMENSION_MIN_AGREE:
        return None
    pairs.sort()
    best_window: list[tuple[float, float]] = []
    j = 0
    for i in range(len(pairs)):
        while pairs[i][0] > pairs[j][0] * (1 + 2 * DIMENSION_AGREE):
            j += 1
        if i + 1 - j > len(best_window):
            best_window = pairs[j : i + 1]
    if len(best_window) < DIMENSION_MIN_AGREE or len(best_window) < DIMENSION_MIN_SHARE * len(
        pairs
    ):
        return None
    per_page = sorted(r for r, _ in best_window)[len(best_window) // 2]
    typical = sorted(v for _, v in best_window)[len(best_window) // 2]
    unit, per_m = ("mm", 1000.0) if typical >= 1000 else ("cm", 100.0)
    width_m = per_page / per_m
    if not DIMENSION_PAGE_WIDTH_M[0] <= width_m <= DIMENSION_PAGE_WIDTH_M[1]:
        return None
    return {
        "page_width_m": round(width_m, 3),
        "unit": unit,
        "agree": len(best_window),
        "pairs": len(pairs),
    }


def _fills(page: Any, *, max_fills: int = 3000, min_area: float = 0.00002) -> list[dict[str, Any]]:
    """Filled, non-dark closed shapes: zones and hatches CAD tools draw under rooms and units.

    ArchiCAD zones, Revit area fills and AutoCAD hatches export as filled polygons that trace a
    unit exactly; near-black fills are walls and columns and are left out. Normalised rings,
    largest first, with the fill colour (0–1 RGB) so the engine can tell zone families apart.
    """
    w, h = float(page.width), float(page.height)
    out: list[dict[str, Any]] = []
    for obj in list(page.curves) + list(page.rects):
        if not obj.get("fill"):
            continue
        rgb = _rgb(obj.get("non_stroking_color"))
        if rgb is not None and sum(rgb) / 3 < 0.2:
            continue
        pts = obj.get("pts")
        if not pts:
            x0, x1, t, b = obj["x0"], obj["x1"], obj["top"], obj["bottom"]
            pts = [(x0, t), (x1, t), (x1, b), (x0, b)]
        ring = [[round(float(x) / w, 5), round(float(y) / h, 5)] for x, y in pts]
        if len(ring) < 3 or abs(_shoelace(ring)) < min_area:
            continue
        out.append({"ring": ring, "rgb": rgb})
    out.sort(key=lambda f: -abs(_shoelace(f["ring"])))
    return out[:max_fills]


def _rgb(color: Any) -> list[float] | None:
    """pdfplumber colours: gray (1 value), RGB (3) or CMYK (4) tuples → RGB in 0–1."""
    if color is None:
        return None
    if isinstance(color, (int, float)):
        color = (color,)
    try:
        c = [float(v) for v in color]
    except (TypeError, ValueError):
        return None
    if len(c) == 1:
        return [round(c[0], 3)] * 3
    if len(c) == 3:
        return [round(v, 3) for v in c]
    if len(c) == 4:
        k = c[3]
        return [round((1 - v) * (1 - k), 3) for v in c[:3]]
    return None


def _shoelace(ring: list[list[float]]) -> float:
    return 0.5 * sum(
        ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1]
        for i in range(len(ring))
    )


def hints_from_text(text: str, vectors: dict[str, int] | None = None) -> dict[str, Any]:
    levels = sorted({m.group(1) for m in LEVEL_RE.finditer(text)}, key=lambda s: float(s))
    scales = sorted({int(m.group(1)) for m in SCALE_RE.finditer(text)})
    found = labels.find_labels(text)
    by_kind: dict[str, set[str]] = {}
    for lb in found:
        by_kind.setdefault(lb.kind or "numbered", set()).add(lb.key)
    apartments = sorted(by_kind.get("apartment", set()), key=_natural)
    areas = [float(a.replace(",", ".")) for a in AREA_RE.findall(text)]
    floor_words = [m.group(1) for m in FLOOR_WORD_RE.finditer(text) if m.group(1)]
    vec_total = sum((vectors or {}).values())
    kind = "unknown"
    typed = any(k != "numbered" for k in by_kind)
    if typed and vec_total > 500:
        kind = "floor_plan"
    elif vec_total > 2000:
        kind = "drawing"
    elif vec_total == 0 and len(text) > 500:
        kind = "text_sheet"
    return {
        "kind": kind,
        "levels": levels[:12],
        "scales": scales,
        "apartment_labels": apartments[:200],
        "unit_labels": {k: sorted(v, key=_natural)[:200] for k, v in sorted(by_kind.items())},
        "area_values": areas[:300],
        "floor_numbers": sorted({int(f) for f in floor_words}),
        "has_text_layer": bool(text.strip()),
    }


def _natural(key: str) -> tuple:
    """Sort "2" before "10" and "A9/10-2" before "A9/10-10"."""
    return tuple(int(p) if p.isdigit() else p for p in re.split(r"(\d+)", key))


def suggest_floor_level(hints: dict[str, Any]) -> int | None:
    """Best-effort floor level: explicit floor words first, then a 0.00 level marker."""
    if hints.get("floor_numbers"):
        return hints["floor_numbers"][0]
    levels = hints.get("levels") or []
    if not levels:
        return None
    try:
        lowest = min(float(x) for x in levels)
    except ValueError:
        return None
    if abs(lowest) < 0.5:
        return 0
    return None
