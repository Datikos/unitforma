"""Guarded storage deletes run by the worker (ADR-0012 Decision 5).

A prefix is deleted only after the row that owned it is gone. The deferral is not part of the
request transaction, so the job may run before the delete commits (then it retries) or after a
request that rolled back (then the row still exists and the job keeps retrying until it fails).
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import text

from unitforma.core.db import tenant_session
from unitforma.storage.service import get_storage

log = structlog.get_logger()

GUARD_TABLES = frozenset({"projects", "documents", "buildings"})


class OwnerStillExists(Exception):
    """The guarded row is still there: the delete has not committed (or was rolled back)."""


async def delete_prefix(
    tenant_id: uuid.UUID, prefix: str, guard_table: str, guard_id: uuid.UUID
) -> dict:
    expected = f"t/{tenant_id}/p/"
    if not prefix.startswith(expected) or len(prefix) <= len(expected):
        raise ValueError(f"prefix {prefix!r} is not under {expected!r}")
    if guard_table not in GUARD_TABLES:
        raise ValueError(f"unknown guard table {guard_table!r}")
    async with tenant_session(tenant_id, scope="tenant") as db:
        row = (
            await db.execute(
                text(f"SELECT 1 FROM {guard_table} WHERE id = :id"),  # noqa: S608 - allow-listed
                {"id": guard_id},
            )
        ).first()
    if row is not None:
        raise OwnerStillExists(f"{guard_table} {guard_id} still exists; retrying")
    n = get_storage().delete_prefix(prefix)
    log.info("storage.prefix_deleted", prefix=prefix, objects=n, guard=f"{guard_table}:{guard_id}")
    return {"deleted": n}


async def queue_delete_prefix(
    tenant_id: uuid.UUID, prefix: str, guard_table: str, guard_id: uuid.UUID
) -> bool:
    """Defer ``storage.delete_prefix``. Never raises: the rows are gone either way, and an
    orphaned prefix waits for the retention sweep (ADR-0012 Decision 5)."""
    from unitforma.jobs.app import app as jobs

    try:
        await jobs.configure_task(name="storage.delete_prefix", queue="default").defer_async(
            tenant_id=str(tenant_id),
            prefix=prefix,
            guard_table=guard_table,
            guard_id=str(guard_id),
        )
        return True
    except Exception as e:  # noqa: BLE001 - the queue may be down; the delete still lands
        log.warning("storage.enqueue_failed", prefix=prefix, error=str(e)[:200])
        return False
