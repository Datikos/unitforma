"""Worker entry point for ``geometry.build_massing`` (plan §12.3)."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select

from unitforma.core.db import tenant_session
from unitforma.geometry import service
from unitforma.tenants.models import Project

log = structlog.get_logger()


async def build_massing(tenant_id: uuid.UUID, project_id: uuid.UUID) -> dict:
    async with tenant_session(tenant_id, scope="tenant") as db:
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        model = await service.generate_massing(db, project)
        log.info(
            "geometry.massing_built",
            project_id=str(project_id),
            model_id=str(model.id),
            status=model.status,
            stats=model.stats,
        )
        return {"model_id": str(model.id), "status": model.status, "stats": model.stats}
