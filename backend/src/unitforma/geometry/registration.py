"""Registering a building's floor sheets to each other on the drawing's grid axes (ADR-0030 #D2).

Each floor plan sheet has its own origin, so outlines in sheet metres stack with a stagger. The
architect's structural grid is the same on every floor: a label in a bubble at both ends of each
axis. Pairing the two bubbles of a label gives the axis' x (vertical) or y (horizontal); the
median difference over the axes two sheets share is the shift from one to the other. Pure: the
solver pass (`autopilot.passes.registration`) feeds it the extract's words in sheet metres.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

# two bubbles of one axis share x (or y) within this, in metres
AXIS_ALIGN_M = 0.3
# and lie at least this far apart (a plan's axes cross the building)
AXIS_MIN_LENGTH_M = 15.0
# a bubble counts only this close to the floor's outlines (not a title block, not another block)
AXIS_NEAR_M = 15.0
# a registration needs this many shared axes in each direction
AXIS_MIN_SHARED = 2
# and the shifts over them may differ by at most this
AXIS_MAX_SPREAD_M = 0.3

Bounds = tuple[float, float, float, float]


@dataclass
class Grid:
    """Axis positions in sheet metres by label: x of the vertical axes, y of the horizontal ones."""

    vertical: dict[str, float] = field(default_factory=dict)
    horizontal: dict[str, float] = field(default_factory=dict)


def is_axis_label(text: str) -> bool:
    """Up to two digits, or one capital Latin letter or one Georgian letter (no case)."""
    if text.isdigit():
        return len(text) <= 2
    if len(text) != 1 or not text.isalpha():
        return False
    return text.isupper() or "ა" <= text <= "ჿ"


def grid_axes(words: list[dict[str, Any]], width_m: float, height_m: float, near: Bounds) -> Grid:
    """The grid of one sheet from its extract words (normalised boxes) and its size in metres;
    only bubbles within ``AXIS_NEAR_M`` of ``near`` (the floor's outlines) count."""
    x0, y0, x1, y1 = near
    bubbles: dict[str, list[tuple[float, float]]] = {}
    for w in words:
        t = str(w.get("t", "")).strip()
        if not is_axis_label(t):
            continue
        cx = (w["x0"] + w["x1"]) / 2 * width_m
        cy = (w["y0"] + w["y1"]) / 2 * height_m
        near_x = x0 - AXIS_NEAR_M <= cx <= x1 + AXIS_NEAR_M
        if near_x and y0 - AXIS_NEAR_M <= cy <= y1 + AXIS_NEAR_M:
            bubbles.setdefault(t, []).append((cx, cy))
    grid = Grid()
    for label, pts in bubbles.items():
        vertical: list[float] = []
        horizontal: list[float] = []
        for i, (ax, ay) in enumerate(pts):
            for bx, by in pts[i + 1 :]:
                if abs(ax - bx) <= AXIS_ALIGN_M and abs(ay - by) >= AXIS_MIN_LENGTH_M:
                    vertical.append((ax + bx) / 2)
                if abs(ay - by) <= AXIS_ALIGN_M and abs(ax - bx) >= AXIS_MIN_LENGTH_M:
                    horizontal.append((ay + by) / 2)
        # a label with two pairs is ambiguous (two blocks, a repeated note): neither counts
        if len(vertical) == 1 and not horizontal:
            grid.vertical[label] = vertical[0]
        if len(horizontal) == 1 and not vertical:
            grid.horizontal[label] = horizontal[0]
    return grid


def register(ref: Grid, grid: Grid) -> dict[str, Any]:
    """The shift that moves ``grid``'s sheet onto ``ref``'s, or why there is none.

    Returns ``{"method": "grid_axes", "dx_m", "dy_m", "axes": [v, h], "spread_m"}`` or
    ``{"method": "none", "axes": [v, h], "reason"}``."""
    vs = [ref.vertical[k] - grid.vertical[k] for k in grid.vertical if k in ref.vertical]
    hs = [ref.horizontal[k] - grid.horizontal[k] for k in grid.horizontal if k in ref.horizontal]
    axes = [len(vs), len(hs)]
    if len(vs) < AXIS_MIN_SHARED or len(hs) < AXIS_MIN_SHARED:
        return {
            "method": "none",
            "axes": axes,
            "reason": f"{len(vs)} vertical and {len(hs)} horizontal grid axes in common with the "
            f"reference floor's sheet; {AXIS_MIN_SHARED} of each are needed",
        }
    spread = max(max(vs) - min(vs), max(hs) - min(hs))
    if spread > AXIS_MAX_SPREAD_M:
        return {
            "method": "none",
            "axes": axes,
            "reason": f"the shared grid axes disagree by {spread:.2f} m (at most "
            f"{AXIS_MAX_SPREAD_M} m): a different grid or a different scale",
        }
    return {
        "method": "grid_axes",
        "dx_m": round(statistics.median(vs), 3),
        "dy_m": round(statistics.median(hs), 3),
        "axes": axes,
        "spread_m": round(spread, 3),
    }
