"""Personal API tokens for non-browser clients (ADR-0015 Decisions 2 and 3).

A token is one user in one tenant with a scope (``read`` or ``write``) and an expiry. The secret
(``ufm_`` + 40 URL-safe characters) is returned once; the row keeps its SHA-256 and a prefix.
Verification is one indexed select with no cache, so a revoke is refused on the next call.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.audit.service import write_audit
from unitforma.core.db import tenant_session
from unitforma.core.errors import ProblemError
from unitforma.core.ids import new_id
from unitforma.tenants.models import ApiToken, User

TOKEN_PREFIX = "ufm_"  # noqa: S105 - a public marker, not a secret
PREFIX_LEN = 12
SCOPES = ("read", "write")
DEFAULT_TTL_DAYS = 90
MAX_TTL_DAYS = 365
# ``last_used_at`` is written at most this often per token, not per call
LAST_USED_THROTTLE = timedelta(minutes=1)


@dataclass(frozen=True)
class TokenPrincipal:
    """What a verified token stands for; the membership is loaded per call inside the tenant."""

    token_id: uuid.UUID
    token_prefix: str
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    scope: str

    @property
    def origin(self) -> str:
        """Audit ``request_id`` for calls made with this token (ADR-0015 Decision 6)."""
        return f"mcp:{self.token_prefix}"


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def generate_secret() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(30)


async def create_token(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    name: str,
    scope: str,
    expires_in_days: int,
    actor: tuple[uuid.UUID, str],
) -> tuple[ApiToken, str]:
    name = name.strip()
    if not name:
        raise ProblemError(422, "Token name is required")
    if scope not in SCOPES:
        raise ProblemError(422, "Unknown scope", f"scope must be one of {', '.join(SCOPES)}")
    if not 1 <= expires_in_days <= MAX_TTL_DAYS:
        raise ProblemError(422, "Expiry out of range", f"1 to {MAX_TTL_DAYS} days")
    secret = generate_secret()
    row = ApiToken(
        id=new_id(),
        tenant_id=tenant_id,
        user_id=user_id,
        name=name,
        token_prefix=secret[:PREFIX_LEN],
        token_hash=_hash(secret),
        scope=scope,
        expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
    )
    db.add(row)
    await db.flush()
    await write_audit(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="api_token",
        entity_id=row.id,
        action="create",
        after={
            "name": name,
            "scope": scope,
            "token_prefix": row.token_prefix,
            "expires_at": row.expires_at.isoformat(),
        },
    )
    return row, secret


async def list_tokens(
    db: AsyncSession, tenant_id: uuid.UUID, *, user_id: uuid.UUID | None = None
) -> list[tuple[ApiToken, str]]:
    """Tokens of the tenant with the owner's e-mail, newest first; ``user_id`` narrows to one."""
    q = (
        select(ApiToken, User.email)
        .join(User, User.id == ApiToken.user_id)
        .where(ApiToken.tenant_id == tenant_id)
    )
    if user_id is not None:
        q = q.where(ApiToken.user_id == user_id)
    rows = await db.execute(q.order_by(ApiToken.created_at.desc()))
    return [(t, email) for t, email in rows]


async def revoke_token(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    token_id: uuid.UUID,
    *,
    actor: tuple[uuid.UUID, str],
    owner_only: uuid.UUID | None = None,
) -> ApiToken:
    """Revoke; ``owner_only`` limits the lookup to that user's tokens (404 otherwise)."""
    q = select(ApiToken).where(ApiToken.tenant_id == tenant_id, ApiToken.id == token_id)
    if owner_only is not None:
        q = q.where(ApiToken.user_id == owner_only)
    row = (await db.execute(q)).scalar_one_or_none()
    if row is None:
        raise ProblemError(404, "Token not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        await write_audit(
            db,
            tenant_id=tenant_id,
            actor_user_id=actor[0],
            actor_role=actor[1],
            entity_type="api_token",
            entity_id=row.id,
            action="revoke",
            after={"name": row.name, "token_prefix": row.token_prefix},
        )
    return row


def status_of(t: ApiToken, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    if t.revoked_at is not None:
        return "revoked"
    if t.expires_at <= now:
        return "expired"
    return "active"


async def verify_token(secret: str) -> TokenPrincipal | None:
    """Resolve a bearer secret; ``None`` for unknown, expired or revoked tokens.

    Runs under platform scope because the tenant is not known before the row is read; the
    caller then opens the tenant's own RLS session for everything else.
    """
    if not secret.startswith(TOKEN_PREFIX) or len(secret) > 80:
        return None
    now = datetime.now(UTC)
    async with tenant_session(None, scope="platform") as db:
        row = (
            await db.execute(select(ApiToken).where(ApiToken.token_hash == _hash(secret)))
        ).scalar_one_or_none()
        if row is None or row.revoked_at is not None or row.expires_at <= now:
            return None
        if row.last_used_at is None or now - row.last_used_at > LAST_USED_THROTTLE:
            row.last_used_at = now
        return TokenPrincipal(
            token_id=row.id,
            token_prefix=row.token_prefix,
            tenant_id=row.tenant_id,
            user_id=row.user_id,
            scope=row.scope,
        )
