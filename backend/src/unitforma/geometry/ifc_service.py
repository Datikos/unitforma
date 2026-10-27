"""IFC models per building: ingestion (worker), space links and their review (ADR-0006 C3–C5).

Unit ids, prices, leads and favourites are never touched by an IFC import: the import creates a
model and a list of spaces; the reviewer links spaces to the units that exist.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.audit.service import write_audit
from unitforma.core.db import tenant_session
from unitforma.core.errors import ProblemError
from unitforma.core.ids import new_id
from unitforma.geometry import ifc, ifc_match, plan_spaces
from unitforma.geometry.service import floor_elevations
from unitforma.storage.service import get_storage, object_key
from unitforma.tenants.models import (
    Building,
    Document,
    DocumentRevision,
    Floor,
    GeometryModel,
    IfcSpaceLink,
    Project,
    Unit,
    UnitArea,
    UnitBoundary,
)

log = structlog.get_logger()

AREA_TYPES = {"net_floor_area": "net_internal", "gross_floor_area": "gross_internal"}
Actor = tuple[uuid.UUID, str]


# --------------------------------------------------------------------------- worker body
async def ingest_ifc(tenant_id: uuid.UUID, revision_id: uuid.UUID) -> dict[str, Any]:
    """Convert an uploaded IFC revision into the building's current model and its space list."""
    storage = get_storage()
    async with tenant_session(tenant_id, scope="tenant") as db:
        rev = (
            await db.execute(select(DocumentRevision).where(DocumentRevision.id == revision_id))
        ).scalar_one()
        doc = (
            await db.execute(select(Document).where(Document.id == rev.document_id))
        ).scalar_one()
        if doc.building_id is None:
            rev.processing_status = "failed"
            rev.processing_error = (
                "An IFC model must be filed under a building: edit the document and pick one"
            )
            return {"error": rev.processing_error}
        rev.processing_status = "processing"
        rev.processing_error = None
        project_id, building_id, object_key_ = doc.project_id, doc.building_id, rev.object_key
    data = storage.get_bytes(object_key_)
    try:
        parsed = ifc.parse_ifc(data)
        extra: list[tuple[ifc.Space, list[float], list[int]]] = []
        plan_fit: dict[str, Any] | None = None
        if not parsed.spaces:
            # ADR-0030 Decision 3: no IfcSpace in the file → the approved plan outlines of the
            # building, placed in the IFC frame
            async with tenant_session(tenant_id, scope="tenant") as db:
                plan_floors, outlines = await _plan_inputs(db, project_id, building_id)
            extra, plan_fit = plan_spaces.build(
                parsed, plan_floors, outlines, building_id=building_id
            )
        model_in = ifc.pack_ifc(parsed, extra_spaces=extra)
        if plan_fit is not None:
            model_in = replace(model_in, stats={**model_in.stats, "plan_fit": plan_fit})
        # Draco in the heavy image (ADR-0006 C2a); the 15 MB budget above applies to the raw GLB,
        # which also bounds what the browser decodes
        glb_small, compression = ifc.compress_glb(model_in.glb)
        model_in = replace(
            model_in,
            glb=glb_small,
            stats={**model_in.stats, "compression": compression, "bytes_raw": len(model_in.glb)},
        )
    except ifc.IfcError as e:
        async with tenant_session(tenant_id, scope="tenant") as db:
            rev = (
                await db.execute(select(DocumentRevision).where(DocumentRevision.id == revision_id))
            ).scalar_one()
            rev.processing_status = "failed"
            rev.processing_error = str(e)[:2000]
        return {"error": str(e)[:500]}
    async with tenant_session(tenant_id, scope="tenant") as db:
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        for old in (
            await db.execute(
                select(GeometryModel).where(
                    GeometryModel.building_id == building_id,
                    GeometryModel.kind == "ifc",
                    GeometryModel.is_current.is_(True),
                )
            )
        ).scalars():
            old.is_current = False
        model = GeometryModel(
            id=new_id(),
            tenant_id=tenant_id,
            project_id=project_id,
            building_id=building_id,
            kind="ifc",
            revision_id=revision_id,
            status="generating",
            is_current=True,
            model_transform={
                "frame": "ifc",
                "units": "m",
                "up": "+Y",
                "offset_m": model_in.stats.get("offset_m"),
            },
        )
        db.add(model)
        await db.flush()
        floors = list(
            (await db.execute(select(Floor).where(Floor.building_id == building_id))).scalars()
        )
        level_of_floor = {f.id: f.level for f in floors}
        units = await _units_with_labels(db, project_id, building_id)
        matches = ifc_match.match_spaces(
            [
                ifc_match.SpaceRef(
                    s.global_id,
                    s.name,
                    s.long_name,
                    s.storey.index if s.storey else None,
                    s.storey.elevation_m if s.storey else None,
                )
                for s in model_in.spaces
                if s.source == "ifc"
            ],
            [ifc_match.FloorRef(f.id, f.level, _f(f.elevation_m)) for f in floors],
            units,
        )
        # a plan space is its unit by construction; the reviewer confirms the alignment
        fit_iou = (plan_fit or {}).get("iou")
        matches += [
            ifc_match.Match(s.global_id, s.floor_id, s.unit_id, fit_iou, "suggested")
            for s in model_in.spaces
            if s.source == "plan"
        ]
        by_gid = {m.global_id: m for m in matches}
        for s in model_in.spaces:
            m = by_gid[s.global_id]
            db.add(
                IfcSpaceLink(
                    id=new_id(),
                    tenant_id=tenant_id,
                    project_id=project_id,
                    building_id=building_id,
                    geometry_model_id=model.id,
                    ifc_global_id=s.global_id,
                    name=(s.name or None) and s.name[:200],
                    long_name=(s.long_name or None) and s.long_name[:200],
                    storey_name=s.storey.name[:200] if s.storey else None,
                    storey_elevation_m=s.storey.elevation_m if s.storey else None,
                    floor_id=m.floor_id,
                    unit_id=m.unit_id,
                    status=m.status,
                    confidence=m.confidence,
                    footprint_m={"ring": s.footprint_m} if s.footprint_m else None,
                    areas=s.areas,
                    source=s.source,
                )
            )
        # the viewer compares floor_level with the project's floor levels, not storey indexes
        glb = ifc.relink_glb(
            model_in.glb,
            {
                m.global_id: {"unit_id": None, "floor_level": level_of_floor.get(m.floor_id)}
                for m in matches
                if m.floor_id is not None
            },
        )
        key = object_key(tenant_id, project_id, "geometry", f"ifc-{model.id.hex[:12]}.glb")
        storage.put_bytes(key, glb, "model/gltf-binary")
        model.glb_key = key
        model.stats = {
            **model_in.stats,
            "bytes": len(glb),
            "building_name": model_in.building_name,
            "spaces_suggested": sum(1 for m in matches if m.status == "suggested"),
            "spaces_unmatched": sum(1 for m in matches if m.status == "unmatched"),
            "storeys_without_floor": sum(
                1
                for st in model_in.storeys
                if not any(
                    m.floor_id
                    for m in matches
                    if any(s.global_id == m.global_id and s.storey is st for s in model_in.spaces)
                )
            ),
        }
        model.status = "ready"
        rev = (
            await db.execute(select(DocumentRevision).where(DocumentRevision.id == revision_id))
        ).scalar_one()
        rev.processing_status = "done"
        rev.page_count = 0
        await write_audit(
            db,
            tenant_id=tenant_id,
            actor_user_id=rev.uploaded_by,
            actor_role="system",
            entity_type="geometry_model",
            entity_id=model.id,
            action="ifc_ingest",
            after={
                "building_id": str(building_id),
                "spaces": len(model_in.spaces),
                "bytes": len(model_in.glb),
                "project": project.slug,
            },
        )
        return {"model_id": str(model.id), "status": model.status, "stats": model.stats}


def _f(v: Any) -> float | None:
    return float(v) if v is not None else None


async def _plan_inputs(
    db: AsyncSession, project_id: uuid.UUID, building_id: uuid.UUID
) -> tuple[list[plan_spaces.PlanFloor], list[plan_spaces.Outline]]:
    """The building's floors with stacked elevations, and one current calibrated outline per
    non-removed unit of every building of the project (the other buildings' outlines carry
    their building and floor level, for the project-scope fit; ADR-0030 Decision 4 inputs)."""
    all_floors = list(
        (
            await db.execute(
                select(Floor)
                .join(Building, Building.id == Floor.building_id)
                .where(Building.project_id == project_id)
            )
        ).scalars()
    )
    floors = [f for f in all_floors if f.building_id == building_id]
    level_of = {f.id: f.level for f in all_floors}
    elev = floor_elevations(floors)
    plan_floors = [
        plan_spaces.PlanFloor(
            id=f.id,
            level=f.level,
            elevation_m=_f(f.elevation_m),
            base_m=elev[f.id][0],
            height_m=elev[f.id][1],
        )
        for f in floors
    ]
    rows = await db.execute(
        select(Unit, UnitBoundary)
        .join(UnitBoundary, UnitBoundary.unit_id == Unit.id)
        .where(
            Unit.project_id == project_id,
            Unit.lifecycle_status != "removed",
            UnitBoundary.is_current.is_(True),
        )
        .order_by(Unit.code)
    )
    seen: set[uuid.UUID] = set()
    outlines: list[plan_spaces.Outline] = []
    for unit, bd in rows:
        ring = (bd.polygon_m or {}).get("ring") if isinstance(bd.polygon_m, dict) else None
        if unit.id in seen or not ring or unit.floor_id is None:
            continue
        seen.add(unit.id)
        outlines.append(
            plan_spaces.Outline(
                unit.id,
                unit.code,
                unit.floor_id,
                ring,
                building_id=unit.building_id,
                level=level_of.get(unit.floor_id),
            )
        )
    return plan_floors, outlines


async def confirm_plan_links(db: AsyncSession, model: GeometryModel, actor: Actor) -> int:
    """Confirm every suggested plan space of the model as its unit in one go (one relink, one
    audit row): the alignment was judged right for the whole building (ADR-0030 C1)."""
    links = await list_links(db, model.id)
    taken = {lk.unit_id for lk in links if lk.status == "confirmed" and lk.unit_id}
    done = 0
    for lk in links:
        if lk.source != "plan" or lk.status != "suggested" or lk.unit_id is None:
            continue
        if lk.unit_id in taken:
            continue
        lk.status, lk.confidence = "confirmed", Decimal("1.00")
        taken.add(lk.unit_id)
        done += 1
    if done:
        await db.flush()
        await write_audit(
            db,
            tenant_id=model.tenant_id,
            actor_user_id=actor[0],
            actor_role=actor[1],
            entity_type="geometry_model",
            entity_id=model.id,
            action="confirm_plan_spaces",
            after={"confirmed": done},
        )
        await relink_model(db, model.id)
    return done


async def _units_with_labels(
    db: AsyncSession, project_id: uuid.UUID, building_id: uuid.UUID
) -> list[ifc_match.UnitRef]:
    rows = await db.execute(
        select(Unit, UnitBoundary.label)
        .outerjoin(
            UnitBoundary,
            (UnitBoundary.unit_id == Unit.id) & (UnitBoundary.is_current.is_(True)),
        )
        .where(
            Unit.project_id == project_id,
            Unit.building_id == building_id,
            Unit.lifecycle_status != "removed",
        )
    )
    seen: set[uuid.UUID] = set()
    out = []
    for unit, label in rows:
        if unit.id in seen:
            continue
        seen.add(unit.id)
        out.append(ifc_match.UnitRef(unit.id, unit.code, unit.floor_id, label))
    return out


# --------------------------------------------------------------------------- reads
async def current_model(db: AsyncSession, building_id: uuid.UUID) -> GeometryModel | None:
    return (
        await db.execute(
            select(GeometryModel).where(
                GeometryModel.building_id == building_id,
                GeometryModel.kind == "ifc",
                GeometryModel.is_current.is_(True),
            )
        )
    ).scalar_one_or_none()


async def list_links(db: AsyncSession, model_id: uuid.UUID) -> list[IfcSpaceLink]:
    rows = await db.execute(
        select(IfcSpaceLink)
        .where(IfcSpaceLink.geometry_model_id == model_id)
        .order_by(IfcSpaceLink.storey_elevation_m, IfcSpaceLink.name)
    )
    return list(rows.scalars())


async def get_link(db: AsyncSession, tenant_id: uuid.UUID, link_id: uuid.UUID) -> IfcSpaceLink:
    link = (
        await db.execute(
            select(IfcSpaceLink).where(
                IfcSpaceLink.tenant_id == tenant_id, IfcSpaceLink.id == link_id
            )
        )
    ).scalar_one_or_none()
    if link is None:
        raise ProblemError(404, "Space link not found")
    return link


def link_counts(links: list[IfcSpaceLink]) -> dict[str, int]:
    out = {"confirmed": 0, "suggested": 0, "unmatched": 0, "rejected": 0}
    for lk in links:
        out[lk.status] = out.get(lk.status, 0) + 1
    return out


# --------------------------------------------------------------------------- review
async def decide(
    db: AsyncSession,
    link: IfcSpaceLink,
    *,
    decision: str,
    unit_id: uuid.UUID | None,
    actor: Actor,
) -> IfcSpaceLink:
    """Confirm (as the suggested or another unit), reject, or reset a space link. Confirming
    writes the space's IFC quantities as ``ifc_quantity`` areas of the unit (Decision 5)."""
    before = {"status": link.status, "unit_id": str(link.unit_id) if link.unit_id else None}
    if decision == "confirm":
        target = unit_id or link.unit_id
        if target is None:
            raise ProblemError(422, "Pick the unit this space is")
        unit = (
            await db.execute(
                select(Unit).where(
                    Unit.id == target,
                    Unit.building_id == link.building_id,
                    Unit.lifecycle_status != "removed",
                )
            )
        ).scalar_one_or_none()
        if unit is None:
            raise ProblemError(422, "Unit does not belong to this building")
        other = (
            await db.execute(
                select(IfcSpaceLink.id).where(
                    IfcSpaceLink.geometry_model_id == link.geometry_model_id,
                    IfcSpaceLink.unit_id == unit.id,
                    IfcSpaceLink.status == "confirmed",
                    IfcSpaceLink.id != link.id,
                )
            )
        ).first()
        if other:
            raise ProblemError(409, "Another space is already confirmed as this unit")
        link.unit_id, link.status, link.confidence = unit.id, "confirmed", Decimal("1.00")
        await _write_areas(db, link, unit)
    elif decision == "reject":
        link.status, link.unit_id = "rejected", None
    elif decision == "reset":
        link.status, link.unit_id, link.confidence = "unmatched", None, None
    else:
        raise ProblemError(422, "Unknown decision")
    await db.flush()
    await write_audit(
        db,
        tenant_id=link.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="ifc_space_link",
        entity_id=link.id,
        action=decision,
        before=before,
        after={"status": link.status, "unit_id": str(link.unit_id) if link.unit_id else None},
    )
    await relink_model(db, link.geometry_model_id)
    return link


async def _write_areas(db: AsyncSession, link: IfcSpaceLink, unit: Unit) -> None:
    project = (await db.execute(select(Project).where(Project.id == unit.project_id))).scalar_one()
    defined = {d.get("key") for d in (project.area_definitions or []) if isinstance(d, dict)}
    for src_key, area_type in AREA_TYPES.items():
        value = (link.areas or {}).get(src_key)
        if value is None or area_type not in defined:
            continue
        for old in (
            await db.execute(
                select(UnitArea).where(
                    UnitArea.unit_id == unit.id,
                    UnitArea.area_type == area_type,
                    UnitArea.source == "ifc_quantity",
                    UnitArea.is_current.is_(True),
                )
            )
        ).scalars():
            old.is_current = False
        db.add(
            UnitArea(
                id=new_id(),
                tenant_id=unit.tenant_id,
                unit_id=unit.id,
                area_type=area_type,
                value_m2=Decimal(str(value)),
                source="ifc_quantity",
                source_ref={
                    "ifc_global_id": link.ifc_global_id,
                    "geometry_model_id": str(link.geometry_model_id),
                    "quantity": src_key,
                },
                verification_status="unverified",
                is_current=True,
            )
        )


async def relink_model(db: AsyncSession, model_id: uuid.UUID) -> GeometryModel | None:
    """Rewrite the GLB's space extras so confirmed spaces pick as their unit (new object key;
    the previous file is left for in-flight viewers)."""
    model = (
        await db.execute(select(GeometryModel).where(GeometryModel.id == model_id))
    ).scalar_one_or_none()
    if model is None or not model.glb_key:
        return model
    links = await list_links(db, model_id)
    mapping = await _space_targets(db, links, listed=None)
    storage = get_storage()
    data = ifc.relink_glb(storage.get_bytes(model.glb_key), mapping)
    key = object_key(
        model.tenant_id,
        model.project_id,
        "geometry",
        f"ifc-{model.id.hex[:12]}-{datetime.now(UTC).strftime('%H%M%S%f')}.glb",
    )
    storage.put_bytes(key, data, "model/gltf-binary")
    model.glb_key = key
    model.stats = {
        **(model.stats or {}),
        "spaces_confirmed": sum(1 for v in mapping.values() if v and v.get("unit_id")),
    }
    return model


async def _space_targets(
    db: AsyncSession, links: list[IfcSpaceLink], *, listed: set[uuid.UUID] | None
) -> dict[str, dict[str, Any] | None]:
    """What each space node should carry: the unit id and code for confirmed spaces (only listed
    ones when publishing), the matched floor's level for all; ``None`` hides a space entirely."""
    unit_ids = [lk.unit_id for lk in links if lk.unit_id]
    units = (
        {u.id: u for u in (await db.execute(select(Unit).where(Unit.id.in_(unit_ids)))).scalars()}
        if unit_ids
        else {}
    )
    floor_ids = [lk.floor_id for lk in links if lk.floor_id]
    levels = (
        {
            f.id: f.level
            for f in (await db.execute(select(Floor).where(Floor.id.in_(floor_ids)))).scalars()
        }
        if floor_ids
        else {}
    )
    out: dict[str, dict[str, Any] | None] = {}
    for lk in links:
        unit = units.get(lk.unit_id) if lk.status == "confirmed" and lk.unit_id else None
        if listed is not None and (unit is None or unit.id not in listed):
            out[lk.ifc_global_id] = None  # published copy: not pickable
            continue
        out[lk.ifc_global_id] = {
            "unit_id": str(unit.id) if unit else None,
            "code": unit.code if unit else None,
            "floor_level": levels.get(lk.floor_id) if lk.floor_id else None,
        }
    return out


async def public_glb(db: AsyncSession, model: GeometryModel, listed: set[uuid.UUID]) -> bytes:
    """The published variant: only confirmed spaces of listed units are pickable."""
    links = await list_links(db, model.id)
    mapping = await _space_targets(db, links, listed=listed)
    return ifc.relink_glb(get_storage().get_bytes(model.glb_key), mapping)


async def building_for_link(db: AsyncSession, link: IfcSpaceLink) -> Building:
    return (await db.execute(select(Building).where(Building.id == link.building_id))).scalar_one()
