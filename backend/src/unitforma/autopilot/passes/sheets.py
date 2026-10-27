"""Sheet → floor pass (ADR-0025 Decision 5 "sheet floors"): confirm the suggested floors of a
sheet when there is one, or several that each have a region of the sheet."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from unitforma.autopilot import rules
from unitforma.autopilot.passes.common import current_sheets
from unitforma.autopilot.service import Context, session
from unitforma.documents import assignments
from unitforma.tenants.models import Sheet

STEP = "sheet_floors"


async def run(ctx: Context) -> None:
    async with session(ctx) as db:
        sheets = await current_sheets(db, ctx.project_id)
        by_sheet = await assignments.list_for_sheets(db, [s.id for s, _ in sheets])
        targets: dict[uuid.UUID, tuple[str, list[tuple[uuid.UUID, int, float]]]] = {}
        unsure: dict[uuid.UUID, tuple[str, list[int]]] = {}
        for sheet, doc in sheets:
            assigns = by_sheet.get(sheet.id, [])
            if any(a.status == "confirmed" for a in assigns):
                continue
            sugg = [a for a in assigns if a.status == "suggested"]
            if not sugg:
                continue
            if len(sugg) == 1:
                conf = rules.SHEET_FLOOR_SINGLE
            elif all(a.region and a.region.get("ring") for a in sugg):
                conf = rules.SHEET_FLOOR_REGIONS
            else:
                unsure.setdefault(doc.id, (doc.title, []))[1].append(sheet.page_no)
                continue
            targets.setdefault(doc.id, (doc.title, []))[1].append((sheet.id, sheet.page_no, conf))
    for doc_id, (title, pages) in targets.items():
        done: list[int] = []
        floors = 0
        lowest = 1.0
        async with session(ctx) as db:
            for sheet_id, page_no, conf in pages:
                sheet = (
                    await db.execute(select(Sheet).where(Sheet.id == sheet_id))
                ).scalar_one_or_none()
                if sheet is None:
                    continue
                confirmed = await assignments.confirm_suggestions(db, sheet, "autopilot", ctx.actor)
                if confirmed:
                    done.append(page_no)
                    floors += len(confirmed)
                    lowest = min(lowest, conf)
        if done:
            ctx.decide(
                STEP,
                "accepted",
                f"{title}: {len(done)} page(s) assigned to floors",
                f"{floors} floor assignment(s) confirmed from the level markers; pages "
                + ", ".join(str(p) for p in done[:12])
                + (" …" if len(done) > 12 else ""),
                confidence=lowest,
                entity_type="document",
                entity_id=doc_id,
            )
    for doc_id, (title, pages) in unsure.items():
        ctx.decide(
            STEP,
            "skipped",
            f"{title}: {len(pages)} page(s) show several floors without regions",
            "Confirm the floors of pages " + ", ".join(str(p) for p in pages[:12]) + " by hand",
            needs_you=True,
            entity_type="document",
            entity_id=doc_id,
        )
