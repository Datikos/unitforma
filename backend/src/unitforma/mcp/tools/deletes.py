"""Delete tools (ADR-0034 Decisions 1 and 2): each needs ``confirm`` equal to what a person sees
on the card, so the assistant states what it removes before the service runs. The services keep
their guards (ADR-0012, ADR-0031): a floor or building with units is refused, a mapped document
asks for ``detach_units``. ``delete_project`` is not a tool (ADR-0034 Decision 2)."""

from __future__ import annotations

import uuid

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from unitforma.documents import floor_proposal as proposal
from unitforma.documents import service as documents
from unitforma.geometry import service as geometry_service
from unitforma.identity.authz import Action
from unitforma.mcp.auth import tenant_ctx
from unitforma.mcp.tools.base import Tool, actor
from unitforma.projects import service as projects


class Deleted(BaseModel):
    kind: str
    id: uuid.UUID
    name: str = Field(description="What the person saw: the floor name, building code or title")
    detached_units: int = 0
    note: str | None = None


def _check(confirm: str | None, expected: str, what: str) -> None:
    if (confirm or "").strip() != expected:
        raise ToolError(
            f"Confirmation does not match: to delete {what} send confirm={expected!r}. "
            "Ask the person before you do."
        )


async def delete_floor(building_id: uuid.UUID, floor_id: uuid.UUID, confirm: str) -> Deleted:
    """Delete a floor that no unit uses (a level read off an outside ground mark, a duplicate).
    `confirm` must equal the floor's display name as shown on the building card ("B1",
    "Ground", "3"); ask the person first. Refused while any unit, in any state, belongs to the
    floor. Afterwards the sheets' floor suggestions and the 3D massing are refreshed."""
    async with tenant_ctx(write=True) as ctx:
        ctx.require("project", Action.WRITE)
        b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
        ctx.require_project(b.project_id)
        floor = next((f for f in b.floors if f.id == floor_id), None)
        if floor is None:
            raise ToolError("Floor not found in this building")
        _check(confirm, floor.display_name, f"floor {floor.display_name}")
        name = floor.display_name
        await projects.delete_floor(ctx.session, b, floor_id, actor(ctx))
        tenant_id, project_id = ctx.tenant_id, b.project_id
    await proposal.queue_resuggest(tenant_id, project_id)
    await geometry_service.queue_massing(tenant_id, project_id)
    return Deleted(kind="floor", id=floor_id, name=name)


async def delete_building(building_id: uuid.UUID, confirm: str) -> Deleted:
    """Delete an empty building: `confirm` must equal its code ("A", "A-9-10"); ask the person
    first. Refused while any unit belongs to it; its documents become project-level, its floors
    and models go with it. The virtual SITE building cannot be deleted."""
    async with tenant_ctx(write=True) as ctx:
        ctx.require("project", Action.WRITE)
        b = await projects.get_building(ctx.session, ctx.tenant_id, building_id)
        ctx.require_project(b.project_id)
        if b.kind != "building":
            raise ToolError("The SITE building holds the outdoor units and cannot be deleted")
        _check(confirm, b.code, f"building {b.code}")
        code = b.code
        await projects.delete_building(ctx.session, b, actor(ctx))
    return Deleted(kind="building", id=building_id, name=code)


async def delete_document(
    document_id: uuid.UUID, confirm: str, detach_units: bool = False
) -> Deleted:
    """Delete a document with its revisions, sheets and files. `confirm` must equal its title as
    listed; ask the person first. A document with units outlined on its sheets is refused unless
    `detach_units` is true: the units then keep their identity and lose their outline, and the
    3D massing is rebuilt without them. Not reversible."""
    async with tenant_ctx(write=True) as ctx:
        ctx.require("documents", Action.WRITE)
        d = await documents.get_document(ctx.session, ctx.tenant_id, document_id)
        ctx.require_project(d.project_id)
        _check(confirm, d.title, f"document {d.title!r}")
        title, project_id, tenant_id = d.title, d.project_id, ctx.tenant_id
        detached = await documents.delete_document(
            ctx.session, d, detach_units=detach_units, actor=actor(ctx)
        )
    if detached:
        await geometry_service.queue_massing(tenant_id, project_id)
    return Deleted(
        kind="document",
        id=document_id,
        name=title,
        detached_units=len(detached),
        note="units kept their identity and lost their outlines" if detached else None,
    )


TOOLS = [
    Tool(delete_floor, "write", "Delete a floor", destructive=True),
    Tool(delete_building, "write", "Delete an empty building", destructive=True),
    Tool(delete_document, "write", "Delete a document", destructive=True),
]
