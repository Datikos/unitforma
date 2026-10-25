"""Procrastinate application: PostgreSQL-backed job queue (plan §4.3, §12.3)."""

from __future__ import annotations

import procrastinate
import structlog

from unitforma.core.settings import get_settings

log = structlog.get_logger()


def _connector() -> procrastinate.PsycopgConnector:
    url = (
        get_settings()
        .database_url.replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+psycopg://", "postgresql://")
    )
    return procrastinate.PsycopgConnector(conninfo=url)


app = procrastinate.App(connector=_connector(), import_paths=["unitforma.jobs.tasks"])
