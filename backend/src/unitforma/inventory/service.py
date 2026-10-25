"""Canonical unit service: identity, codes, boundaries, areas, lineage (plan §5.5, §13.3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.audit.service import write_audit
from unitforma.core.errors import ProblemError
from unitforma.core.ids import new_id
from unitforma.inventory import geometry
from unitforma.inventory.codes import normalise_code, render_code
from unitforma.tenants.models import (
    Building,
    Floor,
    Project,
    Sheet,
    Unit,
    UnitArea,
    UnitBoundary,
    UnitCodeHistory,
    UnitLineageEvent,
)

Actor = tuple[uuid.UUID, str]


async def _code_in_use(
    db: AsyncSession, project_id: uuid.UUID, code: str, exclude: uuid.UUID | None = None
) -> bool:
    q = select(Unit.id).where(
        Unit.project_id == project_id,
        func.lower(Unit.code) == code.lower(),
        Unit.lifecycle_status != "removed",
    )
    if exclude:
        q = q.where(Unit.id != exclude)
    return (await db.execute(q)).first() is not None


async def next_code(db: AsyncSession, project: Project, building: Building, floor: Floor) -> str:
    count = (
        await db.execute(
            select(func.count())
            .select_from(Unit)
            .where(Unit.floor_id == floor.id, Unit.lifecycle_status != "removed")
        )
    ).scalar_one()
    seq = count + 1
    while True:
        code = render_code(project.code_pattern, building=building.code, floor=floor.level, seq=seq)
        if not await _code_in_use(db, project.id, code):
            return code
        seq += 1


async def create_unit_from_boundary(
    db: AsyncSession,
    *,
    project: Project,
    sheet: Sheet,
    ring: list[list[float]],
    unit_type: str,
    code: str | None,
    label: str | None,
    revision_id: uuid.UUID,
    actor: Actor,
) -> tuple[Unit, UnitBoundary]:
    """Drawing a boundary on an assigned sheet creates a draft unit with a permanent id."""
    if sheet.floor_id is None:
        raise ProblemError(409, "Assign the sheet to a floor before drawing units")
    poly = geometry.validate_ring(ring)
    floor = (await db.execute(select(Floor).where(Floor.id == sheet.floor_id))).scalar_one()
    building = (
        await db.execute(select(Building).where(Building.id == floor.building_id))
    ).scalar_one()
    if building.project_id != project.id:
        raise ProblemError(422, "Sheet floor belongs to another project")
    if code:
        code = normalise_code(code)
        if await _code_in_use(db, project.id, code):
            raise ProblemError(409, f"Code {code} is already in use in this project")
    else:
        code = await next_code(db, project, building, floor)
    unit = Unit(
        id=new_id(),
        tenant_id=project.tenant_id,
        project_id=project.id,
        building_id=building.id,
        floor_id=floor.id,
        code=code,
        unit_type=unit_type,
        lifecycle_status="draft",
        created_from_revision_id=revision_id,
    )
    db.add(unit)
    await db.flush()
    db.add(
        UnitCodeHistory(
            id=new_id(),
            tenant_id=project.tenant_id,
            unit_id=unit.id,
            old_code=None,
            new_code=code,
            changed_by=actor[0],
            revision_id=revision_id,
            reason="created",
        )
    )
    boundary = UnitBoundary(
        id=new_id(),
        tenant_id=project.tenant_id,
        unit_id=unit.id,
        sheet_id=sheet.id,
        polygon={"ring": ring},
        source="manual",
        status="draft",
        label=label,
    )
    _apply_calibration(boundary, sheet)
    db.add(boundary)
    await db.flush()
    await _refresh_measured_area(db, unit, boundary, project)
    db.add(
        UnitLineageEvent(
            id=new_id(),
            tenant_id=project.tenant_id,
            project_id=project.id,
            event_type="created",
            revision_id=revision_id,
            to_unit_ids=[unit.id],
            decided_by=actor[0],
        )
    )
    await write_audit(
        db,
        tenant_id=project.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="unit",
        entity_id=unit.id,
        action="create",
        after={
            "code": code,
            "unit_type": unit_type,
            "floor_id": str(floor.id),
            "area_px": round(poly.area, 6),
        },
    )
    return unit, boundary


def _apply_calibration(boundary: UnitBoundary, sheet: Sheet) -> None:
    if sheet.calibration and sheet.calibration_status == "calibrated":
        boundary.polygon_m = {
            "ring": geometry.ring_to_metres(boundary.polygon["ring"], sheet.calibration)
        }
    else:
        boundary.polygon_m = None


async def _refresh_measured_area(
    db: AsyncSession, unit: Unit, boundary: UnitBoundary, project: Project
) -> None:
    """Measured area (source drawing_measured) follows the current boundary; always unverified."""
    rows = await db.execute(
        select(UnitArea).where(
            UnitArea.unit_id == unit.id,
            UnitArea.source == "drawing_measured",
            UnitArea.is_current.is_(True),
        )
    )
    for old in rows.scalars():
        old.is_current = False
    if boundary.polygon_m:
        area_type = _measured_area_type(project)
        db.add(
            UnitArea(
                id=new_id(),
                tenant_id=unit.tenant_id,
                unit_id=unit.id,
                area_type=area_type,
                value_m2=geometry.area_m2(boundary.polygon_m["ring"]),
                source="drawing_measured",
                source_ref={"boundary_id": str(boundary.id), "sheet_id": str(boundary.sheet_id)},
                verification_status="unverified",
            )
        )


def _measured_area_type(project: Project) -> str:
    keys = [a.get("key") for a in (project.area_definitions or []) if isinstance(a, dict)]
    return "net_internal" if "net_internal" in keys or not keys else keys[0]


async def update_boundary(
    db: AsyncSession, boundary: UnitBoundary, ring: list[list[float]], version: int, actor: Actor
) -> UnitBoundary:
    if boundary.version != version:
        raise ProblemError(
            409, "Conflict", f"Boundary changed concurrently (version {boundary.version})"
        )
    geometry.validate_ring(ring)
    sheet = (await db.execute(select(Sheet).where(Sheet.id == boundary.sheet_id))).scalar_one()
    unit = (await db.execute(select(Unit).where(Unit.id == boundary.unit_id))).scalar_one()
    project = (await db.execute(select(Project).where(Project.id == unit.project_id))).scalar_one()
    if boundary.status == "approved":
        # approved geometry is never overwritten: supersede it and record the change
        boundary.status = "superseded"
        boundary.is_current = False
        nb = UnitBoundary(
            id=new_id(),
            tenant_id=boundary.tenant_id,
            unit_id=unit.id,
            sheet_id=sheet.id,
            polygon={"ring": ring},
            source="manual",
            status="draft",
            label=boundary.label,
        )
        _apply_calibration(nb, sheet)
        db.add(nb)
        await db.flush()
        db.add(
            UnitLineageEvent(
                id=new_id(),
                tenant_id=unit.tenant_id,
                project_id=unit.project_id,
                event_type="geometry_updated",
                from_unit_ids=[unit.id],
                to_unit_ids=[unit.id],
                decided_by=actor[0],
            )
        )
        boundary = nb
    else:
        boundary.polygon = {"ring": ring}
        _apply_calibration(boundary, sheet)
        boundary.version += 1
    await _refresh_measured_area(db, unit, boundary, project)
    await write_audit(
        db,
        tenant_id=unit.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="unit_boundary",
        entity_id=boundary.id,
        action="update",
        after={"unit_id": str(unit.id)},
    )
    return boundary


async def recalibrate_sheet(db: AsyncSession, sheet: Sheet, calibration: dict[str, Any]) -> int:
    """Re-derive metric polygons and measured areas of all current boundaries on the sheet."""
    sheet.calibration = calibration
    sheet.calibration_status = "calibrated"
    rows = await db.execute(
        select(UnitBoundary).where(
            UnitBoundary.sheet_id == sheet.id, UnitBoundary.is_current.is_(True)
        )
    )
    n = 0
    for b in rows.scalars():
        _apply_calibration(b, sheet)
        unit = (await db.execute(select(Unit).where(Unit.id == b.unit_id))).scalar_one()
        project = (
            await db.execute(select(Project).where(Project.id == unit.project_id))
        ).scalar_one()
        await _refresh_measured_area(db, unit, b, project)
        n += 1
    return n


async def relabel(
    db: AsyncSession,
    unit: Unit,
    new_code: str,
    version: int,
    actor: Actor,
    reason: str | None = None,
) -> Unit:
    if unit.version != version:
        raise ProblemError(409, "Conflict", f"Unit changed concurrently (version {unit.version})")
    new_code = normalise_code(new_code)
    if new_code == unit.code:
        return unit
    if await _code_in_use(db, unit.project_id, new_code, exclude=unit.id):
        raise ProblemError(409, f"Code {new_code} is already in use in this project")
    old = unit.code
    unit.code = new_code
    unit.version += 1
    db.add(
        UnitCodeHistory(
            id=new_id(),
            tenant_id=unit.tenant_id,
            unit_id=unit.id,
            old_code=old,
            new_code=new_code,
            changed_by=actor[0],
            reason=reason,
        )
    )
    db.add(
        UnitLineageEvent(
            id=new_id(),
            tenant_id=unit.tenant_id,
            project_id=unit.project_id,
            event_type="relabelled",
            from_unit_ids=[unit.id],
            to_unit_ids=[unit.id],
            decided_by=actor[0],
            note=f"{old} → {new_code}",
        )
    )
    await write_audit(
        db,
        tenant_id=unit.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="unit",
        entity_id=unit.id,
        action="relabel",
        before={"code": old},
        after={"code": new_code},
    )
    return unit


async def remove_unit(
    db: AsyncSession,
    unit: Unit,
    version: int,
    actor: Actor,
    revision_id: uuid.UUID | None,
    note: str | None,
) -> Unit:
    """Units are never deleted: lifecycle becomes ``removed``; the row keeps id and history."""
    if unit.version != version:
        raise ProblemError(409, "Conflict")
    if unit.lifecycle_status == "removed":
        return unit
    unit.lifecycle_status = "removed"
    unit.removed_by_revision_id = revision_id
    unit.version += 1
    for b in (
        await db.execute(
            select(UnitBoundary).where(
                UnitBoundary.unit_id == unit.id, UnitBoundary.is_current.is_(True)
            )
        )
    ).scalars():
        b.is_current = False
        b.status = "superseded"
    db.add(
        UnitLineageEvent(
            id=new_id(),
            tenant_id=unit.tenant_id,
            project_id=unit.project_id,
            event_type="removed",
            revision_id=revision_id,
            from_unit_ids=[unit.id],
            decided_by=actor[0],
            note=note,
        )
    )
    await write_audit(
        db,
        tenant_id=unit.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="unit",
        entity_id=unit.id,
        action="remove",
        after={"note": note},
    )
    return unit


async def merge_units(
    db: AsyncSession,
    project: Project,
    survivor: Unit,
    absorbed: list[Unit],
    ring: list[list[float]] | None,
    sheet: Sheet | None,
    actor: Actor,
    revision_id: uuid.UUID | None,
    note: str | None,
) -> Unit:
    """Merge: the chosen survivor keeps its id; absorbed units become removed (plan §13.3)."""
    if any(u.id == survivor.id for u in absorbed):
        raise ProblemError(422, "Survivor cannot be among the absorbed units")
    if any(u.project_id != project.id for u in [survivor, *absorbed]):
        raise ProblemError(422, "All units must belong to the project")
    for u in absorbed:
        u.lifecycle_status = "removed"
        u.removed_by_revision_id = revision_id
        u.version += 1
        for b in (
            await db.execute(
                select(UnitBoundary).where(
                    UnitBoundary.unit_id == u.id, UnitBoundary.is_current.is_(True)
                )
            )
        ).scalars():
            b.is_current = False
            b.status = "superseded"
    if ring is not None and sheet is not None:
        geometry.validate_ring(ring)
        for b in (
            await db.execute(
                select(UnitBoundary).where(
                    UnitBoundary.unit_id == survivor.id, UnitBoundary.is_current.is_(True)
                )
            )
        ).scalars():
            b.is_current = False
            b.status = "superseded"
        nb = UnitBoundary(
            id=new_id(),
            tenant_id=project.tenant_id,
            unit_id=survivor.id,
            sheet_id=sheet.id,
            polygon={"ring": ring},
            source="manual",
            status="draft",
        )
        _apply_calibration(nb, sheet)
        db.add(nb)
        await db.flush()
        await _refresh_measured_area(db, survivor, nb, project)
    survivor.verification_status = "in_review"
    survivor.version += 1
    db.add(
        UnitLineageEvent(
            id=new_id(),
            tenant_id=project.tenant_id,
            project_id=project.id,
            event_type="merged",
            revision_id=revision_id,
            from_unit_ids=[survivor.id, *[u.id for u in absorbed]],
            to_unit_ids=[survivor.id],
            decided_by=actor[0],
            note=note,
        )
    )
    await write_audit(
        db,
        tenant_id=project.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="unit",
        entity_id=survivor.id,
        action="merge",
        after={"absorbed": [str(u.id) for u in absorbed]},
    )
    return survivor


async def split_unit(
    db: AsyncSession,
    project: Project,
    unit: Unit,
    sheet: Sheet,
    rings: list[list[list[float]]],
    codes: list[str | None],
    actor: Actor,
    revision_id: uuid.UUID | None,
    note: str | None,
) -> list[Unit]:
    """Split: the first ring stays on the existing unit (keeps its id); others become new units."""
    if len(rings) < 2:
        raise ProblemError(422, "A split needs at least two boundaries")
    if sheet.floor_id != unit.floor_id:
        raise ProblemError(422, "Sheet is not assigned to the unit's floor")
    for r in rings:
        geometry.validate_ring(r)
    for b in (
        await db.execute(
            select(UnitBoundary).where(
                UnitBoundary.unit_id == unit.id, UnitBoundary.is_current.is_(True)
            )
        )
    ).scalars():
        b.is_current = False
        b.status = "superseded"
    first = UnitBoundary(
        id=new_id(),
        tenant_id=project.tenant_id,
        unit_id=unit.id,
        sheet_id=sheet.id,
        polygon={"ring": rings[0]},
        source="manual",
        status="draft",
    )
    _apply_calibration(first, sheet)
    db.add(first)
    await db.flush()
    await _refresh_measured_area(db, unit, first, project)
    unit.verification_status = "in_review"
    unit.version += 1
    result = [unit]
    for ring, code in zip(
        rings[1:], codes[1:] if len(codes) > 1 else [None] * (len(rings) - 1), strict=False
    ):
        new_unit, _ = await create_unit_from_boundary(
            db,
            project=project,
            sheet=sheet,
            ring=ring,
            unit_type=unit.unit_type,
            code=code,
            label=None,
            revision_id=revision_id or unit.created_from_revision_id,
            actor=actor,
        )
        result.append(new_unit)
    db.add(
        UnitLineageEvent(
            id=new_id(),
            tenant_id=project.tenant_id,
            project_id=project.id,
            event_type="split",
            revision_id=revision_id,
            from_unit_ids=[unit.id],
            to_unit_ids=[u.id for u in result],
            decided_by=actor[0],
            note=note,
        )
    )
    return result


async def approve_sheet(db: AsyncSession, sheet: Sheet, actor: Actor) -> int:
    """Reviewer approval: draft boundaries become approved, their units active + verified."""
    rows = await db.execute(
        select(UnitBoundary).where(
            UnitBoundary.sheet_id == sheet.id,
            UnitBoundary.is_current.is_(True),
            UnitBoundary.status == "draft",
        )
    )
    n = 0
    now = datetime.now(UTC)
    ids: list[uuid.UUID] = []
    project_id: uuid.UUID | None = None
    for b in rows.scalars():
        b.status = "approved"
        b.approved_by = actor[0]
        b.approved_at = now
        unit = (await db.execute(select(Unit).where(Unit.id == b.unit_id))).scalar_one()
        unit.lifecycle_status = "active"
        unit.verification_status = "verified"
        unit.version += 1
        ids.append(unit.id)
        project_id = unit.project_id
        n += 1
    if n:
        db.add(
            UnitLineageEvent(
                id=new_id(),
                tenant_id=sheet.tenant_id,
                project_id=project_id,
                event_type="approved",
                to_unit_ids=ids,
                decided_by=actor[0],
                note=f"sheet {sheet.id}",
            )
        )
        await write_audit(
            db,
            tenant_id=sheet.tenant_id,
            actor_user_id=actor[0],
            actor_role=actor[1],
            entity_type="sheet",
            entity_id=sheet.id,
            action="approve",
            after={"units": n},
        )
    return n


async def set_manual_area(
    db: AsyncSession, unit: Unit, area_type: str, value_m2: float, actor: Actor, verified: bool
) -> UnitArea:
    if value_m2 < 0:
        raise ProblemError(422, "Area cannot be negative")
    for old in (
        await db.execute(
            select(UnitArea).where(
                UnitArea.unit_id == unit.id,
                UnitArea.area_type == area_type,
                UnitArea.source == "manual",
                UnitArea.is_current.is_(True),
            )
        )
    ).scalars():
        old.is_current = False
    a = UnitArea(
        id=new_id(),
        tenant_id=unit.tenant_id,
        unit_id=unit.id,
        area_type=area_type,
        is_current=True,
        value_m2=value_m2,
        source="manual",
        verification_status="verified" if verified else "unverified",
        verified_by=actor[0] if verified else None,
        verified_at=datetime.now(UTC) if verified else None,
    )
    db.add(a)
    await db.flush()
    await write_audit(
        db,
        tenant_id=unit.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="unit_area",
        entity_id=a.id,
        action="set",
        after={
            "unit_id": str(unit.id),
            "area_type": area_type,
            "value_m2": value_m2,
            "verified": verified,
        },
    )
    return a


async def verify_area(db: AsyncSession, area: UnitArea, actor: Actor) -> UnitArea:
    area.verification_status = "verified"
    area.verified_by = actor[0]
    area.verified_at = datetime.now(UTC)
    return area
