"""Portal read side: Host → tenant → live (or previewed) publication → snapshot (plan §9.1, §9.3).

The portal never reads live inventory tables: only ``publications``, ``published_units`` and
the snapshot JSON. Host resolutions and "which publication is live" answers are cached per
process for ``portal_cache_seconds`` (default 5 s) so an unpublish is visible within seconds;
snapshots themselves are immutable and cached by publication id.
"""

from __future__ import annotations

import json
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.core.db import get_sessionmaker, tenant_session
from unitforma.core.errors import ProblemError
from unitforma.core.settings import get_settings
from unitforma.domains.service import resolve_host
from unitforma.publishing import tokens
from unitforma.storage.service import get_storage
from unitforma.tenants.models import Project, Publication, PublishedUnit, Tenant

NOT_CONFIGURED = "https://unitforma.com/problems/portal-not-configured"
NOT_PUBLISHED = "https://unitforma.com/problems/project-not-published"

_hosts: dict[str, tuple[float, dict | None]] = {}
_live: dict[tuple[uuid.UUID, str], tuple[float, uuid.UUID | None]] = {}
_docs: OrderedDict[uuid.UUID, dict[str, Any]] = OrderedDict()
_DOC_CACHE_SIZE = 64


def invalidate(tenant_id: uuid.UUID | None = None) -> None:
    """Drop cached host/live lookups (publish/unpublish in this process)."""
    if tenant_id is None:
        _hosts.clear()
        _live.clear()
        return
    for k in [k for k in _live if k[0] == tenant_id]:
        _live.pop(k, None)


@dataclass
class Site:
    host: str
    domain_id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_slug: str
    project_id: uuid.UUID | None  # project-scoped custom domain


async def site_for_host(host: str) -> Site:
    ttl = get_settings().portal_cache_seconds
    hit = _hosts.get(host)
    if hit and hit[0] > time.monotonic():
        r = hit[1]
    else:
        async with get_sessionmaker()() as s:
            r = await resolve_host(s, host)
        _hosts[host] = (time.monotonic() + ttl, r)
    if r is None or r["tenant_status"] != "active":
        raise ProblemError(
            404, "Portal not configured", f"No active portal for {host}", type_=NOT_CONFIGURED
        )
    return Site(
        host=host,
        domain_id=r["domain_id"],
        tenant_id=r["tenant_id"],
        tenant_slug=r["tenant_slug"],
        project_id=r["project_id"],
    )


async def _project(db: AsyncSession, site: Site, slug: str | None) -> Project:
    q = select(Project).where(Project.tenant_id == site.tenant_id)
    if site.project_id is not None:
        q = q.where(Project.id == site.project_id)
        if slug is not None:
            q = q.where(func.lower(Project.slug) == slug.lower())
    elif slug is not None:
        q = q.where(func.lower(Project.slug) == slug.lower())
    else:
        raise ProblemError(404, "Project not found", type_=NOT_PUBLISHED)
    p = (await db.execute(q)).scalar_one_or_none()
    if p is None:
        raise ProblemError(404, "Project not found", type_=NOT_PUBLISHED)
    return p


async def _live_publication(db: AsyncSession, project: Project) -> uuid.UUID | None:
    key = (project.tenant_id, str(project.id))
    hit = _live.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    pid = (
        await db.execute(
            select(Publication.id).where(
                Publication.project_id == project.id, Publication.status == "published"
            )
        )
    ).scalar_one_or_none()
    _live[key] = (time.monotonic() + get_settings().portal_cache_seconds, pid)
    return pid


async def resolve_publication(
    db: AsyncSession, site: Site, slug: str | None, preview: str | None
) -> tuple[Project, Publication, bool]:
    """(project, publication, is_preview). A valid preview token for this project wins."""
    project = await _project(db, site, slug)
    if preview:
        pub_id = tokens.verify(preview)
        if pub_id is None:
            raise ProblemError(403, "Preview link expired or invalid")
        pub = (
            await db.execute(
                select(Publication).where(
                    Publication.id == pub_id,
                    Publication.project_id == project.id,
                    Publication.status.in_(("preview", "published")),
                )
            )
        ).scalar_one_or_none()
        if pub is None:
            raise ProblemError(403, "Preview link does not belong to this project")
        return project, pub, True
    pid = await _live_publication(db, project)
    if pid is None:
        raise ProblemError(404, "Project not published", type_=NOT_PUBLISHED)
    pub = await db.get(Publication, pid)
    if pub is None or pub.status != "published":
        invalidate(project.tenant_id)
        raise ProblemError(404, "Project not published", type_=NOT_PUBLISHED)
    return project, pub, False


def load_doc(pub: Publication) -> dict[str, Any]:
    doc = _docs.get(pub.id)
    if doc is None:
        doc = json.loads(get_storage().get_bytes(pub.snapshot_key))
        _docs[pub.id] = doc
        while len(_docs) > _DOC_CACHE_SIZE:
            _docs.popitem(last=False)
    else:
        _docs.move_to_end(pub.id)
    return doc


async def site_summary(site: Site) -> dict[str, Any]:
    """Tenant (or single-project) landing: branding and the live projects."""
    async with tenant_session(site.tenant_id) as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.id == site.tenant_id))).scalar_one()
        q = (
            select(Project, Publication)
            .join(Publication, Publication.project_id == Project.id)
            .where(Publication.status == "published", Project.tenant_id == site.tenant_id)
            .order_by(Project.name)
        )
        if site.project_id is not None:
            q = q.where(Project.id == site.project_id)
        projects = []
        branding: dict[str, Any] | None = None
        for p, pub in (await db.execute(q)).all():
            doc = load_doc(pub)
            branding = branding or doc.get("branding")
            projects.append(
                {
                    "slug": p.slug,
                    "name": doc["project"]["name"],
                    "hero_text": doc["project"].get("hero_text"),
                    "construction_stage": doc["project"].get("construction_stage"),
                    "address": doc["project"].get("address"),
                    "stats": doc.get("stats"),
                }
            )
    from unitforma.publishing.snapshot import sanitise_branding

    return {
        "tenant": {"name": tenant.name, "slug": tenant.slug},
        "branding": branding or sanitise_branding(tenant.branding),
        "mode": "project" if site.project_id is not None else "tenant",
        "projects": projects,
        "status": "live" if projects else "coming_soon",
    }


SORTS = {
    "price_asc": (PublishedUnit.price_amount.asc().nulls_last(), PublishedUnit.code),
    "price_desc": (PublishedUnit.price_amount.desc().nulls_last(), PublishedUnit.code),
    "area_asc": (PublishedUnit.area_m2.asc().nulls_last(), PublishedUnit.code),
    "area_desc": (PublishedUnit.area_m2.desc().nulls_last(), PublishedUnit.code),
    "code": (PublishedUnit.building_code, PublishedUnit.floor_level, PublishedUnit.code),
}


async def list_units(db: AsyncSession, pub: Publication, f: dict[str, Any]) -> dict[str, Any]:
    q = select(PublishedUnit).where(
        PublishedUnit.publication_id == pub.id, PublishedUnit.listed.is_(True)
    )
    if f.get("availability"):
        q = q.where(PublishedUnit.availability.in_(f["availability"]))
    if f.get("unit_type"):
        q = q.where(PublishedUnit.unit_type.in_(f["unit_type"]))
    if f.get("building"):
        q = q.where(PublishedUnit.building_code.in_(f["building"]))
    if f.get("floor") is not None:
        q = q.where(PublishedUnit.floor_level.in_(f["floor"]))
    if f.get("min_price") is not None:
        q = q.where(PublishedUnit.price_amount >= Decimal(f["min_price"]))
    if f.get("max_price") is not None:
        q = q.where(PublishedUnit.price_amount <= Decimal(f["max_price"]))
    if f.get("min_area") is not None:
        q = q.where(PublishedUnit.area_m2 >= Decimal(f["min_area"]))
    if f.get("max_area") is not None:
        q = q.where(PublishedUnit.area_m2 <= Decimal(f["max_area"]))
    if f.get("rooms"):
        rooms = f["rooms"]
        cond = PublishedUnit.rooms.in_([r for r in rooms if r < 5])
        if any(r >= 5 for r in rooms):
            cond = cond | (PublishedUnit.rooms >= 5)
        q = q.where(cond)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    q = q.order_by(*SORTS.get(f.get("sort") or "code", SORTS["code"]))
    q = q.offset(f.get("offset", 0)).limit(f.get("limit", 200))
    items = [u.data for u in (await db.execute(q)).scalars()]
    return {"total": total, "items": items}


async def get_unit(db: AsyncSession, pub: Publication, code: str) -> dict[str, Any]:
    u = (
        await db.execute(
            select(PublishedUnit).where(
                PublishedUnit.publication_id == pub.id,
                func.lower(PublishedUnit.code) == code.lower(),
            )
        )
    ).scalar_one_or_none()
    if u is None:
        raise ProblemError(404, "Unit not found")
    return u.data
