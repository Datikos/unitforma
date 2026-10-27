"""Vector-based boundary suggestions (plan §13.2 "Unit boundaries", assisted column).

Pure functions over the per-page extract JSON the worker stores next to the raster
(``documents.processing.extract_page``). Three sources, best first:

1. *Filled zones.* CAD tools export the zone or area fill under each unit (ArchiCAD zones,
   Revit area fills, AutoCAD hatches) as one filled polygon that traces the unit exactly.
   A fill holding one apartment label is the unit outline.
2. *Grown faces.* Without fills, the faces enclosed by the line work are rooms as often as
   units. The face holding a label grows into neighbouring faces until it reaches the area
   printed next to the label ("ბინა №12 / 61.3 m²"); it never takes a face holding another
   unit's label, a level marker (stair halls and corridors carry those) or its own printed
   area (balconies, store rooms), and the result is kept only when its area matches the
   printed one. Matching area does not prove the shape, so grown outlines are proposals at
   review confidence (0.7), below fills and labelled faces.
3. *Plain faces*, as before; a labelled face whose area is far from the printed area is
   flagged with a low confidence so the reviewer knows it is only part of the unit.

Scans have no vectors, so they yield nothing — the manual editor remains the committed path.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree

from unitforma.documents.labels import UnitLabel, find_labels, parking_families, primary_label
from unitforma.documents.processing import AREA_RE, LEVEL_RE

Ring = list[list[float]]
Word = dict[str, Any]

# a lone number such as "12" or "3A" inside a loop is a weaker label candidate than "apt 12"
BARE_LABEL_RE = re.compile(r"^(?:[A-Za-z]?\d{1,4}[A-Za-z]?)$")

# relative difference between measured and printed area accepted as "the same unit"
AREA_MATCH = 0.08
# a labelled face this far below the printed area is only part of the unit
AREA_PARTIAL = 0.15
# a printed scale and the dimensions' page width this far apart: the dimensions win (ADR-0031)
SCALE_AGREE = 0.05

# confidence by source and label (plan §13.2): a CAD zone with a typed label is the unit
FILL_CONFIDENCE = {"typed": 0.95, "parking": 0.9, "numbered": 0.85, "bare": 0.65, None: 0.45}
LOOP_CONFIDENCE = {"typed": 0.9, "parking": 0.85, "numbered": 0.8, "bare": 0.65, None: 0.4}


@dataclass
class Candidate:
    ring: Ring
    label: str | None
    text: str
    confidence: float
    area_norm: float
    source: str = "vector_suggest"
    words: list[str] = field(default_factory=list)
    method: str = "loop"  # fill | grown | loop
    printed_area_m2: float | None = None
    measured_area_m2: float | None = None
    # apartment | commercial | storage | parking, or None when the label does not say
    unit_type: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalise_label(text: str | None) -> str | None:
    """Reduce 'ბინა №12', 'bina #12', 'Apt. 12', '12' to a comparable key ('12')."""
    if not text:
        return None
    lb = primary_label(text)
    if lb:
        return lb.key
    t = text.strip().upper()
    return t or None


def page_metres(extract: dict[str, Any], scale: int | None) -> tuple[float, float] | None:
    """Sheet size in real metres from the page size in points and a 1:N drawing scale."""
    pt = extract.get("page_pt")
    if not pt or not scale:
        return None
    k = 0.0254 / 72 * scale
    return (float(pt[0]) * k, float(pt[1]) * k)


def dimension_metres(
    extract: dict[str, Any], dimension_scale: dict[str, Any] | None
) -> tuple[float, float] | None:
    """Sheet size in real metres from the page width the dimensions give (ADR-0031)."""
    pt = extract.get("page_pt")
    width = (dimension_scale or {}).get("page_width_m")
    if not pt or not width or not float(pt[0]):
        return None
    return (float(width), float(width) * float(pt[1]) / float(pt[0]))


def scale_metres(
    extract: dict[str, Any], scales: list[int], dimension_scale: dict[str, Any] | None
) -> tuple[tuple[float, float], str] | None:
    """Sheet size in metres and its source without a calibration: the single printed scale,
    unless the page's own dimensions disagree with it by more than ``SCALE_AGREE`` (a ramp's
    "1:12" read as the scale, N4 page 11), then the dimensions (ADR-0031 Decision 3)."""
    printed = page_metres(extract, int(scales[0])) if len(scales) == 1 else None
    dims = dimension_metres(extract, dimension_scale)
    if printed and (dims is None or abs(printed[0] - dims[0]) <= SCALE_AGREE * dims[0]):
        return printed, "printed_scale"
    return (dims, "dimensions") if dims else None


@dataclass
class _Label:
    """What the text inside one polygon says about it."""

    unit: UnitLabel | None
    label: str | None  # as shown to the reviewer
    grade: str | None  # typed | parking | numbered | bare | None
    text: str
    printed: float | None

    @property
    def key(self) -> str | None:
        return self.unit.key if self.unit else None

    @property
    def unit_type(self) -> str | None:
        return self.unit.kind if self.unit else None


def _read(words: list[Word], families: frozenset[str] = frozenset()) -> _Label:
    text = _joined(words)
    unit = primary_label(text, families)
    printed = _printed_area(text, unit)
    if unit is not None:
        if unit.kind == "parking" and unit.strength == 1:
            grade = "parking"
        elif unit.kind is None:
            grade = "numbered" if printed is not None else "bare"
        else:
            grade = "typed"
        return _Label(unit, unit.text, grade, text, printed)
    for w in words:
        t = str(w.get("t", ""))
        if BARE_LABEL_RE.match(t):
            return _Label(None, t, "bare", text, None)
    return _Label(None, None, None, text, None)


def closed_loops(
    extract: dict[str, Any],
    *,
    page_m: tuple[float, float] | None = None,
    min_area: float = 0.0004,
    max_area: float = 0.35,
    simplify: float = 0.0012,
    min_segment: float = 1e-4,
    max_candidates: int = 400,
) -> list[Candidate]:
    """Unit outline candidates as normalised rings, labelled with inner text.

    Areas are in normalised page units (page = 1.0), so ``min_area`` 0.0004 is roughly a
    2 % × 2 % patch and ``max_area`` keeps the sheet frame and title block out. ``page_m`` is
    the sheet size in metres (from the calibration or the drawing scale); without it printed
    areas cannot be compared and faces are not grown.
    """
    words = [w for w in (extract.get("words") or []) if "x0" in w]
    m2_per_unit = page_m[0] * page_m[1] if page_m else None
    families = parking_families(_joined(words))

    fills = _fill_candidates(extract, words, m2_per_unit, min_area, max_area, simplify, families)
    covered = {normalise_label(c.label) for c in fills if c.confidence >= 0.85 and c.label}
    fill_polys = [Polygon(c.ring) for c in fills]

    all_faces = [f for f in _faces(extract, min_segment) if 0 < f.area <= max_area]
    all_words = _words_in(all_faces, words)
    reads = [_read(ws, families) for ws in all_words]

    grown = _grow(all_faces, reads, covered, m2_per_unit, simplify)
    covered |= {normalise_label(c.label) for c in grown}

    loops: list[Candidate] = []
    for face, ws, rd in zip(all_faces, all_words, reads, strict=True):
        if face.area < min_area:
            continue
        if rd.key and rd.grade != "bare" and rd.key in covered:
            continue
        if any(_overlap(face, fp) >= 0.8 for fp in fill_polys):
            continue
        poly = face.simplify(simplify, preserve_topology=True)
        if poly.is_empty or not isinstance(poly, Polygon):
            continue
        ring = _ring(poly)
        if len(ring) < 3:
            continue
        measured = round(face.area * m2_per_unit, 1) if m2_per_unit else None
        confidence = LOOP_CONFIDENCE[rd.grade]
        if (
            rd.unit
            and rd.printed
            and measured is not None
            and measured < rd.printed * (1 - AREA_PARTIAL)
        ):
            confidence = 0.5  # a room of the unit, not the unit
        elif rd.unit and len(_unit_keys(rd.text, families)) > 1:
            confidence = 0.5  # two units without a drawn wall between them (ADR-0031)
        loops.append(
            Candidate(
                ring=ring,
                label=rd.label,
                text=rd.text[:200],
                confidence=confidence,
                area_norm=round(face.area, 6),
                words=[str(w.get("t", "")) for w in ws][:40],
                method="loop",
                printed_area_m2=rd.printed if rd.unit else None,
                measured_area_m2=measured,
                unit_type=rd.unit_type,
            )
        )
    out = fills + grown + loops
    out.sort(key=lambda c: (-c.confidence, -c.area_norm))
    return out[:max_candidates]


def _faces(extract: dict[str, Any], min_segment: float) -> list[Polygon]:
    lines: list[LineString] = []
    for seg in extract.get("segments") or []:
        if len(seg) > 4 and seg[4] == 1:
            continue  # annotation crosses rooms (ADR-0031 Decision 2)
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
    return list(polygonize(unary_union(lines)))


def _words_in(polys: list[Polygon], words: list[Word]) -> list[list[Word]]:
    """Words whose centre lies in each polygon, in reading order (spatial index on polygons)."""
    out: list[list[Word]] = [[] for _ in polys]
    if not polys or not words:
        return out
    tree = STRtree(polys)
    for w in words:
        pt = Point((w["x0"] + w["x1"]) / 2, (w["y0"] + w["y1"]) / 2)
        for i in tree.query(pt, predicate="within"):
            out[int(i)].append(w)
    return out


def _joined(words: list[Word]) -> str:
    """Words as text with their line breaks, so a label never runs into the next line."""
    parts: list[str] = []
    prev: Word | None = None
    for w in words:
        if prev is not None:
            h = max(prev["y1"] - prev["y0"], w["y1"] - w["y0"], 1e-6)
            same_line = abs((w["y0"] + w["y1"]) - (prev["y0"] + prev["y1"])) / 2 < 0.6 * h
            parts.append(" " if same_line else "\n")
        parts.append(str(w.get("t", "")))
        prev = w
    return "".join(parts)


def _fill_candidates(
    extract: dict[str, Any],
    words: list[Word],
    m2_per_unit: float | None,
    min_area: float,
    max_area: float,
    simplify: float,
    families: frozenset[str] = frozenset(),
) -> list[Candidate]:
    out: list[Candidate] = []
    kept: list[Polygon] = []
    for f in extract.get("fills") or []:
        try:
            poly = Polygon(f["ring"]).buffer(0)
        except (ValueError, TypeError, KeyError):
            continue
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda g: g.area)
        if not isinstance(poly, Polygon) or not min_area <= poly.area <= max_area:
            continue
        if any(_iou(poly, k) > 0.95 for k in kept):
            continue  # the same zone drawn twice (fill + pattern)
        inner = _words_in([poly], words)[0]
        rd = _read(inner, families)
        if len(_unit_keys(rd.text, families)) > 1:
            continue  # a background or block fill under several units
        measured = round(poly.area * m2_per_unit, 1) if m2_per_unit else None
        confidence = FILL_CONFIDENCE[rd.grade]
        if (
            rd.grade in ("typed", "parking", "numbered")
            and rd.printed
            and measured is not None
            and abs(measured - rd.printed) > rd.printed * AREA_MATCH
        ):
            confidence = 0.6
        simple = poly.simplify(simplify / 4, preserve_topology=True)
        ring = _ring(simple if isinstance(simple, Polygon) else poly)
        if len(ring) < 3:
            continue
        if rd.unit and any(
            o.label == rd.label and Polygon(o.ring).buffer(1e-4).contains(poly) for o in out
        ):
            continue  # a car or a furniture symbol drawn over the zone, inside it (ADR-0031)
        kept.append(poly)
        out.append(
            Candidate(
                ring=ring,
                label=rd.label,
                text=rd.text[:200],
                confidence=confidence,
                area_norm=round(poly.area, 6),
                words=[str(w.get("t", "")) for w in inner][:40],
                method="fill",
                printed_area_m2=rd.printed if rd.unit else None,
                measured_area_m2=measured,
                unit_type=rd.unit_type,
            )
        )
    return out


def _unit_keys(text: str, families: frozenset[str]) -> set[str]:
    return {lb.key for lb in find_labels(text, families)}


def _grow(
    faces: list[Polygon],
    reads: list[_Label],
    covered: set[str | None],
    m2_per_unit: float | None,
    simplify: float,
    *,
    max_steps: int = 200,
) -> list[Candidate]:
    """Grow labelled faces into neighbours up to the printed area (see module docstring)."""
    if not m2_per_unit or not faces:
        return []
    blocked = {
        i
        for i, rd in enumerate(reads)
        if rd.unit is not None
        or LEVEL_RE.search(rd.text) is not None
        or _own_zone(faces[i], rd.text, m2_per_unit)
    }
    seeds = []
    for i, rd in enumerate(reads):
        if rd.unit is None or rd.key in covered or rd.printed is None:
            continue
        target = rd.printed / m2_per_unit
        if faces[i].area >= target * (1 - AREA_MATCH):
            continue  # the face already is the unit; the plain-face path reports it
        seeds.append((target, i))
    if not seeds:
        return []
    tree = STRtree(faces)
    claimed: set[int] = set()
    out: list[Candidate] = []
    for target, i in sorted(seeds):
        rd = reads[i]
        territory = {i}
        shape = faces[i]
        area = faces[i].area
        for _ in range(max_steps):
            if area >= target * (1 - AREA_MATCH / 2):
                break
            best, best_len = None, 0.0
            edge = shape.boundary
            for j in tree.query(shape.buffer(1e-6)):
                j = int(j)
                if j in territory or j in claimed or j in blocked:
                    continue
                if area + faces[j].area > target * (1 + AREA_MATCH):
                    continue
                shared = edge.intersection(faces[j].boundary).length
                if shared > best_len:
                    best, best_len = j, shared
            if best is None or best_len < 2e-3:
                break
            territory.add(best)
            area += faces[best].area
            shape = unary_union([shape, faces[best]])
        if abs(area - target) > target * AREA_MATCH or not isinstance(shape, Polygon):
            continue
        claimed |= territory
        outline = Polygon(shape.exterior).simplify(simplify, preserve_topology=True)
        if not isinstance(outline, Polygon):
            continue
        out.append(
            Candidate(
                ring=_ring(outline),
                label=rd.label,
                text=rd.text[:200],
                confidence=0.7,
                area_norm=round(area, 6),
                words=[],
                method="grown",
                printed_area_m2=rd.printed,
                measured_area_m2=round(area * m2_per_unit, 1),
                unit_type=rd.unit_type,
            )
        )
    return out


def _own_zone(face: Polygon, text: str, m2_per_unit: float) -> bool:
    """A face carrying its own printed area (a balcony "7.5 m²", a store room) is another zone."""
    measured = face.area * m2_per_unit
    return any(
        abs(float(v.replace(",", ".")) - measured) <= max(0.5, 0.15 * measured)
        for v in AREA_RE.findall(text)
    )


def _printed_area(text: str, unit: UnitLabel | None = None) -> float | None:
    """The area printed with a unit label ("ბინა №12 61.3 m²"): the first one after the label."""
    if unit is None:
        unit = primary_label(text)
    after = AREA_RE.search(text, unit.end) if unit else None
    if after:
        return float(after.group(1).replace(",", "."))
    found = AREA_RE.findall(text)
    if len(found) == 1:
        return float(found[0].replace(",", "."))
    return None


def _ring(poly: Polygon) -> Ring:
    return [[round(x, 5), round(y, 5)] for x, y in poly.exterior.coords[:-1]]


def _overlap(a: Polygon, b: Polygon) -> float:
    small = min(a.area, b.area)
    return a.intersection(b).area / small if small > 0 else 0.0


def _iou(a: Polygon, b: Polygon) -> float:
    union = a.union(b).area
    return a.intersection(b).area / union if union > 0 else 0.0
