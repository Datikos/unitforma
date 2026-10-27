"""Map position pass (ADR-0025 Decision 5 "map" and Decision 8): one geocoding request per run
against the configured provider; applied only when the answer is one place.

Nominatim's usage policy (read 2026-10-27, plan §21): at most one request per second, an
identifying User-Agent, no bulk work. One project per run keeps well inside that; the provider
is a setting that defaults to ``none``."""

from __future__ import annotations

import asyncio
import math
import re
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


# the Georgian postal form of the permit register: "ქალაქი თბილისი, ლეო კვაჭაძის ქუჩა, N 19გ"
_CITY_PREFIX = re.compile(r"^(ქალაქი|ქ\.|დაბა|სოფელი|city|town)\s+", re.IGNORECASE)
_HOUSE_NO = re.compile(r"^(?:N|№|#|No\.?)?\s*(\d+)\s*[/\-]?\s*[ა-ჰA-Za-z]?\d*$")


def address_queries(address: dict[str, Any]) -> list[str]:
    """The queries to try, best first (ADR-0025 Decision 5 "map", D1 of 2026-10-27): the address
    as written; then the house number without its "N" and letter suffix after the street with the
    city last; then the street and city alone. Distinct, in that order."""
    parts = [
        str(address.get(k)).strip()
        for k in ("line1", "line2", "city", "region", "postal_code")
        if address.get(k)
    ]
    raw = ", ".join(p for p in parts if p)
    if not raw:
        return []
    out = [raw]
    city, street, number = None, [], None
    for piece in [x.strip() for x in str(address.get("line1") or "").split(",") if x.strip()]:
        if _CITY_PREFIX.match(piece):
            city = _CITY_PREFIX.sub("", piece).strip()
        elif (m := _HOUSE_NO.match(piece)) and number is None:
            number = m.group(1)
        else:
            street.append(piece)
    city = city or (str(address.get("city")).strip() if address.get("city") else None)
    if street and (city or number):
        tail = f", {city}" if city else ""
        if number:
            out.append(f"{' '.join(street)} {number}{tail}")
        if city:
            out.append(f"{' '.join(street)}{tail}")
    seen: set[str] = set()
    return [q for q in out if not (q in seen or seen.add(q))]


def places_agree(places: list[dict[str, Any]], radius_m: float) -> bool:
    """True when every place lies within ``radius_m`` of the first: one address, several entrances
    or buildings (19/4 and 19/5 of one street number), not two streets of one name."""
    if not places:
        return False
    lat0, lng0 = places[0]["lat"], places[0]["lng"]
    k = math.cos(math.radians(lat0)) * 111_320.0
    for p in places[1:]:
        dy = (p["lat"] - lat0) * 111_320.0
        dx = (p["lng"] - lng0) * k
        if math.hypot(dx, dy) > radius_m:
            return False
    return True


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
        queries = address_queries(address)
        if not queries:
            ctx.decide(
                STEP,
                "skipped",
                "No address to geocode",
                "Set the address line on the Publish page, then run again",
                needs_you=True,
            )
            return
        country = address.get("country") if isinstance(address.get("country"), str) else None
        tried: list[str] = []
        for i, query in enumerate(queries):
            if i:
                await asyncio.sleep(rules.GEOCODE_PAUSE_S)  # the provider's one request per second
            places = await geocoder.search(query, country)
            tried.append(f"'{query}': {len(places)} place(s)")
            if not places or not places_agree(places, rules.GEOCODE_AGREE_M):
                continue
            place = places[0]
            if i == len(queries) - 1 and len(queries) > 1:
                # the street alone was found, the house number was not: a street is no pin
                ctx.decide(
                    STEP,
                    "skipped",
                    "Map position needs you",
                    f"{geocoder.name} knows the street ({place['display_name']}) but not the "
                    f"number; " + "; ".join(tried) + ". Set the pin on the Publish page",
                    needs_you=True,
                )
                return
            address["lat"], address["lng"] = place["lat"], place["lng"]
            address["geocoded"] = {
                "provider": geocoder.name,
                "display_name": place["display_name"],
                "query": query[:200],
                "places": len(places),
            }
            await projects.update_project(
                db, project, {"address": address}, project.version, ctx.actor
            )
            ctx.decide(
                STEP,
                "accepted",
                "Map position set",
                f"{place['display_name']} ({place['lat']:.5f}, {place['lng']:.5f}) from "
                f"{geocoder.name}"
                + (
                    f", {len(places)} places within {rules.GEOCODE_AGREE_M:.0f} m"
                    if len(places) > 1
                    else ""
                )
                + "; check the pin on the portal",
                confidence=rules.GEOCODE_CONFIDENCE,
            )
            return
        ctx.decide(
            STEP,
            "skipped",
            "Map position needs you",
            f"{geocoder.name} found no single place: "
            + "; ".join(tried)
            + ". Set latitude and longitude on the Publish page",
            needs_you=True,
        )
