"""Staff API: building footprints, placement and the generated massing model (plan §11.3)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from unitforma.api.schemas import FootprintOut, MassingOut
from unitforma.core.errors import ProblemError
from unitforma.geometry import service as geometry
from unitforma.identity.authz import Action
from unitforma.identity.deps import TenantContext, tenant_context
from unitforma.jobs.app import app as jobs
from unitforma.projects import service as projects

router = APIRouter(prefix="/api/v1/admin/tenants/{tenant_id}", tags=["geometry"])
Ctx = Annotated[TenantContext, Depends(tenant_context)]


def _massing_out(m) -> MassingOut:
    out = MassingOut.model_validate(m)
    out.glb_url = geometry.signed_url(m)
    return out


@router.get("/projects/{project_id}/footprints", response_model=list[FootprintOut])
async def list_footprints(project_id: uuid.UUID, ctx: Ctx):
    """Building outlines (lowest mapped floor, building-local metres) for the placement editor."""
    ctx.require("project", Action.READ)
    ctx.require_project(project_id)
    project = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    return await geometry.footprints(ctx.session, project)


@router.get("/projects/{project_id}/massing", response_model=MassingOut)
async def get_massing(project_id: uuid.UUID, ctx: Ctx):
    ctx.require("project", Action.READ)
    ctx.require_project(project_id)
    return _massing_out(await geometry.require_model(ctx.session, ctx.tenant_id, project_id))


@router.post("/projects/{project_id}/massing", response_model=MassingOut, status_code=202)
async def regenerate_massing(project_id: uuid.UUID, ctx: Ctx):
    """Queue a rebuild of the massing GLB (``geometry.build_massing``). The worker replaces the
    current model; until then the previous one stays available."""
    ctx.require("mapping", Action.WRITE)
    ctx.require_project(project_id)
    project = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    try:
        await jobs.configure_task(name="geometry.build_massing", queue="geometry").defer_async(
            tenant_id=str(ctx.tenant_id), project_id=str(project.id)
        )
    except Exception as e:  # noqa: BLE001
        raise ProblemError(503, "Worker queue unavailable", str(e)[:300]) from e
    current = await geometry.current_massing(ctx.session, project.id)
    if current is None:
        # nothing to show yet: report the queued state without a model row
        return MassingOut(
            id=uuid.UUID(int=0),
            project_id=project.id,
            kind="massing_generated",
            status="generating",
            stats={},
            error=None,
            glb_url=None,
            created_at=project.updated_at,
        )
    return _massing_out(current)
