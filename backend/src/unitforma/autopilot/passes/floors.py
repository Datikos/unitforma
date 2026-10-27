"""Floors pass (ADR-0025 Decision 5 "floors"): accept the floor proposal of every building that
has no floors yet. Split-level blocks (ADR-0013 Decision 4) stay a proposal for the overview; the
building gets the merged storey list."""

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
        blocks = prop["blocks"] if prop["split_level"] else []
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
        if len(blocks) >= 2:
            # Stepped blocks drawn side by side (ADR-0013 Decision 4) may be one building on a
            # slope or several: on permit 1127975 the owner kept one building where the markers
            # showed five blocks (2026-10-27). The merged storey list is applied when its storeys
            # have a storey's height; the split stays a proposal on the overview.
            steps = ", ".join(f"{blk['code']} ({len(blk['floors'])} floors)" for blk in blocks)
            low = [
                f
                for f in floors
                if f.get("height_m") is not None and f["height_m"] < rules.FLOOR_MIN_HEIGHT_M
            ]
            if low:
                ctx.decide(
                    STEP,
                    "skipped",
                    f"Building {code}: {len(blocks)} blocks drawn side by side",
                    f"The level markers step across {steps} by less than a storey "
                    f"({rules.FLOOR_MIN_HEIGHT_M} m); accept the blocks or set the floors on "
                    "the overview",
                    needs_you=True,
                    entity_type="building",
                    entity_id=b.id,
                )
                return False
            ctx.decide(
                STEP,
                "skipped",
                f"Building {code}: {len(blocks)} blocks drawn side by side",
                f"The level markers step across {steps}. Kept as one building with every level; "
                "split it on the overview if they are separate buildings",
                needs_you=True,
                entity_type="building",
                entity_id=b.id,
            )
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
