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
    row = await session.execute(
        text(
            "SELECT 1 FROM portal_domains "
            "WHERE hostname = :h AND status = 'active' AND verification_status = 'verified' LIMIT 1"
        ),
        {"h": host},
    )
    return row.first() is not None
