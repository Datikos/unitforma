"""The MCP server: Streamable HTTP at ``/mcp`` (ADR-0015) over the one tool registry in
``mcp/tools`` (ADR-0028 Decision 6).

Every tool is a thin wrapper over the same service function the admin router calls, inside the
tenant context of the token's owner, and returns the admin API's response shapes so the shape
has one home (``api/schemas.py``). Each tool carries MCP annotations from its registry entry, so
clients can tell reads from writes.
"""

from __future__ import annotations

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp

from unitforma import __version__
from unitforma.core.settings import Settings
from unitforma.mcp.auth import BearerTokenMiddleware
from unitforma.mcp.tools import TOOLS

INSTRUCTIONS = """Unitforma staff tools for one developer workspace (tenant). Calls act as the \
token's owner with their role; a read-only token cannot change anything.
A project holds buildings, a building holds floors, a floor holds units; every project also has \
a virtual "SITE" building for outdoor units. Lengths are metres, areas square metres, money in \
the project's currency; null means unknown, never 0.
Find units by the codes people type with find_units ("A 21" matches A21 and A-21); list_units \
pages through a project. Documents are listed with their kinds, never their text. A generated \
plan render is requested here and reviewed by a person in the admin app. The setup checklist \
says what a project still lacks; run_setup lets the solver apply what it is sure of.
Updates need the record's current `version` (optimistic concurrency): read it first, send it back.
Deleting, uploading, mapping outlines and publishing are not available here; use the admin app."""

MAX_BODY_BYTES = 1024 * 1024  # Caddy limits /mcp to 1 MB as well (Decision 1)


def build_server() -> MCPServer:
    mcp = MCPServer("Unitforma", instructions=INSTRUCTIONS, version=__version__)
    for t in TOOLS:
        mcp.tool(name=t.name, title=t.title, annotations=t.annotations())(t.fn)
    return mcp


def transport_security(settings: Settings) -> TransportSecuritySettings:
    """Host and Origin checks the MCP spec requires; only the admin host in production."""
    hosts = [settings.admin_host, f"{settings.admin_host}:*"]
    origins = [f"https://{settings.admin_host}"]
    if not settings.is_production:
        hosts += ["127.0.0.1:*", "localhost:*", "[::1]:*", "testserver"]
        origins += ["http://127.0.0.1:*", "http://localhost:*", "https://localhost:*"]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins
    )


def mcp_asgi(settings: Settings, path: str = "/mcp") -> tuple[MCPServer, ASGIApp]:
    """The server and the ASGI app to register at ``path``: stateless Streamable HTTP with JSON
    responses (any api replica answers any request), behind the bearer-token middleware."""
    server = build_server()
    app = server.streamable_http_app(
        streamable_http_path=path,
        json_response=True,
        stateless_http=True,
        transport_security=transport_security(settings),
        max_request_body_size=MAX_BODY_BYTES,
    )
    return server, BearerTokenMiddleware(app)
