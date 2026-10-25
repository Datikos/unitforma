"""Text on drawings: legacy Georgian CAD fonts and unit labels (plan §13.2 "Labels & codes").

Legacy Georgian fonts
---------------------
Georgian CAD drawings are often lettered in pre-Unicode fonts (AcadNusx, AcadMtavr, LitNusx,
Avaza, Sanet, Grigolia …) that draw Georgian glyphs at Latin code points following the
phonetic keyboard layout, so a PDF text layer says "bina #12" where the sheet shows "ბინა №12".
Characters set in one of those fonts are decoded with that layout; text in Unicode fonts
(Sylfaen, BPG, Arial) is left alone. **[VALIDATE]** the font list and table are the de-facto
AcadNusx layout as observed on the pilot set, where the decoded title blocks, legends and
labels read as correct Georgian ("მრავალბინიანი საცხოვრებელი სახლი", "ქ. თბილისი"); they
are not taken from a published specification.

Unit labels
-----------
A label names one unit: a unit word and a number on the same line ("ბინა №12", "Apt 3B",
"სათავსო 4"), a parking code next to a P mark ("A9/10-1"), or a bare numbered zone with a
printed area ("№30 12.5 m²"). Labels never span lines, so a legend line ending in "… ბინა"
followed by the next item's "6." is not apartment 6, and a number written with "№" wins over
a stray callout digit between the word and it ("ბინა ⑤ №3" is apartment 3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LEGACY_FONT_RE = re.compile(
    r"^(?:[A-Z]{6}\+)?(?:Acad(?:Nusx|Mtavr|Mtavruli)?|Lit(?:Nusx|Mtavr)|Avaza\w*|Sanet\w*"
    r"|Grigolia\w*|Arial_?Geo\w*|Geo_?\w+)",
    re.I,
)

_LEGACY = {
    "a": "ა", "b": "ბ", "g": "გ", "d": "დ", "e": "ე", "v": "ვ", "z": "ზ", "T": "თ",
    "i": "ი", "k": "კ", "l": "ლ", "m": "მ", "n": "ნ", "o": "ო", "p": "პ", "J": "ჟ",
    "r": "რ", "s": "ს", "t": "ტ", "u": "უ", "f": "ფ", "q": "ქ", "R": "ღ", "y": "ყ",
    "S": "შ", "C": "ჩ", "c": "ც", "Z": "ძ", "w": "წ", "W": "ჭ", "x": "ხ", "j": "ჯ",
    "h": "ჰ", "#": "№",
}  # fmt: skip
_LEGACY_TABLE = str.maketrans(_LEGACY)


def is_legacy_font(fontname: str | None) -> bool:
    return bool(fontname) and LEGACY_FONT_RE.match(str(fontname)) is not None


def decode_legacy(text: str) -> str:
    return text.translate(_LEGACY_TABLE)


# --- unit labels ------------------------------------------------------------------------------
UNIT_WORDS: dict[str, str] = {
    "apartment": r"ბინა|bina|apartment|apt\.?|flat|wohnung|квартира",
    "commercial": r"კომერციული|ოფისი|მაღაზია|commercial|retail|shop|office|büro|laden|офис"
    r"|магазин",
    "storage": r"სათავსო|საკუჭნაო|სარდაფი|storage|store\s?room|abstellraum|кладовая|кладовка",
    "parking": r"პარკინგი|ავტოსადგომი|parking|stellplatz|машиноместо|паркинг",
}
NUM = r"[A-Za-z]?\d{1,4}[A-Za-z]?"
SIGN = r"(?:№|#|N|No\.?|no\.?)"
_H = r"[ \t]"  # labels never cross a line break

_STRICT = {
    kind: re.compile(
        rf"(?<!\w)(?:{words})(?!\w){_H}*(?:\S{{1,2}}{_H}+)?{SIGN}{_H}*(?P<num>{NUM})(?![\w.,])",
        re.I,
    )
    for kind, words in UNIT_WORDS.items()
}
_LOOSE = {
    kind: re.compile(rf"(?<!\w)(?:{words})(?!\w){_H}*[:.]?{_H}*(?P<num>{NUM})(?![\w.,/])", re.I)
    for kind, words in UNIT_WORDS.items()
}
_NUMBERED = re.compile(rf"(?<![\w№#])(?:№|#){_H}*(?P<num>{NUM})(?![\w.,/])")
_PARKING_CODE = re.compile(
    r"(?<![\w/.\-])(?P<num>[A-Za-z]{1,3}\d{0,3}(?:/\d{1,3})?-\d{1,4})(?![\w/.\-])"
)
_PARKING_CUE = re.compile(rf"(?<!\w)(?:P|Ⓟ|(?i:{UNIT_WORDS['parking']}))(?!\w)")


@dataclass(frozen=True)
class UnitLabel:
    kind: str | None  # apartment | commercial | storage | parking | None (numbered zone)
    key: str  # comparable key: "12", "3B", "A9/10-1"
    text: str  # as written on the drawing
    start: int
    end: int
    strength: int  # 3 word + №, 2 word + number, 1 parking code / numbered zone


def parking_families(text: str, min_count: int = 3) -> frozenset[str]:
    """Prefixes of parking codes used on a sheet ("A9/10-" for A9/10-1 … A9/10-26).

    A stall whose P mark is hidden (a dimension line running through it) still belongs to
    the family when the sheet shows P marks and at least ``min_count`` codes share the prefix.
    """
    if not _PARKING_CUE.search(text):
        return frozenset()
    counts: dict[str, int] = {}
    for m in _PARKING_CODE.finditer(text):
        prefix = m.group("num").rsplit("-", 1)[0] + "-"
        counts[prefix] = counts.get(prefix, 0) + 1
    return frozenset(p for p, n in counts.items() if n >= min_count)


def find_labels(text: str, families: frozenset[str] = frozenset()) -> list[UnitLabel]:
    """Every unit label in ``text``, strongest first, without overlaps.

    ``families`` are the sheet's parking-code prefixes (``parking_families``).
    """
    found: list[UnitLabel] = []
    for kind, rx in _STRICT.items():
        for m in rx.finditer(text):
            found.append(_label(kind, m, 3))
    for kind, rx in _LOOSE.items():
        for m in rx.finditer(text):
            found.append(_label(kind, m, 2))
    cue = _PARKING_CUE.search(text) is not None
    for m in _PARKING_CODE.finditer(text):
        if cue or m.group("num").rsplit("-", 1)[0] + "-" in families:
            found.append(_label("parking", m, 1))
    for m in _NUMBERED.finditer(text):
        found.append(_label(None, m, 1))
    found.sort(key=lambda lb: (-lb.strength, lb.start))
    out: list[UnitLabel] = []
    for lb in found:
        if any(lb.start < o.end and o.start < lb.end for o in out):
            continue
        out.append(lb)
    return out


def primary_label(text: str, families: frozenset[str] = frozenset()) -> UnitLabel | None:
    labels = find_labels(text, families)
    return labels[0] if labels else None


def label_keys(text: str, kind: str | None = "*") -> set[str]:
    """Keys of the labels in ``text``; ``kind='*'`` for all, else only that kind."""
    return {lb.key for lb in find_labels(text) if kind == "*" or lb.kind == kind}


def _label(kind: str | None, m: re.Match[str], strength: int) -> UnitLabel:
    return UnitLabel(
        kind=kind,
        key=m.group("num").upper(),
        text=m.group(0).strip(),
        start=m.start(),
        end=m.end(),
        strength=strength,
    )
