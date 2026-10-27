"""Map position pass (ADR-0025 Decision 5 "map" and Decision 8): one geocoding request per run
against the configured provider; applied only when the answer is one place.

Nominatim's usage policy (read 2026-10-27, plan §21): at most one request per second, an
identifying User-Agent, no bulk work. One project per run keeps well inside that; the provider
is a setting that defaults to ``none``."""

from __future__ import annotations

from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select

from unitforma.autopilot import rules
from unitforma.autopilot.service import Context, session
from unitforma.core.settings import get_settings
from unitforma.projects import service as projects
from unitforma.tenants.models import Project

STEP = "location"
USER_AGENT = "unitforma/0.1 (+https://unitforma.com)"
TIMEOUT_S = 10.0


class Geocoder(Protocol):
    name: str

    async def search(self, query: str, country: str | None) -> list[dict[str, Any]]:
        """Places for a free-text address: ``[{lat, lng, display_name}]``, best first."""
        ...


class NominatimGeocoder:
    name = "nominatim"

    def __init__(self, endpoint: str, client: httpx.AsyncClient | None = None):
        if urlsplit(endpoint).scheme != "https":
            raise ValueError("UF_GEOCODER_ENDPOINT must be an https URL")
        self.endpoint = endpoint
        self._client = client

    async def search(self, query: str, country: str | None) -> list[dict[str, Any]]:
        params = {"q": query, "format": "jsonv2", "limit": "3", "addressdetails": "0"}
        if country:
            params["countrycodes"] = country.lower()
        headers = {"User-Agent": USER_AGENT, "Accept-Language": "ka,en"}
        if self._client is not None:
            r = await self._client.get(self.endpoint, params=params, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
                r = await client.get(self.endpoint, params=params, headers=headers)
        r.raise_for_status()
        out = []
        for item in r.json() if isinstance(r.json(), list) else []:
            try:
                out.append(
                    {
                        "lat": float(item["lat"]),
                        "lng": float(item["lon"]),
                        "display_name": str(item.get("display_name") or "")[:200],
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        return out


_geocoder: Geocoder | None = None
_override = False


def get_geocoder() -> Geocoder | None:
    if _override:
        return _geocoder
    s = get_settings()
    if s.geocoder == "nominatim":
        return NominatimGeocoder(s.geocoder_endpoint)
    return None


def set_geocoder(g: Geocoder | None, *, override: bool = True) -> None:
    """Tests swap the provider for a fake (``override=False`` restores the settings' choice)."""
    global _geocoder, _override
    _geocoder, _override = g, override


def address_query(address: dict[str, Any]) -> str | None:
    parts = [
        str(address.get(k)).strip()
        for k in ("line1", "line2", "city", "region", "postal_code")
        if address.get(k)
    ]
    return ", ".join(p for p in parts if p) or None


async def run(ctx: Context) -> None:
    geocoder = get_geocoder()
    if geocoder is None:
        return
    async with session(ctx) as db:
        project = (
            await db.execute(select(Project).where(Project.id == ctx.project_id))
        ).scalar_one()
        address = dict(project.address or {})
        if address.get("lat") is not None and address.get("lng") is not None:
            return
        query = address_query(address)
        if not query:
            ctx.decide(
                STEP,
                "skipped",
                "No address to geocode",
                "Set the address line on the Publish page, then run again",
                needs_you=True,
            )
            return
        country = address.get("country") if isinstance(address.get("country"), str) else None
        places = await geocoder.search(query, country)
        if len(places) != 1:
            ctx.decide(
                STEP,
                "skipped",
                "Map position needs you",
                (
                    f"{geocoder.name} found no place for '{query}'"
                    if not places
                    else f"{geocoder.name} found {len(places)} places for '{query}': "
                    + " | ".join(p["display_name"] for p in places[:3])
                )
                + ". Set latitude and longitude on the Publish page",
                needs_you=True,
            )
            return
        place = places[0]
        address["lat"], address["lng"] = place["lat"], place["lng"]
        address["geocoded"] = {
            "provider": geocoder.name,
            "display_name": place["display_name"],
            "query": query[:200],
        }
        await projects.update_project(db, project, {"address": address}, project.version, ctx.actor)
        ctx.decide(
            STEP,
            "accepted",
            "Map position set",
            f"{place['display_name']} ({place['lat']:.5f}, {place['lng']:.5f}) from "
            f"{geocoder.name}; check the pin on the portal",
            confidence=rules.GEOCODE_CONFIDENCE,
        )
