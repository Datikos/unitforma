"""Vector-based boundary suggestions (plan §13.2 "Unit boundaries", assisted column).

Pure functions over the per-page extract JSON the worker stores next to the raster
(``documents.processing.extract_page``). Closed loops in the line work of a clean CAD PDF
are candidate unit polygons; apartment labels found inside a loop raise its confidence.
Scans have no vectors, so they yield nothing — the manual editor remains the committed path.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polygonize, unary_union

from unitforma.documents.processing import APARTMENT_RE

Ring = list[list[float]]

# a lone number such as "12" or "3A" inside a loop is a weaker label candidate than "apt 12"
BARE_LABEL_RE = re.compile(r"^(?:[A-Za-z]?\d{1,4}[A-Za-z]?)$")


@dataclass
class Candidate:
    ring: Ring
    label: str | None
    text: str
    confidence: float
    area_norm: float
    source: str = "vector_suggest"
    words: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalise_label(text: str | None) -> str | None:
    """Reduce 'bina #12', 'Apt. 12', '12' to a comparable key ('12')."""
    if not text:
        return None
    m = APARTMENT_RE.search(text)
    if m:
        return m.group(1).upper()
    t = text.strip().upper()
    return t or None


def closed_loops(
    extract: dict[str, Any],
    *,
    min_area: float = 0.0004,
    max_area: float = 0.35,
    simplify: float = 0.0012,
    min_segment: float = 1e-4,
    max_candidates: int = 400,
) -> list[Candidate]:
    """Faces enclosed by the page's line work, as normalised rings, labelled with inner text.

    Areas are in normalised page units (page = 1.0), so ``min_area`` 0.0004 is roughly a
    2 % × 2 % patch and ``max_area`` keeps the sheet frame and title block out.
    """
    lines: list[LineString] = []
    for seg in extract.get("segments") or []:
        x0, y0, x1, y1 = seg[:4]
        if abs(x1 - x0) + abs(y1 - y0) < min_segment:
            continue
        lines.append(LineString([(x0, y0), (x1, y1)]))
    for r in extract.get("rects") or []:
        x0, y0, x1, y1 = r[:4]
        if abs(x1 - x0) < min_segment or abs(y1 - y0) < min_segment:
            continue
        lines.append(LineString(box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)).exterior))
    if not lines:
        return []
    noded = unary_union(lines)
    faces = [p for p in polygonize(noded) if min_area <= p.area <= max_area]
    words = extract.get("words") or []
    centres = [
        (Point((w["x0"] + w["x1"]) / 2, (w["y0"] + w["y1"]) / 2), str(w.get("t", "")))
        for w in words
        if "x0" in w
    ]
    out: list[Candidate] = []
    for face in faces:
        poly = face.simplify(simplify, preserve_topology=True)
        if poly.is_empty or not isinstance(poly, Polygon):
            continue
        ring = [[round(x, 5), round(y, 5)] for x, y in poly.exterior.coords[:-1]]
        if len(ring) < 3:
            continue
        inner = [t for pt, t in centres if face.contains(pt)]
        text = " ".join(inner)
        label = _best_label(inner, text)
        confidence = 0.9 if label and APARTMENT_RE.search(text) else 0.65 if label else 0.4
        out.append(
            Candidate(
                ring=ring,
                label=label,
                text=text[:200],
                confidence=round(confidence, 3),
                area_norm=round(face.area, 6),
                words=inner[:40],
            )
        )
    out.sort(key=lambda c: (-c.confidence, -c.area_norm))
    return out[:max_candidates]


def _best_label(words: list[str], text: str) -> str | None:
    m = APARTMENT_RE.search(text)
    if m:
        return m.group(0).strip()
    for w in words:
        if BARE_LABEL_RE.match(w):
            return w
    return None
