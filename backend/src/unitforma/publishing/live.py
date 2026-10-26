"""Availability and price reach the live publication at once (ADR-0018).

``sync_unit`` runs inside the sales transaction: the live publication's ``published_units`` row of
the unit gets the current availability and price, through ``sales.public_view`` so the public-field
switches, "price on request" and the per-m² figures follow the build's rules. ``with_live_sales``
overlays those rows on the cached project document at read time: floor units and the stats.
Listing stays a publish decision (ADR-0018 Decision 3).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.tenants.models import Project, Publication, PublishedUnit, Unit


async def sync_unit(db: AsyncSession, project: Project, unit: Unit) -> bool:
    """Write the unit's current availability and price into the live publication; False when the
    unit is not part of it (or nothing is published)."""
    from unitforma.publishing.service import current_publication
    from unitforma.sales import service as sales

    pub = await current_publication(db, project.id)
    if pub is None:
        return False
    row = (
        await db.execute(
            select(PublishedUnit).where(
                PublishedUnit.publication_id == pub.id, PublishedUnit.unit_id == unit.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    inv = await sales.inventory(db, project, unit_ids=[unit.id])
    if not inv:
        return False
    view = sales.public_view(inv[0], None, [], [])
    price = view.get("price")
    row.availability = view["availability"]
    row.price_amount = Decimal(str(price["amount"])) if price and price.get("amount") else None
    row.currency = price["currency"] if price else None
    data = dict(row.data or {})
    data["availability"] = view["availability"]
    data["price"] = price
    row.data = data
    return True


def _price_from(rows: list[PublishedUnit]) -> dict[str, Any] | None:
    """The snapshot's rule: the lowest price when every priced, listed unit shares one currency."""
    priced = [r for r in rows if r.listed and r.price_amount is not None]
    if not priced or len({r.currency for r in priced}) != 1:
        return None
    return {
        "amount": format(min(r.price_amount for r in priced), "f"),
        "currency": priced[0].currency,
    }


async def with_live_sales(
    db: AsyncSession, pub: Publication, doc: dict[str, Any]
) -> dict[str, Any]:
    """A copy of the cached project document with the live availability on every floor unit and
    the stats recomputed; the cached document itself is never changed."""
    rows = list(
        (
            await db.execute(select(PublishedUnit).where(PublishedUnit.publication_id == pub.id))
        ).scalars()
    )
    if not rows:
        return doc
    live = {str(r.unit_id): r.availability for r in rows}
    buildings = []
    changed = False
    for b in doc.get("buildings") or []:
        floors = []
        for f in b.get("floors") or []:
            units = []
            for u in f.get("units") or []:
                a = live.get(str(u.get("id") or u.get("unit_id") or ""))
                if a is not None and a != u.get("availability"):
                    units.append({**u, "availability": a})
                    changed = True
                else:
                    units.append(u)
            floors.append({**f, "units": units})
        buildings.append({**b, "floors": floors})
    stats = dict(doc.get("stats") or {})
    listed = [r for r in rows if r.listed]
    new_stats = {
        **stats,
        "available": sum(1 for r in listed if r.availability == "available"),
        "price_from": _price_from(rows),
    }
    if not changed and new_stats == stats:
        return doc
    return {**doc, "buildings": buildings, "stats": new_stats}
