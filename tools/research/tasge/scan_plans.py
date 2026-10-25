#!/usr/bin/env python3
"""Inventory an architectural PDF set (floor plans) for the Unitforma mapping workflow.

    python3 scan_plans.py plans.pdf [--out scan.json] [--render-dir ./png --dpi 40]

Requires: pdfplumber (MIT), optionally pypdfium2 (Apache-2.0/BSD-3) for page renders.
For every page it reports size, vector density (lines/curves/rects), text-layer presence,
candidate floor-plan markers (apartment labels such as "ბინა №12 61.0 m²", parking labels such
as "A9/10-24 12.5 m²"), level markers ("+3.20 (652.2)"), drawing scales ("1:100") and grid axes.
It never produces geometry: it tells the reviewer which pages are worth mapping and how much the
automated proposals (plan §13.2) can rely on the vector content.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    print("pip install pdfplumber", file=sys.stderr)
    raise

APARTMENT = re.compile(r"ბინა\s*№?\s*(\d+)\s*([\d.,]+)\s*m\s*[²2]", re.I)  # "ბინა №32 42.7 m²"
# Georgian text in legacy CAD fonts often surfaces as Latin transliteration ("bina N32").
APARTMENT_TRANSLIT = re.compile(r"\bbina\s*(?:#|N|№)?\s*(\d{1,3})\b", re.I)  # "bina #32"
PARKING = re.compile(r"\b([A-Z]\d{1,2}/\d{1,2}-\d{1,3})\b")  # "A9/10-24"
AREA = re.compile(r"(\d{1,4}[.,]\d)\s*m\s*[²2]")
LEVEL = re.compile(r"([+-]\d{1,2}\.\d{2})\s*\(?\s*(\d{3}\.\d{1,2})?\)?")  # "+3.20 (652.2)"
SCALE = re.compile(r"(?:\b|m\.?\s*)1\s*[:/]\s*(\d{2,4})\b")  # "1:100" or "m.1/100"
GRID_AXIS = re.compile(r"^(?:[A-Z]|[1-9]\d?)'?$")


def scan(pdf_path: Path, render_dir: Path | None = None, dpi: int = 40) -> dict:
    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for idx, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            words = [w["text"] for w in page.extract_words()]
            apartments = {m.group(1): m.group(2) for m in APARTMENT.finditer(text)}
            apartments_translit = sorted(set(APARTMENT_TRANSLIT.findall(text)))
            parking = sorted(set(PARKING.findall(text)))
            areas = AREA.findall(text)
            levels = sorted({m.group(1) for m in LEVEL.finditer(text)})
            scales = sorted({m.group(1) for m in SCALE.finditer(text)})
            axes = sorted({w for w in words if GRID_AXIS.match(w)})
            vec = len(page.lines) + len(page.curves) + len(page.rects)
            kind = "unknown"
            if apartments or apartments_translit:
                kind = "floor_plan"
            elif parking:
                kind = "parking_plan"
            elif vec == 0 and len(page.chars) > 500:
                kind = "text_sheet"
            elif len(page.images) and vec < 50:
                kind = "raster_sheet"
            elif vec > 2000:
                kind = "drawing"
            pages.append(
                {
                    "page": idx,
                    "width_pt": round(page.width),
                    "height_pt": round(page.height),
                    "vector_objects": vec,
                    "chars": len(page.chars),
                    "images": len(page.images),
                    "kind": kind,
                    "scales": scales,
                    "levels": levels[:6],
                    "grid_axes": axes[:30],
                    "apartments": apartments,
                    "apartments_translit": apartments_translit,
                    "parking": parking,
                    "area_strings": len(areas),
                }
            )
            if render_dir and kind in ("floor_plan", "parking_plan"):
                try:
                    import pypdfium2 as pdfium

                    render_dir.mkdir(parents=True, exist_ok=True)
                    doc = pdfium.PdfDocument(str(pdf_path))
                    doc[idx - 1].render(scale=dpi / 72).to_pil().save(
                        render_dir / f"page_{idx:03d}.png"
                    )
                except ImportError:
                    pass
    summary = {
        "file": pdf_path.name,
        "pages": len(pages),
        "floor_plan_pages": [p["page"] for p in pages if p["kind"] == "floor_plan"],
        "parking_pages": [p["page"] for p in pages if p["kind"] == "parking_plan"],
        "has_text_layer": any(p["chars"] > 0 for p in pages),
        "is_vector": sum(p["vector_objects"] for p in pages) > 0,
        "apartment_numbers": sorted(
            {int(k) for p in pages for k in list(p["apartments"]) + p["apartments_translit"]}
        ),
        "apartment_count": len(
            {k for p in pages for k in list(p["apartments"]) + p["apartments_translit"]}
        ),
    }
    return {"summary": summary, "pages": pages}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--render-dir", type=Path)
    ap.add_argument("--dpi", type=int, default=40)
    args = ap.parse_args(argv)
    result = scan(args.pdf, args.render_dir, args.dpi)
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if args.out:
        args.out.write_text(text)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
