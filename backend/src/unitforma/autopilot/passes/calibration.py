"""Calibration pass (ADR-0025 Decision 5 "calibration"): a sheet that prints exactly one scale
("1:100") and has no calibration gets one from its page size. Plan §13.2 lists reading an explicit
scale string as reliable; a reviewer's own calibration is never replaced."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from unitforma.autopilot import rules
from unitforma.autopilot.passes.common import current_sheets
from unitforma.autopilot.service import Context, session
from unitforma.inventory import geometry
from unitforma.inventory import service as inventory
from unitforma.mapping import suggest
from unitforma.tenants.models import Sheet

STEP = "calibration"


def _scale(sheet: Sheet) -> tuple[tuple[float, float], str] | None:
    if not sheet.width_pt or not sheet.height_pt or not sheet.raster_width:
        return None
    if not sheet.raster_height:
        return None
    hints = sheet.hints or {}
    return suggest.scale_metres(
        {"page_pt": [float(sheet.width_pt), float(sheet.height_pt)]},
        hints.get("scales") or [],
        hints.get("dimension_scale"),
    )


def from_printed_scale(sheet: Sheet) -> dict | None:
    """Metres per raster pixel from the single printed scale and the page size in points, when
    the page's dimensions do not contradict it (ADR-0031 Decision 3)."""
    found = _scale(sheet)
    if found is None or found[1] != "printed_scale" or found[0][0] <= 0:
        return None
    cal = geometry.calibration_from_points(
        [0.0, 0.5], [1.0, 0.5], found[0][0], sheet.raster_width, sheet.raster_height
    )
    cal["source"] = "printed_scale"
    cal["scale"] = int((sheet.hints or {})["scales"][0])
    return cal


def from_dimensions(sheet: Sheet) -> dict | None:
    """Metres per raster pixel from the page width the drawing's dimensions give (ADR-0031
    Decision 3), for a sheet that prints no scale, several, or one its dimensions contradict
    (N4 page 11: a ramp's "1:12")."""
    found = _scale(sheet)
    if found is None or found[1] != "dimensions":
        return None
    dim = (sheet.hints or {}).get("dimension_scale") or {}
    cal = geometry.calibration_from_points(
        [0.0, 0.5], [1.0, 0.5], found[0][0], sheet.raster_width, sheet.raster_height
    )
    cal["source"] = "dimensions"
    cal["dimension_unit"] = dim.get("unit")
    cal["dimensions_agreeing"] = dim.get("agree")
    if len((sheet.hints or {}).get("scales") or []) == 1:
        cal["printed_scale_ignored"] = int(sheet.hints["scales"][0])
    return cal


def is_a_persons(sheet: Sheet) -> bool:
    """A calibration a person made with two points (no ``source``): never replaced, and the one
    the sibling pages of the document take (ADR-0029 Decision 3)."""
    return sheet.calibration_status == "calibrated" and (sheet.calibration or {}).get(
        "source"
    ) not in ("printed_scale", "sibling", "dimensions")


def same_page_size(a: Sheet, b: Sheet) -> bool:
    tol = rules.CALIBRATION_PAGE_SIZE_TOLERANCE_PT
    try:
        return (
            abs(float(a.width_pt) - float(b.width_pt)) <= tol
            and abs(float(a.height_pt) - float(b.height_pt)) <= tol
        )
    except (TypeError, ValueError):
        return False


def from_sibling(sheet: Sheet, source: Sheet) -> dict | None:
    """The source sheet's calibration carried to a sibling of the same page size: metres per
    pixel scaled when the rasters differ in width."""
    if not sheet.raster_width or not sheet.raster_height or not source.raster_width:
        return None
    cal = dict(source.calibration or {})
    if not cal.get("m_per_px"):
        return None
    cal["m_per_px"] = (
        float(cal["m_per_px"]) * float(source.raster_width) / float(sheet.raster_width)
    )
    cal["raster_width"], cal["raster_height"] = sheet.raster_width, sheet.raster_height
    cal["source"] = "sibling"
    cal["from_sheet_id"] = str(source.id)
    return cal


async def run(ctx: Context) -> None:
    await _from_printed_scales(ctx)
    await _from_dimensions(ctx)
    await _from_siblings(ctx)


async def _from_dimensions(ctx: Context) -> None:
    """Pages without a printed scale, each from its own dimensions, before a person's sibling
    calibration is copied: an "NTS" set is scaled per page (N4: 107.6 to 112.0 m across five
    pages of one size), so a sibling's scale would be a few per cent off."""
    async with session(ctx) as db:
        by_doc: dict[uuid.UUID, tuple[str, list[tuple[int, float]]]] = {}
        for sheet, doc in await current_sheets(db, ctx.project_id):
            if sheet.calibration_status != "none" or doc.kind not in ("floor_plan", "site_plan"):
                continue
            cal = from_dimensions(sheet)
            if cal is None:
                continue
            await inventory.recalibrate_sheet(db, sheet, cal)
            by_doc.setdefault(doc.id, (doc.title, []))[1].append(
                (sheet.page_no, cal["dimensions_agreeing"] or 0)
            )
    for doc_id, (title, pages) in by_doc.items():
        ctx.decide(
            STEP,
            "accepted",
            f"{title}: {len(pages)} page(s) calibrated from their dimensions",
            "No printed scale, or one the dimensions contradict; each page's dimension strings "
            "agree on its width (at least "
            f"{min(n for _, n in pages)} dimensions per page); pages "
            + ", ".join(str(p) for p, _ in pages[:12])
            + (" …" if len(pages) > 12 else ""),
            confidence=rules.CALIBRATION_DIMENSIONS_CONFIDENCE,
            entity_type="document",
            entity_id=doc_id,
        )


async def _from_siblings(ctx: Context) -> None:
    async with session(ctx) as db:
        by_doc: dict[uuid.UUID, tuple[str, list[Sheet]]] = {}
        for sheet, doc in await current_sheets(db, ctx.project_id):
            if doc.kind in ("floor_plan", "site_plan"):
                by_doc.setdefault(doc.id, (doc.title, []))[1].append(sheet)
        for doc_id, (title, sheets) in by_doc.items():
            sources = [s for s in sheets if is_a_persons(s)]
            if not sources:
                continue
            source = sources[0]
            done: list[int] = []
            other_size: list[int] = []
            for sheet in sheets:
                if sheet.calibration_status != "none" or from_printed_scale(sheet) is not None:
                    continue
                if not same_page_size(sheet, source):
                    other_size.append(sheet.page_no)
                    continue
                cal = from_sibling(sheet, source)
                if cal is None:
                    continue
                await inventory.recalibrate_sheet(db, sheet, cal)
                done.append(sheet.page_no)
            if done:
                ctx.decide(
                    STEP,
                    "accepted",
                    f"{title}: {len(done)} page(s) calibrated like page {source.page_no}",
                    "Your calibration of one page serves every page of the same size: pages "
                    + ", ".join(str(p) for p in done[:12])
                    + (" …" if len(done) > 12 else ""),
                    confidence=rules.CALIBRATION_SIBLING_CONFIDENCE,
                    entity_type="document",
                    entity_id=doc_id,
                    entity_ids=[s.id for s in sheets if s.page_no in done],
                )
            if other_size:
                ctx.decide(
                    STEP,
                    "skipped",
                    f"{title}: {len(other_size)} page(s) of another size need you",
                    "Calibrate one of them with two points; the rest of that size follow: pages "
                    + ", ".join(str(p) for p in other_size[:12]),
                    needs_you=True,
                    entity_type="document",
                    entity_id=doc_id,
                )


async def _from_printed_scales(ctx: Context) -> None:
    async with session(ctx) as db:
        targets: dict[uuid.UUID, tuple[str, list[tuple[uuid.UUID, int]]]] = {}
        for sheet, doc in await current_sheets(db, ctx.project_id):
            if sheet.calibration_status != "none" or doc.kind not in ("floor_plan", "site_plan"):
                continue
            if from_printed_scale(sheet) is None:
                continue
            targets.setdefault(doc.id, (doc.title, []))[1].append((sheet.id, sheet.page_no))
    for doc_id, (title, pages) in targets.items():
        done: list[int] = []
        scale = None
        async with session(ctx) as db:
            for sheet_id, page_no in pages:
                sheet = (
                    await db.execute(select(Sheet).where(Sheet.id == sheet_id))
                ).scalar_one_or_none()
                if sheet is None or sheet.calibration_status != "none":
                    continue
                cal = from_printed_scale(sheet)
                if cal is None:
                    continue
                await inventory.recalibrate_sheet(db, sheet, cal)
                scale = cal["scale"]
                done.append(page_no)
        if done:
            ctx.decide(
                STEP,
                "accepted",
                f"{title}: {len(done)} page(s) calibrated",
                f"Scale from the printed 1:{scale} and the page size; pages "
                + ", ".join(str(p) for p in done[:12])
                + (" …" if len(done) > 12 else ""),
                confidence=rules.CALIBRATION_CONFIDENCE,
                entity_type="document",
                entity_id=doc_id,
            )
