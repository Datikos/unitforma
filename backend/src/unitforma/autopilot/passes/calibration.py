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


def from_printed_scale(sheet: Sheet) -> dict | None:
    """Metres per raster pixel from the single printed scale and the page size in points."""
    scales = (sheet.hints or {}).get("scales") or []
    if len(scales) != 1 or not sheet.width_pt or not sheet.height_pt:
        return None
    if not sheet.raster_width or not sheet.raster_height:
        return None
    size = suggest.page_metres(
        {"page_pt": [float(sheet.width_pt), float(sheet.height_pt)]}, int(scales[0])
    )
    if not size or size[0] <= 0:
        return None
    cal = geometry.calibration_from_points(
        [0.0, 0.5], [1.0, 0.5], size[0], sheet.raster_width, sheet.raster_height
    )
    cal["source"] = "printed_scale"
    cal["scale"] = int(scales[0])
    return cal


def is_a_persons(sheet: Sheet) -> bool:
    """A calibration a person made with two points (no ``source``): never replaced, and the one
    the sibling pages of the document take (ADR-0029 Decision 3)."""
    return sheet.calibration_status == "calibrated" and (sheet.calibration or {}).get(
        "source"
    ) not in ("printed_scale", "sibling")


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
    await _from_siblings(ctx)


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
