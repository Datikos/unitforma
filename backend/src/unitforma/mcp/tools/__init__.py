"""The one tool registry (ADR-0028 Decision 6): every Unitforma tool, for external MCP clients
today and for the admin app's assistant chat later. A tool is added here, never to a consumer."""

from __future__ import annotations

from unitforma.mcp.tools import (
    buildings,
    deletes,
    documents,
    layouts,
    mapping,
    projects,
    renders,
    setup,
    units,
)
from unitforma.mcp.tools.base import Tool

TOOLS: list[Tool] = [
    *projects.TOOLS,
    *buildings.TOOLS,
    *units.TOOLS,
    *documents.TOOLS,
    *renders.TOOLS,
    *layouts.TOOLS,
    *setup.TOOLS,
    *mapping.TOOLS,
    *deletes.TOOLS,
]

__all__ = ["TOOLS", "Tool"]
