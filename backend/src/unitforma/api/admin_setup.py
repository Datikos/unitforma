"""Staff API: the setup solver of a project (ADR-0025 Decisions 2, 3 and 7): its switches,
"Run now" and the run history. The checklist itself stays on ``GET /projects/{id}/setup``."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from unitforma.api.schemas import SetupAutoIn, SetupAutoOut, SetupRunDetailOut, SetupRunOut
from unitforma.autopilot import control
from unitforma.autopilot import service as autopilot
from unitforma.autopilot.control import require_publish_defaults
from unitforma.autopilot.queue import queue_run
from unitforma.core.errors import ProblemError
from unitforma.identity.authz import Action
from unitforma.identity.deps import TenantContext, tenant_context
from unitforma.projects import service as projects
from unitforma.tenants.models import SetupRun

router = APIRouter(prefix="/api/v1/admin/tenants/{tenant_id}", tags=["setup"])
Ctx = Annotated[TenantContext, Depends(tenant_context)]


__all__ = ["require_publish_defaults", "router"]  # the check lives in autopilot.control


@router.put("/projects/{project_id}/setup/auto", response_model=SetupAutoOut)
async def set_auto(project_id: uuid.UUID, body: SetupAutoIn, ctx: Ctx):
    """Switch the solver on or off for the project. ``approve_sheets`` needs the mapping approve
    right, since the worker approves as the person who switched it on. Switching on queues a
    run at once."""
    return await control.switch(
        ctx,
        project_id,
        enabled=body.enabled,
        approve_sheets=body.approve_sheets,
        publish_defaults=body.publish_defaults,
    )


@router.post("/projects/{project_id}/setup/run", response_model=SetupRunOut, status_code=202)
async def run_now(project_id: uuid.UUID, ctx: Ctx):
    """Queue one run now, whether or not the solver is switched on; the run acts as the caller
    (it needs the mapping approve right when the project's switches ask for sheet approval)."""
    return await control.run_now(ctx, project_id)


@router.post(
    "/projects/{project_id}/setup/publish-defaults", response_model=SetupRunOut, status_code=202
)
async def publish_defaults(project_id: uuid.UUID, ctx: Ctx):
    """One action that ends with a live portal (ADR-0029 Decision 1): a run whose last pass
    approves the solver's drafts, confirms the proposed plan types, writes a first description,
    marks every active unit and publishes. Usable any time; it publishes a new version."""
    ctx.require("project", Action.WRITE)
    ctx.require_project(project_id)
    require_publish_defaults(ctx)
    await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    run_id = await queue_run(
        ctx.tenant_id,
        project_id,
        "publish_defaults",
        requested_by=ctx.principal.user_id,
        force=True,
        switches={"approve_sheets": True, "publish_defaults": True},
    )
    if run_id is None:
        raise ProblemError(503, "The job queue is unavailable", "Try again in a minute")
    run = (await ctx.session.execute(select(SetupRun).where(SetupRun.id == run_id))).scalar_one()
    return autopilot.run_out(run)


@router.get("/projects/{project_id}/setup/runs", response_model=list[SetupRunOut])
async def list_runs(project_id: uuid.UUID, ctx: Ctx):
    ctx.require("project", Action.READ)
    ctx.require_project(project_id)
    await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    return [autopilot.run_out(r) for r in await autopilot.latest_runs(ctx.session, project_id)]


@router.get("/projects/{project_id}/setup/runs/{run_id}", response_model=SetupRunDetailOut)
async def get_run(project_id: uuid.UUID, run_id: uuid.UUID, ctx: Ctx):
    ctx.require("project", Action.READ)
    ctx.require_project(project_id)
    run = (
        await ctx.session.execute(
            select(SetupRun).where(SetupRun.id == run_id, SetupRun.project_id == project_id)
        )
    ).scalar_one_or_none()
    if run is None:
        raise ProblemError(404, "Run not found")
    return {**autopilot.run_out(run), "decisions": (run.summary or {}).get("decisions") or []}
