"""Publish with defaults (ADR-0029 Decision 1): the last pass of a run that must end with a live
portal. Approve what the solver outlined, confirm what it proposed, write a description from the
facts the project knows, mark every active unit and publish. Prices are never touched (ADR-0025
Decision 9: "price on request"); a person's sheets, texts and choices are never changed."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from unitforma.autopilot import rules
from unitforma.autopilot.passes.common import current_sheets, page_label
from unitforma.autopilot.service import Context, session
from unitforma.core.errors import ProblemError
from unitforma.geometry import service as geometry_service
from unitforma.inventory import service as inventory
from unitforma.mapping import service as mapping
from unitforma.projects import service as projects
from unitforma.publishing import service as publishing
from unitforma.sales import layouts as layout_service
from unitforma.tenants.models import Building, Project, UnitLayout

STEP = "defaults"
SOURCE = "autopilot"


def describe(project: Project, buildings: list[Building]) -> str:
    """A first description from what the project knows: name, address, buildings with their floor
    counts, the permit's number and decision date. Facts only; the person rewrites it."""
    parts = [str(project.name or "").strip().rstrip(".")]
    line1 = str((project.address or {}).get("line1") or "").strip().rstrip(".")
    if line1:
        parts.append(line1)
    houses = [b for b in buildings if b.kind == "building"]
    if houses:
        names = ", ".join(
            f"{b.code} ({len(b.floors)} floors)" if b.floors else b.code for b in houses[:8]
        )
        parts.append(f"{len(houses)} building(s): {names}")
    reg = project.regulatory or {}
    if reg.get("application_no"):
        when = str(reg.get("decided_at") or "")[:10]
        parts.append(
            f"Building permit {reg['application_no']}"
            + (f", decided {_date(when)}" if when else "")
        )
    return ". ".join(p for p in parts if p) + "."


def _date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %B %Y")
    except ValueError:
        return iso


async def run(ctx: Context) -> None:
    await _approve(ctx)
    await _confirm_layouts(ctx)
    await _describe(ctx)
    await _mark_and_publish(ctx)


async def _approve(ctx: Context) -> None:
    approved_units, pages, ids = 0, [], []
    async with session(ctx) as db:
        for sheet, doc in await current_sheets(db, ctx.project_id, kinds=("floor_plan",)):
            current = await mapping.current_boundaries(db, sheet.id)
            if not current or not any(b.status == "draft" for b, _u in current):
                continue
            if any(b.source != SOURCE for b, _u in current):
                continue  # a person drew here: theirs to approve
            n = await inventory.approve_sheet(db, sheet, ctx.actor)
            if n:
                approved_units += n
                pages.append(page_label(doc, sheet))
                ids.append(sheet.id)
    if approved_units:
        ctx.decide(
            STEP,
            "accepted",
            f"{approved_units} unit(s) approved on {len(pages)} sheet(s)",
            "The solver's drafts are active and verified so they can be published: "
            + ", ".join(pages[:8])
            + (" …" if len(pages) > 8 else "")
            + ". Review the outlines on the sheets afterwards",
            confidence=rules.DEFAULTS_APPROVE_CONFIDENCE,
            entity_ids=ids,
        )
        await geometry_service.queue_massing(ctx.tenant_id, ctx.project_id)


async def _confirm_layouts(ctx: Context) -> None:
    async with session(ctx) as db:
        rows = list(
            (
                await db.execute(
                    select(UnitLayout)
                    .where(UnitLayout.project_id == ctx.project_id, UnitLayout.status == "proposed")
                    .order_by(UnitLayout.code)
                )
            ).scalars()
        )
        for lay in rows:
            await layout_service.confirm(db, lay, ctx.actor)
        if rows:
            ctx.decide(
                STEP,
                "accepted",
                f"{len(rows)} plan type(s) confirmed",
                "Proposed plan types are confirmed so their codes reach the portal: "
                + ", ".join(lay.code for lay in rows[:12])
                + (" …" if len(rows) > 12 else ""),
                confidence=rules.DEFAULTS_LAYOUTS_CONFIDENCE,
                entity_ids=[lay.id for lay in rows],
            )


async def _describe(ctx: Context) -> None:
    async with session(ctx) as db:
        project = (
            await db.execute(select(Project).where(Project.id == ctx.project_id))
        ).scalar_one()
        if project.description or (project.portal_settings or {}).get("hero_text"):
            return
        text = describe(project, await projects.list_buildings(db, ctx.project_id))
        await projects.update_project(
            db, project, {"description": text}, project.version, ctx.actor
        )
        ctx.decide(
            STEP,
            "accepted",
            "Description written from the project's facts",
            f'"{text[:200]}" — replace it with your own text on the Publish page',
            confidence=rules.DEFAULTS_DESCRIPTION_CONFIDENCE,
            needs_you=True,
            entity_type="project",
            entity_id=project.id,
        )


async def _mark_and_publish(ctx: Context) -> None:
    async with session(ctx) as db:
        project = (
            await db.execute(select(Project).where(Project.id == ctx.project_id))
        ).scalar_one()
        n = await publishing.set_unit_publication(
            db, project, unit_ids=None, all_active=True, status="published", actor=ctx.actor
        )
        if n:
            ctx.decide(
                STEP,
                "accepted",
                f"{n} unit(s) marked for publication",
                "Every active unit is listed; prices stay as they are (on request when empty)",
                confidence=rules.DEFAULTS_PUBLISH_CONFIDENCE,
                entity_type="project",
                entity_id=project.id,
            )
    async with session(ctx) as db:
        project = (
            await db.execute(select(Project).where(Project.id == ctx.project_id))
        ).scalar_one()
        try:
            pub, _token = await publishing.publish(db, project, mode="publish", actor=ctx.actor)
        except ProblemError as e:
            ctx.decide(
                STEP,
                "skipped",
                "Not published",
                f"{e.detail or e.title}. Fix it and press Publish with defaults again",
                needs_you=True,
                entity_type="project",
                entity_id=project.id,
            )
            return
        base = await publishing.portal_base_url(db, project)
        summary: dict[str, Any] = pub.summary or {}
        ctx.decide(
            STEP,
            "accepted",
            f"Published v{pub.version_no}",
            f"{base or 'The portal'} shows version {pub.version_no} with "
            f"{summary.get('units', summary.get('listed', '')) or ''} unit(s); adjust and publish "
            "again when you are done",
            confidence=rules.DEFAULTS_PUBLISH_CONFIDENCE,
            entity_type="publication",
            entity_id=pub.id,
        )
