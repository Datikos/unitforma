"""The setup solver's controls, shared by the admin API and the MCP tools (ADR-0025 Decisions 2, 3
and 7; ADR-0028 #C1): the checklist with the solver's view, the switches and "Run now".

Each function takes the caller's :class:`TenantContext` and applies the same rights checks, so the
two doors cannot drift apart.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from unitforma.autopilot import service as autopilot
from unitforma.autopilot.queue import queue_run
from unitforma.core.errors import ProblemError
from unitforma.identity.authz import Action
from unitforma.identity.deps import TenantContext
from unitforma.projects import service as projects
from unitforma.publishing import setup as setup_service
from unitforma.tenants.models import SetupRun


def _actor(ctx: TenantContext) -> tuple[uuid.UUID, str]:
    return ctx.principal.user_id, ctx.actor_role


def require_publish_defaults(ctx: TenantContext) -> None:
    """ADR-0029 Decision 2: the worker approves, confirms and publishes as the person, so the
    person holds all three rights."""
    ctx.require("mapping", Action.APPROVE)
    ctx.require("sales", Action.WRITE)
    ctx.require("publication", Action.PUBLISH)


async def checklist(ctx: TenantContext, project_id: uuid.UUID) -> dict[str, Any]:
    """The setup checklist (ADR-0017) with what the solver did and left (ADR-0025 Decision 7):
    the ``SetupOut`` shape."""
    ctx.require("project", Action.READ)
    ctx.require_project(project_id)
    p = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    out = await setup_service.setup_status(ctx.session, p)
    view = await autopilot.checklist_view(ctx.session, p)
    for st in out["steps"]:
        st["auto_detail"] = view["auto_detail"].get(st["key"])
    out["auto"] = view["auto"]
    out["decisions"] = view["decisions"]
    return out


async def switch(
    ctx: TenantContext,
    project_id: uuid.UUID,
    *,
    enabled: bool,
    approve_sheets: bool,
    publish_defaults: bool | None,
) -> dict[str, Any]:
    """Switch the solver on or off: the ``SetupAutoOut`` shape. ``approve_sheets`` needs the
    mapping approve right, ``publish_defaults`` the three rights of ADR-0029, since the worker
    acts as the person who switched it on. ``publish_defaults=None`` keeps the stored value.
    Switching on queues a run at once."""
    ctx.require("project", Action.WRITE)
    ctx.require_project(project_id)
    p = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    if publish_defaults is None:
        publish_defaults = autopilot.auto_settings(p)["publish_defaults"]
    if enabled and approve_sheets:
        ctx.require("mapping", Action.APPROVE)
    if enabled and publish_defaults:
        require_publish_defaults(ctx)
    autopilot.set_auto_settings(
        p,
        enabled=enabled,
        approve_sheets=approve_sheets,
        publish_defaults=publish_defaults,
        actor=_actor(ctx),
    )
    p.version += 1
    await ctx.session.flush()
    if enabled:
        # the switches travel with the run: the worker may start before this request commits
        await queue_run(
            ctx.tenant_id,
            project_id,
            "switched_on",
            requested_by=ctx.principal.user_id,
            force=True,
            switches={"approve_sheets": approve_sheets},
        )
    view = await autopilot.checklist_view(ctx.session, p)
    return view["auto"]


async def run_now(ctx: TenantContext, project_id: uuid.UUID) -> dict[str, Any]:
    """Queue one run now, whether or not the solver is switched on: the ``SetupRunOut`` shape.
    The run acts as the caller, so it needs the mapping approve right when the project's
    switches ask for sheet approval. 503 when the job queue cannot take it."""
    ctx.require("project", Action.WRITE)
    ctx.require_project(project_id)
    p = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    if autopilot.auto_settings(p)["approve_sheets"]:
        ctx.require("mapping", Action.APPROVE)
    run_id = await queue_run(
        ctx.tenant_id, project_id, "run_now", requested_by=ctx.principal.user_id, force=True
    )
    if run_id is None:
        raise ProblemError(503, "The job queue is unavailable", "Try again in a minute")
    run = (await ctx.session.execute(select(SetupRun).where(SetupRun.id == run_id))).scalar_one()
    return autopilot.run_out(run)
