"""Revision diff proposals: build from a processed revision, apply reviewer decisions.

Plan §5.5 rule 1 and §13.3: a new revision never writes to ``units``; every change goes
through an explicit decision that calls the identity-preserving inventory operations.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from shapely.geometry import Polygon
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.audit.service import write_audit
from unitforma.core.errors import ProblemError
from unitforma.core.ids import new_id
from unitforma.documents import assignments, levels
from unitforma.inventory import geometry
from unitforma.inventory import service as inventory
from unitforma.mapping import diff, suggest
from unitforma.storage.service import get_storage
from unitforma.tenants.models import (
    Document,
    DocumentRevision,
    Floor,
    MappingProposal,
    MappingProposalItem,
    Project,
    Sheet,
    Unit,
    UnitBoundary,
)

log = structlog.get_logger()
Actor = tuple[uuid.UUID, str]


def load_extract(sheet: Sheet) -> dict[str, Any]:
    if not sheet.extract_key:
        return {}
    try:
        return json.loads(get_storage().get_bytes(sheet.extract_key))
    except Exception as e:  # noqa: BLE001 - a missing extract only disables suggestions
        log.warning("mapping.extract_unavailable", sheet_id=str(sheet.id), error=str(e))
        return {}


def sheet_metres(sheet: Sheet, extract: dict[str, Any]) -> tuple[float, float] | None:
    """Sheet size in metres: the calibration if there is one, else the single printed scale the
    dimensions do not contradict, else the page width the dimensions give (ADR-0031 Decision 3)."""
    cal = sheet.calibration or {}
    if (
        sheet.calibration_status in ("calibrated", "inherited")
        and cal.get("m_per_px")
        and sheet.raster_width
        and sheet.raster_height
    ):
        m = float(cal["m_per_px"])
        return (m * sheet.raster_width, m * sheet.raster_height)
    if not extract.get("page_pt") and sheet.width_pt and sheet.height_pt:
        extract = {**extract, "page_pt": [float(sheet.width_pt), float(sheet.height_pt)]}
    hints = sheet.hints or {}
    found = suggest.scale_metres(extract, hints.get("scales") or [], hints.get("dimension_scale"))
    return found[0] if found else None


def candidates_for_sheet(sheet: Sheet) -> list[suggest.Candidate]:
    extract = load_extract(sheet)
    return suggest.closed_loops(extract, page_m=sheet_metres(sheet, extract))


async def suggest_for_sheet(
    db: AsyncSession, sheet: Sheet
) -> list[tuple[suggest.Candidate, uuid.UUID | None]]:
    """Candidates with the floor each would be created on (by region), if the sheet decides it.

    A numbered zone without a unit word ("№30 12.5 m²") on a floor below ground is suggested
    as storage; elsewhere its type is left to the reviewer.
    """
    if sheet.excluded:
        raise ProblemError(409, "Sheet is excluded from mapping", sheet.exclusion_reason)
    cands = candidates_for_sheet(sheet)
    conf = await assignments.confirmed(db, sheet)
    pairs = [(a.floor_id, a.region) for a in conf]
    level_of: dict[uuid.UUID, int] = {}
    if conf:
        rows = await db.execute(
            select(Floor.id, Floor.level).where(Floor.id.in_([a.floor_id for a in conf]))
        )
        level_of = {fid: lvl for fid, lvl in rows}
    out = []
    for c in cands:
        fid = None
        if pairs:
            centre = Polygon(c.ring).representative_point()
            fid = levels.region_floor((centre.x, centre.y), pairs)
        if c.unit_type is None and c.printed_area_m2 and fid and level_of.get(fid, 0) < 0:
            c.unit_type = "storage"
        out.append((c, fid))
    return out


async def apply_printed_areas(
    db: AsyncSession, project: Project, sheet: Sheet, actor: Actor
) -> dict[str, int]:
    """Read the areas printed on a sheet into the documented areas of the units drawn on it.

    Each current boundary is matched to the suggestion that overlaps it most (≥ 70 % of the
    smaller polygon, same label key when both have one); its printed area becomes the unit's
    ``drawing_schedule`` area. Units drawn before printed areas were read get them this way.
    """
    if sheet.excluded:
        raise ProblemError(409, "Sheet is excluded from mapping", sheet.exclusion_reason)
    cands = [c for c in candidates_for_sheet(sheet) if c.printed_area_m2]
    polys = [Polygon(c.ring) for c in cands]
    stats = {"updated": 0, "unchanged": 0, "unmatched": 0}
    for b, u in await current_boundaries(db, sheet.id):
        ring = Polygon(b.polygon["ring"])
        best, best_ratio = None, 0.0
        for c, p in zip(cands, polys, strict=True):
            small = min(ring.area, p.area)
            ratio = ring.intersection(p).area / small if small > 0 else 0.0
            if ratio < 0.7 or ratio <= best_ratio:
                continue
            kb, kc = suggest.normalise_label(b.label), suggest.normalise_label(c.label)
            if kb and kc and kb != kc:
                continue
            best, best_ratio = c, ratio
        if best is None:
            stats["unmatched"] += 1
            continue
        row = await inventory.set_printed_area(
            db,
            u,
            project,
            float(best.printed_area_m2),
            sheet_id=sheet.id,
            label=best.label,
            revision_id=sheet.revision_id,
        )
        stats["updated" if row else "unchanged"] += 1
    if stats["updated"]:
        await write_audit(
            db,
            tenant_id=sheet.tenant_id,
            actor_user_id=actor[0],
            actor_role=actor[1],
            entity_type="sheet",
            entity_id=sheet.id,
            action="read_printed_areas",
            after=stats,
        )
    return stats


async def current_boundaries(
    db: AsyncSession, sheet_id: uuid.UUID
) -> list[tuple[UnitBoundary, Unit]]:
    rows = await db.execute(
        select(UnitBoundary, Unit)
        .join(Unit, Unit.id == UnitBoundary.unit_id)
        .where(
            UnitBoundary.sheet_id == sheet_id,
            UnitBoundary.is_current.is_(True),
            Unit.lifecycle_status != "removed",
        )
        .order_by(Unit.code)
    )
    return [(b, u) for b, u in rows]


async def inherit_sheet_setup(db: AsyncSession, old: Sheet, new: Sheet) -> None:
    """Carry floor assignments (with regions) and calibration over to the new revision's page.

    Floors arrive as suggestions; accepting a diff item confirms the unit's floor. A page the
    reviewer excluded stays excluded in the new revision.
    """
    if old.excluded and not new.excluded:
        for a in await assignments.list_for_sheet(db, new.id):
            if a.status == "suggested":
                await db.delete(a)
        await db.flush()
        assignments.sync_primary(new, [])
        new.excluded = True
        new.exclusion_reason = f"excluded in the previous revision: {old.exclusion_reason or ''}"[
            :200
        ]
        return
    await assignments.inherit(db, old, new)
    if (
        old.calibration
        and old.calibration_status == "calibrated"
        and new.calibration_status == "none"
        and new.raster_width
        and new.raster_height
    ):
        try:
            new.calibration = geometry.calibration_from_points(
                old.calibration["p1"],
                old.calibration["p2"],
                old.calibration["distance_m"],
                new.raster_width,
                new.raster_height,
            )
            new.calibration_status = "inherited"
        except (ValueError, KeyError):
            pass


async def build_proposal(
    db: AsyncSession, tenant_id: uuid.UUID, new_rev: DocumentRevision, actor_id: uuid.UUID | None
) -> MappingProposal | None:
    """Diff the new revision against the mapping on the revision it supersedes.

    Returns ``None`` when there is nothing to diff (first revision, or no mapped pages).
    """
    if new_rev.supersedes_revision_id is None:
        return None
    doc = (
        await db.execute(select(Document).where(Document.id == new_rev.document_id))
    ).scalar_one()
    old_sheets = {
        s.page_no: s
        for s in (
            await db.execute(
                select(Sheet).where(Sheet.revision_id == new_rev.supersedes_revision_id)
            )
        ).scalars()
    }
    new_sheets = list(
        (
            await db.execute(
                select(Sheet).where(Sheet.revision_id == new_rev.id).order_by(Sheet.page_no)
            )
        ).scalars()
    )
    items: list[MappingProposalItem] = []
    pages_compared = 0
    for ns in new_sheets:
        os_ = old_sheets.get(ns.page_no)
        if os_ is None:
            continue
        await inherit_sheet_setup(db, os_, ns)
        if ns.excluded:
            continue
        olds = await current_boundaries(db, os_.id)
        if not olds:
            continue
        pages_compared += 1
        cands = candidates_for_sheet(ns)
        old_in = [
            diff.OldBoundary(
                boundary_id=str(b.id),
                unit_id=str(u.id),
                ring=b.polygon["ring"],
                label=b.label,
                code=u.code,
                status=b.status,
            )
            for b, u in olds
        ]
        new_in = [
            diff.NewCandidate(index=i, ring=c.ring, label=c.label) for i, c in enumerate(cands)
        ]
        for it in diff.classify(old_in, new_in):
            items.append(
                MappingProposalItem(
                    id=new_id(),
                    tenant_id=tenant_id,
                    kind=it.kind,
                    old_unit_ids=[uuid.UUID(x) for x in it.old_unit_ids],
                    old_boundary_ids=[uuid.UUID(x) for x in it.old_boundary_ids],
                    old_sheet_id=os_.id,
                    new_sheet_id=ns.id,
                    new_rings=[cands[j].ring for j in it.new_indexes],
                    labels=[cands[j].label for j in it.new_indexes],
                    printed_areas=[cands[j].printed_area_m2 for j in it.new_indexes],
                    overlaps=it.overlaps,
                    confidence=it.confidence,
                )
            )
    if pages_compared == 0:
        return None
    # one open proposal per revision: an earlier one (re-run) is dismissed
    for old_p in (
        await db.execute(
            select(MappingProposal).where(
                MappingProposal.new_revision_id == new_rev.id, MappingProposal.status == "open"
            )
        )
    ).scalars():
        old_p.status = "dismissed"
        old_p.resolved_at = datetime.now(UTC)
    summary = {}
    for it in items:
        summary[it.kind] = summary.get(it.kind, 0) + 1
    summary["total"] = len(items)
    summary["pages_compared"] = pages_compared
    proposal = MappingProposal(
        id=new_id(),
        tenant_id=tenant_id,
        project_id=doc.project_id,
        document_id=doc.id,
        old_revision_id=new_rev.supersedes_revision_id,
        new_revision_id=new_rev.id,
        status="open" if items else "resolved",
        summary=summary,
        created_by=actor_id,
        resolved_at=None if items else datetime.now(UTC),
    )
    db.add(proposal)
    await db.flush()
    for it in items:
        it.proposal_id = proposal.id
        db.add(it)
    await db.flush()
    log.info(
        "mapping.proposal_built",
        proposal_id=str(proposal.id),
        revision_id=str(new_rev.id),
        summary=summary,
    )
    return proposal


async def get_proposal(
    db: AsyncSession, tenant_id: uuid.UUID, proposal_id: uuid.UUID
) -> MappingProposal:
    p = (
        await db.execute(
            select(MappingProposal).where(
                MappingProposal.tenant_id == tenant_id, MappingProposal.id == proposal_id
            )
        )
    ).scalar_one_or_none()
    if p is None:
        raise ProblemError(404, "Proposal not found")
    return p


async def list_items(db: AsyncSession, proposal_id: uuid.UUID) -> list[MappingProposalItem]:
    rows = await db.execute(
        select(MappingProposalItem)
        .where(MappingProposalItem.proposal_id == proposal_id)
        .order_by(MappingProposalItem.created_at, MappingProposalItem.id)
    )
    return list(rows.scalars())


async def _refresh_status(db: AsyncSession, proposal: MappingProposal) -> None:
    pending = [i for i in await list_items(db, proposal.id) if i.decision == "pending"]
    if not pending and proposal.status == "open":
        proposal.status = "resolved"
        proposal.resolved_at = datetime.now(UTC)


async def _ensure_floor(db: AsyncSession, sheet: Sheet, wanted_floor_id: uuid.UUID | None) -> None:
    """Accepting a diff item implies the page shows the unit's floor: confirm that floor.

    The floor must already be on the page (inherited or suggested from level markers, or
    confirmed); a floor the page was never linked to needs the reviewer's assignment first.
    For a new unit (no wanted floor) the page's suggestions are confirmed when it has no
    confirmed floor yet.
    """
    assigns = await assignments.list_for_sheet(db, sheet.id)
    if wanted_floor_id is not None:
        match = next((a for a in assigns if a.floor_id == wanted_floor_id), None)
        if match is None:
            if any(a.status == "confirmed" for a in assigns):
                raise ProblemError(
                    409,
                    "Sheet is assigned to another floor",
                    "The new page is not assigned to the floor of the unit it should replace",
                )
            fl = (
                await db.execute(select(Floor).where(Floor.id == wanted_floor_id))
            ).scalar_one_or_none()
            if fl is None:
                raise ProblemError(409, "The unit's floor no longer exists")
        await assignments.confirm(db, sheet, wanted_floor_id, "diff_accept")
        return
    if any(a.status == "confirmed" for a in assigns):
        return
    if not assigns:
        raise ProblemError(409, "Assign the new sheet to a floor before accepting this item")
    for a in assigns:
        await assignments.confirm(db, sheet, a.floor_id, "diff_accept")


def _printed_at(item: MappingProposalItem, j: int) -> float | None:
    areas = item.printed_areas or []
    return float(areas[j]) if j < len(areas) and areas[j] else None


async def _printed(
    db: AsyncSession,
    project: Project,
    unit: Unit,
    sheet: Sheet,
    item: MappingProposalItem,
    j: int,
    revision_id: uuid.UUID,
) -> None:
    """A revision's printed area follows the unit like its outline does (plan §13.3)."""
    value = _printed_at(item, j)
    if value:
        label = item.labels[j] if j < len(item.labels or []) else None
        await inventory.set_printed_area(
            db, unit, project, value, sheet_id=sheet.id, label=label, revision_id=revision_id
        )


async def _unit(db: AsyncSession, unit_id: uuid.UUID) -> Unit:
    u = (await db.execute(select(Unit).where(Unit.id == unit_id))).scalar_one_or_none()
    if u is None:
        raise ProblemError(409, "A unit referenced by this item no longer exists")
    return u


def _inherit_index(item: MappingProposalItem, override: int | None) -> int:
    if override is not None:
        if not 0 <= override < len(item.new_rings):
            raise ProblemError(422, "inherit_index out of range")
        return override
    best, best_ratio = 0, -1.0
    for _uid, j, ratio in item.overlaps:
        if ratio > best_ratio:
            best, best_ratio = int(j), float(ratio)
    return best


def _survivor(item: MappingProposalItem, override: uuid.UUID | None) -> uuid.UUID:
    if override is not None:
        if override not in item.old_unit_ids:
            raise ProblemError(422, "survivor_id is not one of the merged units")
        return override
    best, best_ratio = item.old_unit_ids[0], -1.0
    for uid, _j, ratio in item.overlaps:
        if ratio > best_ratio:
            best, best_ratio = uuid.UUID(str(uid)), float(ratio)
    return best


async def decide_item(
    db: AsyncSession,
    proposal: MappingProposal,
    item: MappingProposalItem,
    *,
    decision: str,
    overrides: dict[str, Any],
    actor: Actor,
) -> MappingProposalItem:
    if proposal.status != "open":
        raise ProblemError(409, "Proposal is not open")
    if item.decision != "pending":
        raise ProblemError(409, "Item already decided", item.decision)
    now = datetime.now(UTC)
    if decision == "reject":
        item.decision = "rejected"
        item.decided_by, item.decided_at = actor[0], now
        item.result = {"note": overrides.get("note")}
        await _refresh_status(db, proposal)
        return item

    project = (
        await db.execute(select(Project).where(Project.id == proposal.project_id))
    ).scalar_one()
    sheet = (
        (await db.execute(select(Sheet).where(Sheet.id == item.new_sheet_id))).scalar_one_or_none()
        if item.new_sheet_id
        else None
    )
    if sheet is None:
        raise ProblemError(409, "The new sheet of this item no longer exists")
    note = overrides.get("note") or f"revision diff {proposal.new_revision_id}"
    result: dict[str, Any] = {}
    try:
        if item.kind in ("matched", "relabelled"):
            unit = await _unit(db, item.old_unit_ids[0])
            await _ensure_floor(db, sheet, unit.floor_id)
            b = await inventory.rehome_boundary(
                db,
                unit,
                sheet,
                item.new_rings[0],
                label=item.labels[0] if item.labels else None,
                source="vector_suggest",
                revision_id=proposal.new_revision_id,
                actor=actor,
            )
            result = {"unit_id": str(unit.id), "boundary_id": str(b.id)}
            await _printed(db, project, unit, sheet, item, 0, proposal.new_revision_id)
            if overrides.get("code"):
                await inventory.relabel(
                    db, unit, overrides["code"], unit.version, actor, reason=note
                )
                result["code"] = unit.code
        elif item.kind == "split":
            unit = await _unit(db, item.old_unit_ids[0])
            await _ensure_floor(db, sheet, unit.floor_id)
            keep = _inherit_index(item, overrides.get("inherit_index"))
            order = [keep, *[j for j in range(len(item.new_rings)) if j != keep]]
            rings = [item.new_rings[j] for j in order]
            codes_in = overrides.get("codes") or []
            codes = [codes_in[j] if j < len(codes_in) else None for j in order]
            codes[0] = None  # the inheriting part keeps its code
            units = await inventory.split_unit(
                db, project, unit, sheet, rings, codes, actor, proposal.new_revision_id, note
            )
            for part, j in zip(units, order, strict=False):
                await _printed(db, project, part, sheet, item, j, proposal.new_revision_id)
            result = {"unit_ids": [str(u.id) for u in units], "inherit_index": keep}
        elif item.kind == "merged":
            survivor_id = _survivor(item, overrides.get("survivor_id"))
            survivor = await _unit(db, survivor_id)
            absorbed = [await _unit(db, i) for i in item.old_unit_ids if i != survivor_id]
            await _ensure_floor(db, sheet, survivor.floor_id)
            await inventory.merge_units(
                db,
                project,
                survivor,
                absorbed,
                item.new_rings[0],
                sheet,
                actor,
                proposal.new_revision_id,
                note,
            )
            await _printed(db, project, survivor, sheet, item, 0, proposal.new_revision_id)
            result = {"survivor_id": str(survivor.id), "absorbed": [str(u.id) for u in absorbed]}
        elif item.kind == "new":
            await _ensure_floor(db, sheet, None)
            unit, b = await inventory.create_unit_from_boundary(
                db,
                project=project,
                sheet=sheet,
                ring=item.new_rings[0],
                unit_type=overrides.get("unit_type") or "apartment",
                code=overrides.get("code"),
                label=item.labels[0] if item.labels else None,
                revision_id=proposal.new_revision_id,
                actor=actor,
                source="vector_suggest",
                printed_area_m2=_printed_at(item, 0),
            )
            result = {"unit_id": str(unit.id), "boundary_id": str(b.id), "code": unit.code}
        elif item.kind == "missing":
            unit = await _unit(db, item.old_unit_ids[0])
            await inventory.remove_unit(
                db, unit, unit.version, actor, proposal.new_revision_id, note
            )
            result = {"unit_id": str(unit.id)}
        else:
            raise ProblemError(
                422,
                "Complex change needs manual resolution",
                "Several old units overlap several new polygons: resolve with the boundary editor "
                "and reject this item",
            )
    except ValueError as e:
        raise ProblemError(422, "Invalid geometry in proposal", str(e)) from e
    item.decision = "accepted"
    item.decided_by, item.decided_at = actor[0], now
    item.result = result
    await write_audit(
        db,
        tenant_id=proposal.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="mapping_proposal_item",
        entity_id=item.id,
        action="accept",
        after={"kind": item.kind, **result},
    )
    await _refresh_status(db, proposal)
    return item


async def accept_all(
    db: AsyncSession, proposal: MappingProposal, kinds: set[str], actor: Actor
) -> int:
    n = 0
    for it in await list_items(db, proposal.id):
        if it.decision == "pending" and it.kind in kinds:
            await decide_item(db, proposal, it, decision="accept", overrides={}, actor=actor)
            n += 1
    return n
