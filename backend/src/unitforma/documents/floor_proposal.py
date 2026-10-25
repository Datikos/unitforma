"""Floor proposal for a building from its sheets' level markers (ADR-0010 Decision 1)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.documents import levels, storeys
from unitforma.tenants.models import Building, Document, DocumentRevision, Floor, Project, Sheet


async def markers_for_building(db: AsyncSession, building: Building) -> dict[uuid.UUID, list]:
    """Cleaned level markers per sheet: current revisions of the building's documents, plus
    project-level floor plans when the project has one building besides SITE."""
    others = (
        await db.execute(
            select(Building.id).where(
                Building.project_id == building.project_id,
                Building.kind == "building",
                Building.id != building.id,
            )
        )
    ).first()
    cond = Document.building_id == building.id
    if others is None:
        cond = cond | ((Document.building_id.is_(None)) & (Document.kind == "floor_plan"))
    rows = await db.execute(
        select(Sheet)
        .join(DocumentRevision, DocumentRevision.id == Sheet.revision_id)
        .join(Document, Document.id == DocumentRevision.document_id)
        .where(
            Document.project_id == building.project_id,
            Document.current_revision_id == DocumentRevision.id,
            cond,
            Sheet.excluded.is_(False),
        )
    )
    out: dict[uuid.UUID, list] = {}
    for sheet in rows.scalars():
        hints = sheet.hints or {}
        if hints.get("duplicate_of"):
            continue
        ms = [levels.Marker.from_dict(d) for d in hints.get("level_markers") or []]
        if ms:
            out[sheet.id] = ms
    return out


async def floor_proposal(db: AsyncSession, building: Building) -> dict[str, Any]:
    markers = await markers_for_building(db, building)
    floors = (await db.execute(select(Floor).where(Floor.building_id == building.id))).scalars()
    existing = [
        storeys.ExistingFloor(
            id=f.id,
            level=f.level,
            display_name=f.display_name,
            elevation_m=float(f.elevation_m) if f.elevation_m is not None else None,
            height_m=float(f.height_m) if f.height_m is not None else None,
        )
        for f in floors
    ]
    proposed, unmatched, roof = storeys.propose(markers, existing)
    taken = frozenset(
        (
            await db.execute(
                select(Building.code).where(Building.project_id == building.project_id)
            )
        ).scalars()
    )
    blocks = storeys.detect_blocks(markers, taken_codes=taken, source_code=building.code)
    return {
        "building_id": str(building.id),
        "sheets_with_markers": len(markers),
        "split_level": len(blocks) >= 2,
        "blocks": [b.as_dict() for b in blocks],
        "floors": [p.as_dict() for p in proposed],
        "unmatched_existing": [
            {"floor_id": str(f.id), "level": f.level, "display_name": f.display_name}
            for f in unmatched
        ],
        "roof": roof,
        "counts": {
            "new": sum(1 for p in proposed if p.status == "new"),
            "update": sum(1 for p in proposed if p.status == "update"),
            "existing": sum(1 for p in proposed if p.status == "existing"),
        },
    }


async def accept_blocks(
    db: AsyncSession,
    source: Building,
    blocks: list[dict[str, Any]],
    *,
    delete_source: bool,
    actor: tuple[uuid.UUID, str],
) -> tuple[list[Building], bool]:
    """One building per block with its floors (ADR-0013 Decision 4); the source building is
    removed when asked and empty. Returns the new buildings and whether the source went."""
    from unitforma.core.errors import ProblemError
    from unitforma.projects import service as projects

    if not blocks:
        raise ProblemError(422, "No blocks to create")
    project = (
        await db.execute(select(Project).where(Project.id == source.project_id))
    ).scalar_one()
    codes = [str(b.get("code") or "").upper() for b in blocks]
    if len(set(codes)) != len(codes) or any(not c for c in codes):
        raise ProblemError(422, "Block codes must be unique and not empty")
    created: list[Building] = []
    for code in codes:
        if code == source.code.upper() and not delete_source:
            raise ProblemError(409, f"Code {code} is the source building; remove it or rename")
    removed = False
    if delete_source:
        await projects.delete_building(db, source, actor)
        removed = True
    for blk, code in zip(blocks, codes, strict=True):
        b = await projects.create_building(
            db, project, {"code": code, "name": blk.get("name")}, actor
        )
        floors = blk.get("floors") or []
        if floors:
            await projects.set_floors(db, b, floors, actor)
        created.append(b)
    return created, removed
