"""DXF intake (ADR-0006 Decision 2): one sheet per layout, the same per-sheet extract as a PDF
page, a raster drawn from the vectors, and a calibration taken from the drawing units.

AutoCAD and ArchiCAD both export DXF. Model space is page 1; paper-space layouts that hold
entities follow in tab order. Lines, polylines, arcs, circles, ellipses and splines are
flattened into ``segments``; closed polylines and HATCH boundaries become ``fills`` (ArchiCAD
zones and AutoCAD hatches trace a unit exactly, plan §13.2); TEXT, MTEXT and ATTRIB become
``words`` with the legacy Georgian font decoding of ``documents/labels.py`` applied by text
style. Block references are exploded one level. ``$INSUNITS`` gives metres per drawing unit, so
the sheet arrives calibrated and the two-point step can be skipped.

Coordinates: DXF is Y-up; the extract is normalised to the layout's extent (plus a margin) with
Y down, like a rasterised page, so ``mapping/suggest.py`` and ``documents/levels.py`` read it
unchanged. Text boxes are estimated from the style's cap height and ignore rotation.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any

from unitforma.documents import labels, preview_text

MIME = "application/dxf"
ALIASES = frozenset({"application/dxf", "image/vnd.dxf", "application/x-dxf", "image/x-dxf"})
MAX_BYTES = 50 * 1024 * 1024
MAX_ENTITIES = 200_000
MAX_SEGMENTS = 20_000
MAX_FILLS = 3000
MAX_WORDS = 20_000
MARGIN = 0.02
# metres per drawing unit by $INSUNITS (plan: metres, centimetres, millimetres; inches and feet
# cost nothing). 0 = unitless → no calibration.
UNIT_METRES = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0}
UNIT_NAMES = {1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m"}
POINTS_PER_METRE = 72 / 0.0254
_BINARY_SENTINEL = b"AutoCAD Binary DXF"
_TEXT_HEAD_RE = re.compile(rb"^\s*0\s*\r?\n\s*SECTION\b")
_CURVE_TYPES = frozenset({"ARC", "CIRCLE", "ELLIPSE", "SPLINE"})
_LINEAR_TYPES = frozenset({"LINE", "LWPOLYLINE", "POLYLINE"})


class DxfError(ValueError):
    """The file is not a DXF this reader can use; the message is shown to the reviewer."""


def is_dxf(data: bytes) -> bool:
    head = data[:4096]
    if head.startswith(b"\xef\xbb\xbf"):
        head = head[3:]
    return head.startswith(_BINARY_SENTINEL) or _TEXT_HEAD_RE.match(head) is not None


@dataclass
class LayoutInfo:
    page_no: int
    name: str
    extent: tuple[float, float, float, float]  # minx, miny, maxx, maxy in drawing units
    width_pt: float
    height_pt: float
    entities: int


class DxfDrawing:
    """One parsed DXF; cheap per-layout extraction and rasterisation after a single parse."""

    def __init__(self, data: bytes):
        if len(data) > MAX_BYTES:
            raise DxfError(f"DXF larger than {MAX_BYTES // (1024 * 1024)} MB")
        if data.lstrip()[:32].startswith(_BINARY_SENTINEL):
            raise DxfError("Binary DXF is not supported; save as ASCII DXF (AutoCAD 2018 DXF)")
        import ezdxf

        text = _decode(data)
        try:
            self.doc = ezdxf.read(io.StringIO(text))
        except Exception as e:  # noqa: BLE001 - ezdxf raises several exception types
            raise DxfError(f"DXF could not be read: {e}"[:300]) from e
        self.insunits = int(self.doc.header.get("$INSUNITS", 0) or 0)
        self.m_per_unit: float | None = UNIT_METRES.get(self.insunits)
        self.layouts: list[LayoutInfo] = []
        self._layouts: dict[int, Any] = {}
        page_no = 0
        for name in self.doc.layouts.names_in_taborder():
            layout = self.doc.layouts.get(name)
            count = len(layout)
            if not layout.is_modelspace and count == 0:
                continue
            if count > MAX_ENTITIES:
                raise DxfError(f"layout {name!r} has more than {MAX_ENTITIES} entities")
            extent = _extent(layout)
            page_no += 1
            w_u, h_u = extent[2] - extent[0], extent[3] - extent[1]
            k = self.m_per_unit * POINTS_PER_METRE if self.m_per_unit else 1.0
            self.layouts.append(
                LayoutInfo(page_no, name, extent, round(w_u * k, 3), round(h_u * k, 3), count)
            )
            self._layouts[page_no] = layout

    # ------------------------------------------------------------------ per layout
    def layout(self, page_no: int) -> LayoutInfo:
        for info in self.layouts:
            if info.page_no == page_no:
                return info
        raise DxfError(f"no layout {page_no}")

    def extract(self, page_no: int) -> dict[str, Any]:
        """The per-sheet extract (``words``, ``segments``, ``rects``, ``fills``, ``page_pt``,
        ``hints``) in the shape of ``documents.processing.extract_page``."""
        from unitforma.documents import processing

        info = self.layout(page_no)
        geo = _Geometry(self, info)
        geo.collect(self._layouts[page_no])
        words = geo.words_out()
        text = "\n".join(geo.texts)
        vectors = {"lines": len(geo.segments), "rects": len(geo.rects), "curves": geo.curves}
        hints = processing.hints_from_text(text, vectors)
        hints.update(
            {
                "cad": "dxf",
                "layout": info.name,
                "units": UNIT_NAMES.get(self.insunits),
                "layers": dict(sorted(geo.layers.items(), key=lambda kv: -kv[1])[:60]),
                "legacy_font_chars": geo.legacy_chars,
            }
        )
        return {
            "text": text,
            "words": words,
            "vectors": vectors,
            "segments": geo.segments[:MAX_SEGMENTS],
            "rects": geo.rects[:MAX_SEGMENTS],
            "fills": geo.fills_out(),
            "page_pt": [info.width_pt, info.height_pt],
            "hints": hints,
        }

    def rasterize(
        self, page_no: int, long_edge: int = 4000, thumb_edge: int = 320
    ) -> tuple[bytes, bytes, int, int]:
        """(png, thumbnail_png, width, height): fills in their colour, lines dark, text sized to
        the text height in Noto Sans Georgian and Noto Sans (``preview_text``)."""
        from PIL import Image, ImageDraw

        preview_text.font(True, 12)  # a missing font file fails the job, not every label
        preview_text.font(False, 12)

        info = self.layout(page_no)
        w_u = info.extent[2] - info.extent[0]
        h_u = info.extent[3] - info.extent[1]
        if w_u >= h_u:
            width, height = long_edge, max(1, round(long_edge * h_u / w_u))
        else:
            width, height = max(1, round(long_edge * w_u / h_u)), long_edge
        geo = _Geometry(self, info)
        geo.collect(self._layouts[page_no])
        im = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(im)
        for f in geo.fills:
            rgb = f["rgb"]
            colour = (
                tuple(int(round(c * 255)) for c in rgb) if rgb else (232, 236, 242)
            )  # grey-blue for plain closed polylines
            pts = [(x * width, y * height) for x, y in f["ring"]]
            if len(pts) >= 3:
                draw.polygon(pts, fill=colour)
        for x0, y0, x1, y1 in geo.segments:
            draw.line((x0 * width, y0 * height, x1 * width, y1 * height), fill=(40, 40, 40))
        for wd in geo.words:
            px = max(6, int(round((wd["y1"] - wd["y0"]) * height)))
            try:
                preview_text.draw_label(
                    draw, (wd["x0"] * width, wd["y0"] * height), wd["t"], px, (20, 20, 20)
                )
            except Exception:  # noqa: BLE001, S112 - text on the preview is best effort
                continue
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        thumb = im.copy()
        thumb.thumbnail((thumb_edge, thumb_edge))
        tbuf = io.BytesIO()
        thumb.save(tbuf, format="PNG", optimize=True)
        return buf.getvalue(), tbuf.getvalue(), width, height

    def calibration(self, page_no: int, raster_width: int, raster_height: int) -> dict | None:
        """Metres per raster pixel from ``$INSUNITS`` and the layout extent; None when the
        drawing has no units. Shape of ``inventory.geometry.calibration_from_points`` plus the
        source so the editor can say where it came from."""
        if not self.m_per_unit or raster_width < 2:
            return None
        info = self.layout(page_no)
        width_m = (info.extent[2] - info.extent[0]) * self.m_per_unit
        if width_m <= 0:
            return None
        return {
            "p1": [0.0, 0.5],
            "p2": [1.0, 0.5],
            "distance_m": round(width_m, 4),
            "m_per_px": width_m / raster_width,
            "raster_width": raster_width,
            "raster_height": raster_height,
            "source": "dxf_insunits",
            "insunits": self.insunits,
            "unit": UNIT_NAMES.get(self.insunits),
        }


# ---------------------------------------------------------------------- internals
def _decode(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    for enc in ("utf-8", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extent(layout: Any) -> tuple[float, float, float, float]:
    from ezdxf import bbox

    ext = bbox.extents(layout, fast=True)
    if not ext.has_data:
        return (0.0, 0.0, 1.0, 1.0)
    minx, miny = float(ext.extmin.x), float(ext.extmin.y)
    maxx, maxy = float(ext.extmax.x), float(ext.extmax.y)
    w, h = max(maxx - minx, 1e-6), max(maxy - miny, 1e-6)
    m = MARGIN * max(w, h)
    return (minx - m, miny - m, maxx + m, maxy + m)


class _Geometry:
    """Collects one layout's entities into normalised, Y-down page coordinates."""

    def __init__(self, drawing: DxfDrawing, info: LayoutInfo):
        self.doc = drawing.doc
        self.info = info
        self.minx, self.miny, self.maxx, self.maxy = info.extent
        self.w = self.maxx - self.minx
        self.h = self.maxy - self.miny
        self.flat = max(self.w, self.h) / 2000  # flattening tolerance in drawing units
        self.segments: list[list[float]] = []
        self.rects: list[list[float]] = []
        self.fills: list[dict[str, Any]] = []
        self.words: list[dict[str, Any]] = []
        self.texts: list[str] = []
        self.layers: dict[str, int] = {}
        self.curves = 0
        self.legacy_chars = 0

    def norm(self, x: float, y: float) -> tuple[float, float]:
        return (round((x - self.minx) / self.w, 5), round((self.maxy - y) / self.h, 5))

    def collect(self, layout: Any, depth: int = 0) -> None:
        for e in layout:
            self._entity(e, depth)

    def _entity(self, e: Any, depth: int) -> None:
        kind = e.dxftype()
        layer = str(getattr(e.dxf, "layer", "0") or "0")
        self.layers[layer] = self.layers.get(layer, 0) + 1
        if kind == "INSERT":
            if depth == 0:
                try:
                    for v in e.virtual_entities():
                        self._entity(v, depth + 1)
                except Exception:  # noqa: BLE001 - a broken block must not stop the sheet
                    return
            return
        if kind in ("TEXT", "ATTRIB", "MTEXT"):
            self._text(e, kind)
            return
        if kind == "HATCH":
            self._hatch(e, layer)
            return
        if kind in _LINEAR_TYPES or kind in _CURVE_TYPES:
            if kind in _CURVE_TYPES:
                self.curves += 1
            self._path(e, layer, kind)

    def _path(self, e: Any, layer: str, kind: str) -> None:
        from ezdxf import path

        try:
            pts = [(float(v.x), float(v.y)) for v in path.make_path(e).flattening(self.flat)]
        except Exception:  # noqa: BLE001 - unsupported geometry is skipped, not fatal
            return
        if len(pts) < 2:
            return
        closed = bool(getattr(e, "closed", False)) or (
            kind in ("CIRCLE", "ELLIPSE") or (len(pts) > 3 and _close(pts[0], pts[-1]))
        )
        if closed and not _close(pts[0], pts[-1]):
            pts.append(pts[0])
        for (x0, y0), (x1, y1) in zip(pts, pts[1:], strict=False):
            a, b = self.norm(x0, y0), self.norm(x1, y1)
            if a != b and len(self.segments) < MAX_SEGMENTS:
                self.segments.append([a[0], a[1], b[0], b[1]])
        if closed and kind in ("LWPOLYLINE", "POLYLINE") and len(pts) >= 4:
            ring = [list(self.norm(x, y)) for x, y in pts[:-1]]
            if len(ring) == 4 and _axis_aligned(ring):
                xs, ys = [p[0] for p in ring], [p[1] for p in ring]
                self.rects.append([min(xs), min(ys), max(xs), max(ys)])
            if len(self.fills) < MAX_FILLS:
                self.fills.append(
                    {"ring": ring, "rgb": None, "layer": layer, "closed_polyline": True}
                )

    def _hatch(self, e: Any, layer: str) -> None:
        from ezdxf import path

        rgb = _hatch_rgb(self.doc, e)
        if rgb is not None and sum(rgb) / 3 < 0.2:
            return  # walls and columns are drawn as dark fills
        try:
            paths = list(path.from_hatch(e))
        except Exception:  # noqa: BLE001
            return
        for p in paths:
            try:
                pts = [(float(v.x), float(v.y)) for v in p.flattening(self.flat)]
            except Exception:  # noqa: BLE001, S112
                continue
            if len(pts) >= 3 and _close(pts[0], pts[-1]):
                pts = pts[:-1]
            if len(pts) < 3 or len(self.fills) >= MAX_FILLS:
                continue
            self.fills.append(
                {"ring": [list(self.norm(x, y)) for x, y in pts], "rgb": rgb, "layer": layer}
            )

    def _text(self, e: Any, kind: str) -> None:
        try:
            raw = e.plain_text() if kind == "MTEXT" else e.plain_text()
        except Exception:  # noqa: BLE001
            raw = str(getattr(e.dxf, "text", "") or "")
        raw = (raw or "").strip()
        if not raw:
            return
        font = _style_font(self.doc, getattr(e.dxf, "style", None))
        if labels.is_legacy_font(font):
            raw = labels.decode_legacy(raw)
            self.legacy_chars += len(raw)
        ins = e.dxf.insert
        x, y = float(ins.x), float(ins.y)
        height = float(getattr(e.dxf, "char_height", None) or getattr(e.dxf, "height", 0) or 0)
        if height <= 0:
            height = self.h / 200
        lines = raw.splitlines() or [raw]
        self.texts.append(raw)
        for li, line in enumerate(lines):
            if not line.strip():
                continue
            # MTEXT grows downwards from its insert point; TEXT sits on its baseline
            top = y + height if kind != "MTEXT" else y - li * height * 1.3
            width = len(line) * height * 0.8  # average glyph advance for CAD fonts
            if kind != "MTEXT":
                try:
                    from ezdxf.tools.text_size import text_size

                    width = float(text_size(e).width) or width
                except Exception:  # noqa: BLE001, S110
                    pass
            x0 = x
            for tok in re.finditer(r"\S+", line):
                if len(self.words) >= MAX_WORDS:
                    return
                frac0 = tok.start() / max(len(line), 1)
                frac1 = tok.end() / max(len(line), 1)
                a = self.norm(x0 + width * frac0, top)
                b = self.norm(x0 + width * frac1, top - height)
                self.words.append(
                    {"t": tok.group(0), "x0": a[0], "y0": a[1], "x1": b[0], "y1": b[1]}
                )

    def words_out(self) -> list[dict[str, Any]]:
        # reading order like pdfplumber: top to bottom, then left to right
        return sorted(self.words, key=lambda w: (round(w["y0"], 3), w["x0"]))

    def fills_out(self) -> list[dict[str, Any]]:
        out = [
            f for f in self.fills if len(f["ring"]) >= 3 and abs(_shoelace(f["ring"])) >= 0.00002
        ]
        out.sort(key=lambda f: -abs(_shoelace(f["ring"])))
        return out[:MAX_FILLS]


def _close(a: tuple[float, float], b: tuple[float, float], eps: float = 1e-6) -> bool:
    return abs(a[0] - b[0]) <= eps and abs(a[1] - b[1]) <= eps


def _axis_aligned(ring: list[list[float]], eps: float = 1e-4) -> bool:
    for i in range(4):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % 4]
        if abs(x0 - x1) > eps and abs(y0 - y1) > eps:
            return False
    return True


def _shoelace(ring: list[list[float]]) -> float:
    return 0.5 * sum(
        ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1]
        for i in range(len(ring))
    )


def _style_font(doc: Any, style: str | None) -> str | None:
    if not style:
        return None
    try:
        st = doc.styles.get(style)
    except Exception:  # noqa: BLE001
        return style
    font = str(getattr(st.dxf, "font", "") or "")
    name = re.sub(r"\.(ttf|shx|otf)$", "", font.rsplit("/", 1)[-1].rsplit("\\", 1)[-1], flags=re.I)
    return name or style


def _hatch_rgb(doc: Any, e: Any) -> list[float] | None:
    """Fill colour in 0–1 RGB: true colour, else the ACI index, else the layer's colour."""
    from ezdxf.colors import aci2rgb

    rgb = getattr(e, "rgb", None)
    if rgb is not None:
        return [round(int(c) / 255, 3) for c in rgb]
    aci = int(getattr(e.dxf, "color", 256) or 256)
    if aci == 256:  # BYLAYER
        try:
            aci = int(doc.layers.get(str(e.dxf.layer)).color)
        except Exception:  # noqa: BLE001
            aci = 7
    if aci == 0:  # BYBLOCK
        aci = 7
    try:
        r, g, b = aci2rgb(aci)
    except Exception:  # noqa: BLE001
        return None
    return [round(r / 255, 3), round(g / 255, 3), round(b / 255, 3)]
