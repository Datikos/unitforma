"""Floors pass (ADR-0025 Decision 5 "floors"): accept the floor proposal of every building that
has no floors yet; split-level blocks become buildings (ADR-0013 Decision 4)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from unitforma.autopilot import rules
from unitforma.autopilot.service import Context, session
from unitforma.documents import floor_proposal
from unitforma.documents import jobs as documents_jobs
from unitforma.projects import service as projects
from unitforma.tenants.models import Building

STEP = "floors"


async def run(ctx: Context) -> None:
    async with session(ctx) as db:
        targets = [
            (b.id, b.code)
            for b in await projects.list_buildings(db, ctx.project_id)
            if b.kind == "building" and not b.floors
        ]
    changed = False
    for building_id, code in targets:
        if await _one(ctx, building_id, code):
            changed = True
    if changed:
        # sheets processed before these floors existed get their page → floor suggestions now,
        # inline (a queued job would start another run)
        await documents_jobs.resuggest_floors(ctx.tenant_id, ctx.project_id)


async def _one(ctx: Context, building_id: uuid.UUID, code: str) -> bool:
    async with session(ctx) as db:
        b = (
            await db.execute(select(Building).where(Building.id == building_id))
        ).scalar_one_or_none()
        if b is None:
            return False
        await db.refresh(b, attribute_names=["floors"])
        if b.floors:
            return False  # a person added floors meanwhile: theirs
        prop = await floor_proposal.floor_proposal(db, b)
        if prop["sheets_with_markers"] == 0:
            ctx.decide(
                STEP,
                "skipped",
                f"Building {code}: no level markers",
                "No sheet of this building prints level markers; add the floors on the overview",
                needs_you=True,
                entity_type="building",
                entity_id=b.id,
            )
            return False
        if prop["split_level"] and len(prop["blocks"]) >= 2:
            blocks = [
                {"code": blk["code"], "name": None, "floors": blk["floors"]}
                for blk in prop["blocks"]
            ]
            created, removed = await floor_proposal.accept_blocks(
                db, b, blocks, delete_source=True, actor=ctx.actor
            )
            ctx.decide(
                STEP,
                "accepted",
                f"Building {code}: {len(created)} blocks",
                "Split-level blocks drawn side by side became buildings "
                + ", ".join(f"{c.code} ({len(c.floors)} floors)" for c in created)
                + ("; the empty source building was removed" if removed else ""),
                confidence=rules.BLOCKS_CONFIDENCE,
                entity_type="building",
                entity_id=created[0].id if created else b.id,
            )
            return True
        floors = [f for f in prop["floors"] if f["status"] in ("new", "update")]
        if not floors or prop["unmatched_existing"]:
            ctx.decide(
                STEP,
                "skipped",
                f"Building {code}: floors need you",
                "The level markers do not give a clean storey list; review the proposal on the "
                "overview",
                needs_you=True,
                entity_type="building",
                entity_id=b.id,
            )
            return False
        await projects.set_floors(
            db,
            b,
            [
                {
                    "level": f["level"],
                    "display_name": f["display_name"],
                    "height_m": f.get("height_m"),
                    "elevation_m": f.get("elevation_m"),
                }
                for f in floors
            ],
            ctx.actor,
        )
        levels = ", ".join(f["display_name"] for f in sorted(floors, key=lambda x: x["level"]))
        ctx.decide(
            STEP,
            "accepted",
            f"Building {code}: {len(floors)} floors",
            f"Floors from the level markers of {prop['sheets_with_markers']} sheet(s): {levels}"
            + ("" if prop.get("roof") else "; no roof marker, the top floor has no height"),
            confidence=(
                rules.FLOORS_CONFIDENCE_WITH_ROOF
                if prop.get("roof")
                else rules.FLOORS_CONFIDENCE_NO_ROOF
            ),
            entity_type="building",
            entity_id=b.id,
        )
        return True
