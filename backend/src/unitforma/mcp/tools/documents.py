"""Document tools (ADR-0028 Decision 6): metadata and kinds, never page text."""

from __future__ import annotations

import uuid

from unitforma.api.admin_documents import _doc_out as document_out
from unitforma.api.schemas import DocumentOut
from unitforma.documents import service as documents
from unitforma.identity.authz import Action
from unitforma.mcp.auth import tenant_ctx
from unitforma.mcp.tools.base import Tool
from unitforma.projects import service as projects


async def list_documents(project_id: uuid.UUID) -> list[DocumentOut]:
    """Documents of a project: title, kind (floor_plan, site_plan, elevation, render, permit, …)
    and where the kind came from, the building it is filed under, visibility, and the current
    revision's file name, page count and processing status. No page text and no file content."""
    async with tenant_ctx() as ctx:
        ctx.require("documents", Action.READ)
        ctx.require_project(project_id)
        await projects.get_project(ctx.session, ctx.tenant_id, project_id)
        return [
            document_out(d, r) for d, r in await documents.list_documents(ctx.session, project_id)
        ]


TOOLS = [Tool(list_documents, "read", "List documents")]
