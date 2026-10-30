"""Task registry. Each task is a thin wrapper around a module service."""

from __future__ import annotations

import procrastinate
import structlog

from unitforma.jobs.app import app
from unitforma.jobs.visibility import WAIT_FOR_COMMIT

log = structlog.get_logger()


@app.task(name="housekeeping.ping", queue="default", retry=3)
async def ping(message: str = "pong") -> str:
    log.info("job.ping", message=message)
    return message


@app.periodic(cron="15 3 * * *")
@app.task(name="housekeeping.retention", queue="periodic", pass_context=True)
async def retention(context, timestamp: int) -> dict:
    """Daily retention sweep (ADR-0021): dead uploads, expired invitations and tokens, old render
    crops, orphaned and retired storage objects; then Procrastinate's own job-table cleanup."""
    from unitforma.core.settings import get_settings
    from unitforma.housekeeping.service import sweep

    counts = await sweep()
    s = get_settings()
    old_jobs = app.configure_task(
        name="procrastinate.builtin_tasks.remove_old_jobs", queue="periodic"
    )
    await old_jobs.defer_async(max_hours=s.retention_job_days * 24)
    await old_jobs.defer_async(
        max_hours=s.retention_failed_job_days * 24,
        remove_failed=True,
        remove_cancelled=True,
        remove_aborted=True,
    )
    return counts


@app.task(
    name="storage.delete_prefix",
    queue="default",
    retry=procrastinate.RetryStrategy(max_attempts=5, wait=30),
)
async def delete_prefix(tenant_id: str, prefix: str, guard_table: str, guard_id: str) -> dict:
    """Delete a project's or document's objects once its row is gone (ADR-0012 Decision 5)."""
    import uuid

    from unitforma.storage.jobs import delete_prefix as run

    return await run(uuid.UUID(tenant_id), prefix, guard_table, uuid.UUID(guard_id))


@app.task(name="documents.ingest_revision", queue="docs", retry=WAIT_FOR_COMMIT)
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


@app.task(name="regulatory.import_attachments", queue="docs", retry=WAIT_FOR_COMMIT)
async def import_attachments(tenant_id: str, import_id: str) -> dict:
    """Download a permit's current drawings into the project's documents (ADR-0007)."""
    import uuid

    from unitforma.regulatory.service import import_attachments as run

    return await run(uuid.UUID(tenant_id), uuid.UUID(import_id))


@app.task(name="geometry.ingest_ifc", queue="geometry-heavy", retry=WAIT_FOR_COMMIT)
async def ingest_ifc(tenant_id: str, revision_id: str) -> dict:
    """IFC → GLB per building + space list for review (ADR-0006 Phase C); heavy worker only."""
    import uuid

    from unitforma.geometry.ifc_service import ingest_ifc as run

    return await run(uuid.UUID(tenant_id), uuid.UUID(revision_id))


@app.task(name="documents.resuggest_floors", queue="docs", retry=1)
async def resuggest_floors(tenant_id: str, project_id: str) -> dict:
    """Page → floor suggestions again after floors changed (ADR-0010)."""
    import uuid

    from unitforma.documents.jobs import resuggest_floors as run

    return await run(uuid.UUID(tenant_id), uuid.UUID(project_id))


@app.periodic(cron="*/10 * * * *")
@app.task(name="documents.requeue_stuck", queue="periodic", pass_context=True)
async def requeue_stuck(context, timestamp: int) -> dict:
    """Queue again every revision left "queued" or "processing" without a live job for over
    15 minutes (a worker lost mid-import or mid-run), three runs at most (ADR-0016 Decision 8)."""
    from unitforma.documents.jobs import requeue_stuck as run

    return await run()


@app.task(name="renders.generate", queue="docs", retry=0)
async def render_generate(tenant_id: str, render_id: str) -> dict:
    """Crop a unit's plan, ask the image provider for a 3D plan render, store it for review
    (ADR-0017 Decision 3). No retry: a failure is shown to the reviewer, who asks again."""
    import uuid

    from unitforma.renders.jobs import generate as run

    return await run(uuid.UUID(tenant_id), uuid.UUID(render_id))


@app.task(name="setup.autopilot", queue="docs", retry=0)
async def setup_autopilot(tenant_id: str, project_id: str) -> dict:
    """The oldest queued solver run of a project (ADR-0025 Decision 3): apply the confident
    proposals, record every decision. No retry: the next intake event or "Run now" queues anew."""
    import uuid

    from unitforma.autopilot.service import run_project

    return await run_project(uuid.UUID(tenant_id), uuid.UUID(project_id))


@app.task(name="geometry.relink_ifc", queue="geometry", retry=2)
async def relink_ifc(tenant_id: str, model_id: str) -> dict:
    """Rewrite an IFC model's GLB extras after space links changed (BACKLOG 15)."""
    import uuid

    from unitforma.geometry.ifc_service import run_relink

    return await run_relink(uuid.UUID(tenant_id), uuid.UUID(model_id))
