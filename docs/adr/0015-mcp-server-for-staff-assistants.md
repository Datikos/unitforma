# ADR-0015: An MCP server so a developer's staff can build projects from their AI assistant

- **Status:** accepted (2026-10-26, Option B now, Option C to the backlog; implemented 2026-10-26; on 2026-10-27 ADR-0028 #C1 to #C3 moved the tools into one registry in `mcp/tools/` and added units, documents, generated renders, plan types and setup: 25 tools, the same door, token and audit origin)
- **Date:** 2026-10-26
- **Deciders:** David Sakhelashvili (platform owner); the credential kind (Decision 2) is his call
- **Plan reference:** §3.3 (routing), §3.4 (authorization), §8.6 (abuse protection), §12.2 (API
  boundaries), ADR-0012 (deletes stay out), ADR-0013 (block acceptance)

## Context

The owner wants a developer's staff, the people who create projects and buildings, to do that
work from an AI assistant (Claude Code, Claude Desktop, Cursor) instead of the admin screens. The
Model Context Protocol (MCP) is the way those assistants call an external system: the server
publishes tools with JSON schemas, the assistant calls them over HTTP. Nothing in the plan, the
ADRs or the code mentions MCP today.

What `main` has, and what the server must reuse:

- Staff authentication is a Kratos browser session only: `identity/deps.py::current_staff` reads
  the `ory_kratos_session` cookie and asks Kratos `whoami` (60 s cache). There is no credential
  for a non-browser client. An assistant cannot hold a Kratos cookie.
- Authorization is `TenantContext` (`identity/deps.py`): `tenant_session(tenant_id, user_id,
  scope)` opens the RLS transaction, `_load_membership` loads the role and project set, and the
  matrix in `identity/authz.py` answers `require(resource, action)`. Every admin router calls a
  module service with that context; `projects/service.py` has `create_project`, `update_project`,
  `list_buildings`, `create_building`, `update_building`, `set_floors`, `create_site_feature`;
  `documents/floor_proposal.py` has the proposal and `accept_blocks` (ADR-0013). Each write calls
  `audit.write_audit` in the same transaction.
- `core/security.py::RequestedWithMiddleware` refuses every POST, PUT, PATCH and DELETE under
  `/api/` and `/auth/` without `X-Requested-With: unitforma`. That is the CSRF defence for cookie
  sessions. MCP clients send JSON-RPC over POST and set no such header.
- Caddy (`deploy/caddy/Caddyfile.prod`) imports the same `api_routes` snippet into the app host,
  the tenant subdomains and custom domains; `/api/*` is proxied round robin to `api:8000`, so no
  request may depend on in-process state of one replica.
- Deletes of projects, buildings and documents are confirmed in the UI and refused while
  published (ADR-0012).

Third-party facts (checked 2026-10-26; sources in plan §21):

- MCP specification, current revision 2026-07-28. Streamable HTTP transport: servers MUST validate
  the `Origin` header; a server MAY assign an `Mcp-Session-Id`, and the 2026 protocol path has none.
  Authorization: OPTIONAL for implementations, but when used, servers MUST serve RFC 9728
  protected-resource metadata naming at least one OAuth authorization server and MUST NOT accept
  or transit any other tokens.
- Python SDK `mcp` 2.3.0 (PyPI, released 2026-10-02, MIT, Python ≥ 3.10; docs say 3.11+). The
  server class is `mcp.server.MCPServer` (the v1 `FastMCP` import is gone). `streamable_http_app()`
  returns a Starlette app to mount; the host app must enter `mcp.session_manager.run()` in its own
  lifespan or the first request fails. Run options: `json_response=True` (one JSON body per POST
  instead of SSE), `stateless_http=True` (fresh transport per request), `transport_security`
  (allowed hosts and origins; without it the app answers only localhost and returns 421 behind a
  real host), `max_request_body_size` (default 4 MiB). `ctx.headers` exposes request headers, which
  the SDK docs call "client-supplied input, never an identity". The SDK's own `AuthSettings`
  requires `issuer_url` and publishes OAuth metadata; it is meant for an OAuth authorization server.
  The package depends on `httpx2`, a different distribution from the project's `httpx>=0.27`;
  coexistence is UNVERIFIED until `uv lock` runs.
- Ory Kratos issues sessions, not OAuth access tokens. An OAuth 2.1 authorization server next to
  it would be Ory Hydra (Apache-2.0), a new container.
- Client support for a static bearer header on HTTP MCP servers (checked 2026-10-26): Claude Code
  `claude mcp add --transport http <name> <url> --header "Authorization: Bearer <token>"`, and
  `${VAR}` expansion in `headers` of `.mcp.json` (code.claude.com/docs/en/mcp); claude.ai custom
  connectors accept "fixed credentials such as API keys that Claude sends on every request" next
  to OAuth (support.claude.com article 11175166). Cursor and VS Code: UNVERIFIED.

## Decision

1. **One MCP endpoint on the app host, `https://app.<platform>/mcp`, nowhere else.** Streamable
   HTTP, `json_response=True`, `stateless_http=True`, so any `api` replica answers any request.
   `transport_security` allows the admin host (`UF_ADMIN_HOST`) and, outside production, localhost.
   The Caddy `handle /mcp*` lives only in the `app.{$PLATFORM_DOMAIN}` block, with
   `request_body max_size 1MB` and a `rate_limit` zone `mcp_by_ip` of 120 events per minute per
   IP. Tenant hosts and custom domains keep serving the portal SPA for `/mcp`. The path is outside
   `/api/` on purpose: the `X-Requested-With` CSRF check does not apply because the endpoint never
   accepts a cookie.
2. **Credential: a personal API token per staff user per tenant** (Option B below; see "Options" for
   the OAuth alternative). Table `api_tokens`: `id`, `tenant_id`, `user_id`, `name`,
   `token_prefix` (12 chars shown in lists), `token_hash` (SHA-256 of the secret), `scope`
   (`read` | `write`), `expires_at` (required; default 90 days, maximum 365), `last_used_at`,
   `revoked_at`, `created_at`. RLS with `enable_tenant_rls`. The secret is `ufm_` + 40 URL-safe
   random characters, shown once at creation, never stored, never logged (logs carry the prefix).
   Sent as `Authorization: Bearer <secret>`. A revoked or expired token is refused on the next
   call: one indexed select per call, no cache. `last_used_at` is written at most once per minute
   per token.
3. **A token acts as its user in its tenant, never more.** Every tool call opens
   `tenant_session(tenant_id, user_id, scope="tenant")`, loads the membership, refuses an inactive
   one (404 as the admin API does), and builds the same `TenantContext`. The role matrix applies
   unchanged; the token scope narrows it: a `read` token cannot call a write tool even when the
   role allows the write. Platform administrators get tenant scope only (a token cannot prove
   aal2): a platform admin holds a token only in a workspace where they are an active member, and
   the token carries that membership's role; without a membership the create call answers 403
   "Not a member of this workspace" and the tokens page shows the reason instead of the button.
   *Found while using (2026-10-27):* the first implementation refused every platform admin, also
   a member; fixed the same day (`test_platform_admin_holds_a_token_only_where_a_member`).
   Tokens are created by the user for themselves; a tenant admin can list and revoke every
   token of the tenant.
4. **Auth is our middleware, not the SDK's.** A Starlette middleware around the mounted MCP app
   reads the bearer, verifies it against `api_tokens`, and puts the principal in a `contextvar`;
   tools read the contextvar. The SDK's `AuthSettings` is not wired, because it would publish
   RFC 9728 metadata pointing at an authorization server that does not exist. The gap against the
   spec's authorization chapter (static bearer instead of OAuth) is written in the plan and on the
   tokens screen until Option C lands.
5. **Tools, phase 1, projects and buildings only**, each a thin wrapper over the existing
   service function, returning the `api/schemas.py` shapes (`ProjectOut`, `BuildingOut`,
   `FloorOut`, `FloorProposalOut`, `SiteFeatureOut`) so the response shape has one home:
   `whoami`, `list_projects`, `get_project`, `create_project`, `update_project`,
   `list_buildings`, `create_building`, `update_building`, `set_floors`, `get_floor_proposal`,
   `accept_floor_proposal_blocks`, `list_site_features`, `create_site_feature`. No delete tools
   (ADR-0012 deletes are confirmed in the UI). Tool docstrings state units (metres, `numeric`,
   null means unknown, never 0) because the assistant reads them.
6. **Every write is audited as today**, through the service functions and `write_audit`, with
   `request_id = "mcp:" + token_prefix` so the audit page shows which token did it. No new audit
   column. *Found while implementing:* the service functions do not take a request id, so the
   audit writer fills `request_id` from a request-scoped origin (`audit.service.set_audit_origin`)
   that the MCP middleware sets; the admin API keeps passing the `X-Request-Id` header as before.
7. **Package `backend/src/unitforma/mcp/`** (`server.py` builds the `MCPServer` and tools,
   `auth.py` the bearer middleware and tenant context, `tokens` service in `identity/tokens.py`).
   *Found while implementing:* a Starlette `Mount("/mcp")` answers `/mcp` with a redirect to
   `/mcp/`, so the SDK app is registered as one `Route("/mcp")`; the token lookup runs under
   platform scope because the tenant is unknown before the row is read, everything after it in
   the tenant's own RLS session. It
   imports `identity`, `projects`, `documents` services and `api/schemas`; `core` never imports it
   (added to the import-linter forbidden list). Dependency `mcp>=2.3,<3` in `pyproject.toml`,
   required, not an extra.
8. **Screen: "API tokens" under the tenant menu** (`t/:tenantId/tokens`): create with name, scope
   and expiry; list with prefix, scope, created, last used, expires; revoke with a dialog. The
   guide entry carries the exact commands with the host filled in, for example
   `claude mcp add --transport http unitforma https://app.unitforma.com/mcp --header "Authorization: Bearer <token>"`,
   and the sentence that the token is shown once.

## Options considered

### Option A: read-only buyer MCP on the portal hosts

Public tools over the published inventory, anonymous. Pros: no credential. Cons: it is not what
was asked; staff cannot create anything. Kept as a later ADR.

### Option B: personal API tokens as bearer (chosen for phase 1)

Pros: nothing new to operate, works with every client that can set a header, the role matrix and
RLS apply unchanged, revocation is one row. Cons: not the spec's OAuth path, so a client that
only does OAuth discovery cannot connect; a token is a long-lived secret the user must keep.

### Option C: OAuth 2.1 with Ory Hydra as the authorization server

Hydra (Apache-2.0) next to Kratos, login and consent handed to the admin app, the SDK's
`AuthSettings` and RFC 9728 metadata wired. Pros: spec-compliant, works with OAuth-only clients,
short-lived tokens. Cons: a new container and Compose service, a login-consent bridge to write,
per-client registration (dynamic client registration or a platform admin screen). Size L+ on its
own, and it does not remove the need for tokens for scripted clients. Follows B as its own ADR
when an OAuth-only client matters.

### Option D: reuse the Kratos session cookie

The assistant would need the browser's cookie; the SDK docs and the spec both treat headers as
client input, and the cookie would carry the CSRF regime with it. Rejected.

## Trade-off analysis

| Axis | B tokens | C OAuth (Hydra) | D cookie |
|---|---|---|---|
| New container | none | Hydra | none |
| Spec authorization chapter | not followed, documented | followed | not followed |
| Works in Claude Code and claude.ai connectors | yes (checked 2026-10-26) | yes | no |
| Works with OAuth-only clients | no | yes | no |
| Revocation | one row, next call | token expiry or Hydra revoke | Kratos session |
| Size | L (with screen) | L+ | S but unsafe |

## Consequences

**Easier.** A project manager says "create project X with buildings A and B, 12 floors each" and
the assistant does it with the same rules, audit rows and RLS as the screens. Scripts and
integrations get a credential kind for the first time.

**Harder.** A second door to keep in review: every new tool must call a service function with a
`TenantContext` and never the session directly (one rule per review). Tokens are secrets users
hold; the screen must say so. A token with `write` scope held by a leaver stays valid until it
expires or an admin revokes it: membership suspension refuses it on the next call, which covers the
offboarding path.

**Operations.** One more dependency in the API image (`mcp`, MIT). One more Caddy handle and rate
limit zone on the app host. No new secret, no new container.

**Revisit.** Option C when a client that only does OAuth is needed (Cursor and VS Code are
unchecked); tools for documents, mapping and sales; a `delete_*` tool family with
an explicit confirmation argument; the buyer-side read-only server (Option A).

**Out of scope here:** Option A, Option C, deletes, uploads through MCP (presigned PUT already
exists for scripts), tools beyond projects and buildings, the Unitforma backend calling a model
itself.

## Action items

Phase 1, tokens

- [x] 1 Migration `0013_api_tokens.py`: table, indexes on `(tenant_id, user_id)` and
      `token_hash` unique, `enable_tenant_rls("api_tokens")`.
- [x] 2 `identity/tokens.py`: `create_token`, `list_tokens`, `revoke_token`, `verify_token`
      (hash lookup, expiry, revocation, membership active, `last_used_at` throttle). Tests
      `test_api_tokens.py`: valid, expired, revoked, wrong tenant, suspended membership, read
      token on write.
- [x] 3 `api/admin.py`: `GET/POST /tenants/{id}/tokens`, `DELETE /tenants/{id}/tokens/{token_id}`;
      schemas; OpenAPI and api-client regenerated.

Phase 2, server

- [x] 4 `pyproject.toml`: `mcp>=2.3,<3`; `uv lock`; `httpx2` 2.16.0 and `httpx` 0.28.1 resolve
      side by side (checked 2026-10-26).
      Import-linter: `unitforma.mcp` added to the forbidden list for `core`.
- [x] 5 `mcp/auth.py`: bearer middleware and contextvar principal; `mcp/server.py`: `MCPServer`,
      the 13 tools of Decision 5, `streamable_http_app(json_response=True, stateless_http=True,
      transport_security=...)`; mounted at `/mcp` in `main.py`, `session_manager.run()` entered
      in `_lifespan`. Settings `UF_MCP_ENABLED` (default true) and the allowed hosts derived from
      `UF_ADMIN_HOST`.
- [x] 6 Tests `test_mcp_server.py` through the ASGI app: `initialize`, `tools/list`,
      `tools/call list_projects`; `create_building` with a write token writes the audit row with
      `request_id = mcp:<prefix>`; `read` token refused on `create_project`; a foreign project id
      is 404; a request without bearer is 401; a wrong `Host` is 421. *Checked 2026-10-26* with
      the SDK's own `ClientSession` over `streamable_http_client` against uvicorn: initialize
      (protocol 2025-11-25 negotiated), 13 tools listed, `whoami`, `create_project`, the error path.
- [x] 7 Caddy: `handle /mcp*` in the app host block with the rate limit zone and body limit;
      `deploy/validate.sh` passes; `docs/runbooks/deploy.md` gets the line.

Phase 3, screen

- [x] 8 Admin: route `t/:tenantId/tokens`, side-menu entry, `pages/tokens.page.ts` (create
      dialog, one-time secret display with copy, list, revoke dialog), guide entry with the exact
      client commands; `ng lint`, `ng test`, `ng build admin`.

Phase 4, docs

- [x] 9 Plan: §3.3 row for `/mcp`, §12.2 boundary row "MCP | `/mcp` | bearer API token | token",
      §8.6 row for token theft, §21 sources (spec 2026-07-28, python-sdk, PyPI `mcp`). README:
      decision list and status. `.env.example`: `UF_MCP_ENABLED`. Known gap written on the
      tokens screen and in §12.2: bearer tokens, not OAuth.
