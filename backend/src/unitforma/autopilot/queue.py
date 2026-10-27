"""Queue a solver run (ADR-0025 Decision 3). A leaf: ``documents`` and ``regulatory`` call it at
the end of their jobs, so it imports nothing of the solver itself and the jobs app only lazily.

One run waits per project: the job carries the project, not the run, and executes the oldest
queued run row when it starts, so the Procrastinate queueing lock can collapse a burst of triggers
into one waiting job without losing the row the checklist shows. A queue outage is logged and
marks the row failed; nothing raises.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select

from unitforma.core.db import tenant_session
from unitforma.core.ids import new_id
from unitforma.tenants.models import Project, SetupRun

log = structlog.get_logger()

TASK = "setup.autopilot"
QUEUE = "docs"


def lock_of(project_id: uuid.UUID) -> str:
    return f"autopilot:{project_id}"


async def queue_run(
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    trigger: str,
    *,
    requested_by: uuid.UUID | None = None,
    force: bool = False,
    switches: dict | None = None,
) -> uuid.UUID | None:
    """Create a ``setup_runs`` row and defer the job. ``None`` when the project has the solver
    off (unless ``force``, the person's own "Run now"), or when a run is already waiting."""
    async with tenant_session(tenant_id, scope="tenant") as db:
        project = (
            await db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        if project is None:
            return None
        auto = project.setup_auto or {}
        if not force and not auto.get("enabled"):
            return None
        waiting = (
            await db.execute(
                select(SetupRun.id).where(
                    SetupRun.project_id == project_id, SetupRun.status == "queued"
                )
            )
        ).first()
        if waiting is not None:
            return waiting[0]
        who = requested_by
        if who is None and auto.get("requested_by"):
            try:
                who = uuid.UUID(str(auto["requested_by"]))
            except ValueError:
                who = None
        run = SetupRun(
            id=new_id(),
            tenant_id=tenant_id,
            project_id=project_id,
            status="queued",
            trigger=trigger[:40],
            requested_by=who,
            summary={"switches": switches} if switches else {},
        )
        db.add(run)
        await db.flush()
        run_id = run.id
    try:
        from procrastinate.exceptions import AlreadyEnqueued

        from unitforma.jobs.app import app as jobs

        try:
            await jobs.configure_task(
                name=TASK, queue=QUEUE, queueing_lock=lock_of(project_id)
            ).defer_async(tenant_id=str(tenant_id), project_id=str(project_id))
        except AlreadyEnqueued:
            pass  # a job for this project is waiting; it picks up the row when it starts
    except Exception as e:  # noqa: BLE001 - the queue may be down; the caller's work still lands
        log.warning("autopilot.enqueue_failed", project_id=str(project_id), error=str(e)[:200])
        async with tenant_session(tenant_id, scope="tenant") as db:
            row = await db.get(SetupRun, run_id)
            if row is not None:
                row.status = "failed"
                row.error = f"could not enqueue: {e}"[:500]
        return None
    return run_id
