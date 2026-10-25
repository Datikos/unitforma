"""Level markers → floor suggestions with regions (plan §13.2 "Page → floor").

Pure functions over the positioned words of a page extract, so they are testable without
storage or a database.

A plan sheet of a stepped or multi-block building shows several floors side by side, each
with its own level marker ("+3.20 (652.2)", "+4.20 (654.2)", ...). The title block often
repeats the building's overall range ("-4.05 ... +14.70") on every sheet; those markers say
nothing about the page and are dropped when the same marker sits at the same place on pages
that otherwise show different levels. Sections and elevations stack their markers in a
column and are skipped. Every remaining marker that matches a floor's elevation suggests that
floor; with several floors, each gets the part of the sheet closest to its marker.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from shapely.geometry import MultiPoint, Point, Polygon, box
from shapely.ops import unary_union, voronoi_diagram

# a word that is a signed level: "+3.20", "-2.55", "±0.00". CAD fonts often glue the marker
# symbol to it ("O+3.20") or split the sign off ("+O" "4.20"); "(-4.05" (a range in prose) and
# "+1.00," (a caption list) are not markers.
LEVEL_WORD_RE = re.compile(r"^[^\d,(]{0,2}?([+\-±])[^\d,(]?(\d{1,2}\.\d{2})$")
UNSIGNED_RE = re.compile(r"^(\d{1,2}\.\d{2})$")
SIGN_ONLY_RE = re.compile(r"^([+\-±])[^\d,(]?$")
LIST_ITEM_RE = re.compile(r"^[+\-±]?\d{1,2}\.\d{2},$")
ABSOLUTE_RE = re.compile(r"^\((\d{2,4}(?:\.\d{1,3})?)\)$")

# elevation match tolerance (metres) between a marker and floors.elevation_m
ELEVATION_TOLERANCE_M = 0.02


@dataclass(frozen=True)
class Marker:
    text: str
    value: float
    x: float
    y: float
    absolute: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "value": self.value,
            "x": self.x,
            "y": self.y,
            "absolute": self.absolute,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Marker:
        return cls(
            text=str(d["text"]),
            value=float(d["value"]),
            x=float(d["x"]),
            y=float(d["y"]),
            absolute=float(d["absolute"]) if d.get("absolute") is not None else None,
        )


@dataclass(frozen=True)
class FloorRef:
    id: uuid.UUID
    building_id: uuid.UUID
    level: int
    elevation_m: float | None


def markers_from_words(words: list[dict[str, Any]]) -> list[Marker]:
    """Level markers in reading order; list items of a caption ("+1.00, +2.00") are skipped."""
    out: list[Marker] = []
    for i, w in enumerate(words):
        if "x0" not in w:
            continue
        t = str(w.get("t", ""))
        prev = str(words[i - 1].get("t", "")) if i > 0 else ""
        nxt = str(words[i + 1].get("t", "")) if i + 1 < len(words) else ""
        m = LEVEL_WORD_RE.match(t)
        if m:
            sign, digits = m.group(1), m.group(2)
        else:
            u, s = UNSIGNED_RE.match(t), SIGN_ONLY_RE.match(prev)
            if not (u and s):
                continue
            sign, digits = s.group(1), u.group(1)
        if LIST_ITEM_RE.match(prev):
            continue
        a = ABSOLUTE_RE.match(nxt)
        text = ("-" if sign == "-" else "+") + digits
        out.append(
            Marker(
                text=text,
                value=float(text),
                x=round((w["x0"] + w["x1"]) / 2, 5),
                y=round((w["y0"] + w["y1"]) / 2, 5),
                absolute=float(a.group(1)) if a else None,
            )
        )
    return out


def _key(m: Marker, tol: float) -> tuple[str, int, int]:
    return (m.text, round(m.x / tol), round(m.y / tol))


def _in_margin(k: tuple[str, int, int], tol: float, band: float = 0.12) -> bool:
    """Title blocks and legends live along the sheet edges."""
    x, y = k[1] * tol, k[2] * tol
    return min(x, 1 - x) < band or min(y, 1 - y) < band


def drop_repeated(
    per_page: dict[int, list[Marker]], *, min_pages: int = 3, tol: float = 0.01
) -> dict[int, list[Marker]]:
    """Drop title-block markers: same text at the same place on pages showing other levels.

    A marker repeated on duplicate copies of the same plan (fire-safety or accessibility sets
    reprint the floor plans) keeps its page company and survives; a title-block marker sits
    next to a different set of levels on each sheet.
    """
    if len(per_page) < min_pages:
        return per_page
    company: dict[tuple[str, int, int], set[frozenset[str]]] = defaultdict(set)
    pages: dict[tuple[str, int, int], set[int]] = defaultdict(set)
    for page_no, markers in per_page.items():
        texts = {m.text for m in markers}
        for m in markers:
            k = _key(m, tol)
            pages[k].add(page_no)
            company[k].add(frozenset(texts - {m.text}))
    repeated = {
        k
        for k in pages
        if len(pages[k]) >= min_pages and (len(company[k]) >= min_pages or _in_margin(k, tol))
    }
    return {
        p: [m for m in markers if _key(m, tol) not in repeated] for p, markers in per_page.items()
    }


def is_stacked(markers: list[Marker], *, tol: float = 0.02) -> bool:
    """Three or more different levels in one column: a section or an elevation, not a plan."""
    for m in markers:
        column = {o.text for o in markers if abs(o.x - m.x) <= tol}
        if len(column) >= 3:
            return True
    return False


def match_floors(
    markers: list[Marker],
    floors: list[FloorRef],
    preferred_building: uuid.UUID | None = None,
) -> list[tuple[Marker, FloorRef]]:
    """Each marker → the floor whose elevation equals it; ambiguity is left to the reviewer."""
    out: list[tuple[Marker, FloorRef]] = []
    with_elev = [f for f in floors if f.elevation_m is not None]
    for m in markers:
        hits = [
            f
            for f in with_elev
            if abs(float(f.elevation_m) - m.value) <= ELEVATION_TOLERANCE_M  # type: ignore[arg-type]
        ]
        if len(hits) > 1 and preferred_building is not None:
            own = [f for f in hits if f.building_id == preferred_building]
            hits = own or hits
        if len(hits) == 1:
            out.append((m, hits[0]))
    if out or with_elev:
        return out
    # no elevations entered yet: a lone ±0.00 marker still means the entrance level
    if len(markers) == 1 and abs(markers[0].value) < 0.005 and preferred_building is not None:
        ground = [f for f in floors if f.building_id == preferred_building and f.level == 0]
        if ground:
            return [(markers[0], ground[0])]
    return []


def floor_regions(
    matched: list[tuple[Marker, FloorRef]], *, aspect: float = 1.0
) -> list[dict[str, Any]]:
    """One suggestion per floor; with several floors, the Voronoi cell of each floor's markers.

    ``aspect`` is sheet height / width: normalised coordinates are stretched, so the cells
    are computed in proportional space and mapped back.
    """
    by_floor: dict[uuid.UUID, list[Marker]] = defaultdict(list)
    floors: dict[uuid.UUID, FloorRef] = {}
    for m, f in matched:
        by_floor[f.id].append(m)
        floors[f.id] = f
    if not by_floor:
        return []
    order = sorted(by_floor, key=lambda fid: min(m.x for m in by_floor[fid]))
    if len(order) == 1:
        fid = order[0]
        return [{"floor_id": fid, "marker": by_floor[fid][0].text, "region": None}]
    pts = {(m.x, m.y * aspect): fid for fid in order for m in by_floor[fid]}
    frame = box(0.0, 0.0, 1.0, aspect)
    cells = voronoi_diagram(MultiPoint(list(pts)), envelope=frame)
    per_floor: dict[uuid.UUID, list[Polygon]] = defaultdict(list)
    for cell in cells.geoms:
        clipped = cell.intersection(frame)
        if clipped.is_empty:
            continue
        for (x, y), fid in pts.items():
            if cell.contains(Point(x, y)) or cell.touches(Point(x, y)):
                per_floor[fid].append(clipped)
                break
    out: list[dict[str, Any]] = []
    for fid in order:
        shape = unary_union(per_floor.get(fid, []))
        if shape.is_empty or not isinstance(shape, Polygon):
            shape = shape.convex_hull if not shape.is_empty else None
        region = None
        if isinstance(shape, Polygon):
            ring = [
                [round(min(max(x, 0.0), 1.0), 5), round(min(max(y / aspect, 0.0), 1.0), 5)]
                for x, y in shape.exterior.coords[:-1]
            ]
            region = {"ring": ring}
        out.append({"floor_id": fid, "marker": by_floor[fid][0].text, "region": region})
    return out


def region_floor(
    point: tuple[float, float], assignments: list[tuple[uuid.UUID, dict | None]]
) -> uuid.UUID | None:
    """The floor whose region contains a point; a single unrestricted floor takes everything."""
    with_region = [(fid, r) for fid, r in assignments if r and r.get("ring")]
    pt = Point(point)
    for fid, r in with_region:
        try:
            if Polygon(r["ring"]).buffer(1e-9).contains(pt):
                return fid
        except (ValueError, TypeError):
            continue
    whole = [fid for fid, r in assignments if not (r and r.get("ring"))]
    if len(whole) == 1:
        return whole[0]
    return None
