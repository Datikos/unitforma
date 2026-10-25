"""Apply the Procrastinate schema once (idempotent) as part of `unitforma migrate`."""

from __future__ import annotations

import psycopg
import structlog

from unitforma.core.settings import get_settings

log = structlog.get_logger()


async def ensure_job_schema() -> None:
    url = get_settings().database_admin_url.replace("postgresql+psycopg://", "postgresql://")
    async with await psycopg.AsyncConnection.connect(url) as conn:
        exists = await (
            await conn.execute("SELECT to_regclass('public.procrastinate_jobs') IS NOT NULL")
        ).fetchone()
        if exists and exists[0]:
            log.info("jobs.schema.present")
            return
    from procrastinate import App, PsycopgConnector

    app = App(connector=PsycopgConnector(conninfo=url))
    async with app.open_async():
        await app.schema_manager.apply_schema_async()
    async with await psycopg.AsyncConnection.connect(url) as conn:
        await conn.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_rw') THEN "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_rw; "
            "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_rw; "
            "GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO app_rw; END IF; END $$;"
        )
        await conn.commit()
    log.info("jobs.schema.applied")
