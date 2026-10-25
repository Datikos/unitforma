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
