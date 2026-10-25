"""Platform administration (cross-tenant)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from unitforma.api.schemas import InvitationOut, TenantCreate, TenantOut
from unitforma.core.db import tenant_session
from unitforma.core.errors import ProblemError
from unitforma.identity.deps import require_platform_admin
from unitforma.identity.principal import StaffPrincipal
from unitforma.tenants import service as tenants
from unitforma.tenants.models import Tenant

router = APIRouter(prefix="/api/v1/platform", tags=["platform"])


@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants(principal: Annotated[StaffPrincipal, Depends(require_platform_admin)]):
    async with tenant_session(None, user_id=principal.user_id, scope="platform") as db:
        rows = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
        return [TenantOut.model_validate(t) for t in rows.scalars()]


@router.post("/tenants", response_model=TenantOut, status_code=201)
async def create_tenant(
    body: TenantCreate, principal: Annotated[StaffPrincipal, Depends(require_platform_admin)]
):
    async with tenant_session(None, user_id=principal.user_id, scope="platform") as db:
        tenant = await tenants.create_tenant(
            db,
            slug=body.slug,
            name=body.name,
            default_currency=body.default_currency,
            actor_user_id=principal.user_id,
        )
        out = TenantOut.model_validate(tenant)
        if body.admin_email:
            await tenants.create_invitation(
                db,
                tenant_id=tenant.id,
                email=body.admin_email,
                role="tenant_admin",
                all_projects=True,
                project_ids=[],
                actor_user_id=principal.user_id,
                actor_role="platform_admin",
            )
        return out


@router.post("/tenants/{tenant_id}/invitations", response_model=InvitationOut, status_code=201)
async def invite_tenant_admin(
    tenant_id: uuid.UUID,
    email: str,
    principal: Annotated[StaffPrincipal, Depends(require_platform_admin)],
):
    async with tenant_session(tenant_id, user_id=principal.user_id, scope="platform") as db:
        if (
            await db.execute(select(func.count()).select_from(Tenant).where(Tenant.id == tenant_id))
        ).scalar_one() == 0:
            raise ProblemError(404, "Tenant not found")
        inv, token = await tenants.create_invitation(
            db,
            tenant_id=tenant_id,
            email=email,
            role="tenant_admin",
            all_projects=True,
            project_ids=[],
            actor_user_id=principal.user_id,
            actor_role="platform_admin",
        )
        return InvitationOut(
            id=inv.id,
            email=inv.email,
            role=inv.role,
            project_ids=inv.project_ids,
            expires_at=inv.expires_at,
            accepted=False,
            accept_url=tenants.accept_url(token),
        )
