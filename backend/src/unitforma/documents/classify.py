"""Document kind from the file name and from page content (ADR-0008 Decision 1).

Pure functions. ``kind_from_name`` reads Georgian, Latin-transliterated Georgian (what legacy
CAD fonts and lazy file names produce) and English words; ``kind_from_pages`` reads the per-page
hints the worker already writes (``documents.processing.hints_from_text``). Both return ``None``
when unsure, and the document stays ``unclassified`` for the reviewer.
"""

from __future__ import annotations

import re
from typing import Any

# order matters: a "planning permit" is a permit, a "site plan" is not a floor plan
_NAME_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("permit", ("ნებართვ", "ბრძანებ", r"\bpermit", r"\border\b", "nebartv")),
    (
        "site_plan",
        (
            "გენგეგმ",
            "გენერალური გეგმ",
            r"\bsite\s?plan",
            r"\bmaster\s?plan",
            "gengegm",
            "genplan",
            r"\bsitu",
        ),
    ),
    (
        "schedule",
        (
            "ექსპლიკაც",
            "სპეციფიკაც",
            "ცხრილ",
            r"\bschedule",
            r"\bexplicat",
            r"\bspecific",
            r"\barea\s?table",
            r"\bareas\b",
        ),
    ),
    ("section", ("ჭრილ", r"\bsection", "chril", "razrez", r"\bsec\b")),
    ("elevation", ("ფასად", r"\bfacade", r"\belevation", "fasad", r"\bfas\b")),
    (
        "render",
        (
            "რენდერ",
            "ვიზუალ",
            "ფოტომონტაჟ",
            "აქსონომეტრ",
            r"\brender",
            r"\b3d\b",
            r"\bvisual",
            r"\bphotomontage",
            r"\baxonometr",
            r"\bviz\b",
        ),
    ),
    (
        "floor_plan",
        (
            "გეგმ",
            "სართულ",
            r"\bplans?\b",
            r"\bfloor",
            "gegm",
            "sartul",
            r"\betaj",
            r"\bplan_",
            r"\bplan-",
        ),
    ),
)
_RULES = tuple((kind, tuple(re.compile(p, re.I) for p in pats)) for kind, pats in _NAME_RULES)


def kind_from_name(*names: str | None) -> str | None:
    """First rule that matches the title or the file name; ``None`` when nothing does."""
    text = " ".join(n for n in names if n).replace("_", " ").replace("-", " ")
    text = re.sub(r"\.[a-z0-9]{2,4}$", "", text.strip(), flags=re.I)
    if not text:
        return None
    for kind, patterns in _RULES:
        if any(p.search(text) for p in patterns):
            return kind
    return None


def is_plan_page(h: dict[str, Any]) -> bool:
    """A plan page: the per-page kind, or typed unit labels on a page that has line work (the
    worker adds ``vector_lines``); a schedule lists the same labels without lines."""
    return str(h.get("kind") or "") == "floor_plan" or (
        any(kk != "numbered" for kk in (h.get("unit_labels") or {}))
        and int(h.get("vector_lines") or 0) > 0
    )


def kind_from_pages(page_hints: list[dict[str, Any]], mime: str | None = None) -> str | None:
    """A document kind from the processed pages; ``None`` when the pages do not say.

    * at least half of the pages are floor plans (per-page kind, or typed unit labels on a page
      with line work; cover sheets and sections make up the rest) → ``floor_plan``
    * every page is a text sheet and one of them prints areas → ``schedule``
    * a single image without a text layer → ``render``
    """
    hints = [h for h in page_hints if isinstance(h, dict)]
    if not hints:
        return None
    kinds = [str(h.get("kind") or "unknown") for h in hints]
    n = len(kinds)
    plans = sum(1 for h in hints if is_plan_page(h))
    if plans / n >= 0.5:
        return "floor_plan"
    if all(k == "text_sheet" for k in kinds) and any(h.get("area_values") for h in hints):
        return "schedule"
    if (
        mime
        and mime.startswith("image/")
        and n == 1
        and not hints[0].get("has_text_layer")
        and not hints[0].get("apartment_labels")
    ):
        return "render"
    return None
