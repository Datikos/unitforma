"""Mapping tools (ADR-0034 Decision 3): what the sheet editor does, over the same services and
with the same rights as the admin API. A sheet is one page of a processed drawing revision; a
unit outline is a ring of normalised sheet coordinates (0..1, x right, y down)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from unitforma.api.schemas import BoundaryOut, SheetOut, SuggestionOut, UnitOut
from unitforma.documents import assignments
from unitforma.documents import service as documents
from unitforma.geometry import service as geometry_service
from unitforma.identity.authz import Action
from unitforma.identity.deps import TenantContext
from unitforma.inventory import service as inventory
from unitforma.mapping import service as mapping
from unitforma.mcp.auth import tenant_ctx
from unitforma.mcp.tools.base import Tool, actor
from unitforma.projects import service as projects
from unitforma.tenants.models import Sheet

Ring = list[list[float]]


class SheetFloor(BaseModel):
    floor_id: uuid.UUID
    region: Ring | None = Field(
        default=None,
        description="Part of the sheet showing this floor (normalised ring), on multi-block sheets",
    )


class OutlineCreated(BaseModel):
    unit: UnitOut
    boundary: BoundaryOut


class Approved(BaseModel):
    sheet_id: uuid.UUID
    approved_units: int
    massing_queued: bool


async def _sheet(ctx: TenantContext, sheet_id: uuid.UUID) -> tuple[Sheet, uuid.UUID]:
    sheet = await documents.get_sheet(ctx.session, ctx.tenant_id, sheet_id)
    project_id = await documents.sheet_project_id(ctx.session, sheet)
    ctx.require_project(project_id)
    return sheet, project_id


async def _sheet_out(ctx: TenantContext, sheet: Sheet) -> SheetOut:
    return (await documents.sheets_with_floors(ctx.session, [sheet]))[0]


async def list_sheets(revision_id: uuid.UUID) -> list[SheetOut]:
    """The pages of a processed document revision (`list_documents` gives the current
    revision id): page number, processing hints (kind, level markers, labels), the floors each
    page shows with their status (suggested or confirmed) and region, the scale
    (`calibration_status`: none, calibrated, inherited), exclusion, and signed URLs of the
    raster and thumbnail. Read a sheet's `version` before changing it."""
    async with tenant_ctx() as ctx:
        ctx.require("documents", Action.READ)
        rev = await documents.get_revision(ctx.session, ctx.tenant_id, revision_id)
        doc = await documents.get_document(ctx.session, ctx.tenant_id, rev.document_id)
        ctx.require_project(doc.project_id)
        return await documents.sheets_with_floors(
            ctx.session, await documents.list_sheets(ctx.session, revision_id)
        )


async def set_sheet_floors(sheet_id: uuid.UUID, floors: list[SheetFloor], version: int) -> SheetOut:
    """Confirm which floors a sheet shows: replaces the sheet's floor set with these, all
    confirmed. One floor for a normal plan; several with a `region` each on a sheet that draws
    blocks side by side; an empty list says the sheet shows no floor (a detail, a schedule).
    A floor with units drawn on this sheet cannot be removed. Needs the sheet's current
    `version`."""
    async with tenant_ctx(write=True) as ctx:
        ctx.require("mapping", Action.WRITE)
        sheet, _project_id = await _sheet(ctx, sheet_id)
        await assignments.set_floors(
            ctx.session,
            sheet,
            [
                {"floor_id": f.floor_id, "region": {"ring": f.region} if f.region else None}
                for f in floors
            ],
            version,
            actor(ctx),
        )
        return await _sheet_out(ctx, sheet)


async def calibrate_sheet(
    sheet_id: uuid.UUID, p1: list[float], p2: list[float], distance_m: float, version: int
) -> SheetOut:
    """Set a sheet's scale from two points and the real distance between them in metres (a
    dimension line, a known wall). Points are normalised sheet coordinates (0..1). The current
    outlines on the sheet are recomputed in metres. A DXF or a sheet with a printed 1:N usually
    arrives calibrated; check `calibration_status` first. Needs the sheet's current `version`."""
    async with tenant_ctx(write=True) as ctx:
        ctx.require("mapping", Action.WRITE)
        sheet, project_id = await _sheet(ctx, sheet_id)
        if len(p1) != 2 or len(p2) != 2:
            raise ToolError("p1 and p2 are [x, y] pairs in normalised sheet coordinates")
        await documents.calibrate_sheet(
            ctx.session,
            sheet,
            p1=p1,
            p2=p2,
            distance_m=distance_m,
            version=version,
            actor=actor(ctx),
        )
        out = await _sheet_out(ctx, sheet)
        tenant_id = ctx.tenant_id
    await geometry_service.queue_massing(tenant_id, project_id)
    return out


async def exclude_pages(
    revision_id: uuid.UUID, pages: list[int], excluded: bool = True, reason: str | None = None
) -> list[SheetOut]:
    """Take pages of a revision out of mapping (reprints of the plans in a fire-safety set,
    details, schedules) or bring them back. An excluded page has no floors, offers no
    suggestions and accepts no units. `pages` are page numbers as shown."""
    async with tenant_ctx(write=True) as ctx:
        ctx.require("documents", Action.WRITE)
        rev = await documents.get_revision(ctx.session, ctx.tenant_id, revision_id)
        doc = await documents.get_document(ctx.session, ctx.tenant_id, rev.document_id)
        ctx.require_project(doc.project_id)
        sheets = await documents.list_sheets(ctx.session, revision_id)
        wanted = set(pages)
        missing = sorted(wanted - {s.page_no for s in sheets})
        if missing:
            raise ToolError(f"No such pages: {', '.join(map(str, missing[:20]))}")
        await documents.set_excluded(
            ctx.session,
            [s for s in sheets if s.page_no in wanted],
            excluded,
            reason,
            actor(ctx),
        )
        return await documents.sheets_with_floors(ctx.session, sheets)


async def suggest_outlines(sheet_id: uuid.UUID) -> list[SuggestionOut]:
    """Unit outlines the drawing suggests on a sheet: closed shapes of the line work, filled
    zones and hatches, labelled from the text inside (apartment number, printed area, type),
    each with a confidence (0.95 a filled zone with one label, 0.9 a labelled loop, lower when
    the measured and printed areas disagree) and the floor it would land on. Nothing is written;
    pass a suggestion's ring, label, unit type and printed area to `create_outline`."""
    async with tenant_ctx() as ctx:
        ctx.require("mapping", Action.READ)
        sheet, _ = await _sheet(ctx, sheet_id)
        return [
            SuggestionOut(**c.as_dict(), floor_id=fid)
            for c, fid in await mapping.suggest_for_sheet(ctx.session, sheet)
        ]


async def create_outline(
    sheet_id: uuid.UUID,
    ring: Ring,
    unit_type: Literal["apartment", "commercial", "parking", "storage"] = "apartment",
    label: str | None = None,
    code: str | None = None,
    floor_id: uuid.UUID | None = None,
    printed_area_m2: float | None = None,
    source: Literal["manual", "vector_suggest"] = "vector_suggest",
) -> OutlineCreated:
    """Draw a unit outline on a sheet: creates a draft unit with a permanent id and a code from
    the project's pattern (or `code`). `ring` is a normalised ring (at least 3 points); `label`
    is the text on the drawing ("ბინა №12"); `printed_area_m2` the area printed next to it, kept
    as the documented area; `floor_id` only on a sheet showing several floors when the region
    does not decide. The outline stays a draft until `approve_sheet`."""
    async with tenant_ctx(write=True) as ctx:
        ctx.require("mapping", Action.WRITE)
        sheet, project_id = await _sheet(ctx, sheet_id)
        project = await projects.get_project(ctx.session, ctx.tenant_id, project_id)
        try:
            unit, boundary = await inventory.create_unit_from_boundary(
                ctx.session,
                project=project,
                sheet=sheet,
                ring=ring,
                unit_type=unit_type,
                code=code,
                label=label,
                revision_id=sheet.revision_id,
                actor=actor(ctx),
                source=source,
                floor_id=floor_id,
                printed_area_m2=float(Decimal(str(printed_area_m2))) if printed_area_m2 else None,
            )
        except ValueError as e:
            raise ToolError(f"Invalid boundary: {e}") from None
        out = OutlineCreated(
            unit=UnitOut.model_validate(unit), boundary=BoundaryOut.model_validate(boundary)
        )
        tenant_id = ctx.tenant_id
    await geometry_service.queue_massing(tenant_id, project_id)
    return out


async def approve_sheet(sheet_id: uuid.UUID) -> Approved:
    """Approve the mapping of a sheet: every draft outline on it becomes an active, verified
    unit, and the 3D massing is rebuilt. Needs the mapping approve right (architectural
    reviewer or tenant admin). Check the outlines with `list_units` or the sheet editor first."""
    async with tenant_ctx(write=True) as ctx:
        ctx.require("mapping", Action.APPROVE)
        sheet, project_id = await _sheet(ctx, sheet_id)
        n = await inventory.approve_sheet(ctx.session, sheet, actor(ctx))
        tenant_id = ctx.tenant_id
    queued = bool(n) and await geometry_service.queue_massing(tenant_id, project_id)
    return Approved(sheet_id=sheet_id, approved_units=n, massing_queued=queued)


TOOLS = [
    Tool(list_sheets, "read", "Pages of a drawing revision"),
    Tool(
        set_sheet_floors,
        "write",
        "Confirm the floors a sheet shows",
        destructive=True,
        idempotent=True,
    ),
    Tool(calibrate_sheet, "write", "Set a sheet's scale", destructive=True, idempotent=True),
    Tool(exclude_pages, "write", "Exclude or include pages", destructive=True, idempotent=True),
    Tool(suggest_outlines, "read", "Suggested unit outlines"),
    Tool(create_outline, "write", "Draw a unit outline"),
    Tool(approve_sheet, "write", "Approve a sheet's mapping", destructive=True, idempotent=True),
]
