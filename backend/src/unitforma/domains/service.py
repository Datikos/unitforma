"""Portal domain resolution and the Caddy on-demand TLS ``ask`` decision (plan §9)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.core.settings import Settings


def normalise_hostname(value: str) -> str:
    host = value.strip().lower().rstrip(".")
    if ":" in host:
        host = host.split(":", 1)[0]
    return host.encode("idna").decode("ascii")


def is_platform_host(host: str, settings: Settings) -> bool:
    d = settings.platform_domain
    return (
        host == d
        or host == f"www.{d}"
        or host == settings.admin_host
        or host == settings.portals_cname_target
    )


async def is_host_allowed(session: AsyncSession, host: str, settings: Settings) -> bool:
    """200/403 decision for Caddy's ``ask`` endpoint.

    Platform hosts are always allowed. Tenant subdomains and custom domains are allowed
    only when the ``portal_domains`` row is active and verified.
    """
    host = normalise_hostname(host)
    if is_platform_host(host, settings):
        return True
    r = await resolve_host(session, host)
    return r is not None and r["verification_status"] == "verified"


async def resolve_host(session: AsyncSession, host: str) -> dict | None:
    """Active portal domain for a hostname, through the ``portal_resolve_host`` SECURITY
    DEFINER function (migration 0006): portal_domains is tenant-scoped under forced RLS, and
    an anonymous request has no tenant yet. Returns routing columns only."""
    host = normalise_hostname(host)
    if not host:
        return None
    row = (
        (await session.execute(text("SELECT * FROM portal_resolve_host(:h)"), {"h": host}))
        .mappings()
        .first()
    )
    return dict(row) if row else None
