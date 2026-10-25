"""Tenant and project slug rules (plan §3.3)."""

from __future__ import annotations

import re

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$")

# Subdomains that can never be used as tenant slugs. The database table
# ``reserved_subdomains`` is seeded from this list and can be extended at runtime.
RESERVED_SUBDOMAINS: frozenset[str] = frozenset(
    {
        "www",
        "app",
        "api",
        "accounts",
        "auth",
        "login",
        "admin",
        "portals",
        "cdn",
        "static",
        "assets",
        "mail",
        "smtp",
        "imap",
        "pop",
        "status",
        "docs",
        "help",
        "support",
        "dev",
        "staging",
        "test",
        "demo",
        "internal",
        "ns1",
        "ns2",
        "mx",
        "autodiscover",
        "autoconfig",
        "_dmarc",
        "localhost",
        "unitforma",
        "kratos",
        "grafana",
        "metrics",
        "backup",
    }
)


class SlugError(ValueError):
    pass


def validate_slug(value: str, *, reserved: frozenset[str] | set[str] = RESERVED_SUBDOMAINS) -> str:
    """Return the normalised slug or raise :class:`SlugError`."""
    slug = value.strip().lower()
    if len(slug) < 3:
        raise SlugError("slug must have at least 3 characters")
    if not SLUG_RE.match(slug):
        raise SlugError("slug may contain lowercase letters, digits and single hyphens only")
    if slug.isdigit():
        raise SlugError("slug cannot be numeric only")
    if "--" in slug:
        raise SlugError("slug cannot contain consecutive hyphens")
    if slug in reserved:
        raise SlugError(f"'{slug}' is reserved")
    return slug
