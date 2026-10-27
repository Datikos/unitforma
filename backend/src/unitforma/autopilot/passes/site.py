"""Site plan pass (ADR-0025 Decision 5 "site plan"): the project's one processed site plan
becomes the site frame; several leave the choice to a person."""

from __future__ import annotations

from sqlalchemy import select

from unitforma.autopilot import rules
from unitforma.autopilot.passes.common import current_sheets
from unitforma.autopilot.service import Context, session
from unitforma.projects import service as projects
from unitforma.tenants.models import Project

STEP = "site_plan"


async def run(ctx: Context) -> None:
    async with session(ctx) as db:
        project = (
            await db.execute(select(Project).where(Project.id == ctx.project_id))
        ).scalar_one()
        frame = dict(project.site_frame or {})
        if frame.get("sheet_id"):
            return
        sheets = await current_sheets(db, ctx.project_id, kinds=("site_plan",))
        docs: dict = {}
        for sheet, doc in sheets:
            docs.setdefault(doc.id, (doc.title, []))[1].append(sheet)
        if not docs:
            return
        if len(docs) > 1:
            ctx.decide(
                STEP,
                "skipped",
                f"{len(docs)} site plan documents",
                "Choose the one the portal should show on Site placement: "
                + ", ".join(t for t, _ in docs.values()),
                needs_you=True,
            )
            return
        (title, pages) = next(iter(docs.values()))
        sheet = sorted(pages, key=lambda s: s.page_no)[0]
        frame["sheet_id"] = str(sheet.id)
        await projects.update_project(
            db, project, {"site_frame": frame}, project.version, ctx.actor
        )
        calibrated = bool(sheet.calibration_status in ("calibrated", "inherited"))
        ctx.decide(
            STEP,
            "accepted",
            f"Site plan: {title} p.{sheet.page_no}",
            "The project's only site plan is the site frame"
            + ("" if calibrated else "; it has no scale yet: calibrate it on Site placement"),
            confidence=rules.SITE_PLAN_CONFIDENCE,
            entity_type="sheet",
            entity_id=sheet.id,
            sheet_id=sheet.id,
        )
        if not calibrated:
            ctx.decide(
                STEP,
                "skipped",
                "Site plan has no scale",
                "No single printed scale on the sheet; set two points of a known distance",
                needs_you=True,
                entity_type="sheet",
                entity_id=sheet.id,
                sheet_id=sheet.id,
            )
