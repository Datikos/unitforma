"""Storeys from level markers (ADR-0010 Decisions 2 to 4). Pure functions.

Input: the cleaned level markers of each sheet (``sheets.hints.level_markers``) and the
building's existing floors. Output: proposed floors with level number, name, elevation, height
and how they relate to what exists.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from typing import Any

from unitforma.documents import levels

STOREY_TOLERANCE_M = 0.25  # markers closer than this are the same storey
GROUND_WINDOW_M = 0.5  # a storey this close to 0.00 is the ground floor
EXISTING_TOLERANCE_M = 0.05  # a storey this close to an existing floor is that floor
DEFAULT_HEIGHT_M = 3.0


@dataclass
class ExistingFloor:
    id: Any
    level: int
    display_name: str
    elevation_m: float | None
    height_m: float | None


@dataclass
class ProposedFloor:
    level: int
    display_name: str
    elevation_m: float
    height_m: float | None
    status: str  # new | update | existing
    floor_id: Any = None
    sheets: int = 0  # sheets that print this storey
    markers: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["floor_id"] = str(self.floor_id) if self.floor_id else None
        return d


@dataclass
class _Storey:
    values: list[float]
    texts: list[str]
    sheets: set[Any]
    plan_sheets: set[Any]

    @property
    def elevation(self) -> float:
        return round(statistics.median(self.values), 2)


def _cluster(markers: list[tuple[Any, levels.Marker, bool]]) -> list[_Storey]:
    storeys: list[_Storey] = []
    for sheet_id, m, stacked in sorted(markers, key=lambda t: t[1].value):
        if storeys and abs(m.value - storeys[-1].elevation) <= STOREY_TOLERANCE_M:
            s = storeys[-1]
            s.values.append(m.value)
            s.texts.append(m.text)
        else:
            s = _Storey([m.value], [m.text], set(), set())
            storeys.append(s)
        s.sheets.add(sheet_id)
        if not stacked:
            s.plan_sheets.add(sheet_id)
    return storeys


def display_name(level: int) -> str:
    return "Ground" if level == 0 else (f"B{-level}" if level < 0 else str(level))


def propose(
    markers_by_sheet: dict[Any, list[levels.Marker]],
    existing: list[ExistingFloor],
) -> tuple[list[ProposedFloor], list[ExistingFloor], dict[str, Any]]:
    """(proposed floors low to high, existing floors with no storey, info about the roof).

    A storey needs a plan sheet; one seen only on stacked sheets (sections, elevations) is the roof
    when it is the topmost and gives the last floor its height, otherwise it is dropped.
    """
    flat: list[tuple[Any, levels.Marker, bool]] = []
    for sheet_id, ms in markers_by_sheet.items():
        stacked = levels.is_stacked(ms)
        flat.extend((sheet_id, m, stacked) for m in ms)
    if not flat:
        return [], list(existing), {}
    storeys = _cluster(flat)
    floors = [s for s in storeys if s.plan_sheets]
    roof: dict[str, Any] = {}
    section_only = [s for s in storeys if not s.plan_sheets]
    if floors and section_only:
        top = max(section_only, key=lambda s: s.elevation)
        if top.elevation > floors[-1].elevation:
            roof = {"elevation_m": top.elevation, "sheets": len(top.sheets)}
    if not floors:
        return [], list(existing), roof
    # heights: difference to the next storey; the top floor takes the roof or the median
    elevations = [s.elevation for s in floors]
    heights: list[float | None] = [
        round(elevations[i + 1] - elevations[i], 2) for i in range(len(elevations) - 1)
    ]
    if roof:
        heights.append(round(roof["elevation_m"] - elevations[-1], 2))
    elif heights:
        heights.append(round(statistics.median(h for h in heights if h), 2))
    else:
        heights.append(DEFAULT_HEIGHT_M)
    # numbering: ground = nearest 0.00 within the window, else the lowest at or above zero
    near = [i for i, e in enumerate(elevations) if abs(e) <= GROUND_WINDOW_M]
    if near:
        ground = min(near, key=lambda i: abs(elevations[i]))
    else:
        above = [i for i, e in enumerate(elevations) if e >= 0]
        ground = above[0] if above else len(elevations) - 1
    out: list[ProposedFloor] = []
    matched: set[Any] = set()
    for i, s in enumerate(floors):
        level = i - ground
        name, status, floor_id, height = display_name(level), "new", None, heights[i]
        hit = next(
            (
                f
                for f in existing
                if f.elevation_m is not None
                and abs(float(f.elevation_m) - s.elevation) <= EXISTING_TOLERANCE_M
            ),
            None,
        )
        if hit is None:
            hit = next((f for f in existing if f.elevation_m is None and f.level == level), None)
            if hit is not None:
                status = "update"
        else:
            status = "existing"
        if hit is not None:
            matched.add(hit.id)
            level, name, floor_id = hit.level, hit.display_name, hit.id
            if hit.height_m is not None:
                height = float(hit.height_m)
        out.append(
            ProposedFloor(
                level=level,
                display_name=name,
                elevation_m=s.elevation,
                height_m=height,
                status=status,
                floor_id=floor_id,
                sheets=len(s.sheets),
                markers=sorted(set(s.texts))[:6],
            )
        )
    # two storeys may have landed on one existing level (unlikely); keep levels unique
    seen: set[int] = set()
    for p in out:
        while p.level in seen:
            p.level += 1
            p.display_name = display_name(p.level)
        seen.add(p.level)
    unmatched = [f for f in existing if f.id not in matched]
    return out, unmatched, roof


# --------------------------------------------------------------------------- blocks (ADR-0013)
COLUMN_TOLERANCE = 0.12  # normalised sheet width: markers this close sit over the same block
MIN_BLOCK_SHEETS = 2
BLOCK_LETTERS = "ABCDEFGH"


@dataclass
class Block:
    code: str
    column_x: float
    sheets: int
    floors: list[ProposedFloor]
    roof: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "column_x": self.column_x,
            "sheets": self.sheets,
            "floors": [f.as_dict() for f in self.floors],
            "roof": self.roof,
        }


def detect_blocks(
    markers_by_sheet: dict[Any, list[levels.Marker]],
    *,
    taken_codes: frozenset[str] = frozenset(),
    source_code: str | None = None,
) -> list[Block]:
    """Split-level blocks drawn side by side: columns of markers across the plan sheets.

    Plan sheets with two or more markers at distinct horizontal positions vote; the markers of
    all such sheets are clustered by ``x``; a column seen on at least two sheets is a block. Each
    block's storeys come from its own column only: a section stacks every block's levels, so the
    other blocks' storeys would pass for this block's roof. Fewer than two blocks → an empty list,
    and the single-building proposal stands.
    """
    plan: dict[Any, list[levels.Marker]] = {}
    for sheet_id, ms in markers_by_sheet.items():
        if ms and not levels.is_stacked(ms):
            plan[sheet_id] = ms
    multi = {
        sid: ms
        for sid, ms in plan.items()
        if len(ms) >= 2 and max(m.x for m in ms) - min(m.x for m in ms) > COLUMN_TOLERANCE
    }
    if len(multi) < MIN_BLOCK_SHEETS:
        return []
    points = sorted(((m.x, sid, m) for sid, ms in multi.items() for m in ms), key=lambda t: t[0])
    columns: list[dict[str, Any]] = []
    for x, sid, m in points:
        if columns and abs(x - columns[-1]["x"]) <= COLUMN_TOLERANCE:
            col = columns[-1]
        else:
            col = {"x": x, "xs": [], "markers": {}}
            columns.append(col)
        col["xs"].append(x)
        col["x"] = statistics.median(col["xs"])
        col["markers"].setdefault(sid, []).append(m)
    columns = [c for c in columns if len(c["markers"]) >= MIN_BLOCK_SHEETS]
    if len(columns) < 2:
        return []
    out: list[Block] = []
    for i, col in enumerate(columns):
        floors, _unmatched, roof = propose(dict(col["markers"]), [])
        if not floors:
            continue
        letter = BLOCK_LETTERS[i] if i < len(BLOCK_LETTERS) else str(i + 1)
        code = letter
        if code in taken_codes:
            code = f"{(source_code or 'B')[:16]}-{letter}"
        out.append(
            Block(
                code=code,
                column_x=round(float(col["x"]), 3),
                sheets=len(col["markers"]),
                floors=floors,
                roof=roof,
            )
        )
    return out if len(out) >= 2 else []
