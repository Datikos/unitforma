"""Row-level security tests against a real PostgreSQL (PoC V4).

Requires ``UF_TEST_DATABASE_ADMIN_URL`` (owner role, sync psycopg URL) and
``UF_TEST_DATABASE_URL`` (app_rw role, asyncpg URL) pointing at a database where the
migrations have been applied. Skipped otherwise.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ADMIN_URL = os.environ.get("UF_TEST_DATABASE_ADMIN_URL")
APP_URL = os.environ.get("UF_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL), reason="RLS tests need a PostgreSQL test database"
)


async def _set_ctx(conn, tenant_id, scope="tenant"):
    await conn.execute(text("SELECT set_config('app.scope', :s, true)"), {"s": scope})
    await conn.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"),
        {"t": str(tenant_id) if tenant_id else ""},
    )


@pytest.fixture
async def two_tenants():
    admin = create_async_engine(ADMIN_URL.replace("postgresql+psycopg://", "postgresql+asyncpg://"))
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    async with admin.begin() as conn:
        await _set_ctx(conn, None, "platform")
        for tid, slug in ((t1, f"t1-{t1.hex[:6]}"), (t2, f"t2-{t2.hex[:6]}")):
            await conn.execute(
                text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, :name)"),
                {"id": tid, "slug": slug, "name": slug},
            )
            await conn.execute(
                text(
                    "INSERT INTO portal_domains "
                    "(id, tenant_id, hostname, kind, verification_status) "
                    "VALUES (:id, :tid, :h, 'platform_subdomain', 'verified')"
                ),
                {"id": uuid.uuid4(), "tid": tid, "h": f"{slug}.unitforma.test"},
            )
    yield t1, t2
    async with admin.begin() as conn:
        await _set_ctx(conn, None, "platform")
        await conn.execute(text("DELETE FROM tenants WHERE id IN (:a, :b)"), {"a": t1, "b": t2})
    await admin.dispose()


async def test_app_role_sees_only_its_tenant(two_tenants):
    t1, t2 = two_tenants
    app = create_async_engine(APP_URL)
    try:
        async with app.begin() as conn:
            await _set_ctx(conn, t1)
            rows = (await conn.execute(text("SELECT tenant_id FROM portal_domains"))).all()
            assert {r[0] for r in rows} == {t1}
            tenants = (await conn.execute(text("SELECT id FROM tenants"))).all()
            assert {r[0] for r in tenants} == {t1}
        async with app.begin() as conn:
            await _set_ctx(conn, None)  # no tenant context → nothing visible
            assert (
                await conn.execute(text("SELECT count(*) FROM portal_domains"))
            ).scalar_one() == 0
        async with app.begin() as conn:
            await _set_ctx(conn, t1)
            # cross-tenant insert must be rejected by WITH CHECK
            with pytest.raises(Exception, match="row-level security"):
                await conn.execute(
                    text(
                        "INSERT INTO portal_domains (id, tenant_id, hostname, kind) "
                        "VALUES (:id, :tid, 'evil.unitforma.test', 'custom')"
                    ),
                    {"id": uuid.uuid4(), "tid": t2},
                )
    finally:
        await app.dispose()


async def test_platform_scope_sees_all(two_tenants):
    t1, t2 = two_tenants
    app = create_async_engine(APP_URL)
    try:
        async with app.begin() as conn:
            await _set_ctx(conn, None, "platform")
            rows = (await conn.execute(text("SELECT tenant_id FROM portal_domains"))).all()
            ids = {r[0] for r in rows}
            assert {t1, t2} <= ids
    finally:
        await app.dispose()
