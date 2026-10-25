"""Geometry service: collect massing input from the mapping, store generated GLBs, footprints.

Plan §11.3 (MVP 3D) and §3.5 (placement model): every unit with a calibrated current
boundary is extruded between its floor's elevation and elevation + height; buildings are
moved into the site frame with their ``site_transform``. Unplaced buildings stay at the
origin and are reported in ``stats`` so the reviewer knows what to place.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.core.errors import ProblemError
from unitforma.core.ids import new_id
from unitforma.geometry import massing
from unitforma.storage.service import get_storage, object_key
from unitforma.tenants.models import (
    Building,
    Floor,
    GeometryModel,
    Project,
    Unit,
    UnitBoundary,
)

log = structlog.get_logger()
DEFAULT_FLOOR_HEIGHT_M = 3.0


def floor_elevations(floors: list[Floor]) -> dict[uuid.UUID, tuple[float, float]]:
    """(base elevation, height) per floor. Explicit ``elevation_m`` wins; otherwise heights are
    stacked from the ground floor (level 0, or the lowest non-negative level)."""
    ordered = sorted(floors, key=lambda f: f.level)
    heights = {
        f.id: float(f.height_m) if f.height_m is not None else DEFAULT_FLOOR_HEIGHT_M
        for f in ordered
    }
    out: dict[uuid.UUID, tuple[float, float]] = {}
    ground_idx = next((i for i, f in enumerate(ordered) if f.level >= 0), 0)
    # above ground: stack upwards
    base = 0.0
    for f in ordered[ground_idx:]:
        out[f.id] = (float(f.elevation_m) if f.elevation_m is not None else base, heights[f.id])
        base = out[f.id][0] + heights[f.id]
    # below ground: stack downwards
    base = 0.0
    for f in reversed(ordered[:ground_idx]):
        base -= heights[f.id]
        out[f.id] = (float(f.elevation_m) if f.elevation_m is not None else base, heights[f.id])
    return out


async def collect(
    db: AsyncSession, project: Project
) -> tuple[list[massing.BuildingSolids], dict[str, Any]]:
    buildings = list(
        (
            await db.execute(
                select(Building)
                .where(Building.project_id == project.id, Building.kind == "building")
                .order_by(Building.sort_order, Building.code)
            )
        ).scalars()
    )
    floors = (
        list(
            (
                await db.execute(
                    select(Floor).where(Floor.building_id.in_([b.id for b in buildings]))
                )
            ).scalars()
        )
        if buildings
        else []
    )
    floors_by_building: dict[uuid.UUID, list[Floor]] = {}
    for f in floors:
        floors_by_building.setdefault(f.building_id, []).append(f)
    floor_by_id = {f.id: f for f in floors}
    rows = await db.execute(
        select(Unit, UnitBoundary)
        .join(UnitBoundary, UnitBoundary.unit_id == Unit.id)
        .where(
            Unit.project_id == project.id,
            Unit.lifecycle_status != "removed",
            UnitBoundary.is_current.is_(True),
        )
        .order_by(Unit.code)
    )
    solids_by_building: dict[uuid.UUID, list[massing.UnitSolid]] = {}
    seen: set[uuid.UUID] = set()
    units_total = 0
    skipped_uncalibrated = 0
    for unit, boundary in rows:
        if unit.id in seen:
            continue
        seen.add(unit.id)
        units_total += 1
        floor = floor_by_id.get(unit.floor_id)
        if floor is None:
            continue
        if not boundary.polygon_m:
            skipped_uncalibrated += 1
            continue
        elev = floor_elevations(floors_by_building[floor.building_id])
        base, height = elev[floor.id]
        bld = next(b for b in buildings if b.id == floor.building_id)
        solids_by_building.setdefault(bld.id, []).append(
            massing.UnitSolid(
                unit_id=str(unit.id),
                code=unit.code,
                unit_type=unit.unit_type,
                building_code=bld.code,
                floor_level=floor.level,
                ring_m=[(float(x), float(y)) for x, y in boundary.polygon_m["ring"]],
                base_m=base,
                height_m=height,
                extras={
                    "lifecycle_status": unit.lifecycle_status,
                    "verification_status": unit.verification_status,
                    "floor_id": str(floor.id),
                },
            )
        )
    out: list[massing.BuildingSolids] = []
    unplaced: list[str] = []
    for b in buildings:
        units = solids_by_building.get(b.id, [])
        if not units:
            continue
        if b.placement_status == "unplaced":
            unplaced.append(b.code)
        out.append(
            massing.BuildingSolids(
                building_id=str(b.id),
                code=b.code,
                name=b.name,
                placement=massing.Placement.from_dict(b.site_transform),
                units=units,
                extras={"placement_status": b.placement_status},
            )
        )
    stats = {
        "units_total": units_total,
        "units_skipped_uncalibrated": skipped_uncalibrated,
        "buildings_unplaced": unplaced,
    }
    return out, stats


async def current_massing(db: AsyncSession, project_id: uuid.UUID) -> GeometryModel | None:
    return (
        (
            await db.execute(
                select(GeometryModel)
                .where(
                    GeometryModel.project_id == project_id,
                    GeometryModel.kind == "massing_generated",
                    GeometryModel.is_current.is_(True),
                )
                .order_by(GeometryModel.created_at.desc())
            )
        )
        .scalars()
        .first()
    )


async def generate_massing(db: AsyncSession, project: Project) -> GeometryModel:
    """Build the GLB for the project, store it and make it the current massing model."""
    model = GeometryModel(
        id=new_id(),
        tenant_id=project.tenant_id,
        project_id=project.id,
        kind="massing_generated",
        status="generating",
        is_current=True,
    )
    for old in (
        await db.execute(
            select(GeometryModel).where(
                GeometryModel.project_id == project.id,
                GeometryModel.kind == "massing_generated",
                GeometryModel.is_current.is_(True),
            )
        )
    ).scalars():
        old.is_current = False
    db.add(model)
    await db.flush()
    try:
        buildings, stats = await collect(db, project)
        data, build_stats = massing.build_glb(
            buildings,
            {"project_id": str(project.id), "generated_at": datetime.now(UTC).isoformat()},
        )
        key = object_key(
            project.tenant_id, project.id, "geometry", f"massing-{model.id.hex[:12]}.glb"
        )
        get_storage().put_bytes(key, data, "model/gltf-binary")
        model.glb_key = key
        model.stats = {**stats, **build_stats}
        model.status = "ready"
        model.model_transform = {"frame": "site", "units": "m", "up": "+Y"}
    except Exception as e:  # noqa: BLE001 - keep the failure visible to the reviewer
        log.exception("geometry.massing_failed", project_id=str(project.id))
        model.status = "failed"
        model.error = str(e)[:2000]
    return model


def signed_url(model: GeometryModel) -> str | None:
    return get_storage().presign_get(model.glb_key, expires=3600) if model.glb_key else None


async def footprints(db: AsyncSession, project: Project) -> list[dict[str, Any]]:
    """Per building: outline of the lowest mapped floor in building-local metres, plus placement.

    The outline is the union of that floor's current calibrated boundaries (convex hull when
    the union is not a single polygon). Buildings without calibrated boundaries get ``None``.
    """
    buildings = list(
        (
            await db.execute(
                select(Building)
                .where(Building.project_id == project.id, Building.kind == "building")
                .order_by(Building.sort_order, Building.code)
            )
        ).scalars()
    )
    out: list[dict[str, Any]] = []
    for b in buildings:
        floors = sorted(
            (await db.execute(select(Floor).where(Floor.building_id == b.id))).scalars(),
            key=lambda f: f.level,
        )
        ring = None
        source_floor = None
        total_height = sum(
            float(f.height_m) if f.height_m is not None else DEFAULT_FLOOR_HEIGHT_M for f in floors
        )
        for f in floors:
            polys = [
                Polygon(bd.polygon_m["ring"])
                for (bd,) in await db.execute(
                    select(UnitBoundary)
                    .join(Unit, Unit.id == UnitBoundary.unit_id)
                    .where(
                        Unit.floor_id == f.id,
                        Unit.lifecycle_status != "removed",
                        UnitBoundary.is_current.is_(True),
                        UnitBoundary.polygon_m.is_not(None),
                    )
                )
            ]
            polys = [p.buffer(0) for p in polys if not p.is_empty]
            if not polys:
                continue
            u = unary_union(polys)
            if isinstance(u, MultiPolygon) or u.geom_type != "Polygon":
                u = u.convex_hull
            u = u.simplify(0.05, preserve_topology=True)
            ring = [[round(x, 3), round(y, 3)] for x, y in u.exterior.coords[:-1]]
            source_floor = f.level
            break
        out.append(
            {
                "building_id": b.id,
                "code": b.code,
                "name": b.name,
                "placement_status": b.placement_status,
                "site_transform": b.site_transform or {},
                "version": b.version,
                "ring_m": ring,
                "source_floor_level": source_floor,
                "floors": len(floors),
                "height_m": round(total_height, 2),
            }
        )
    return out


async def require_model(
    db: AsyncSession, tenant_id: uuid.UUID, project_id: uuid.UUID
) -> GeometryModel:
    m = await current_massing(db, project_id)
    if m is None or m.tenant_id != tenant_id:
        raise ProblemError(404, "No massing model yet", "Approve a mapped sheet or generate it")
    return m
