"""Staff API: publication readiness, unit publication flags, preview, publish, unpublish (§9.3)."""

from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends

from unitforma.api.schemas import (
    PublicationOut,
    PublishRequest,
    PublishResult,
    ReadinessOut,
    UnitPublicationIn,
    UnitPublicationOut,
)
from unitforma.identity.authz import Action
from unitforma.identity.deps import TenantContext, tenant_context
from unitforma.projects import service as projects
from unitforma.publishing import service as publishing

router = APIRouter(prefix="/api/v1/admin/tenants/{tenant_id}", tags=["publishing"])
Ctx = Annotated[TenantContext, Depends(tenant_context)]


def _actor(ctx: TenantContext) -> tuple[uuid.UUID, str]:
    return ctx.principal.user_id, ctx.actor_role


async def _project(ctx: TenantContext, project_id: uuid.UUID, action: Action):
    ctx.require("publication", action)
    ctx.require_project(project_id)
    return await projects.get_project(ctx.session, ctx.tenant_id, project_id)


@router.get("/projects/{project_id}/publish/readiness", response_model=ReadinessOut)
async def readiness(project_id: uuid.UUID, ctx: Ctx):
    project = await _project(ctx, project_id, Action.READ)
    out = await publishing.readiness(ctx.session, project)
    out["unit_counts"] = await publishing.count_public_units(ctx.session, project.id)
    return out


@router.put("/projects/{project_id}/units/publication", response_model=UnitPublicationOut)
async def set_unit_publication(project_id: uuid.UUID, body: UnitPublicationIn, ctx: Ctx):
    """Mark units published / hidden (linkable, not listed) / unpublished (plan §6.1)."""
    project = await _project(ctx, project_id, Action.PUBLISH)
    n = await publishing.set_unit_publication(
        ctx.session,
        project,
        unit_ids=body.unit_ids,
        all_active=body.all_active,
        status=body.status,
        actor=_actor(ctx),
    )
    return {
        "changed": n,
        "unit_counts": await publishing.count_public_units(ctx.session, project.id),
    }


@router.get("/projects/{project_id}/publications", response_model=list[PublicationOut])
async def list_publications(project_id: uuid.UUID, ctx: Ctx):
    project = await _project(ctx, project_id, Action.READ)
    return await publishing.list_publications(ctx.session, project.id)


@router.post("/projects/{project_id}/publications", response_model=PublishResult, status_code=201)
async def publish(project_id: uuid.UUID, body: PublishRequest, ctx: Ctx):
    """``preview``: build a snapshot visible only with the returned 1 h link.
    ``publish``: build it and switch the portal to it atomically."""
    project = await _project(ctx, project_id, Action.PUBLISH)
    pub, token = await publishing.publish(ctx.session, project, mode=body.mode, actor=_actor(ctx))
    base = await publishing.portal_base_url(ctx.session, project)
    return PublishResult(
        publication=PublicationOut.model_validate(pub),
        portal_url=base,
        preview_token=token,
        preview_url=f"{base}?preview={quote(token)}" if (token and base) else None,
    )


@router.post("/projects/{project_id}/unpublish", response_model=PublicationOut)
async def unpublish(project_id: uuid.UUID, ctx: Ctx):
    """Retire the live publication; the portal shows "coming soon" within seconds."""
    project = await _project(ctx, project_id, Action.PUBLISH)
    return await publishing.unpublish(ctx.session, project, _actor(ctx))
