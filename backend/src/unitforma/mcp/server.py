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
from starlette.types import ASGIApp, Receive, Scope, Send

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
Mapping: list_sheets shows a drawing's pages with their floors and scale; set_sheet_floors, \
calibrate_sheet, suggest_outlines, create_outline and approve_sheet do what the sheet editor \
does; exclude_pages takes reprints out. Deleting a floor, an empty building or a document needs \
`confirm` equal to what the person sees (the floor name, the building code, the document title): \
ask them before you send it. Deleting a project, uploading and publishing stay in the admin app."""

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


PORTAL_INSTRUCTIONS = """Public, read-only tools of one developer's sales portal (the host you \
are talking to). Everything here is what the portal already shows to any visitor: published \
projects, buildings and floors, units with availability, prices in the project's currency (null \
means price on request, never 0), areas in square metres, plan types. Nothing can be changed or \
reserved here, and no personal data is involved. Start with `site`, then `list_units` with \
filters or `get_unit` by the code printed on the portal."""


def build_portal_server() -> MCPServer:
    from unitforma.mcp.portal_tools import PORTAL_TOOLS, portal_annotations

    mcp = MCPServer("Unitforma portal", instructions=PORTAL_INSTRUCTIONS, version=__version__)
    for fn, title in PORTAL_TOOLS:
        mcp.tool(name=fn.__name__, title=title, annotations=portal_annotations(title))(fn)
    return mcp


class HostDispatch:
    """One `/mcp` route, two servers (ADR-0034 Decision 5): the admin host gets the staff server
    behind its bearer middleware; every other host gets the anonymous portal server, after the
    spec's Origin rule is applied by hand (the portal cannot list its hosts, Decision 6)."""

    def __init__(self, settings: Settings, staff: ASGIApp | None, portal: ASGIApp | None) -> None:
        self.staff_hosts = {settings.admin_host.lower()}
        if not settings.is_production:
            # the staff server's own transport security allows these outside production
            self.staff_hosts |= {"localhost", "127.0.0.1", "[::1]", "testserver"}
        self.staff = staff
        self.portal = portal

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        from starlette.datastructures import Headers
        from starlette.responses import JSONResponse

        from unitforma.domains.service import normalise_hostname
        from unitforma.mcp.portal_tools import current_host

        headers = Headers(scope=scope)
        host = normalise_hostname(headers.get("x-forwarded-host") or headers.get("host", ""))
        if host.split(":")[0] in self.staff_hosts or self.portal is None:
            if self.staff is None:
                await JSONResponse({"title": "Not found", "status": 404}, status_code=404)(
                    scope, receive, send
                )
                return
            await self.staff(scope, receive, send)
            return
        origin = headers.get("origin")
        if origin:
            from urllib.parse import urlsplit

            if normalise_hostname(urlsplit(origin).hostname or "") != host.split(":")[0]:
                await JSONResponse({"title": "Origin not allowed", "status": 403}, status_code=403)(
                    scope, receive, send
                )
                return
        token = current_host.set(host)
        try:
            await self.portal(scope, receive, send)
        finally:
            current_host.reset(token)


def portal_asgi(path: str = "/mcp") -> tuple[MCPServer, ASGIApp]:
    """The portal server's ASGI app: stateless JSON Streamable HTTP, the SDK's host list off
    (custom domains cannot be listed; the dispatcher checks Origin), 64 KB bodies."""
    server = build_portal_server()
    app = server.streamable_http_app(
        streamable_http_path=path,
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        max_request_body_size=64 * 1024,
    )
    return server, app


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
