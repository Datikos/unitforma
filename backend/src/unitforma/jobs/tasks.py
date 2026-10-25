"""Task registry. Each task is a thin wrapper around a module service."""

from __future__ import annotations

import structlog

from unitforma.jobs.app import app

log = structlog.get_logger()


@app.task(name="housekeeping.ping", queue="default", retry=3)
async def ping(message: str = "pong") -> str:
    log.info("job.ping", message=message)
    return message


@app.periodic(cron="15 3 * * *")
@app.task(name="housekeeping.retention", queue="periodic", pass_context=True)
async def retention(context, timestamp: int) -> None:
    """Daily retention sweep (drafts, auth attempts, invitations). Implemented in Phase 5."""
    log.info("job.retention", at=timestamp)


@app.task(name="documents.ingest_revision", queue="docs", retry=2)
async def ingest_revision(tenant_id: str, revision_id: str) -> dict:
    """Inspect, rasterise and extract an uploaded document revision (plan §13)."""
    import uuid

    from unitforma.documents.jobs import process_revision

    return await process_revision(uuid.UUID(tenant_id), uuid.UUID(revision_id))
