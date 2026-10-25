"""Endpoints reachable only from the Docker networks (proxy, Prometheus)."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Header, Query, Response

from unitforma.core.db import check_database_ready, get_sessionmaker
from unitforma.core.settings import get_settings
from unitforma.domains.service import is_host_allowed
from unitforma.identity.kratos import KratosClient

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/health/live")
async def live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(response: Response) -> dict:
    checks: dict[str, bool] = {}
    try:
        checks["database"] = await check_database_ready()
    except Exception:  # noqa: BLE001 - readiness must never raise
        checks["database"] = False
    kratos = KratosClient()
    try:
        checks["kratos_admin"] = await kratos.admin_ready()
    finally:
        await kratos.aclose()
    ok = all(checks.values())
    response.status_code = 200 if ok else 503
    return {"status": "ok" if ok else "degraded", "checks": checks}


@router.get("/domains/ask")
async def domains_ask(
    response: Response,
    domain: str = Query(min_length=1, max_length=253),
    x_unitforma_internal: str | None = Header(default=None),
) -> dict:
    """Caddy on-demand TLS permission endpoint: 200 allows issuance, 403 denies."""
    settings = get_settings()
    if settings.internal_ask_token and not (
        x_unitforma_internal
        and hmac.compare_digest(x_unitforma_internal, settings.internal_ask_token)
    ):
        response.status_code = 403
        return {"allowed": False, "reason": "unauthorised"}
    async with get_sessionmaker()() as session:
        allowed = await is_host_allowed(session, domain, settings)
    response.status_code = 200 if allowed else 403
    return {"allowed": allowed}
