"""Floor bands on an elevation or section sheet from its level markers (ADR-0014 Decision 1).

The markers were extracted when the sheet was processed (``sheet.hints["level_markers"]``, sheet
space, ``y`` top-down). Each floor's marker line starts its band; the band ends at the next higher
floor's line, and the topmost band at a stacked marker above the highest floor (the roof) or one
median band height up. Floors match by ``elevation_m`` (the tolerance of ADR-0010) or, when no floor
has an elevation and the distinct marker levels equal the floor count, by order.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any

from unitforma.documents.levels import ELEVATION_TOLERANCE_M, Marker

MIN_FLOORS = 2
PAD = 0.03


@dataclass(frozen=True)
class FloorLine:
    level: int
    elevation_m: Any  # Decimal | float | None


@dataclass(frozen=True)
class Band:
    level: int
    y0: float  # top, sheet-normalised
    y1: float  # bottom (the floor's marker line)

    def as_dict(self) -> dict[str, Any]:
        return {"level": self.level, "y0": round(self.y0, 5), "y1": round(self.y1, 5)}


def _lines(markers: list[Marker], floors: list[FloorLine]) -> dict[int, float]:
    """level → y of the floor's marker line (median when the level is printed more than once)."""
    ys: dict[int, list[float]] = {}
    with_elev = [f for f in floors if f.elevation_m is not None]
    if with_elev:
        for f in with_elev:
            e = float(f.elevation_m)
            hits = [m.y for m in markers if abs(m.value - e) <= ELEVATION_TOLERANCE_M]
            if hits:
                ys[f.level] = hits
    else:
        values = sorted({m.value for m in markers})
        if len(values) == len(floors):
            for f, v in zip(sorted(floors, key=lambda x: x.level), values, strict=True):
                ys[f.level] = [m.y for m in markers if m.value == v]
    return {lvl: median(v) for lvl, v in ys.items()}


def bands(markers: list[Marker], floors: list[FloorLine]) -> list[Band] | None:
    """One band per matched floor, lowest first; None when fewer than two floors match."""
    lines = _lines(markers, floors)
    if len(lines) < MIN_FLOORS:
        return None
    order = sorted(lines.items(), key=lambda kv: -kv[1])  # bottom of the sheet first
    out: list[Band] = []
    for i, (level, y) in enumerate(order):
        if i + 1 < len(order):
            out.append(Band(level, order[i + 1][1], y))
    heights = [b.y1 - b.y0 for b in out]
    top_level, top_y = order[-1]
    matched_values = {
        float(f.elevation_m) for f in floors if f.elevation_m is not None and f.level in lines
    }
    above = [
        m.y
        for m in markers
        if m.y < top_y - 1e-6
        and (not matched_values or m.value > max(matched_values) + ELEVATION_TOLERANCE_M)
    ]
    roof_y = max(above) if above else None  # the nearest marker above the top floor line
    top_y0 = roof_y if roof_y is not None else max(0.0, top_y - median(heights))
    out.append(Band(top_level, top_y0, top_y))
    return [b for b in out if b.y1 - b.y0 > 1e-4]


def crop_of(bs: list[Band], pad: float = PAD) -> tuple[float, float, float, float]:
    """Vertical crop of the sheet around the bands; the full width stays (the reviewer sees it)."""
    y0 = max(0.0, min(b.y0 for b in bs) - pad)
    y1 = min(1.0, max(b.y1 for b in bs) + pad)
    return (0.0, round(y0, 4), 1.0, round(y1, 4))
