"""FastAPI dependencies: Kratos client, staff principal, tenant context, authorization."""

from __future__ import annotations

import dataclasses
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.core.db import get_sessionmaker, tenant_session
from unitforma.core.errors import ProblemError
from unitforma.core.ids import new_id
from unitforma.core.settings import Settings, get_settings
from unitforma.identity.authz import Action, MembershipContext, Role, can_access_project, is_allowed
from unitforma.identity.kratos import KratosClient
from unitforma.identity.principal import StaffPrincipal
from unitforma.tenants.models import Membership, MembershipProjectAccess, User

_kratos_singleton: KratosClient | None = None


def get_kratos() -> KratosClient:
    global _kratos_singleton
    if _kratos_singleton is None:
        _kratos_singleton = KratosClient()
    return _kratos_singleton


# --- whoami cache (60 s per session id) ---------------------------------------------
_WHOAMI_TTL = 60.0
_whoami_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _cache_get(key: str) -> dict[str, Any] | None:
    hit = _whoami_cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    _whoami_cache.pop(key, None)
    return None


def _cache_put(key: str, value: dict[str, Any]) -> None:
    if len(_whoami_cache) > 5000:
        _whoami_cache.clear()
    _whoami_cache[key] = (time.monotonic() + _WHOAMI_TTL, value)


def clear_whoami_cache() -> None:
    _whoami_cache.clear()


async def _upsert_user(session: AsyncSession, identity: dict[str, Any]) -> User:
    identity_id = uuid.UUID(identity["id"])
    traits = identity.get("traits") or {}
    email = (traits.get("email") or "").lower()
    user = (
        await session.execute(select(User).where(User.kratos_identity_id == identity_id))
    ).scalar_one_or_none()
    if user is None:
        user = User(
            id=new_id(),
            kratos_identity_id=identity_id,
            email=email,
            display_name=traits.get("name"),
        )
        session.add(user)
        await session.flush()
    elif user.email != email and email:
        user.email = email
    return user


async def current_staff(
    request: Request,
    kratos: Annotated[KratosClient, Depends(get_kratos)],
) -> StaffPrincipal:
    """Resolve the Kratos browser session forwarded by the proxy (cookie) into a principal."""
    cookie = request.headers.get("cookie", "")
    if "ory_kratos_session" not in cookie:
        raise ProblemError(401, "Not authenticated")
    key = cookie  # the whole cookie header is a safe cache key for the browser session
    session_data = _cache_get(key)
    if session_data is None:
        session_data = await kratos.whoami_from_cookie(cookie)
        if session_data is None or not session_data.get("active", True):
            raise ProblemError(401, "Session expired")
        _cache_put(key, session_data)
    identity = session_data["identity"]
    verified = any(a.get("verified") for a in identity.get("verifiable_addresses") or [])
    async with get_sessionmaker()() as db:
        async with db.begin():
            user = await _upsert_user(db, identity)
            principal = StaffPrincipal(
                user_id=user.id,
                kratos_identity_id=user.kratos_identity_id,
                kratos_session_id=session_data.get("id", ""),
                email=user.email,
                email_verified=verified,
                is_platform_admin=user.is_platform_admin,
                aal=session_data.get("authenticator_assurance_level", "aal1"),
            )
    return principal


def require_platform_admin(
    principal: Annotated[StaffPrincipal, Depends(current_staff)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StaffPrincipal:
    if not principal.is_platform_admin:
        raise ProblemError(403, "Platform administrator required")
    if settings.is_production and principal.aal != "aal2":
        raise ProblemError(403, "Second factor required", type_="urn:unitforma:aal2-required")
    return principal


@dataclass
class TenantContext:
    principal: StaffPrincipal
    tenant_id: uuid.UUID
    membership: MembershipContext
    scope: str  # tenant | platform
    session: AsyncSession
    request_id: str | None = None

    def require(self, resource: str, action: Action) -> None:
        if self.scope == "platform":
            return
        if not is_allowed(self.membership, resource, action):
            raise ProblemError(403, "Not allowed", f"{action} on {resource}")

    def require_project(self, project_id: uuid.UUID) -> None:
        if self.scope == "platform":
            return
        if not can_access_project(self.membership, project_id):
            # 404 so that restricted staff cannot probe project ids
            raise ProblemError(404, "Project not found")

    @property
    def actor_role(self) -> str:
        return "platform_admin" if self.scope == "platform" else self.membership.role.value


async def load_membership(
    db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> MembershipContext | None:
    m = (
        await db.execute(
            select(Membership).where(
                Membership.tenant_id == tenant_id, Membership.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if m is None:
        return None
    project_ids: frozenset[uuid.UUID] = frozenset()
    if not m.all_projects:
        rows = await db.execute(
            select(MembershipProjectAccess.project_id).where(
                MembershipProjectAccess.membership_id == m.id
            )
        )
        project_ids = frozenset(r[0] for r in rows)
    return MembershipContext(
        tenant_id=tenant_id,
        user_id=user_id,
        role=Role(m.role),
        all_projects=m.all_projects,
        project_ids=project_ids,
        is_active=m.status == "active",
    )


async def tenant_access(
    tenant_id: uuid.UUID,
    request: Request,
    principal: Annotated[StaffPrincipal, Depends(current_staff)],
) -> TenantContext:
    """The checks of :func:`tenant_context` in a short transaction, returning a context without a
    session (``session`` is ``None``). For handlers that call a slow outside service: they check
    rights first, make the call with no database connection held, and open
    :func:`open_session` for their writes (BACKLOG 15, the permit registry)."""
    gen = tenant_context(tenant_id, request, principal)
    ctx = await gen.__anext__()
    try:
        return dataclasses.replace(ctx, session=None)  # type: ignore[arg-type]
    finally:
        await gen.aclose()


@asynccontextmanager
async def open_session(access: TenantContext) -> AsyncIterator[TenantContext]:
    """A transaction for a context from :func:`tenant_access`; the membership is read again,
    since the outside call in between may have taken a while."""
    async with tenant_session(
        access.tenant_id, user_id=access.principal.user_id, scope=access.scope
    ) as db:
        if access.scope == "tenant":
            m = await load_membership(db, access.tenant_id, access.principal.user_id)
            if m is None or not m.is_active:
                raise ProblemError(404, "Tenant not found")
        yield dataclasses.replace(access, session=db)


async def tenant_context(
    tenant_id: uuid.UUID,
    request: Request,
    principal: Annotated[StaffPrincipal, Depends(current_staff)],
) -> AsyncIterator[TenantContext]:
    """Open an RLS-scoped transaction for the tenant and verify membership.

    Platform administrators get ``scope = platform`` (cross-tenant policies apply);
    everyone else must hold an active membership. Unknown tenants and non-members get 404.
    """
    scope = "platform" if principal.is_platform_admin else "tenant"
    async with tenant_session(tenant_id, user_id=principal.user_id, scope=scope) as db:
        membership = await load_membership(db, tenant_id, principal.user_id)
        if scope == "tenant":
            if membership is None or not membership.is_active:
                raise ProblemError(404, "Tenant not found")
        elif membership is None:
            membership = MembershipContext(
                tenant_id=tenant_id,
                user_id=principal.user_id,
                role=Role.TENANT_ADMIN,
                all_projects=True,
                is_member=False,
            )
        yield TenantContext(
            principal=principal,
            tenant_id=tenant_id,
            membership=membership,
            scope=scope,
            session=db,
            request_id=request.headers.get("x-request-id"),
        )
