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


async def run(ctx: Context) -> None:
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
