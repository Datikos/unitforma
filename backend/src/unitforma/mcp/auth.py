"""Bearer API tokens on the MCP endpoint and the tenant context a tool call runs in.

The middleware is pure ASGI: it verifies ``Authorization: Bearer ufm_...`` against ``api_tokens``
and puts the :class:`TokenPrincipal` in a context variable; tools never read headers themselves.
The SDK's OAuth ``AuthSettings`` is deliberately not wired (ADR-0015 Decision 4).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar

from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import select
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from unitforma.audit.service import reset_audit_origin, set_audit_origin
from unitforma.core.db import tenant_session
from unitforma.core.errors import ProblemError
from unitforma.identity.deps import TenantContext, load_membership
from unitforma.identity.principal import StaffPrincipal
from unitforma.identity.tokens import TokenPrincipal, verify_token
from unitforma.tenants.models import User

_principal: ContextVar[TokenPrincipal | None] = ContextVar("mcp_principal", default=None)


def _problem(status: int, title: str, detail: str | None = None, **headers: str) -> JSONResponse:
    body: dict[str, object] = {"type": "about:blank", "title": title, "status": status}
    if detail:
        body["detail"] = detail
    return JSONResponse(
        body, status_code=status, media_type="application/problem+json", headers=headers
    )


class BearerTokenMiddleware:
    """401 without a valid token; otherwise the principal and audit origin are set for the call."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        scheme, _, secret = Headers(scope=scope).get("authorization", "").partition(" ")
        principal = None
        if scheme.lower() == "bearer" and secret.strip():
            principal = await verify_token(secret.strip())
        if principal is None:
            response = _problem(
                401,
                "Not authenticated",
                "Send a personal API token as Authorization: Bearer ufm_...",
                **{"WWW-Authenticate": 'Bearer realm="unitforma-mcp"'},
            )
            await response(scope, receive, send)
            return
        token = _principal.set(principal)
        origin = set_audit_origin(principal.origin)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_audit_origin(origin)
            _principal.reset(token)


def current_principal() -> TokenPrincipal:
    p = _principal.get()
    if p is None:  # only reachable when the middleware is bypassed
        raise ToolError("Not authenticated")
    return p


@asynccontextmanager
async def tenant_ctx(*, write: bool = False) -> AsyncIterator[TenantContext]:
    """The same :class:`TenantContext` the admin API builds, from the token instead of a cookie.

    The membership is loaded on every call (a suspended member is refused at once), the role
    matrix applies unchanged, and a ``read`` token is refused before a write tool runs.
    Problem errors from the services become tool errors the assistant can read.
    """
    p = current_principal()
    if write and p.scope != "write":
        raise ToolError(
            "This token is read-only; create a token with the write scope to change data"
        )
    try:
        async with tenant_session(p.tenant_id, user_id=p.user_id, scope="tenant") as db:
            membership = await load_membership(db, p.tenant_id, p.user_id)
            if membership is None or not membership.is_active:
                raise ProblemError(404, "Tenant not found")
            user = (await db.execute(select(User).where(User.id == p.user_id))).scalar_one()
            principal = StaffPrincipal(
                user_id=user.id,
                kratos_identity_id=user.kratos_identity_id,
                kratos_session_id="",
                email=user.email,
                email_verified=True,
                is_platform_admin=False,  # a token never carries platform scope (Decision 3)
                aal="aal1",
            )
            yield TenantContext(
                principal=principal,
                tenant_id=p.tenant_id,
                membership=membership,
                scope="tenant",
                session=db,
                request_id=p.origin,
            )
    except ProblemError as e:
        raise ToolError(f"{e.title}: {e.detail}" if e.detail else e.title) from None
