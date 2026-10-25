"""Projects, buildings, floors and site features (plan §3.5)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from unitforma.audit.service import write_audit
from unitforma.core.errors import ProblemError
from unitforma.core.ids import new_id
from unitforma.core.slugs import SlugError, validate_slug
from unitforma.tenants.models import Building, Floor, Project, SiteFeature


def _snapshot(obj: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    out = {}
    for f in fields:
        v = getattr(obj, f)
        out[f] = str(v) if isinstance(v, uuid.UUID) else v
    return out


PROJECT_FIELDS = (
    "slug",
    "name",
    "status",
    "currency",
    "address",
    "description",
    "code_pattern",
    "area_definitions",
    "site_frame",
    "regulatory",
    "portal_settings",
)
BUILDING_FIELDS = ("code", "name", "kind", "site_transform", "placement_status", "sort_order")


def check_version(obj: Any, version: int) -> None:
    if obj.version != version:
        raise ProblemError(
            409,
            "Conflict",
            f"Record changed concurrently (current version {obj.version}, you sent {version})",
        )


async def create_project(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    data: dict[str, Any],
    actor: tuple[uuid.UUID, str],
    default_currency: str,
) -> Project:
    try:
        slug = validate_slug(data["slug"], reserved=frozenset())
    except SlugError as e:
        raise ProblemError(422, "Invalid slug", str(e)) from e
    if (
        await db.execute(
            select(Project.id).where(Project.tenant_id == tenant_id, Project.slug == slug)
        )
    ).first():
        raise ProblemError(409, "Project slug already in use in this tenant")
    project = Project(
        id=new_id(),
        tenant_id=tenant_id,
        slug=slug,
        name=data["name"],
        currency=(data.get("currency") or default_currency).upper(),
        address=data.get("address") or {},
        description=data.get("description"),
        area_definitions=[
            a if isinstance(a, dict) else a.model_dump() for a in data.get("area_definitions") or []
        ],
    )
    db.add(project)
    await db.flush()
    # every project has a virtual "site" building for outdoor units (parking, storage) — plan §3.5
    db.add(
        Building(
            id=new_id(),
            tenant_id=tenant_id,
            project_id=project.id,
            code="SITE",
            name="Site",
            kind="site",
            sort_order=9999,
            floors=[],
        )
    )
    await write_audit(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="project",
        entity_id=project.id,
        action="create",
        after=_snapshot(project, PROJECT_FIELDS),
    )
    return project


async def get_project(db: AsyncSession, tenant_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    p = (
        await db.execute(
            select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id)
        )
    ).scalar_one_or_none()
    if p is None:
        raise ProblemError(404, "Project not found")
    return p


async def update_project(
    db: AsyncSession,
    project: Project,
    changes: dict[str, Any],
    version: int,
    actor: tuple[uuid.UUID, str],
) -> Project:
    check_version(project, version)
    before = _snapshot(project, PROJECT_FIELDS)
    for k, v in changes.items():
        if k == "area_definitions" and v is not None:
            v = [a if isinstance(a, dict) else a.model_dump() for a in v]
        if v is not None:
            setattr(project, k, v)
    project.version += 1
    await write_audit(
        db,
        tenant_id=project.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="project",
        entity_id=project.id,
        action="update",
        before=before,
        after=_snapshot(project, PROJECT_FIELDS),
    )
    return project


async def list_buildings(db: AsyncSession, project_id: uuid.UUID) -> list[Building]:
    rows = await db.execute(
        select(Building)
        .where(Building.project_id == project_id)
        .order_by(Building.sort_order, Building.code)
        .options(selectinload(Building.floors))
    )
    return list(rows.scalars())


async def create_building(
    db: AsyncSession, project: Project, data: dict[str, Any], actor: tuple[uuid.UUID, str]
) -> Building:
    code = data["code"].upper()
    if (
        await db.execute(
            select(Building.id).where(Building.project_id == project.id, Building.code == code)
        )
    ).first():
        raise ProblemError(409, "Building code already exists in this project")
    b = Building(
        id=new_id(),
        tenant_id=project.tenant_id,
        project_id=project.id,
        code=code,
        name=data.get("name"),
        kind=data.get("kind", "building"),
        sort_order=data.get("sort_order", 0),
        floors=[],
    )
    db.add(b)
    await db.flush()
    await write_audit(
        db,
        tenant_id=project.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="building",
        entity_id=b.id,
        action="create",
        after=_snapshot(b, BUILDING_FIELDS),
    )
    return b


async def get_building(db: AsyncSession, tenant_id: uuid.UUID, building_id: uuid.UUID) -> Building:
    b = (
        await db.execute(
            select(Building)
            .where(Building.tenant_id == tenant_id, Building.id == building_id)
            .options(selectinload(Building.floors))
        )
    ).scalar_one_or_none()
    if b is None:
        raise ProblemError(404, "Building not found")
    return b


async def update_building(
    db: AsyncSession,
    b: Building,
    changes: dict[str, Any],
    version: int,
    actor: tuple[uuid.UUID, str],
) -> Building:
    check_version(b, version)
    before = _snapshot(b, BUILDING_FIELDS)
    for k, v in changes.items():
        if v is not None:
            setattr(b, k, v)
    b.version += 1
    await write_audit(
        db,
        tenant_id=b.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="building",
        entity_id=b.id,
        action="update",
        before=before,
        after=_snapshot(b, BUILDING_FIELDS),
    )
    return b


async def set_floors(
    db: AsyncSession, b: Building, floors: list[dict[str, Any]], actor: tuple[uuid.UUID, str]
) -> list[Floor]:
    """Create missing floors and update existing levels (idempotent)."""
    levels = [f["level"] for f in floors]
    if len(set(levels)) != len(levels):
        raise ProblemError(422, "Duplicate floor levels")
    existing = {f.level: f for f in b.floors}
    created = 0
    for i, f in enumerate(sorted(floors, key=lambda x: x["level"])):
        if f["level"] in existing:
            fl = existing[f["level"]]
            fl.display_name = f["display_name"]
            fl.height_m = f.get("height_m")
            fl.elevation_m = f.get("elevation_m")
            fl.sort_order = i
        else:
            db.add(
                Floor(
                    id=new_id(),
                    tenant_id=b.tenant_id,
                    building_id=b.id,
                    level=f["level"],
                    display_name=f["display_name"],
                    height_m=f.get("height_m"),
                    elevation_m=f.get("elevation_m"),
                    sort_order=i,
                )
            )
            created += 1
    await db.flush()
    await write_audit(
        db,
        tenant_id=b.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="building",
        entity_id=b.id,
        action="set_floors",
        after={"levels": sorted(levels), "created": created},
    )
    await db.refresh(b, attribute_names=["floors"])
    return sorted(b.floors, key=lambda f: f.level)


async def create_site_feature(
    db: AsyncSession, project: Project, data: dict[str, Any], actor: tuple[uuid.UUID, str]
) -> SiteFeature:
    sf = SiteFeature(id=new_id(), tenant_id=project.tenant_id, project_id=project.id, **data)
    db.add(sf)
    await db.flush()
    await write_audit(
        db,
        tenant_id=project.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="site_feature",
        entity_id=sf.id,
        action="create",
        after={"kind": sf.kind, "name": sf.name},
    )
    return sf
