"""Floor proposal for a building from its sheets' level markers (ADR-0010 Decision 1)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.documents import levels, storeys
from unitforma.tenants.models import Building, Document, DocumentRevision, Floor, Sheet


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
    return {
        "building_id": str(building.id),
        "sheets_with_markers": len(markers),
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
