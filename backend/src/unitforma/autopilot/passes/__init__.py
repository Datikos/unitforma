"""The passes of a solver run, in data-flow order (ADR-0025 Decision 5): what a later pass needs
is produced by an earlier one (floors before sheet floors, calibration before outlines, outlines
before layouts and placement, the site frame before placement and facades)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from unitforma.autopilot.passes import (
    calibration,
    classify,
    facades,
    floors,
    gallery,
    geocode,
    layouts,
    outlines,
    placement,
    sheets,
    site,
)
from unitforma.autopilot.service import Context

PASSES: list[tuple[str, Callable[[Context], Awaitable[None]]]] = [
    ("classify", classify.run),
    ("floors", floors.run),
    ("calibration", calibration.run),
    ("sheet_floors", sheets.run),
    ("mapping", outlines.run),
    ("site_plan", site.run),
    ("placement", placement.run),
    ("facades", facades.run),
    ("gallery", gallery.run),
    ("location", geocode.run),
    ("layouts", layouts.run),
]
