"""Outlines pass (ADR-0025 Decision 5 "outlines" and "approve"): on every sheet with confirmed
floors and no boundary drawn by a person, the candidates at or above the threshold become draft
units; when the person asked for it and every printed label is covered, the sheet is approved.

Below the threshold (grown faces at 0.7, bare numbers at 0.65) and ambiguous labels (one key on
two zones) stay candidates in the sheet editor and are listed as "needs you"."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from shapely.geometry import Polygon
from sqlalchemy import select

from unitforma.autopilot import rules
from unitforma.autopilot.passes.common import current_sheets, page_label
from unitforma.autopilot.service import Context, session
from unitforma.core.errors import ProblemError
from unitforma.documents import assignments
from unitforma.geometry import service as geometry_service
from unitforma.inventory import service as inventory
from unitforma.mapping import service as mapping
from unitforma.mapping import suggest
from unitforma.projects import service as projects
from unitforma.tenants.models import Sheet, Unit, UnitBoundary

STEP = "mapping"
SOURCE = "autopilot"


@dataclass
class SheetOutcome:
    created: int = 0
    lowest: float = 1.0
    skipped_low: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    covered: bool = False  # every labelled candidate has a boundary now
    approved: int = 0


async def run(ctx: Context) -> None:
    async with session(ctx) as db:
        sheets = await current_sheets(db, ctx.project_id, kinds=("floor_plan",))
        by_sheet = await assignments.list_for_sheets(db, [s.id for s, _ in sheets])
        targets = [
            (sheet.id, page_label(doc, sheet))
            for sheet, doc in sheets
            if sheet.raster_key and any(a.status == "confirmed" for a in by_sheet.get(sheet.id, []))
        ]
    massing = False
    for sheet_id, label in targets:
        outcome = await _one(ctx, sheet_id, label)
        if outcome is None:
            continue
        if outcome.created or outcome.approved:
            massing = True
        _record(ctx, sheet_id, label, outcome)
    if massing:
        await geometry_service.queue_massing(ctx.tenant_id, ctx.project_id)


def _record(ctx: Context, sheet_id: uuid.UUID, label: str, o: SheetOutcome) -> None:
    if o.created:
        ctx.decide(
            STEP,
            "accepted",
            f"{label}: {o.created} unit(s) outlined",
            "Outlines from the drawing's filled zones and labelled rooms"
            + (f"; {o.approved} approved and active" if o.approved else " as drafts"),
            confidence=o.lowest,
            entity_type="sheet",
            entity_id=sheet_id,
            sheet_id=sheet_id,
        )
    elif o.approved:
        ctx.decide(
            STEP,
            "accepted",
            f"{label}: {o.approved} unit(s) approved",
            "Every printed label on the sheet is outlined; the drafts are active now",
            confidence=o.lowest,
            entity_type="sheet",
            entity_id=sheet_id,
            sheet_id=sheet_id,
        )
    left = []
    if o.skipped_low:
        left.append(
            f"{len(o.skipped_low)} candidate(s) below {rules.OUTLINE_MIN_CONFIDENCE:.1f}: "
            + ", ".join(o.skipped_low[:8])
        )
    if o.ambiguous:
        left.append("labels printed twice: " + ", ".join(o.ambiguous[:8]))
    if o.failed:
        left.append("could not place: " + ", ".join(o.failed[:8]))
    if left:
        ctx.decide(
            STEP,
            "skipped",
            f"{label}: {sum(len(x) for x in (o.skipped_low, o.ambiguous, o.failed))} need(s) you",
            "; ".join(left) + ". Accept or draw them in the sheet editor",
            needs_you=True,
            entity_type="sheet",
            entity_id=sheet_id,
            sheet_id=sheet_id,
        )


async def _one(ctx: Context, sheet_id: uuid.UUID, label: str) -> SheetOutcome | None:
    async with session(ctx) as db:
        sheet = (await db.execute(select(Sheet).where(Sheet.id == sheet_id))).scalar_one_or_none()
        if sheet is None or sheet.excluded:
            return None
        existing = await mapping.current_boundaries(db, sheet.id)
        if any(b.source != SOURCE for b, _u in existing):
            return None  # a person drew here: theirs
        removed = (
            await db.execute(
                select(UnitBoundary.id)
                .join(Unit, Unit.id == UnitBoundary.unit_id)
                .where(
                    UnitBoundary.sheet_id == sheet.id,
                    UnitBoundary.source == SOURCE,
                    Unit.lifecycle_status == "removed",
                )
                .limit(1)
            )
        ).first()
        if removed is not None:
            return None  # a person removed one of the solver's units here: theirs
        project_id = await _project_id(db, sheet)
        project = await projects.get_project(db, ctx.tenant_id, project_id)
        cands = await mapping.suggest_for_sheet(db, sheet)
        keyed = [(c, fid, suggest.normalise_label(c.label)) for c, fid in cands]
        counts: dict[str, int] = {}
        for _c, _fid, key in keyed:
            if key:
                counts[key] = counts.get(key, 0) + 1
        taken = [Polygon(b.polygon["ring"]) for b, _u in existing]
        o = SheetOutcome()
        covered_keys: set[str] = set()
        for c, fid, key in keyed:
            if not key:
                continue  # rooms, legends: never a unit on their own
            poly = Polygon(c.ring)
            if any(_overlap(poly, t) >= rules.OUTLINE_EXISTING_OVERLAP for t in taken):
                covered_keys.add(key)
                continue  # already outlined (an earlier run)
            if counts.get(key, 0) > 1:
                if key not in o.ambiguous:
                    o.ambiguous.append(key)
                continue
            if c.confidence < rules.OUTLINE_MIN_CONFIDENCE:
                o.skipped_low.append(f"{key} ({c.confidence:.2f})")
                continue
            try:
                await inventory.create_unit_from_boundary(
                    db,
                    project=project,
                    sheet=sheet,
                    ring=c.ring,
                    unit_type=c.unit_type or "apartment",
                    code=None,
                    label=c.label,
                    revision_id=sheet.revision_id,
                    actor=ctx.actor,
                    source=SOURCE,
                    floor_id=fid,
                    printed_area_m2=c.printed_area_m2,
                )
            except (ProblemError, ValueError) as e:
                o.failed.append(f"{key}: {getattr(e, 'detail', None) or e}"[:80])
                continue
            taken.append(poly)
            covered_keys.add(key)
            o.created += 1
            o.lowest = min(o.lowest, c.confidence)
        labelled = {k for _c, _fid, k in keyed if k}
        o.covered = bool(labelled) and labelled <= covered_keys and not o.failed
        if ctx.approve_sheets and o.covered:
            current = await mapping.current_boundaries(db, sheet.id)
            drafts = [b for b, _u in current if b.status == "draft"]
            if current and drafts and all(b.source == SOURCE for b, _u in current):
                o.approved = await inventory.approve_sheet(db, sheet, ctx.actor)
        return o


def _overlap(a: Polygon, b: Polygon) -> float:
    small = min(a.area, b.area)
    return a.intersection(b).area / small if small > 0 else 0.0


async def _project_id(db, sheet: Sheet) -> uuid.UUID:
    from unitforma.documents import service as documents

    return await documents.sheet_project_id(db, sheet)
