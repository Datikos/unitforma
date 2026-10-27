"""The solver run (ADR-0025 Decisions 3 to 5): the processing guard, the passes in data-flow
order, each in its own transaction, and the decision record the checklist shows.

A pass acts only where nothing was set by a person (Decision 4) and writes through the ordinary
services with the actor ``(requested_by, "autopilot")``. A pass that raises is recorded and the
next one runs; the run ends ``done`` with every decision in ``summary``, or ``failed`` only when
the run itself could not start.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.autopilot import rules
from unitforma.core.db import tenant_session
from unitforma.tenants.models import (
    Document,
    DocumentRevision,
    Project,
    RegulatoryImport,
    SetupRun,
)

log = structlog.get_logger()

ACTOR_ROLE = "autopilot"
Actor = tuple[uuid.UUID, str]


@dataclass
class Context:
    tenant_id: uuid.UUID
    project_id: uuid.UUID
    run_id: uuid.UUID
    actor: Actor
    approve_sheets: bool
    # ADR-0029 Decision 1: the run ends with the ``defaults`` pass and a live portal
    publish_defaults: bool = False
    decisions: list[dict[str, Any]] = field(default_factory=list)
    passes: list[dict[str, Any]] = field(default_factory=list)
    # entity ids earlier runs decided on, per step: what a person undid afterwards is never
    # redone (Decision 4), so a pass skips what it already touched once
    history: dict[str, set[str]] = field(default_factory=dict)

    def seen(self, step: str) -> set[str]:
        return self.history.get(step, set())

    def decide(
        self,
        step: str,
        kind: str,
        title: str,
        detail: str,
        *,
        confidence: float | None = None,
        needs_you: bool = False,
        entity_type: str | None = None,
        entity_id: uuid.UUID | str | None = None,
        sheet_id: uuid.UUID | str | None = None,
        link: str | None = None,
        entity_ids: list[uuid.UUID | str] | None = None,
        todo: str | None = None,
    ) -> None:
        """One line of the run summary: what was decided (``accepted``), what was left for a
        person (``skipped`` with ``needs_you``), what the pass could not do (``error``)."""
        self.decisions.append(
            {
                "step": step,
                "kind": kind,
                "title": title[:120],
                "detail": detail[:500],
                "confidence": round(confidence, 3) if confidence is not None else None,
                "needs_you": needs_you,
                "entity_type": entity_type,
                "entity_id": str(entity_id) if entity_id else None,
                "sheet_id": str(sheet_id) if sheet_id else None,
                "entity_ids": [str(x) for x in entity_ids] if entity_ids else None,
                "link": link or rules.LINK_OF_STEP.get(step, "overview"),
                # ADR-0029 Decision 5: a "needs you" line says what to do
                "todo": (todo or rules.TODO_OF_STEP.get(step)) if needs_you else None,
                "at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
        )


def session(ctx: Context):
    return tenant_session(ctx.tenant_id, scope="tenant")


# --------------------------------------------------------------------------- settings
def auto_settings(project: Project) -> dict[str, Any]:
    auto = project.setup_auto or {}
    return {
        "enabled": bool(auto.get("enabled")),
        "approve_sheets": bool(auto.get("approve_sheets")),
        "publish_defaults": bool(auto.get("publish_defaults")),
        "requested_by": auto.get("requested_by"),
        "since": auto.get("since"),
    }


def set_auto_settings(
    project: Project,
    *,
    enabled: bool,
    approve_sheets: bool,
    publish_defaults: bool = False,
    actor: Actor,
) -> dict[str, Any]:
    """The switches (ADR-0025 Decision 2, ADR-0029 Decision 2); who turned them on is who the
    worker acts as."""
    project.setup_auto = {
        "enabled": enabled,
        "approve_sheets": approve_sheets,
        "publish_defaults": publish_defaults,
        "requested_by": str(actor[0]),
        "since": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    return auto_settings(project)


# --------------------------------------------------------------------------- the run
async def processing_revisions(db: AsyncSession, project_id: uuid.UUID) -> int:
    """Revisions of the project still queued or processing, plus permit imports still filing
    documents (between two downloads nothing is "processing" yet): the guard of Decision 3."""
    rows = await db.execute(
        select(DocumentRevision.id)
        .join(Document, Document.current_revision_id == DocumentRevision.id)
        .where(
            Document.project_id == project_id,
            DocumentRevision.processing_status.in_(("queued", "processing")),
        )
    )
    imports = await db.execute(
        select(RegulatoryImport.id).where(
            RegulatoryImport.project_id == project_id, RegulatoryImport.status == "importing"
        )
    )
    return len(rows.all()) + len(imports.all())


async def decided_before(
    db: AsyncSession, project_id: uuid.UUID, except_run: uuid.UUID
) -> dict[str, set[str]]:
    """Entity ids every earlier run decided on, per step (``entity_id`` and ``entity_ids`` of
    accepted decisions): the solver's memory of what it did once."""
    rows = await db.execute(
        select(SetupRun.summary).where(
            SetupRun.project_id == project_id,
            SetupRun.id != except_run,
            SetupRun.status.in_(("done", "failed")),
        )
    )
    out: dict[str, set[str]] = {}
    for (summary,) in rows:
        for d in (summary or {}).get("decisions") or []:
            if d.get("kind") != "accepted":
                continue
            ids = set(d.get("entity_ids") or [])
            if d.get("entity_id"):
                ids.add(str(d["entity_id"]))
            if ids:
                out.setdefault(str(d.get("step")), set()).update(ids)
    return out


async def run_project(tenant_id: uuid.UUID, project_id: uuid.UUID) -> dict[str, Any]:
    """Worker body of ``setup.autopilot``: every queued run of the project, oldest first.

    Two intake events within seconds create two rows and one job (the queueing lock drops the
    second deferral); the job must drain both, or the second row stays ``queued`` for ever and
    ``queue_run`` keeps returning it without a job (seen on 2026-10-27, project ``nn4``: the run
    that should have followed the plan set's processing never happened)."""
    results: list[dict[str, Any]] = []
    for _ in range(20):  # bounded: a pass that queues a run would otherwise loop here
        async with tenant_session(tenant_id, scope="tenant") as db:
            row = (
                await db.execute(
                    select(SetupRun.id)
                    .where(SetupRun.project_id == project_id, SetupRun.status == "queued")
                    .order_by(SetupRun.created_at)
                    .limit(1)
                )
            ).first()
        if row is None:
            break
        results.append(await run_autopilot(tenant_id, row[0]))
    if not results:
        return {"skipped": "no queued run"}
    return results[-1] if len(results) == 1 else {"runs": results}


async def run_autopilot(tenant_id: uuid.UUID, run_id: uuid.UUID) -> dict[str, Any]:
    """One run: the guard, then every pass. Returns the counts of the run."""
    from unitforma.autopilot.passes import PASSES

    async with tenant_session(tenant_id, scope="tenant") as db:
        run = (await db.execute(select(SetupRun).where(SetupRun.id == run_id))).scalar_one_or_none()
        if run is None:
            return {"skipped": "no such run"}
        if run.status != "queued":
            return {"skipped": run.status}
        project = (
            await db.execute(select(Project).where(Project.id == run.project_id))
        ).scalar_one_or_none()
        if project is None:
            run.status = "failed"
            run.error = "project is gone"
            run.finished_at = datetime.now(UTC)
            return {"skipped": "no project"}
        auto = auto_settings(project)
        who = run.requested_by
        if who is None and auto.get("requested_by"):
            try:
                who = uuid.UUID(str(auto["requested_by"]))
            except ValueError:
                who = None
        if who is None:
            run.status = "failed"
            run.error = "no requesting user: switch the solver on again"
            run.finished_at = datetime.now(UTC)
            return {"skipped": "no actor"}
        run.status = "running"
        run.started_at = datetime.now(UTC)
        switches = (run.summary or {}).get("switches") or {}
        ctx = Context(
            tenant_id=tenant_id,
            project_id=run.project_id,
            run_id=run.id,
            actor=(who, ACTOR_ROLE),
            approve_sheets=bool(switches.get("approve_sheets", auto["approve_sheets"])),
            history=await decided_before(db, run.project_id, run.id),
        )
        # ADR-0029 Decision 2: the button's run always publishes; the project switch publishes
        # the first version only, later versions are the person's
        if switches.get("publish_defaults"):
            ctx.publish_defaults = True
            ctx.approve_sheets = True
        elif auto["publish_defaults"]:
            from unitforma.publishing.service import current_publication

            ctx.publish_defaults = await current_publication(db, run.project_id) is None
            if ctx.publish_defaults:
                ctx.approve_sheets = True
        pending = await processing_revisions(db, run.project_id)
        if pending:
            ctx.decide(
                "documents",
                "waiting",
                "Waiting for processing",
                f"{pending} document(s) or import(s) still processing; "
                "the run repeats when they finish",
                needs_you=False,
            )
            run.status = "waiting"
            run.finished_at = datetime.now(UTC)
            run.summary = summary_of(ctx)
            return {"waiting": pending}

    from unitforma.autopilot.passes import defaults

    steps = list(PASSES) + ([("defaults", defaults.run)] if ctx.publish_defaults else [])
    for name, fn in steps:
        started = datetime.now(UTC)
        before = len(ctx.decisions)
        try:
            await fn(ctx)
            outcome = "ok"
        except Exception as e:  # noqa: BLE001 - one pass must not stop the others
            log.warning(
                "autopilot.pass_failed", run_id=str(run_id), pass_=name, error=str(e), exc_info=True
            )
            ctx.decide(name, "error", f"{name} failed", str(e)[:300], needs_you=True)
            outcome = "error"
        ctx.passes.append(
            {
                "name": name,
                "outcome": outcome,
                "decisions": len(ctx.decisions) - before,
                "ms": int((datetime.now(UTC) - started).total_seconds() * 1000),
            }
        )

    async with tenant_session(tenant_id, scope="tenant") as db:
        run = (await db.execute(select(SetupRun).where(SetupRun.id == run_id))).scalar_one()
        run.status = "done"
        run.finished_at = datetime.now(UTC)
        run.summary = summary_of(ctx)
        counts = run.summary["counts"]
    log.info("autopilot.run_done", run_id=str(run_id), project_id=str(ctx.project_id), **counts)
    return counts


def summary_of(ctx: Context) -> dict[str, Any]:
    accepted = sum(1 for d in ctx.decisions if d["kind"] == "accepted")
    needs_you = sum(1 for d in ctx.decisions if d["needs_you"])
    errors = sum(1 for d in ctx.decisions if d["kind"] == "error")
    return {
        "v": 1,
        "decisions": ctx.decisions,
        "passes": ctx.passes,
        "counts": {"accepted": accepted, "needs_you": needs_you, "errors": errors},
    }


# --------------------------------------------------------------------------- for the checklist
# a run's steps → the keys of the setup checklist (publishing/setup.py)
CHECKLIST_STEP = {
    "classify": "documents",
    "calibration": "mapping",
    "sheet_floors": "mapping",
    "defaults": "publish",
}


async def latest_runs(db: AsyncSession, project_id: uuid.UUID, limit: int = 20) -> list[SetupRun]:
    rows = await db.execute(
        select(SetupRun)
        .where(SetupRun.project_id == project_id)
        .order_by(SetupRun.created_at.desc())
        .limit(limit)
    )
    return list(rows.scalars())


def run_out(run: SetupRun) -> dict[str, Any]:
    counts = (run.summary or {}).get("counts") or {}
    return {
        "id": run.id,
        "status": run.status,
        "trigger": run.trigger,
        "requested_by": run.requested_by,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "created_at": run.created_at,
        "accepted": int(counts.get("accepted") or 0),
        "needs_you": int(counts.get("needs_you") or 0),
        "errors": int(counts.get("errors") or 0),
        "error": run.error,
    }


async def checklist_view(db: AsyncSession, project: Project) -> dict[str, Any]:
    """What the setup checklist adds (Decision 7): the switches, whether a run is queued or
    running, the last finished run, its decisions lowest confidence first with the ``needs_you``
    items first of all, and one line per step."""
    runs = await latest_runs(db, project.id, limit=10)
    running = any(r.status in ("queued", "running") for r in runs)
    last = next((r for r in runs if r.status in ("done", "failed", "waiting")), None)
    decisions: list[dict[str, Any]] = []
    if last is not None:
        decisions = list((last.summary or {}).get("decisions") or [])
    decisions.sort(
        key=lambda d: (
            0 if d.get("needs_you") else 1,
            d.get("confidence") if d.get("confidence") is not None else 2.0,
        )
    )
    by_step: dict[str, list[dict[str, Any]]] = {}
    for d in decisions:
        by_step.setdefault(CHECKLIST_STEP.get(d["step"], d["step"]), []).append(d)
    auto_detail: dict[str, str] = {}
    for step, items in by_step.items():
        acc = [d for d in items if d["kind"] == "accepted"]
        left = [d for d in items if d.get("needs_you")]
        parts = []
        if acc:
            conf = [d["confidence"] for d in acc if d["confidence"] is not None]
            parts.append(
                f"{len(acc)} decision(s) made for you"
                + (f" (lowest confidence {min(conf):.2f})" if conf else "")
            )
        if left:
            parts.append(f"{len(left)} need(s) you: " + "; ".join(d["title"] for d in left[:3]))
        if parts:
            auto_detail[step] = ". ".join(parts)
    return {
        "auto": {
            **auto_settings(project),
            "running": running,
            "last_run": run_out(last) if last is not None else None,
        },
        "decisions": decisions,
        "auto_detail": auto_detail,
    }
