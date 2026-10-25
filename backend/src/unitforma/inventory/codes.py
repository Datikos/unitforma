"""Readable unit codes from the project's pattern (plan §5.4)."""

from __future__ import annotations

import re

PLACEHOLDER_RE = re.compile(r"\{(building|floor|seq)(?::(\d+))?\}")


def render_code(pattern: str, *, building: str, floor: int, seq: int) -> str:
    """``{building}-{floor:02}-{seq:02}`` → ``A-02-03``. Negative floors render as ``B1``."""

    def repl(m: re.Match[str]) -> str:
        name, width = m.group(1), m.group(2)
        if name == "building":
            return building
        if name == "floor":
            if floor < 0:
                return f"B{-floor}"
            return f"{floor:0{int(width)}d}" if width else str(floor)
        return f"{seq:0{int(width)}d}" if width else str(seq)

    return PLACEHOLDER_RE.sub(repl, pattern)


def normalise_code(code: str) -> str:
    code = code.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9./-]{0,39}", code):
        raise ValueError("code may contain letters, digits, '.', '/', '-' (max 40)")
    return code
