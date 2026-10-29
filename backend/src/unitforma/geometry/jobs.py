"""Worker entry point for ``geometry.build_massing`` (plan §12.3)."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select

from unitforma.core.db import tenant_session
from unitforma.geometry import service, site_outline
from unitforma.tenants.models import Project

log = structlog.get_logger()


async def build_massing(tenant_id: uuid.UUID, project_id: uuid.UUID) -> dict:
    async with tenant_session(tenant_id, scope="tenant") as db:
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        model = await service.generate_massing(db, project)
        try:
            # the site plan's own outline of each placed building (ADR-0035 Decision 1)
            outlines = await site_outline.refresh(db, project)
        except Exception as e:  # noqa: BLE001 - the hull stays; the massing is built
            log.warning("geometry.site_outline_failed", project_id=str(project_id), error=str(e))
            outlines = None
        log.info(
            "geometry.massing_built",
            project_id=str(project_id),
            model_id=str(model.id),
            status=model.status,
            stats=model.stats,
            outlines=outlines,
        )
        return {"model_id": str(model.id), "status": model.status, "stats": model.stats}
