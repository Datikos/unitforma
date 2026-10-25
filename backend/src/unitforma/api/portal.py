"""Public portal API skeleton: resolves the tenant/project from the Host header."""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text

from unitforma.core.db import get_sessionmaker
from unitforma.core.errors import ProblemError
from unitforma.domains.service import normalise_hostname

router = APIRouter(prefix="/api/v1/portal", tags=["portal"])


@router.get("/branding")
async def branding(request: Request) -> dict:
    host = normalise_hostname(
        request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    )
    async with get_sessionmaker()() as session:
        row = (
            await session.execute(
                text(
                    "SELECT t.id, t.slug, t.name, t.branding, d.project_id "
                    "FROM portal_domains d JOIN tenants t ON t.id = d.tenant_id "
                    "WHERE d.hostname = :h AND d.status = 'active'"
                ),
                {"h": host},
            )
        ).first()
    if row is None:
        raise ProblemError(404, "Portal not configured", f"No active portal for host {host}")
    return {
        "tenant_slug": row.slug,
        "tenant_name": row.name,
        "branding": row.branding,
        "project_id": str(row.project_id) if row.project_id else None,
    }
