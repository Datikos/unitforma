"""FastAPI application factory."""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager

import structlog
from fastapi import FastAPI
from starlette.routing import Route

from unitforma import __version__
from unitforma.api import (
    admin,
    admin_documents,
    admin_geometry,
    admin_layouts,
    admin_mapping,
    admin_projects,
    admin_publishing,
    admin_regulatory,
    admin_renders,
    admin_sales,
    internal,
    platform,
    portal,
)
from unitforma.core.db import dispose_engine
from unitforma.core.errors import install_error_handlers
from unitforma.core.logging import configure_logging
from unitforma.core.security import RequestedWithMiddleware
from unitforma.core.settings import get_settings
from unitforma.mcp.server import mcp_asgi

log = structlog.get_logger()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    log.info("api.start", version=__version__, environment=settings.environment)
    # The API enqueues jobs (upload processing, massing, diffs); Procrastinate needs its
    # connector opened in this process too, not only in the worker.
    from unitforma.jobs.app import app as jobs_app

    jobs_open = False
    try:
        await jobs_app.open_async()
        jobs_open = True
    except Exception as e:  # noqa: BLE001 - the API still serves reads; enqueue errors surface
        log.warning("api.jobs_unavailable", error=str(e))
    async with AsyncExitStack() as stack:
        # the mounted MCP app's own lifespan never runs; its session manager starts here
        mcp_server = getattr(app.state, "mcp_server", None)
        if mcp_server is not None:
            await stack.enter_async_context(mcp_server.session_manager.run())
        yield
    if jobs_open:
        await jobs_app.close_async()
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
    app.include_router(admin_sales.router)
    app.include_router(admin_renders.router)
    app.include_router(admin_layouts.router)
    app.include_router(admin_publishing.router)
    app.include_router(admin_regulatory.router)
    app.state.mcp_server = None
    if settings.mcp_enabled:
        # one route, not a Mount: a Mount would answer /mcp with a redirect to /mcp/
        app.state.mcp_server, mcp_app = mcp_asgi(settings)
        app.router.routes.append(Route("/mcp", endpoint=mcp_app, methods=["GET", "POST", "DELETE"]))
    return app


app = create_app()
