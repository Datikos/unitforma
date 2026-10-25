"""Publish, preview, unpublish, readiness checklist, unit publication flags (plan §9.3, §6.1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.audit.service import write_audit
from unitforma.core.errors import ProblemError
from unitforma.core.settings import get_settings
from unitforma.publishing import portal, snapshot, tokens
from unitforma.sales import service as sales
from unitforma.tenants.models import (
    Building,
    Document,
    Floor,
    GeometryModel,
    PortalDomain,
    Project,
    Publication,
    Sheet,
    Unit,
    UnitBoundary,
)

Actor = tuple[uuid.UUID, str]
PUBLICATION_STATES = ("unpublished", "published", "hidden")


async def portal_base_url(db: AsyncSession, project: Project) -> str | None:
    """Primary portal host of the tenant (custom domain preferred when active)."""
    rows = list(
        (
            await db.execute(
                select(PortalDomain).where(
                    PortalDomain.tenant_id == project.tenant_id,
                    PortalDomain.status == "active",
                    PortalDomain.verification_status == "verified",
                )
            )
        ).scalars()
    )
    rows.sort(key=lambda d: (not d.is_primary, d.kind != "custom", d.hostname))
    for d in rows:
        if d.project_id is None or d.project_id == project.id:
            base = f"{get_settings().public_scheme}://{d.hostname}"
            return base if d.project_id == project.id else f"{base}/projects/{project.slug}"
    return None


async def set_unit_publication(
    db: AsyncSession,
    project: Project,
    *,
    unit_ids: list[uuid.UUID] | None,
    all_active: bool,
    status: str,
    actor: Actor,
) -> int:
    if status not in PUBLICATION_STATES:
        raise ProblemError(422, f"status must be one of {', '.join(PUBLICATION_STATES)}")
    q = update(Unit).where(Unit.project_id == project.id, Unit.lifecycle_status != "removed")
    if all_active:
        q = q.where(Unit.lifecycle_status == "active")
    elif unit_ids:
        q = q.where(Unit.id.in_(unit_ids))
    else:
        raise ProblemError(422, "Give unit_ids or all_active")
    q = q.where(Unit.publication_status != status).values(
        publication_status=status, version=Unit.version + 1
    )
    n = (await db.execute(q)).rowcount or 0
    await write_audit(
        db,
        tenant_id=project.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="project",
        entity_id=project.id,
        action="unit_publication",
        after={
            "status": status,
            "units": n,
            "all_active": all_active,
            "unit_ids": [str(u) for u in (unit_ids or [])][:500],
        },
    )
    return n


async def readiness(db: AsyncSession, project: Project) -> dict[str, Any]:
    """Checklist before publishing (plan §13.1 step 7). Errors block, warnings inform."""
    units = list(
        (
            await db.execute(
                select(Unit).where(
                    Unit.project_id == project.id, Unit.lifecycle_status != "removed"
                )
            )
        ).scalars()
    )
    public = [u for u in units if u.publication_status in ("published", "hidden")]
    ids = [u.id for u in public]
    rows = await sales.inventory(db, project, unit_ids=ids) if ids else []
    items: list[dict[str, Any]] = []

    def add(key: str, level: str, message: str, count: int | None = None) -> None:
        items.append({"key": key, "level": level, "message": message, "count": count})

    if not public:
        add("units", "error", "No units are marked for publication", 0)
    else:
        add("units", "ok", f"{len(public)} unit(s) will be published", len(public))
    drafts = [u for u in public if u.lifecycle_status != "active"]
    if drafts:
        add(
            "drafts", "warning", "Draft units (mapping not approved) are marked public", len(drafts)
        )
    unverified = [u for u in public if u.verification_status != "verified"]
    if unverified:
        add(
            "unverified",
            "warning",
            "Units with unverified plans/areas are shown as indicative",
            len(unverified),
        )
    no_price = [
        r
        for r in rows
        if r["list_price"] is None
        and not r["price_on_request"]
        and r["availability"] == "available"
    ]
    if no_price:
        add(
            "no_price",
            "warning",
            "Available units without a price show 'price on request'",
            len(no_price),
        )
    if ids:
        with_plan = set(
            (
                await db.execute(
                    select(UnitBoundary.unit_id)
                    .join(Sheet, Sheet.id == UnitBoundary.sheet_id)
                    .where(
                        UnitBoundary.unit_id.in_(ids),
                        UnitBoundary.is_current.is_(True),
                        Sheet.raster_key.is_not(None),
                    )
                )
            ).scalars()
        )
        missing = [u for u in public if u.id not in with_plan]
        if missing:
            add(
                "plans",
                "warning",
                "Units without a floor plan polygon (no plan on the unit page)",
                len(missing),
            )
    unplaced = list(
        (
            await db.execute(
                select(Building.code).where(
                    Building.project_id == project.id,
                    Building.kind == "building",
                    Building.placement_status == "unplaced",
                    Building.id.in_(select(Floor.building_id)),
                )
            )
        ).scalars()
    )
    if unplaced:
        add(
            "placement",
            "warning",
            f"Buildings not placed on the site plan: {', '.join(unplaced)}",
            len(unplaced),
        )
    if not (project.site_frame or {}).get("sheet_id"):
        add(
            "site_plan",
            "warning",
            "No site plan chosen: the portal shows buildings as a list",
            None,
        )
    massing_model = (
        await db.execute(
            select(GeometryModel.id).where(
                GeometryModel.project_id == project.id,
                GeometryModel.is_current.is_(True),
                GeometryModel.status == "ready",
            )
        )
    ).first()
    if massing_model is None:
        add("massing", "warning", "No 3D massing yet: the portal falls back to 2D plans", None)
    if not (project.portal_settings or {}).get("hero_text") and not project.description:
        add("text", "warning", "No project description or hero text", None)
    public_renders = (
        await db.execute(
            select(Document.id).where(
                Document.project_id == project.id,
                Document.kind == "render",
                Document.visibility == "public",
            )
        )
    ).first()
    if public_renders is None:
        add(
            "gallery",
            "warning",
            "No renders in the portal gallery: mark a render document public under Documents",
            None,
        )
    current = await current_publication(db, project.id)
    return {
        "ok": not any(i["level"] == "error" for i in items),
        "items": items,
        "published_version": current.version_no if current else None,
        "portal_url": await portal_base_url(db, project),
    }


async def current_publication(db: AsyncSession, project_id: uuid.UUID) -> Publication | None:
    return (
        await db.execute(
            select(Publication).where(
                Publication.project_id == project_id, Publication.status == "published"
            )
        )
    ).scalar_one_or_none()


async def publish(
    db: AsyncSession, project: Project, *, mode: str, actor: Actor
) -> tuple[Publication, str | None]:
    """Build a snapshot; ``publish`` retires the live one in the same transaction (atomic
    switch), ``preview`` returns a signed 1 h token instead."""
    check = await readiness(db, project)
    if not check["ok"]:
        raise ProblemError(
            422,
            "Project is not ready to publish",
            "; ".join(i["message"] for i in check["items"] if i["level"] == "error"),
        )
    if mode == "publish":
        # serialise concurrent publishes of one project
        await db.execute(select(Project.id).where(Project.id == project.id).with_for_update())
        prev = await current_publication(db, project.id)
        if prev is not None:
            prev.status = "retired"
            prev.retired_at = datetime.now(UTC)
            await db.flush()
    pub, _doc = await snapshot.build(
        db, project, status="published" if mode == "publish" else "preview", actor_id=actor[0]
    )
    await write_audit(
        db,
        tenant_id=project.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="publication",
        entity_id=pub.id,
        action=mode,
        after={"project_id": str(project.id), "version_no": pub.version_no, **pub.summary},
    )
    portal.invalidate(project.tenant_id)
    token = tokens.issue(pub.id, actor[0]) if mode == "preview" else None
    return pub, token


async def unpublish(db: AsyncSession, project: Project, actor: Actor) -> Publication:
    pub = await current_publication(db, project.id)
    if pub is None:
        raise ProblemError(409, "Project is not published")
    pub.status = "retired"
    pub.retired_at = datetime.now(UTC)
    await write_audit(
        db,
        tenant_id=project.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="publication",
        entity_id=pub.id,
        action="unpublish",
        after={"project_id": str(project.id), "version_no": pub.version_no},
    )
    portal.invalidate(project.tenant_id)
    return pub


async def list_publications(db: AsyncSession, project_id: uuid.UUID) -> list[Publication]:
    return list(
        (
            await db.execute(
                select(Publication)
                .where(Publication.project_id == project_id)
                .order_by(Publication.version_no.desc())
                .limit(50)
            )
        ).scalars()
    )


async def count_public_units(db: AsyncSession, project_id: uuid.UUID) -> dict[str, int]:
    rows = await db.execute(
        select(Unit.publication_status, func.count())
        .where(Unit.project_id == project_id, Unit.lifecycle_status != "removed")
        .group_by(Unit.publication_status)
    )
    return {k: v for k, v in rows.all()}
