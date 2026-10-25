"""Sheet → floor assignments: one sheet may show several floors, each in a region of it.

A stepped building's typical sheet shows block A at +3.20, block B at +4.20 and block C at
+5.20 side by side; each block is a building with its own floors, so the sheet carries one
assignment per floor, each limited to the part of the sheet that shows it (plan §13.2).

``sheets.floor_id`` / ``sheets.suggested_floor_id`` are kept in sync with the first confirmed
and first suggested assignment so older clients and reports keep working (expand phase).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.audit.service import write_audit
from unitforma.core.errors import ProblemError
from unitforma.core.ids import new_id
from unitforma.documents import levels
from unitforma.inventory import geometry
from unitforma.tenants.models import Building, Document, DocumentRevision, Floor, Sheet, SheetFloor

Actor = tuple[uuid.UUID, str]


async def list_for_sheet(db: AsyncSession, sheet_id: uuid.UUID) -> list[SheetFloor]:
    rows = await db.execute(
        select(SheetFloor)
        .where(SheetFloor.sheet_id == sheet_id)
        .order_by(SheetFloor.sort_order, SheetFloor.created_at, SheetFloor.id)
    )
    return list(rows.scalars())


async def list_for_sheets(
    db: AsyncSession, sheet_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[SheetFloor]]:
    out: dict[uuid.UUID, list[SheetFloor]] = {s: [] for s in sheet_ids}
    if not sheet_ids:
        return out
    rows = await db.execute(
        select(SheetFloor)
        .where(SheetFloor.sheet_id.in_(sheet_ids))
        .order_by(SheetFloor.sort_order, SheetFloor.created_at, SheetFloor.id)
    )
    for a in rows.scalars():
        out[a.sheet_id].append(a)
    return out


async def confirmed(db: AsyncSession, sheet: Sheet) -> list[SheetFloor]:
    return [a for a in await list_for_sheet(db, sheet.id) if a.status == "confirmed"]


async def require_floor_on_sheet(db: AsyncSession, sheet: Sheet, floor_id: uuid.UUID) -> None:
    if not any(a.floor_id == floor_id for a in await confirmed(db, sheet)):
        raise ProblemError(422, "Sheet is not assigned to the unit's floor")


async def resolve_floor(
    db: AsyncSession, sheet: Sheet, ring: list[list[float]], requested: uuid.UUID | None
) -> uuid.UUID:
    """The floor a new unit drawn on this sheet belongs to.

    An explicit floor must be one of the sheet's confirmed floors; otherwise the region that
    contains the outline's centre decides, and a single whole-sheet floor takes everything.
    """
    conf = await confirmed(db, sheet)
    if not conf:
        raise ProblemError(409, "Assign the sheet to a floor before drawing units")
    if requested is not None:
        if not any(a.floor_id == requested for a in conf):
            raise ProblemError(422, "The chosen floor is not assigned to this sheet")
        return requested
    centre = geometry.validate_ring(ring).representative_point()
    fid = levels.region_floor((centre.x, centre.y), [(a.floor_id, a.region) for a in conf])
    if fid is None:
        raise ProblemError(
            409,
            "Choose the floor for this unit",
            "The sheet shows several floors and the outline is not inside one floor's region",
            extra={"floor_ids": [str(a.floor_id) for a in conf]},
        )
    return fid


def _validate_region(region: Any) -> dict | None:
    if region is None:
        return None
    ring = region.get("ring") if isinstance(region, dict) else None
    if not ring:
        return None
    try:
        geometry.validate_ring(ring)
    except ValueError as e:
        raise ProblemError(422, "Invalid floor region", str(e)) from e
    return {"ring": [[float(x), float(y)] for x, y in ring]}


async def _project_floor_ids(db: AsyncSession, sheet: Sheet) -> set[uuid.UUID]:
    rows = await db.execute(
        select(Floor.id)
        .join(Building, Building.id == Floor.building_id)
        .join(Document, Document.project_id == Building.project_id)
        .join(DocumentRevision, DocumentRevision.document_id == Document.id)
        .where(DocumentRevision.id == sheet.revision_id)
    )
    return {r[0] for r in rows}


def sync_primary(sheet: Sheet, assigns: list[SheetFloor]) -> None:
    conf = [a for a in assigns if a.status == "confirmed"]
    sugg = [a for a in assigns if a.status == "suggested"]
    sheet.floor_id = conf[0].floor_id if conf else None
    sheet.suggested_floor_id = sugg[0].floor_id if sugg else None
    if conf:
        sheet.assignment_status = "confirmed"
    elif sugg:
        sheet.assignment_status = "suggested"
    elif sheet.assignment_status in ("confirmed", "suggested"):
        sheet.assignment_status = "unassigned"


async def set_floors(
    db: AsyncSession,
    sheet: Sheet,
    items: list[dict[str, Any]],
    version: int,
    actor: Actor,
) -> list[SheetFloor]:
    """Replace the sheet's assignments with ``items`` ({floor_id, region}), all confirmed.

    An empty list rejects the sheet (it shows no floor: a detail or a schedule). Floors that
    already carry units drawn on this sheet cannot be removed while those units are current.
    """
    if sheet.version != version:
        raise ProblemError(409, "Conflict", f"Sheet changed concurrently (version {sheet.version})")
    if sheet.excluded and items:
        raise ProblemError(409, "Sheet is excluded from mapping", sheet.exclusion_reason)
    allowed = await _project_floor_ids(db, sheet)
    seen: set[uuid.UUID] = set()
    wanted: list[tuple[uuid.UUID, dict | None]] = []
    for it in items:
        fid = uuid.UUID(str(it["floor_id"]))
        if fid not in allowed:
            raise ProblemError(422, "Floor does not belong to this project")
        if fid in seen:
            raise ProblemError(422, "A floor is listed twice")
        seen.add(fid)
        wanted.append((fid, _validate_region(it.get("region"))))
    await _guard_drawn_floors(db, sheet, seen)
    before = [
        {"floor_id": str(a.floor_id), "status": a.status, "region": a.region}
        for a in await list_for_sheet(db, sheet.id)
    ]
    existing = {a.floor_id: a for a in await list_for_sheet(db, sheet.id)}
    await db.execute(
        delete(SheetFloor).where(SheetFloor.sheet_id == sheet.id, SheetFloor.floor_id.not_in(seen))
    )
    out: list[SheetFloor] = []
    for i, (fid, region) in enumerate(wanted):
        a = existing.get(fid)
        if a is None:
            a = SheetFloor(
                id=new_id(),
                tenant_id=sheet.tenant_id,
                sheet_id=sheet.id,
                floor_id=fid,
                source="manual",
            )
            db.add(a)
        a.status = "confirmed"
        a.region = region
        a.sort_order = i
        out.append(a)
    await db.flush()
    sync_primary(sheet, out)
    if not out:
        sheet.assignment_status = "rejected"
    sheet.version += 1
    await write_audit(
        db,
        tenant_id=sheet.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="sheet",
        entity_id=sheet.id,
        action="assign_floors",
        before={"floors": before},
        after={"floors": [{"floor_id": str(f), "region": r} for f, r in wanted]},
    )
    return out


async def _guard_drawn_floors(db: AsyncSession, sheet: Sheet, keep: set[uuid.UUID]) -> None:
    from unitforma.tenants.models import Unit, UnitBoundary

    rows = await db.execute(
        select(Unit.floor_id, Unit.code)
        .join(UnitBoundary, UnitBoundary.unit_id == Unit.id)
        .where(
            UnitBoundary.sheet_id == sheet.id,
            UnitBoundary.is_current.is_(True),
            Unit.lifecycle_status != "removed",
        )
    )
    orphaned = sorted({code for fid, code in rows if fid not in keep})
    if orphaned:
        raise ProblemError(
            409,
            "Units on this sheet belong to a floor being removed",
            f"Remove or move these units first: {', '.join(orphaned[:20])}",
        )


async def confirm(db: AsyncSession, sheet: Sheet, floor_id: uuid.UUID, source: str) -> None:
    """Confirm one floor on the sheet (accepting a revision-diff item implies it)."""
    assigns = await list_for_sheet(db, sheet.id)
    a = next((x for x in assigns if x.floor_id == floor_id), None)
    if a is None:
        a = SheetFloor(
            id=new_id(),
            tenant_id=sheet.tenant_id,
            sheet_id=sheet.id,
            floor_id=floor_id,
            source=source,
            sort_order=len(assigns),
        )
        db.add(a)
        assigns.append(a)
    if a.status != "confirmed":
        a.status = "confirmed"
        sheet.version += 1
    await db.flush()
    sync_primary(sheet, assigns)


async def replace_suggestions(
    db: AsyncSession, sheet: Sheet, suggestions: list[dict[str, Any]], source: str
) -> None:
    """Swap the sheet's suggested assignments; confirmed ones are never touched."""
    if sheet.excluded:
        return
    assigns = await list_for_sheet(db, sheet.id)
    taken = {a.floor_id for a in assigns if a.status == "confirmed"}
    for a in [a for a in assigns if a.status == "suggested"]:
        await db.delete(a)
    await db.flush()  # deletes first: a re-suggested floor reuses the (sheet, floor) key
    kept = [a for a in assigns if a.status == "confirmed"]
    for i, s in enumerate(suggestions):
        fid = uuid.UUID(str(s["floor_id"]))
        if fid in taken:
            continue
        taken.add(fid)
        a = SheetFloor(
            id=new_id(),
            tenant_id=sheet.tenant_id,
            sheet_id=sheet.id,
            floor_id=fid,
            status="suggested",
            source=source,
            region=s.get("region"),
            marker=s.get("marker"),
            sort_order=len(kept) + i,
        )
        db.add(a)
        kept.append(a)
    await db.flush()
    sync_primary(sheet, kept)


async def inherit(db: AsyncSession, old: Sheet, new: Sheet) -> None:
    """A new revision's page gets the old page's floors (with regions) as suggestions."""
    if any(a.status == "confirmed" for a in await list_for_sheet(db, new.id)):
        return
    # the reviewer's floors on the previous page beat level-marker guesses on the new one
    prev = [a for a in await list_for_sheet(db, old.id) if a.status == "confirmed"]
    if not prev:
        return
    await replace_suggestions(
        db,
        new,
        [{"floor_id": a.floor_id, "region": a.region, "marker": a.marker} for a in prev],
        "inherited",
    )
