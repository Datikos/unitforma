"""Document processing used by the worker (plan §12.3, §13.2).

Pure functions over bytes so they are testable without storage or a database:
* ``inspect`` — sha256, mime sniffing, page count and page sizes
* ``rasterize_page`` — PNG at a target long edge plus a thumbnail (pypdfium2 / Pillow)
* ``extract_page`` — text with positions, vector segment statistics, hints (levels, scale,
  apartment labels) for floor suggestions (pdfplumber)
"""

from __future__ import annotations

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
        text = page.extract_text() or ""
        words = [
            {
                "t": w["text"],
                "x0": round(w["x0"] / page.width, 5),
                "y0": round(w["top"] / page.height, 5),
                "x1": round(w["x1"] / page.width, 5),
                "y1": round(w["bottom"] / page.height, 5),
            }
            for w in page.extract_words()
        ]
        vectors = {"lines": len(page.lines), "rects": len(page.rects), "curves": len(page.curves)}
        # keep the raw line segments (normalised) for snapping in the boundary editor, capped
        segments = [
            [
                round(ln["x0"] / page.width, 5),
                round(ln["top"] / page.height, 5),
                round(ln["x1"] / page.width, 5),
                round(ln["bottom"] / page.height, 5),
            ]
            for ln in page.lines[:20000]
        ]
        fills = _fills(page)
        # rectangles are closed loops already; the suggestion engine turns them into faces
        rects = [
            [
                round(r["x0"] / page.width, 5),
                round(r["top"] / page.height, 5),
                round(r["x1"] / page.width, 5),
                round(r["bottom"] / page.height, 5),
            ]
            for r in page.rects[:20000]
        ]
    return {
        "text": text,
        "words": words,
        "vectors": vectors,
        "segments": segments,
        "rects": rects,
        "fills": fills,
        "page_pt": [round(float(page_w), 3), round(float(page_h), 3)],
        "hints": {**hints_from_text(text, vectors), "legacy_font_chars": legacy},
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
