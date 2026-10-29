# ADR-0034: MCP deletes behind a confirmation argument, mapping tools, and a read-only MCP server on the portal hosts

- **Status:** accepted (2026-10-29; implemented 2026-10-29)
- **Date:** 2026-10-29
- **Deciders:** David Sakhelashvili (platform owner); BACKLOG 31 said "owner's pick" for the confirmation form, and "complete 31" on 2026-10-29 left the pick to this ADR (Decision 1), which he can overrule
- **Plan reference:** §3.4 (authorization), §7 (buyer portal), §12.2 (API boundaries), ADR-0012 (deletes), ADR-0015 (MCP server, Revisit), ADR-0028 Decision 6 (one tool registry)

## Context

BACKLOG 31 (ADR-0015 Revisit, ADR-0028 #C2) held three things: a `delete_*` tool family with an
explicit confirmation argument, the mapping tools, and the buyer-side read-only server that
ADR-0015 called Option A and "kept as a later ADR".

What `main` has (commit `72ec6c3`):

- One tool registry `mcp/tools/` with 25 tools; `test_mcp_registry.py` pins the count, requires a
  docstring and a title per tool, and checks that every `write` tool opens `tenant_ctx(write=True)`
  before anything else. `mcp/server.py` says in its instructions that deleting, uploading, mapping
  outlines and publishing are not available.
- The deletes exist as services with their guards: `projects.delete_floor` (ADR-0031 #E1, refused
  while a unit uses the floor), `projects.delete_building` (ADR-0012, refused with units or
  documents), `documents.delete_document` (ADR-0012, `detach_units`), `projects.delete_project`
  (tenant admin, typed slug, publication retired first). The admin cards confirm them in dialogs.
- The mapping endpoints hold two bodies of logic outside a service: `calibrate_sheet` (version
  and raster checks, `calibration_from_points`, `recalibrate_sheet`, audit, massing) and the
  `_sheets_out` helper (signed URLs plus floor assignments). Everything else calls a service.
- The portal read model lives in `publishing/portal.py`: `site_for_host`, `resolve_publication`,
  `site_summary`, `list_units`, `list_layouts`, `get_unit`, all anonymous, keyed by the request
  host; `api/portal.py` wraps them for the SPA.
- ADR-0015 Decision 1: `/mcp` only on the admin host; tenant hosts and custom domains serve the SPA
  for that path. The SDK validates Host and Origin from a fixed list (`TransportSecuritySettings`);
  custom domains make such a list impossible for the portal.
- A real confirmation prompt (MCP elicitation) reaches only clients on the 2026-07-28 revision and
  needs a shared `requestState` key for the two `api` replicas (ADR-0015 Revisit, checked
  2026-10-27).

## Decision

1. **Deletes take an explicit `confirm` argument equal to what a person sees.** The floor's
   `display_name`, the building `code`, the document `title`. A mismatch is a tool error that
   names the expected value, so the assistant has to state the thing it is about to remove.
   Chosen over MCP elicitation because it works with every client today and needs no shared
   secret between replicas; elicitation stays in ADR-0015 Revisit.
2. **The family is `delete_floor`, `delete_building`, `delete_document`.** Each wraps the same
   service as its endpoint, with the same rights (`project` WRITE, `documents` WRITE) and the same
   side effects (floor: re-suggest floors and rebuild the massing; document with `detach_units`:
   rebuild the massing). `delete_project` is not a tool: ADR-0012 ties the permanent delete to a
   tenant admin's typed slug in a browser session, it destroys files and takes a portal offline,
   and ADR-0015 Decision 3 says a bearer token cannot prove aal2. The owner can reaffirm it.
3. **Mapping tools** over the services, with the endpoints' rights: `list_sheets` (`documents`
   READ; sheets with floors and signed URLs), `set_sheet_floors` (`mapping` WRITE), `calibrate_sheet`
   (`mapping` WRITE), `exclude_pages` (`documents` WRITE), `suggest_outlines` (`mapping` READ),
   `create_outline` (`mapping` WRITE), `approve_sheet` (`mapping` APPROVE). The calibration body
   moves from the router into `documents.service.calibrate_sheet`, and `sheets_with_floors` into
   the service, so the router and the tool share one home.
4. **A second, anonymous, read-only MCP server on every portal host at `/mcp`** ("Unitforma
   portal"), over its own `PORTAL_TOOLS`: `site`, `get_project`, `list_units` (the portal
   endpoint's filters), `get_unit`, `list_layouts`. They return exactly the dicts the portal API
   publishes, resolved by the request host like the SPA; no preview tokens, no cookies, no writes.
   This amends ADR-0015 Decision 1: tenant hosts and custom domains now answer `/mcp` from `api`,
   the SPA keeps every other path.
5. **One route, dispatched by host.** `/mcp` on the admin host is the staff server behind the
   bearer middleware (unchanged); on any other host it is the portal server. Both are stateless
   JSON Streamable HTTP; both session managers run in the app lifespan. The host comes from
   `X-Forwarded-Host`, then `Host`, through `normalise_hostname`, into a context variable.
6. **Portal transport security by hand.** The portal server cannot list its hosts, so the SDK's
   DNS-rebinding protection is off for it and the spec's Origin rule is kept in the dispatcher: a
   request whose `Origin` host differs from the request host is refused with 403. The staff
   server keeps the SDK's fixed list. Caddy serves `handle /mcp*` in the tenant block of both
   Caddyfiles with a `portal_mcp_by_ip` zone of 60 requests per minute per IP and a 64 KB body.
   Setting `UF_PORTAL_MCP_ENABLED` (default true) leaves `/mcp` on portal hosts a 404 when off.

## Options considered

- **O1 (chosen): `confirm` argument.** Pros: every client, no replica secret, one rule to read.
  Cons: an assistant can fill it in without asking the person; the tool docstrings tell it not to.
- **O2: MCP elicitation.** Pros: a real prompt to the person. Cons: 2026-07-28 clients only, a
  shared key file for the replicas, nothing for older clients. Stays in ADR-0015 Revisit.
- **O3: no delete tools** (status quo). Rejected by the owner on 2026-10-29.
- **O4: portal server on its own path or host** (`/portal-mcp`, `mcp.<tenant>`). Rejected: a second
  path to explain, a wildcard certificate per tenant for a host; `/mcp` with a host dispatch keeps
  the one address people already know.

## Consequences

**Easier.** An assistant can clean up a wrong floor or building, map a sheet end to end
(floors, scale, suggestions, outlines, approval) and, on the public side, answer "which two-bedroom
flats under 150 000 are left in block A" straight from a developer's portal, with no credential.

**Harder.** Two rules for reviewers: every delete tool checks `confirm` before the service, and
every portal tool reads only through `publishing.portal`. The dispatcher is a second place where
the host decides behaviour (the first is the portal API). The portal server runs without the
SDK's host list, so its Origin check in the dispatcher is the only one.

**Operations.** One more Caddy handle and rate-limit zone per portal host; no new container or
secret. The `/mcp` 404 on portal hosts stops being the signal that the staff server is misrouted.

**Revisit.** Elicitation once clients on 2026-07-28 are common and the replicas share a key;
`delete_project` if the owner wants it from an assistant; portal tools for inquiries once
Phase 5 exists (they would need the buyer session, a different door).

**Out of scope here:** `delete_project`, uploads through MCP, OAuth (ADR-0015 Option C), portal
writes, preview links through the portal server.

## Action items

- [x] 1 `mcp/tools/deletes.py`: the three tools with the `confirm` contract; registry count and
      instructions updated; tests: wrong confirm refused and nothing deleted, right confirm deletes
      with the side effects, floor with units refused, read token refused.
- [x] 2 `documents.service.calibrate_sheet` and `sheets_with_floors` moved out of the router;
      `mcp/tools/mapping.py` with the seven tools; tests through the token: floors set, scale
      set, suggestions read, outline created, sheet approved, pages excluded, rights kept.
- [x] 3 `mcp/portal_tools.py` and `mcp/server.py` portal server, host dispatcher in `main.py`,
      Origin check, `portal_mcp_enabled`; tests: tools list without a bearer on a portal host, units
      listed, unknown host refused, admin host still 401.
      *Found while implementing (2026-10-29):* the staff server's 421 for an unknown host (ADR-0015
      `test_wrong_host_is_refused`) is gone by construction: an unknown host is a portal host now
      and gets the anonymous server, whose tools only answer "Portal not configured" for it; the
      test was rewritten to say so. Outside production the dispatcher treats `localhost`,
      `127.0.0.1`, `[::1]` and `testserver` as staff hosts, matching the staff server's own
      transport security. List results of the mapping tools come back as `{"result": [...]}`
      like the other list tools.
- [x] 4 Caddy: `/mcp*` in the tenant block of `Caddyfile.prod` and `Caddyfile.dev`, validated;
      `.env.example`; plan §12.2 and §19 tables; ADR-0015 and ADR-0012 amended; README; tokens
      guide; BACKLOG row 31 removed.
