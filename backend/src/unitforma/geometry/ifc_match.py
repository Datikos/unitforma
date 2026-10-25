"""Match IFC storeys to floors and IFC spaces to units (ADR-0006 Decision 4). Pure functions.

A space is matched by its storey first, then by the apartment label in its name ("ბინა №12",
"Apt 3B", a bare "12"); the reviewer confirms every link, so the output is a suggestion with a
confidence, never a decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from unitforma.documents import labels

STOREY_TOLERANCE_M = 0.3
CONF_LABEL = 0.9
CONF_AMBIGUOUS = 0.5
CONF_ONLY_ONE = 0.6


@dataclass(frozen=True)
class FloorRef:
    id: Any
    level: int
    elevation_m: float | None


@dataclass(frozen=True)
class UnitRef:
    id: Any
    code: str
    floor_id: Any
    label: str | None


@dataclass(frozen=True)
class SpaceRef:
    global_id: str
    name: str | None
    long_name: str | None
    storey_index: int | None
    storey_elevation_m: float | None


@dataclass
class Match:
    global_id: str
    floor_id: Any | None
    unit_id: Any | None
    confidence: float | None
    status: str  # suggested | unmatched


def _keys(text: str | None) -> set[str]:
    """Unit label keys in a text: typed labels first, else bare numbers."""
    if not text:
        return set()
    found = labels.label_keys(text)
    if found:
        return {k.upper() for k in found}
    return {m.group(1) for m in re.finditer(r"(?<![\w.])(\d{1,4}[A-Za-z]?)(?![\w.])", text)}


def match_floors(
    storeys: list[tuple[int, float | None]], floors: list[FloorRef]
) -> dict[int, Any | None]:
    """Storey index → floor id: by elevation within 0.3 m, else by order when counts agree."""
    out: dict[int, Any | None] = {}
    by_elev = [f for f in floors if f.elevation_m is not None]
    for idx, elev in storeys:
        hit = None
        if elev is not None and by_elev:
            best = min(by_elev, key=lambda f: abs(float(f.elevation_m) - elev))  # type: ignore[arg-type]
            if abs(float(best.elevation_m) - elev) <= STOREY_TOLERANCE_M:  # type: ignore[arg-type]
                hit = best.id
        out[idx] = hit
    if any(v is None for v in out.values()) and len(storeys) == len(floors):
        ordered = sorted(floors, key=lambda f: f.level)
        for (idx, _), f in zip(sorted(storeys, key=lambda s: s[0]), ordered, strict=True):
            out.setdefault(idx, None)
            if out[idx] is None:
                out[idx] = f.id
    return out


def match_spaces(
    spaces: list[SpaceRef], floors: list[FloorRef], units: list[UnitRef]
) -> list[Match]:
    storeys = sorted(
        {(s.storey_index, s.storey_elevation_m) for s in spaces if s.storey_index is not None}
    )
    floor_of_storey = match_floors([(i, e) for i, e in storeys], floors)
    unit_keys = {u.id: _keys(u.label) | _keys(u.code.rsplit("-", 1)[-1]) for u in units}
    taken: set[Any] = set()
    out: list[Match] = []
    pending: list[tuple[SpaceRef, Any]] = []
    for sp in spaces:
        floor_id = floor_of_storey.get(sp.storey_index) if sp.storey_index is not None else None
        if floor_id is None:
            out.append(Match(sp.global_id, None, None, None, "unmatched"))
            continue
        keys = _keys(f"{sp.name or ''} {sp.long_name or ''}")
        candidates = [
            u
            for u in units
            if u.floor_id == floor_id and u.id not in taken and keys & unit_keys[u.id]
        ]
        if len(candidates) == 1:
            taken.add(candidates[0].id)
            out.append(Match(sp.global_id, floor_id, candidates[0].id, CONF_LABEL, "suggested"))
        elif candidates:
            out.append(Match(sp.global_id, floor_id, candidates[0].id, CONF_AMBIGUOUS, "suggested"))
        else:
            pending.append((sp, floor_id))
    # a floor with exactly one space and one unit left: pair them
    for sp, floor_id in pending:
        left_units = [u for u in units if u.floor_id == floor_id and u.id not in taken]
        left_spaces = [p for p, fl in pending if fl == floor_id]
        if len(left_units) == 1 and len(left_spaces) == 1:
            taken.add(left_units[0].id)
            out.append(Match(sp.global_id, floor_id, left_units[0].id, CONF_ONLY_ONE, "suggested"))
        else:
            out.append(Match(sp.global_id, floor_id, None, None, "unmatched"))
    return out
