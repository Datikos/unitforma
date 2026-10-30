"""Text on the preview raster of a DXF sheet (ADR-0006 #E2).

Pillow's default font has no Georgian glyphs, and Pillow (without libraqm, as in our images)
does no font fallback, so a label is split into runs by script and each run is drawn with a
font that has it: Noto Sans Georgian for the three Georgian blocks, Noto Sans for everything
else (digits, Latin, №, ², ±, −, ×; Noto Sans Georgian lacks ² ± − ×). Both fonts ship in
``fonts/`` under the SIL Open Font License 1.1; versions and checksums are in ADR-0006 #E2.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

FONT_DIR = Path(__file__).parent / "fonts"
GEORGIAN_FONT = FONT_DIR / "NotoSansGeorgian-Regular.ttf"
OTHER_FONT = FONT_DIR / "NotoSans-Regular.ttf"

# Mkhedruli and Asomtavruli/Nuskhuri, Mtavruli, Nuskhuri supplement
GEORGIAN_BLOCKS = ((0x10A0, 0x10FF), (0x1C90, 0x1CBF), (0x2D00, 0x2D2F))


def is_georgian(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in GEORGIAN_BLOCKS)


def script_runs(text: str) -> list[tuple[bool, str]]:
    """``text`` cut into consecutive runs of (is_georgian, run); the runs join back to it."""
    runs: list[tuple[bool, str]] = []
    for ch in text:
        geo = is_georgian(ch)
        if runs and runs[-1][0] == geo:
            runs[-1] = (geo, runs[-1][1] + ch)
        else:
            runs.append((geo, ch))
    return runs


@lru_cache(maxsize=128)
def font(georgian: bool, px: int) -> Any:
    """The font for a run at ``px`` pixels per em; cached, one file open per size."""
    from PIL import ImageFont

    return ImageFont.truetype(str(GEORGIAN_FONT if georgian else OTHER_FONT), px)


def draw_label(draw: Any, xy: tuple[float, float], text: str, px: int, fill: Any) -> None:
    """Draw ``text`` left to right from ``xy`` (top left at the ascender), run by run."""
    x, y = xy
    for georgian, run in script_runs(text):
        f = font(georgian, px)
        draw.text((x, y), run, fill=fill, font=f, anchor="la")
        x += f.getlength(run)
