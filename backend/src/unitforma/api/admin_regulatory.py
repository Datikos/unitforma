"""Staff API: bootstrap a project from a public building permit (ADR-0007)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from unitforma.api import admin_setup
from unitforma.api.schemas import (
    PermitImportCreate,
    PermitImportResult,
    PermitPreviewOut,
    PermitReference,
    RegulatoryImportOut,
)
from unitforma.core.errors import ProblemError
from unitforma.core.settings import get_settings
from unitforma.identity.authz import Action
from unitforma.identity.deps import TenantContext, open_session, tenant_access, tenant_context
from unitforma.jobs.app import app as jobs
from unitforma.projects import service as projects
from unitforma.regulatory import service as regulatory
from unitforma.regulatory import tasge
from unitforma.tenants.models import RegulatoryImport, Tenant

router = APIRouter(prefix="/api/v1/admin/tenants/{tenant_id}", tags=["regulatory"])
Ctx = Annotated[TenantContext, Depends(tenant_context)]
# rights checked, no session held across the registry call (BACKLOG 15)
Access = Annotated[TenantContext, Depends(tenant_access)]


def _enabled() -> None:
    if not get_settings().regulatory_tasge_enabled:
        raise ProblemError(404, "Not found", "Permit import is disabled on this installation")


def _actor(ctx: TenantContext) -> tuple[uuid.UUID, str]:
    return ctx.principal.user_id, ctx.actor_role


def _out(row: RegulatoryImport) -> RegulatoryImportOut:
    out = RegulatoryImportOut.model_validate(row)
    out.permit = {
        **((row.record or {}).get("permit") or {}),
        "heights": tasge.heights(row.record or {}),
    }
    out.counts = {k: len(v) for k, v in (row.stats or {}).items() if isinstance(v, list)}
    return out


async def _enqueue(row: RegulatoryImport) -> None:
    try:
        await jobs.configure_task(name="regulatory.import_attachments", queue="docs").defer_async(
            tenant_id=str(row.tenant_id), import_id=str(row.id)
        )
    except Exception as e:  # noqa: BLE001 - the worker schema may be absent in minimal setups
        row.error = f"could not enqueue: {e}"[:500]


@router.post("/regulatory/tasge/preview", response_model=PermitPreviewOut)
async def preview_permit(body: PermitReference, access: Access):
    """The registry call runs with no database connection held (BACKLOG 15)."""
    _enabled()
    access.require("project", Action.WRITE)
    return await regulatory.preview(body.reference)


@router.post("/regulatory/tasge/import", response_model=PermitImportResult, status_code=201)
async def import_permit(body: PermitImportCreate, access: Access):
    """Rights first, then the registry call outside any transaction, then one transaction for
    the project, building and import row (BACKLOG 15)."""
    _enabled()
    access.require("project", Action.WRITE)
    if body.setup_auto and body.setup_auto.enabled and body.setup_auto.approve_sheets:
        access.require("mapping", Action.APPROVE)
    if body.setup_auto and body.setup_auto.enabled and body.setup_auto.publish_defaults:
        admin_setup.require_publish_defaults(access)
    record = await regulatory.fetch_normalised(body.reference)
    async with open_session(access) as ctx:
        tenant = (
            await ctx.session.execute(select(Tenant).where(Tenant.id == ctx.tenant_id))
        ).scalar_one()
        project, building, row = await regulatory.start_import(
            ctx.session,
            tenant_id=ctx.tenant_id,
            actor=_actor(ctx),
            reference=body.reference,
            slug=body.slug,
            name=body.name,
            building_code=body.building_code,
            default_currency=tenant.default_currency,
            setup_auto=body.setup_auto.model_dump() if body.setup_auto else None,
            record=record,
        )
        await _enqueue(row)
        building = await projects.get_building(ctx.session, ctx.tenant_id, building.id)
        return PermitImportResult(project=project, building=building, job=_out(row))


@router.post("/projects/{project_id}/regulatory/tasge/refresh", response_model=RegulatoryImportOut)
async def refresh_permit(project_id: uuid.UUID, access: Access):
    """Checks in a short transaction, the registry call outside one, the write in a third; the
    checks run again there in case another refresh started meanwhile (BACKLOG 15)."""
    _enabled()
    access.require("documents", Action.WRITE)
    access.require_project(project_id)
    async with open_session(access) as ctx:
        project = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
        external_id = await regulatory.refresh_target(ctx.session, project)
    record = await regulatory.fetch_normalised(external_id)
    async with open_session(access) as ctx:
        project = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
        row = await regulatory.refresh(ctx.session, project, _actor(ctx), record=record)
        await _enqueue(row)
        return _out(row)


@router.get("/projects/{project_id}/regulatory/imports", response_model=list[RegulatoryImportOut])
async def list_imports(project_id: uuid.UUID, ctx: Ctx):
    ctx.require("project", Action.READ)
    ctx.require_project(project_id)
    await projects.get_project(ctx.session, ctx.tenant_id, project_id)
    return [_out(r) for r in await regulatory.list_imports(ctx.session, project_id)]
