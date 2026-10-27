"""Tools over buildings and floors (ADR-0015 Decision 5), moved from ``mcp/server.py``
unchanged (ADR-0028 #C1)."""

from __future__ import annotations

import uuid
from typing import Any

from unitforma.api.schemas import (
    BlockAccept,
    BlocksAcceptOut,
    BuildingCreate,
    BuildingOut,
    BuildingUpdate,
    FloorIn,
    FloorOut,
    FloorProposalOut,
)
from unitforma.documents import floor_proposal as proposal
from unitforma.identity.authz import Action
from unitforma.mcp.auth import tenant_ctx
from unitforma.mcp.tools.base import Tool, actor
from unitforma.projects import service as projects


async def list_buildings(project_id: uuid.UUID) -> list[BuildingOut]:
    """Buildings of a project with their floors (the SITE building included)."""
    async with tenant_ctx() as ctx:
        ctx.require("project", Action.READ)
        ctx.require_project(project_id)
        await projects.get_project(ctx.session, ctx.tenant_id, project_id)
        rows = await projects.list_buildings(ctx.session, project_id)
        return [BuildingOut.model_validate(b) for b in rows]


async def create_building(project_id: uuid.UUID, building: BuildingCreate) -> BuildingOut:
    """Add a building (code 1 to 20 chars, unique in the project). Floors come next with
    set_floors or from the drawings with get_floor_proposal."""
    async with tenant_ctx(write=True) as ctx:
        ctx.require("project", Action.WRITE)
        ctx.require_project(project_id)
        p = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
        b = await projects.create_building(ctx.session, p, building.model_dump(), actor(ctx))
        return BuildingOut.model_validate(
            await projects.get_building(ctx.session, ctx.tenant_id, b.id)
        )


async def update_building(building_id: uuid.UUID, changes: BuildingUpdate) -> BuildingOut:
    """Change name, sort order, construction status (planned, under_construction, completed),
    completion, terms, site placement or elevation sheet. Fields left out are kept; name,
    construction_status, completion, terms and elevation_sheet_id sent as null are cleared.
    `changes.version` must be the current one."""
    async with tenant_ctx(write=True) as ctx:
        ctx.require("project", Action.WRITE)
        b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
        ctx.require_project(b.project_id)
        data: dict[str, Any] = changes.model_dump(exclude={"version"}, exclude_unset=True)
        data = {k: v for k, v in data.items() if v is not None or k in projects.BUILDING_CLEARABLE}
        if changes.site_transform is not None:
            data["site_transform"] = changes.site_transform.model_dump()
        if "site_transform" in data and "placement_status" not in data:
            if b.placement_status == "unplaced":
                data["placement_status"] = "draft"
        b = await projects.update_building(ctx.session, b, data, changes.version, actor(ctx))
        return BuildingOut.model_validate(
            await projects.get_building(ctx.session, ctx.tenant_id, b.id)
        )


async def set_floors(building_id: uuid.UUID, floors: list[FloorIn]) -> list[FloorOut]:
    """Replace the building's floor list: level (integer, 0 = ground, negative below),
    display name, height and elevation in metres (null when unknown)."""
    async with tenant_ctx(write=True) as ctx:
        ctx.require("project", Action.WRITE)
        b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
        ctx.require_project(b.project_id)
        rows = await projects.set_floors(
            ctx.session, b, [f.model_dump() for f in floors], actor(ctx)
        )
        out = [FloorOut.model_validate(f) for f in rows]
        await proposal.queue_resuggest(ctx.tenant_id, b.project_id)
        return out


async def get_floor_proposal(building_id: uuid.UUID) -> FloorProposalOut:
    """Floors read from the building's drawings (level markers): elevations, heights, and
    split-level blocks when the sheets draw several side by side. Accept with set_floors or
    accept_floor_proposal_blocks."""
    async with tenant_ctx() as ctx:
        ctx.require("project", Action.READ)
        b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
        ctx.require_project(b.project_id)
        return FloorProposalOut.model_validate(await proposal.floor_proposal(ctx.session, b))


async def accept_floor_proposal_blocks(
    building_id: uuid.UUID, blocks: list[BlockAccept], delete_source: bool = False
) -> BlocksAcceptOut:
    """Create one building per split-level block with its floors; delete_source removes the
    source building when it has no units and no documents."""
    async with tenant_ctx(write=True) as ctx:
        ctx.require("project", Action.WRITE)
        b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
        ctx.require_project(b.project_id)
        project_id = b.project_id
        created, removed = await proposal.accept_blocks(
            ctx.session,
            b,
            [blk.model_dump() for blk in blocks],
            delete_source=delete_source,
            actor=actor(ctx),
        )
        out = [
            BuildingOut.model_validate(
                await projects.get_building(ctx.session, ctx.tenant_id, c.id)
            )
            for c in created
        ]
        await proposal.queue_resuggest(ctx.tenant_id, project_id)
        return BlocksAcceptOut(buildings=out, source_removed=removed)


TOOLS = [
    Tool(list_buildings, "read", "List buildings"),
    Tool(create_building, "write", "Add a building"),
    Tool(update_building, "write", "Update a building", destructive=True),
    Tool(set_floors, "write", "Replace a building's floors", destructive=True, idempotent=True),
    Tool(get_floor_proposal, "read", "Floors read from the drawings"),
    Tool(
        accept_floor_proposal_blocks, "write", "Split a building into its blocks", destructive=True
    ),
]
