"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from unitforma import __version__
from unitforma.api import (
    admin,
    admin_documents,
    admin_geometry,
    admin_mapping,
    admin_projects,
    internal,
    platform,
    portal,
)
from unitforma.core.db import dispose_engine
from unitforma.core.errors import install_error_handlers
from unitforma.core.logging import configure_logging
from unitforma.core.security import RequestedWithMiddleware
from unitforma.core.settings import get_settings

log = structlog.get_logger()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    log.info("api.start", version=__version__, environment=settings.environment)
    yield
    await dispose_engine()
    log.info("api.stop")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Unitforma API",
        version=__version__,
        docs_url="/api/docs" if not settings.is_production else None,
        openapi_url="/api/openapi.json",
        lifespan=_lifespan,
    )
    install_error_handlers(app)
    app.add_middleware(RequestedWithMiddleware)
    app.include_router(internal.router)
    app.include_router(portal.router)
    app.include_router(platform.router)
    app.include_router(admin.router)
    app.include_router(admin_projects.router)
    app.include_router(admin_documents.router)
    app.include_router(admin_mapping.router)
    app.include_router(admin_geometry.router)
    return app


app = create_app()
