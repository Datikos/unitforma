"""Database access with per-request tenant context for row-level security.

Every tenant-scoped transaction runs ``SET LOCAL app.tenant_id = ...`` so PostgreSQL
policies (``tenant_id = current_setting('app.tenant_id')::uuid``) filter rows even if
application code forgets a WHERE clause. ``SET LOCAL`` lasts until the end of the
transaction, so pooled connections never leak context between requests.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from unitforma.core.settings import Settings, get_settings

_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine(settings: Settings | None = None):
    global _engine, _sessionmaker
    if _engine is None:
        s = settings or get_settings()
        _engine = create_async_engine(
            s.database_url, pool_size=s.database_pool_size, pool_pre_ping=True
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


@asynccontextmanager
async def tenant_session(
    tenant_id: uuid.UUID | None,
    *,
    user_id: uuid.UUID | None = None,
    scope: str = "tenant",
) -> AsyncIterator[AsyncSession]:
    """Open a transaction with the RLS context set.

    ``scope`` is ``tenant`` for ordinary staff/portal requests, ``platform`` for platform
    administrators (policies allow cross-tenant reads only when scope = platform).
    """
    async with get_sessionmaker()() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.scope', :scope, true)"), {"scope": scope}
            )
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": str(tenant_id) if tenant_id else ""},
            )
            await session.execute(
                text("SELECT set_config('app.user_id', :uid, true)"),
                {"uid": str(user_id) if user_id else ""},
            )
            yield session


async def check_database_ready() -> bool:
    async with get_sessionmaker()() as session:
        result = await session.execute(text("SELECT 1"))
        return result.scalar_one() == 1


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
