"""The layout registry (ADR-0022): plan types of a project that own the media shared by the
units linked to them.

A layout is a code (unique per project without case) and a name. Units link by
``units.layout_id``; this release also mirrors the code into ``units.attributes.layout`` so the
previous release keeps reading it (contract step E1). Deleting a layout refuses while units are
linked unless the caller asks to unlink them; its media objects are removed at once, because the
retention sweep (ADR-0021) knows project and document prefixes only.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.audit.service import write_audit
from unitforma.core.errors import ProblemError
from unitforma.core.ids import new_id
from unitforma.sales import media as media_service
from unitforma.tenants.models import (
    Building,
    Floor,
    Project,
    Unit,
    UnitLayout,
    UnitMedia,
    UnitSales,
)

Actor = tuple[uuid.UUID, str]
LAYOUT_IN_USE = "https://unitforma.com/problems/layout-in-use"


def clean_code(code: str) -> str:
    c = (code or "").strip()
    if not c or len(c) > 40:
        raise ProblemError(422, "Layout code is 1 to 40 characters")
    return c


async def list_layouts(db: AsyncSession, project: Project) -> list[UnitLayout]:
    rows = await db.execute(
        select(UnitLayout)
        .where(UnitLayout.project_id == project.id)
        .order_by(func.lower(UnitLayout.code))
    )
    return list(rows.scalars())


async def by_code(db: AsyncSession, project_id: uuid.UUID, code: str) -> UnitLayout | None:
    return (
        await db.execute(
            select(UnitLayout).where(
                UnitLayout.project_id == project_id,
                func.lower(UnitLayout.code) == code.strip().lower(),
            )
        )
    ).scalar_one_or_none()


async def get_layout(db: AsyncSession, tenant_id: uuid.UUID, layout_id: uuid.UUID) -> UnitLayout:
    row = (
        await db.execute(
            select(UnitLayout).where(UnitLayout.tenant_id == tenant_id, UnitLayout.id == layout_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise ProblemError(404, "Layout not found")
    return row


async def members(db: AsyncSession, layout_id: uuid.UUID) -> list[Unit]:
    rows = await db.execute(
        select(Unit)
        .where(Unit.layout_id == layout_id, Unit.lifecycle_status != "removed")
        .order_by(Unit.code)
    )
    return list(rows.scalars())


async def overview(db: AsyncSession, project: Project) -> list[dict[str, Any]]:
    """Every layout of the project with its member units (code, availability, floor, building),
    media counts and a signed cover: the Layouts page in one call."""
    layouts = await list_layouts(db, project)
    if not layouts:
        return []
    ids = [lay.id for lay in layouts]
    units = (
        await db.execute(
            select(Unit, Building.code, Floor.level, UnitSales.availability)
            .join(Building, Building.id == Unit.building_id)
            .join(Floor, Floor.id == Unit.floor_id)
            .outerjoin(UnitSales, UnitSales.unit_id == Unit.id)
            .where(Unit.layout_id.in_(ids), Unit.lifecycle_status != "removed")
            .order_by(Unit.code)
        )
    ).all()
    by_layout: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for u, bcode, level, availability in units:
        by_layout.setdefault(u.layout_id, []).append(
            {
                "unit_id": u.id,
                "code": u.code,
                "availability": availability or "available",
                "building_code": bcode,
                "floor_level": level,
            }
        )
    media = list(
        (
            await db.execute(
                select(UnitMedia)
                .where(UnitMedia.layout_id.in_(ids), UnitMedia.status == "ready")
                .order_by(UnitMedia.sort_order, UnitMedia.created_at)
            )
        ).scalars()
    )
    media_by_layout: dict[uuid.UUID, list[UnitMedia]] = {}
    for m in media:
        media_by_layout.setdefault(m.layout_id, []).append(m)
    out = []
    for lay in layouts:
        items = media_by_layout.get(lay.id, [])
        cover = next(
            (m for m in items if m.is_public and m.mime.startswith("image/")),
            None,
        )
        out.append(
            {
                "layout": lay,
                "units": by_layout.get(lay.id, []),
                "media_count": len(items),
                "public_media_count": sum(1 for m in items if m.is_public),
                "cover_url": media_service.signed_url(cover) if cover else None,
            }
        )
    return out


async def create(
    db: AsyncSession, project: Project, data: dict[str, Any], actor: Actor
) -> UnitLayout:
    code = clean_code(data.get("code", ""))
    if await by_code(db, project.id, code) is not None:
        raise ProblemError(409, "Layout code already exists", f"{code} is taken in this project")
    lay = UnitLayout(
        id=new_id(),
        tenant_id=project.tenant_id,
        project_id=project.id,
        code=code,
        name=_name(data.get("name")),
    )
    db.add(lay)
    await db.flush()
    await _audit(db, lay, actor, "create", {"code": lay.code, "name": lay.name})
    return lay


async def update(
    db: AsyncSession, lay: UnitLayout, data: dict[str, Any], version: int, actor: Actor
) -> UnitLayout:
    if lay.version != version:
        raise ProblemError(409, "Conflict", f"Layout changed (current version {lay.version})")
    before = {"code": lay.code, "name": lay.name}
    if "code" in data and data["code"] is not None:
        code = clean_code(data["code"])
        other = await by_code(db, lay.project_id, code)
        if other is not None and other.id != lay.id:
            raise ProblemError(
                409, "Layout code already exists", f"{code} is taken in this project"
            )
        if code != lay.code:
            lay.code = code
            # the mirror of every member follows the rename (ADR-0022 Decision 7)
            for u in await members(db, lay.id):
                u.attributes = {**(u.attributes or {}), "layout": code}
                u.version += 1
    if "name" in data:
        lay.name = _name(data["name"])
    lay.version += 1
    await _audit(db, lay, actor, "update", {"code": lay.code, "name": lay.name}, before)
    return lay


async def delete(db: AsyncSession, lay: UnitLayout, *, unlink_units: bool, actor: Actor) -> None:
    linked = await members(db, lay.id)
    if linked and not unlink_units:
        raise ProblemError(
            409,
            "Layout in use",
            f"{len(linked)} unit(s) link to {lay.code}; unlink them first "
            "or send unlink_units=true",
            type_=LAYOUT_IN_USE,
            extra={"units": [u.code for u in linked]},
        )
    for u in linked:
        u.layout_id = None
        attrs = dict(u.attributes or {})
        attrs.pop("layout", None)
        u.attributes = attrs
        u.version += 1
    media = await media_service.list_media(db, layout_id=lay.id)
    for m in media:
        await media_service.delete(db, m, actor)
    await _audit(
        db,
        lay,
        actor,
        "delete",
        {"code": lay.code, "unlinked": [u.code for u in linked], "media": len(media)},
    )
    await db.delete(lay)
    await db.flush()


def _name(v: Any) -> str | None:
    s = (v or "").strip() if isinstance(v, str) else None
    if s and len(s) > 120:
        raise ProblemError(422, "Layout name is limited to 120 characters")
    return s or None


async def _audit(db, lay: UnitLayout, actor: Actor, action: str, after, before=None) -> None:
    await write_audit(
        db,
        tenant_id=lay.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="unit_layout",
        entity_id=lay.id,
        action=action,
        before=before,
        after=after,
    )
