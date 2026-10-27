"""The setup checklist (ADR-0017 Decision 5): the order of work for a project, what each step
needs and which screen completes it. Read-only; it reuses the publish readiness."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.documents import service as documents
from unitforma.geometry import service as geometry
from unitforma.projects import service as projects
from unitforma.publishing.service import current_publication, readiness
from unitforma.tenants.models import Floor, GeometryModel, Project, Sheet, SiteFeature, Unit

Status = str  # done | todo | optional | attention


def _step(
    key: str,
    title: str,
    status: Status,
    detail: str,
    link: str,
    count: int | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "status": status,
        "detail": detail,
        "count": count,
        "link": link,
    }


def units_todo(n_units: int, n_active: int) -> str:
    """What stands between the project and its first publication, said exactly (ADR-0029
    Decision 5): the readiness item only says "no units are marked"."""
    if n_units == 0:
        return (
            "No units yet: open a processed floor plan page, accept the solver's candidates or "
            "draw the apartments, then approve the sheet"
        )
    if n_active == 0:
        return (
            f"{n_units} draft unit(s) and none approved: open their sheets and approve them, or "
            "press Publish with defaults on this checklist"
        )
    return (
        f"{n_active} active unit(s) and none marked for publication: select them in the "
        "inventory grid, or press Publish with defaults on this checklist"
    )


def _msg(item: dict[str, Any] | None) -> str:
    if not item:
        return ""
    return str(item.get("message") or item.get("text") or item.get("detail") or "")


async def setup_status(db: AsyncSession, project: Project) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    docs = await documents.list_documents(db, project.id)
    plans = [(d, r) for d, r in docs if d.kind == "floor_plan"]
    processed = sum(1 for _, r in plans if r is not None and r.processing_status == "done")
    steps.append(
        _step(
            "documents",
            "Floor plans uploaded and processed",
            "done" if processed else "todo",
            f"{len(plans)} floor plan document(s), {processed} processed"
            if plans
            else "Upload the floor plans (PDF or DXF); the worker reads the pages and proposes "
            "floors",
            "documents",
            processed,
        )
    )

    # the "site" pseudo-building (outdoor units) has no floors, placement or facades
    buildings = [b for b in await projects.list_buildings(db, project.id) if b.kind == "building"]
    floor_counts = dict(
        (
            await db.execute(
                select(Floor.building_id, func.count())
                .where(Floor.building_id.in_([b.id for b in buildings] or [uuid.uuid4()]))
                .group_by(Floor.building_id)
            )
        ).all()
    )
    without = [b.code for b in buildings if not floor_counts.get(b.id)]
    steps.append(
        _step(
            "floors",
            "Buildings and their floors",
            "done" if buildings and not without else "todo",
            (
                f"{len(buildings)} building(s), {sum(floor_counts.values())} floor(s)"
                + (f"; no floors yet: {', '.join(without)}" if without else "")
            )
            if buildings
            else "Add a building, then accept the floor proposal or generate floors",
            "overview",
            len(buildings),
        )
    )

    rd = await readiness(db, project)
    items = {i["key"]: i for i in rd["items"]}
    units_item = items.get("units")
    n_units, n_active = (
        await db.execute(
            select(
                func.count(),
                func.count().filter(Unit.lifecycle_status == "active"),
            ).where(Unit.project_id == project.id, Unit.lifecycle_status != "removed")
        )
    ).one()
    units_ok = units_item is not None and units_item.get("level") == "ok"
    steps.append(
        _step(
            "mapping",
            "Units outlined and approved on the sheets",
            "done" if units_ok else "todo",
            _msg(units_item) if units_ok else units_todo(int(n_units), int(n_active)),
            "documents",
        )
    )

    frame = project.site_frame or {}
    sheet = None
    if frame.get("sheet_id"):
        try:
            sheet = (
                await db.execute(select(Sheet).where(Sheet.id == uuid.UUID(str(frame["sheet_id"]))))
            ).scalar_one_or_none()
        except ValueError:
            sheet = None
    calibrated = bool(sheet is not None and (sheet.calibration or {}).get("m_per_px"))
    site_docs = [d for d, _ in docs if d.kind == "site_plan"]
    if sheet is not None and calibrated:
        site_status, site_detail = "done", "Site plan chosen and calibrated"
    elif sheet is not None:
        site_status, site_detail = "attention", "Site plan chosen but not calibrated: set its scale"
    elif site_docs:
        site_status = "attention"
        site_detail = (
            f"{len(site_docs)} site plan document(s) uploaded; choose one on Site placement"
        )
    else:
        site_status = "todo"
        site_detail = "Upload the general plan (გენგეგმა) as a Site plan document"
    steps.append(
        _step("site_plan", "Site plan chosen and calibrated", site_status, site_detail, "placement")
    )

    confirmed = [b for b in buildings if b.placement_status == "confirmed"]
    steps.append(
        _step(
            "placement",
            "Buildings placed on the site plan",
            "done" if buildings and len(confirmed) == len(buildings) and calibrated else "todo",
            f"{len(confirmed)} of {len(buildings)} placement(s) confirmed"
            if buildings
            else "Place each footprint once the site plan is calibrated",
            "placement",
            len(confirmed),
        )
    )

    assigned = {str(b.id): len(geometry.facade_assignments(project, b)) for b in buildings}
    with_facade = [b for b in buildings if assigned.get(str(b.id), 0) > 0]
    steps.append(
        _step(
            "facades",
            "Facade drawings on the 3D model",
            "done" if buildings and len(with_facade) == len(buildings) else "todo",
            f"{sum(assigned.values())} side(s) assigned on {len(with_facade)} of "
            f"{len(buildings)} building(s)"
            if buildings
            else "Pick the elevation sheet for each side of each building",
            "placement",
            sum(assigned.values()),
        )
    )

    features = (
        await db.execute(
            select(func.count())
            .select_from(SiteFeature)
            .where(SiteFeature.project_id == project.id, SiteFeature.is_public.is_(True))
        )
    ).scalar_one()
    steps.append(
        _step(
            "features",
            "Site features: green, roads, parking, entrances",
            "done" if features else "optional",
            f"{features} public feature(s) drawn on the site plan"
            if features
            else "Draw them on the site plan; the portal shows them in 2D and as ground, paving "
            "and trees in 3D",
            "placement",
            features,
        )
    )

    public_renders = sum(1 for d, _ in docs if d.kind == "render" and d.visibility == "public")
    steps.append(
        _step(
            "gallery",
            "Renders in the portal gallery",
            "done" if "gallery" not in items else "todo",
            f"{public_renders} public render document(s)"
            if public_renders
            else _msg(items.get("gallery")) or "Mark a render document public under Documents",
            "documents",
            public_renders,
        )
    )

    address = project.address or {}
    has_position = address.get("lat") is not None and address.get("lng") is not None
    steps.append(
        _step(
            "location",
            "Map position",
            "done" if has_position else "todo",
            f"{address.get('lat')}, {address.get('lng')}"
            if has_position
            else "Set latitude and longitude on the Publish page; the portal shows a map",
            "publish",
        )
    )

    steps.append(
        _step(
            "prices",
            "Prices, or 'price on request'",
            "done" if "no_price" not in items else "attention",
            _msg(items.get("no_price"))
            or "Every available unit has a price or is marked on request",
            "inventory",
        )
    )

    ifc = (
        await db.execute(
            select(func.count())
            .select_from(GeometryModel)
            .where(
                GeometryModel.project_id == project.id,
                GeometryModel.kind == "ifc",
                GeometryModel.status == "ready",
            )
        )
    ).scalar_one()
    steps.append(
        _step(
            "architect_model",
            "Architect's 3D model (IFC)",
            "done" if ifc else "optional",
            f"{ifc} model(s) linked; the portal shows the model instead of the massing"
            if ifc
            else "Ask the architect for an IFC export (ArchiCAD: File → Save as → IFC, zones as "
            "spaces) and upload it under the building; the portal then shows the real building",
            "documents",
            ifc,
        )
    )

    pub = await current_publication(db, project.id)
    blocking = [
        units_todo(int(n_units), int(n_active)) if i.get("key") == "units" else _msg(i)
        for i in rd["items"]
        if i.get("level") == "error"
    ]
    steps.append(
        _step(
            "publish",
            "Published to the portal",
            "done" if pub is not None else ("attention" if blocking else "todo"),
            f"v{pub.version_no} is live"
            if pub is not None
            else (
                "; ".join(blocking)
                if blocking
                else "Preview, then publish the first version, or press Publish with defaults"
            ),
            "publish",
        )
    )

    done = sum(1 for s in steps if s["status"] == "done")
    return {"done": done, "total": len(steps), "steps": steps}
