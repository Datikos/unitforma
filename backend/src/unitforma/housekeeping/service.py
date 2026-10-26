"""The retention sweep (ADR-0021): rows and objects nobody can reach any more, each target behind
a grace period from settings. ``sweep`` returns the counts per target; with ``retention_enabled``
false it only counts.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, func, select, update

from unitforma.core.db import tenant_session
from unitforma.core.settings import get_settings
from unitforma.storage.service import Storage, get_storage
from unitforma.tenants.models import (
    ApiToken,
    Document,
    DocumentRevision,
    Project,
    Publication,
    StaffInvitation,
    UnitRender,
)

log = structlog.get_logger()
UUID_LEN = 36


async def sweep(now: datetime | None = None) -> dict[str, int]:
    s = get_settings()
    now = now or datetime.now(UTC)
    live = s.retention_enabled
    counts = {
        "pending_uploads": await _pending_uploads(
            now - timedelta(hours=s.retention_pending_upload_hours), live
        ),
        "invitations": await _invitations(now - timedelta(days=s.retention_invitation_days), live),
        "api_tokens": await _api_tokens(now - timedelta(days=s.retention_token_days), live),
        "render_inputs": await _render_inputs(
            now - timedelta(days=s.retention_render_input_days), live
        ),
        "orphan_prefixes": await _orphan_prefixes(
            now - timedelta(days=s.retention_orphan_days), live
        ),
        "retired_assets": await _retired_assets(
            now - timedelta(days=s.retention_retired_asset_days), live
        ),
    }
    log.info("job.retention", dry_run=not live, **counts)
    return counts


def _delete_object(storage: Storage, key: str) -> None:
    try:
        storage.delete(key)
    except Exception as e:  # noqa: BLE001 - the row goes anyway; the object is found by the orphan walk
        log.warning("retention.delete_failed", key=key, error=str(e)[:200])


async def _pending_uploads(cutoff: datetime, live: bool) -> int:
    """Upload intents never completed, and documents left without any revision."""
    storage = get_storage()
    n = 0
    async with tenant_session(None, scope="platform") as db:
        revs = list(
            (
                await db.execute(
                    select(DocumentRevision).where(
                        DocumentRevision.processing_status == "pending",
                        DocumentRevision.created_at < cutoff,
                    )
                )
            ).scalars()
        )
        for rev in revs:
            n += 1
            if live:
                _delete_object(storage, rev.object_key)
                await db.delete(rev)
        await db.flush()
        # documents with no revision once the dead intents are gone (same count in a dry run)
        has_live_rev = select(DocumentRevision.id).where(
            DocumentRevision.document_id == Document.id,
            ~(
                (DocumentRevision.processing_status == "pending")
                & (DocumentRevision.created_at < cutoff)
            ),
        )
        docs = list(
            (
                await db.execute(
                    select(Document).where(~has_live_rev.exists(), Document.created_at < cutoff)
                )
            ).scalars()
        )
        for doc in docs:
            n += 1
            if live:
                await db.delete(doc)
    return n


async def _invitations(cutoff: datetime, live: bool) -> int:
    async with tenant_session(None, scope="platform") as db:
        where = (
            StaffInvitation.expires_at < cutoff,
            StaffInvitation.accepted_membership_id.is_(None),
        )
        n = (
            await db.execute(select(func.count()).select_from(StaffInvitation).where(*where))
        ).scalar_one()
        if live and n:
            await db.execute(delete(StaffInvitation).where(*where))
    return int(n)


async def _api_tokens(cutoff: datetime, live: bool) -> int:
    async with tenant_session(None, scope="platform") as db:
        where = ((ApiToken.expires_at < cutoff) | (ApiToken.revoked_at < cutoff),)
        n = (
            await db.execute(select(func.count()).select_from(ApiToken).where(*where))
        ).scalar_one()
        if live and n:
            await db.execute(delete(ApiToken).where(*where))
    return int(n)


async def _render_inputs(cutoff: datetime, live: bool) -> int:
    """The plan crops of renders finished long ago; the render rows stay as history."""
    storage = get_storage()
    async with tenant_session(None, scope="platform") as db:
        rows = list(
            (
                await db.execute(
                    select(UnitRender.id, UnitRender.input_key).where(
                        UnitRender.input_key.is_not(None), UnitRender.finished_at < cutoff
                    )
                )
            ).all()
        )
        if live:
            for _rid, key in rows:
                _delete_object(storage, key)
            if rows:
                await db.execute(
                    update(UnitRender)
                    .where(UnitRender.id.in_([r[0] for r in rows]))
                    .values(input_key=None)
                )
    return len(rows)


def _id_of(prefix: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(prefix.rstrip("/").rsplit("/", 1)[-1])
    except ValueError:
        return None


def _newest(storage: Storage, prefix: str) -> datetime | None:
    stamps = [o.modified for o in storage.list_objects(prefix) if o.modified is not None]
    return max(stamps) if stamps else None


async def _orphan_prefixes(cutoff: datetime, live: bool) -> int:
    """Project, document and ``pub/`` prefixes whose row is gone, once nothing in them is newer than
    the grace period (a delete job that never ran, ADR-0012 Decision 5)."""
    storage = get_storage()
    async with tenant_session(None, scope="platform") as db:
        projects = {r for r in (await db.execute(select(Project.id))).scalars()}
        documents = {r for r in (await db.execute(select(Document.id))).scalars()}
    n = 0

    def drop(prefix: str) -> None:
        nonlocal n
        newest = _newest(storage, prefix)
        if newest is None or newest >= cutoff:
            return
        n += 1
        if live:
            storage.delete_prefix(prefix)
            log.info("retention.orphan_prefix", prefix=prefix)

    for tenant_prefix in storage.list_prefixes("t/"):
        for project_prefix in storage.list_prefixes(f"{tenant_prefix}p/"):
            pid = _id_of(project_prefix)
            if pid is None or pid not in projects:
                drop(project_prefix)
                continue
            for doc_prefix in storage.list_prefixes(f"{project_prefix}documents/"):
                did = _id_of(doc_prefix)
                if did is None or did not in documents:
                    drop(doc_prefix)
    for tenant_prefix in storage.list_prefixes("pub/"):
        for project_prefix in storage.list_prefixes(tenant_prefix):
            pid = _id_of(project_prefix)
            if pid is None or pid not in projects:
                drop(project_prefix)
    return n


async def _retired_assets(cutoff: datetime, live: bool) -> int:
    """Under ``pub/{tenant}/{project}/`` of a living project: objects that no non-retired
    publication references and that are not a version's snapshot document (ADR-0012 known gap)."""
    storage = get_storage()
    async with tenant_session(None, scope="platform") as db:
        pubs = list(
            (
                await db.execute(
                    select(
                        Publication.project_id,
                        Publication.status,
                        Publication.snapshot_key,
                        Publication.assets,
                    )
                )
            ).all()
        )
    keep: dict[uuid.UUID, set[str]] = {}
    for project_id, status, snapshot_key, assets in pubs:
        k = keep.setdefault(project_id, set())
        k.add(snapshot_key)
        if status != "retired":
            k.update((assets or {}).values())
    n = 0
    for tenant_prefix in storage.list_prefixes("pub/"):
        for project_prefix in storage.list_prefixes(tenant_prefix):
            pid = _id_of(project_prefix)
            if pid is None or pid not in keep:
                continue  # no publication rows: the orphan walk decides
            for o in storage.list_objects(project_prefix):
                if o.key in keep[pid] or o.modified is None or o.modified >= cutoff:
                    continue
                n += 1
                if live:
                    _delete_object(storage, o.key)
    if n:
        log.info("retention.retired_assets", removed=n if live else 0, found=n)
    return n
