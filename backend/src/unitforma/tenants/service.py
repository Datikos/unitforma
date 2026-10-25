"""Tenant, membership and invitation services (plan §3.4)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.audit.service import write_audit
from unitforma.core.errors import ProblemError
from unitforma.core.ids import new_id
from unitforma.core.settings import get_settings
from unitforma.core.slugs import SlugError, validate_slug
from unitforma.tenants.models import (
    Membership,
    MembershipProjectAccess,
    PortalDomain,
    Project,
    ReservedSubdomain,
    StaffInvitation,
    Tenant,
    User,
)

INVITATION_TTL = timedelta(days=7)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_tenant(
    db: AsyncSession, *, slug: str, name: str, default_currency: str, actor_user_id: uuid.UUID
) -> Tenant:
    reserved = {r[0] for r in await db.execute(select(ReservedSubdomain.name))}
    try:
        slug = validate_slug(slug, reserved=reserved)
    except SlugError as e:
        raise ProblemError(422, "Invalid slug", str(e)) from e
    if (await db.execute(select(Tenant.id).where(Tenant.slug == slug))).first():
        raise ProblemError(409, "Slug already in use")
    tenant = Tenant(id=new_id(), slug=slug, name=name, default_currency=default_currency.upper())
    db.add(tenant)
    await db.flush()
    # the platform subdomain is a portal_domains row so routing has one code path (plan §9.1)
    db.add(
        PortalDomain(
            id=new_id(),
            tenant_id=tenant.id,
            hostname=f"{slug}.{get_settings().platform_domain}",
            kind="platform_subdomain",
            verification_status="verified",
            verified_at=datetime.now(UTC),
            is_primary=True,
            status="active",
        )
    )
    await write_audit(
        db,
        tenant_id=tenant.id,
        actor_user_id=actor_user_id,
        actor_role="platform_admin",
        entity_type="tenant",
        entity_id=tenant.id,
        action="create",
        after={"slug": slug, "name": name},
    )
    return tenant


async def create_invitation(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    email: str,
    role: str,
    all_projects: bool,
    project_ids: list[uuid.UUID],
    actor_user_id: uuid.UUID,
    actor_role: str,
) -> tuple[StaffInvitation, str]:
    email = email.lower().strip()
    if not all_projects and project_ids:
        found = {
            r[0]
            for r in await db.execute(
                select(Project.id).where(
                    Project.tenant_id == tenant_id, Project.id.in_(project_ids)
                )
            )
        }
        missing = set(project_ids) - found
        if missing:
            raise ProblemError(422, "Unknown project ids", ", ".join(str(m) for m in missing))
    token = secrets.token_urlsafe(32)
    inv = StaffInvitation(
        id=new_id(),
        tenant_id=tenant_id,
        email=email,
        role=role,
        project_ids=[] if all_projects else list(project_ids),
        token_hash=_hash_token(token),
        expires_at=datetime.now(UTC) + INVITATION_TTL,
    )
    db.add(inv)
    await write_audit(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        entity_type="staff_invitation",
        entity_id=inv.id,
        action="create",
        after={"email": email, "role": role, "all_projects": all_projects},
    )
    return inv, token


def accept_url(token: str) -> str:
    return f"https://{get_settings().admin_host}/invite/{token}"


async def accept_invitation(
    db: AsyncSession, *, token: str, user: User, user_email_verified: bool
) -> Membership:
    """Called under platform scope because the user is not yet a member of the tenant."""
    inv = (
        await db.execute(
            select(StaffInvitation).where(StaffInvitation.token_hash == _hash_token(token))
        )
    ).scalar_one_or_none()
    if inv is None or inv.accepted_membership_id is not None:
        raise ProblemError(404, "Invitation not found or already used")
    if inv.expires_at < datetime.now(UTC):
        raise ProblemError(410, "Invitation expired")
    if user.email.lower() != inv.email.lower():
        raise ProblemError(403, "Invitation was issued to a different email address")
    if not user_email_verified:
        raise ProblemError(403, "Email address not verified")
    existing = (
        await db.execute(
            select(Membership).where(
                Membership.tenant_id == inv.tenant_id, Membership.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.role = inv.role
        existing.status = "active"
        existing.all_projects = not inv.project_ids
        existing.accepted_at = datetime.now(UTC)
        membership = existing
    else:
        membership = Membership(
            id=new_id(),
            tenant_id=inv.tenant_id,
            user_id=user.id,
            role=inv.role,
            status="active",
            all_projects=not inv.project_ids,
            accepted_at=datetime.now(UTC),
        )
        db.add(membership)
    await db.flush()
    if inv.project_ids:
        for pid in inv.project_ids:
            db.add(
                MembershipProjectAccess(
                    id=new_id(),
                    tenant_id=inv.tenant_id,
                    membership_id=membership.id,
                    project_id=pid,
                )
            )
    inv.accepted_membership_id = membership.id
    await write_audit(
        db,
        tenant_id=inv.tenant_id,
        actor_user_id=user.id,
        actor_role=inv.role,
        entity_type="membership",
        entity_id=membership.id,
        action="accept_invitation",
        after={"role": inv.role, "all_projects": not inv.project_ids},
    )
    return membership


async def member_project_ids(db: AsyncSession, membership_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await db.execute(
        select(MembershipProjectAccess.project_id).where(
            MembershipProjectAccess.membership_id == membership_id
        )
    )
    return [r[0] for r in rows]


async def count_active_admins(db: AsyncSession, tenant_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.tenant_id == tenant_id,
                Membership.role == "tenant_admin",
                Membership.status == "active",
            )
        )
    ).scalar_one()
