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


@app.task(name="mapping.propose_revision_diff", queue="docs", retry=1)
async def propose_revision_diff(tenant_id: str, revision_id: str) -> dict:
    """Overlap matrix old vs new → proposal items for the reviewer (plan §12.3, §13.3)."""
    import uuid

    from unitforma.mapping.jobs import propose_revision_diff as run

    return await run(uuid.UUID(tenant_id), uuid.UUID(revision_id))


@app.task(name="geometry.build_massing", queue="geometry", retry=1)
async def build_massing(tenant_id: str, project_id: str) -> dict:
    """Extrude current unit boundaries into the project massing GLB (plan §11.3)."""
    import uuid

    from unitforma.geometry.jobs import build_massing as run

    return await run(uuid.UUID(tenant_id), uuid.UUID(project_id))
