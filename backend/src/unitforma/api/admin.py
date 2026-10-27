"""Staff workspace API: me, tenant settings, members, invitations, API tokens, audit."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from unitforma.api.schemas import (
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenOut,
    AuditOut,
    AuditPage,
    InvitationAccept,
    InvitationCreate,
    InvitationOut,
    MemberOut,
    MembershipSummary,
    MemberUpdate,
    MeOut,
    TenantOut,
    TenantUpdate,
)
from unitforma.audit.service import write_audit
from unitforma.core.db import tenant_session
from unitforma.core.errors import ProblemError
from unitforma.core.ids import new_id
from unitforma.identity import tokens
from unitforma.identity.authz import Action, is_allowed
from unitforma.identity.deps import TenantContext, current_staff, tenant_context
from unitforma.identity.principal import StaffPrincipal
from unitforma.tenants import service as tenants
from unitforma.tenants.models import (
    AuditLog,
    Membership,
    MembershipProjectAccess,
    StaffInvitation,
    Tenant,
    User,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
Ctx = Annotated[TenantContext, Depends(tenant_context)]


@router.get("/me", response_model=MeOut)
async def me(principal: Annotated[StaffPrincipal, Depends(current_staff)]):
    async with tenant_session(None, user_id=principal.user_id, scope="platform") as db:
        rows = await db.execute(
            select(Membership, Tenant)
            .join(Tenant, Tenant.id == Membership.tenant_id)
            .where(Membership.user_id == principal.user_id)
        )
        memberships = [
            MembershipSummary(
                tenant_id=t.id,
                tenant_slug=t.slug,
                tenant_name=t.name,
                role=m.role,
                status=m.status,
                all_projects=m.all_projects,
            )
            for m, t in rows
        ]
    return MeOut(
        user_id=principal.user_id,
        email=principal.email,
        email_verified=principal.email_verified,
        is_platform_admin=principal.is_platform_admin,
        aal=principal.aal,
        memberships=memberships,
    )


@router.post("/invitations/accept", response_model=MembershipSummary)
async def accept_invitation(
    body: InvitationAccept, principal: Annotated[StaffPrincipal, Depends(current_staff)]
):
    async with tenant_session(None, user_id=principal.user_id, scope="platform") as db:
        user = (await db.execute(select(User).where(User.id == principal.user_id))).scalar_one()
        m = await tenants.accept_invitation(
            db, token=body.token, user=user, user_email_verified=principal.email_verified
        )
        t = (await db.execute(select(Tenant).where(Tenant.id == m.tenant_id))).scalar_one()
        return MembershipSummary(
            tenant_id=t.id,
            tenant_slug=t.slug,
            tenant_name=t.name,
            role=m.role,
            status=m.status,
            all_projects=m.all_projects,
        )


# --- tenant -------------------------------------------------------------------------
@router.get("/tenants/{tenant_id}", response_model=TenantOut)
async def get_tenant(ctx: Ctx):
    t = (
        await ctx.session.execute(select(Tenant).where(Tenant.id == ctx.tenant_id))
    ).scalar_one_or_none()
    if t is None:
        raise ProblemError(404, "Tenant not found")
    return t


@router.patch("/tenants/{tenant_id}", response_model=TenantOut)
async def update_tenant(body: TenantUpdate, ctx: Ctx):
    ctx.require("tenant.settings", Action.WRITE)
    t = (await ctx.session.execute(select(Tenant).where(Tenant.id == ctx.tenant_id))).scalar_one()
    changes = body.model_dump(exclude_none=True)
    if "status" in changes and ctx.scope != "platform":
        raise ProblemError(403, "Only platform administrators change tenant status")
    before = {k: getattr(t, k) for k in changes}
    for k, v in changes.items():
        if k == "settings":  # merge: a page editing one key keeps the others (ADR-0023)
            v = {**(t.settings or {}), **v}  # branding stays replace-whole: Publish clears keys
        setattr(t, k, v.upper() if k == "default_currency" else v)
    await write_audit(
        ctx.session,
        tenant_id=t.id,
        actor_user_id=ctx.principal.user_id,
        actor_role=ctx.actor_role,
        entity_type="tenant",
        entity_id=t.id,
        action="update",
        before=before,
        after=changes,
        request_id=ctx.request_id,
    )
    return t


# --- members ------------------------------------------------------------------------
async def _member_out(ctx: TenantContext, m: Membership, u: User) -> MemberOut:
    return MemberOut(
        id=m.id,
        user_id=u.id,
        email=u.email,
        display_name=u.display_name,
        role=m.role,
        status=m.status,
        all_projects=m.all_projects,
        project_ids=[] if m.all_projects else await tenants.member_project_ids(ctx.session, m.id),
        accepted_at=m.accepted_at,
    )


@router.get("/tenants/{tenant_id}/members", response_model=list[MemberOut])
async def list_members(ctx: Ctx):
    ctx.require("tenant.users", Action.READ)
    rows = await ctx.session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.tenant_id == ctx.tenant_id)
        .order_by(User.email)
    )
    return [await _member_out(ctx, m, u) for m, u in rows]


@router.patch("/tenants/{tenant_id}/members/{membership_id}", response_model=MemberOut)
async def update_member(membership_id: uuid.UUID, body: MemberUpdate, ctx: Ctx):
    ctx.require("tenant.users", Action.MANAGE)
    row = (
        await ctx.session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.tenant_id == ctx.tenant_id, Membership.id == membership_id)
        )
    ).first()
    if row is None:
        raise ProblemError(404, "Member not found")
    m, u = row
    changes = body.model_dump(exclude_none=True)
    before = {"role": m.role, "status": m.status, "all_projects": m.all_projects}
    demoting_admin = m.role == "tenant_admin" and (
        changes.get("role") not in (None, "tenant_admin") or changes.get("status") == "suspended"
    )
    if demoting_admin and await tenants.count_active_admins(ctx.session, ctx.tenant_id) <= 1:
        raise ProblemError(409, "Cannot remove the last tenant administrator")
    if "role" in changes:
        m.role = changes["role"]
    if "status" in changes:
        m.status = changes["status"]
    if "all_projects" in changes:
        m.all_projects = changes["all_projects"]
    if "project_ids" in changes:
        await ctx.session.execute(
            MembershipProjectAccess.__table__.delete().where(
                MembershipProjectAccess.membership_id == m.id
            )
        )
        for pid in changes["project_ids"]:
            ctx.session.add(
                MembershipProjectAccess(
                    id=new_id(), tenant_id=ctx.tenant_id, membership_id=m.id, project_id=pid
                )
            )
        if changes["project_ids"]:
            m.all_projects = False
    await ctx.session.flush()
    await write_audit(
        ctx.session,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.principal.user_id,
        actor_role=ctx.actor_role,
        entity_type="membership",
        entity_id=m.id,
        action="update",
        before=before,
        after={k: (v if k != "project_ids" else [str(x) for x in v]) for k, v in changes.items()},
        request_id=ctx.request_id,
    )
    return await _member_out(ctx, m, u)


# --- invitations --------------------------------------------------------------------
@router.get("/tenants/{tenant_id}/invitations", response_model=list[InvitationOut])
async def list_invitations(ctx: Ctx):
    ctx.require("tenant.users", Action.READ)
    rows = await ctx.session.execute(
        select(StaffInvitation)
        .where(StaffInvitation.tenant_id == ctx.tenant_id)
        .order_by(StaffInvitation.created_at.desc())
    )
    return [
        InvitationOut(
            id=i.id,
            email=i.email,
            role=i.role,
            project_ids=i.project_ids,
            expires_at=i.expires_at,
            accepted=i.accepted_membership_id is not None,
        )
        for i in rows.scalars()
    ]


@router.post("/tenants/{tenant_id}/invitations", response_model=InvitationOut, status_code=201)
async def create_invitation(body: InvitationCreate, ctx: Ctx):
    ctx.require("tenant.users", Action.MANAGE)
    inv, token = await tenants.create_invitation(
        ctx.session,
        tenant_id=ctx.tenant_id,
        email=body.email,
        role=body.role,
        all_projects=body.all_projects,
        project_ids=body.project_ids,
        actor_user_id=ctx.principal.user_id,
        actor_role=ctx.actor_role,
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


@router.delete("/tenants/{tenant_id}/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(invitation_id: uuid.UUID, ctx: Ctx):
    ctx.require("tenant.users", Action.MANAGE)
    inv = (
        await ctx.session.execute(
            select(StaffInvitation).where(
                StaffInvitation.tenant_id == ctx.tenant_id, StaffInvitation.id == invitation_id
            )
        )
    ).scalar_one_or_none()
    if inv is None:
        raise ProblemError(404, "Invitation not found")
    if inv.accepted_membership_id is not None:
        raise ProblemError(409, "Invitation already accepted")
    await ctx.session.delete(inv)
    await write_audit(
        ctx.session,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.principal.user_id,
        actor_role=ctx.actor_role,
        entity_type="staff_invitation",
        entity_id=inv.id,
        action="revoke",
        request_id=ctx.request_id,
    )
    return None


# --- API tokens (ADR-0015) ------------------------------------------------------------
def _token_out(t, email: str) -> ApiTokenOut:
    return ApiTokenOut(
        id=t.id,
        user_id=t.user_id,
        user_email=email,
        name=t.name,
        token_prefix=t.token_prefix,
        scope=t.scope,
        status=tokens.status_of(t),
        expires_at=t.expires_at,
        last_used_at=t.last_used_at,
        revoked_at=t.revoked_at,
        created_at=t.created_at,
    )


def _manages_tokens(ctx: TenantContext) -> bool:
    return ctx.scope == "platform" or is_allowed(ctx.membership, "tenant.users", Action.MANAGE)


@router.get("/tenants/{tenant_id}/tokens", response_model=list[ApiTokenOut])
async def list_api_tokens(ctx: Ctx):
    """Own tokens; every token of the tenant for whoever manages its users."""
    owner = None if _manages_tokens(ctx) else ctx.principal.user_id
    rows = await tokens.list_tokens(ctx.session, ctx.tenant_id, user_id=owner)
    return [_token_out(t, email) for t, email in rows]


@router.post("/tenants/{tenant_id}/tokens", response_model=ApiTokenCreated, status_code=201)
async def create_api_token(body: ApiTokenCreate, ctx: Ctx):
    """A token for the caller; it acts through the caller's membership and never does more
    than that role allows. A platform admin holds a token only where they are a member
    (ADR-0015 Decision 3): the MCP side loads the membership on every call."""
    m = ctx.membership
    if not (m.is_member and m.is_active):
        raise ProblemError(
            403,
            "Not a member of this workspace",
            "A token acts through a membership; join this workspace as a member first",
        )
    t, secret = await tokens.create_token(
        ctx.session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.principal.user_id,
        name=body.name,
        scope=body.scope,
        expires_in_days=body.expires_in_days,
        actor=(ctx.principal.user_id, ctx.actor_role),
    )
    out = _token_out(t, ctx.principal.email)
    return ApiTokenCreated(**out.model_dump(), secret=secret)


@router.delete("/tenants/{tenant_id}/tokens/{token_id}", status_code=204)
async def revoke_api_token(token_id: uuid.UUID, ctx: Ctx):
    owner = None if _manages_tokens(ctx) else ctx.principal.user_id
    await tokens.revoke_token(
        ctx.session,
        ctx.tenant_id,
        token_id,
        actor=(ctx.principal.user_id, ctx.actor_role),
        owner_only=owner,
    )
    return None


# --- audit --------------------------------------------------------------------------
@router.get("/tenants/{tenant_id}/audit", response_model=AuditPage)
async def list_audit(
    ctx: Ctx,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    entity_type: str | None = None,
):
    ctx.require("tenant.settings", Action.READ)
    q = select(AuditLog).where(AuditLog.tenant_id == ctx.tenant_id)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    total = (await ctx.session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = await ctx.session.execute(q.order_by(AuditLog.at.desc()).limit(limit).offset(offset))
    return AuditPage(items=[AuditOut.model_validate(a) for a in rows.scalars()], total=total)
