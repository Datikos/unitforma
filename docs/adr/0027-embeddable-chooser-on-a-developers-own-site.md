# ADR-0027: A developer embeds the chooser in their own site: the portal page in an iframe, framed loads carry a per-tenant `frame-ancestors` list, the snippet sits on the Publish page

- **Status:** proposed (2026-10-27)
- **Date:** 2026-10-27
- **Deciders:** David Sakhelashvili (platform owner). A relaxed clickjacking control is a security boundary: Decision 2 (who may add an origin, https only, the cap) and Decision 3 (what a framed load may do) are his to confirm before "start".
- **Plan reference:** §3.3 (routing), §4.5 (Caddy), §7.2 (anonymous vs authenticated), §8.3 (buyer session cookie, Phase 5), §9.1 (domain kinds), §9.2 (custom-domain lifecycle, not built), §9.5 (implementation notes), §11.2 (Settings page), ADR-0003 (Caddy as the single entry), ADR-0014 (lisihouse.ge is WordPress), ADR-0023 (`tenants.settings`, the Settings page), ADR-0026 (Caddy routes a subset of document loads on portal hosts; proposed the same day, shares the Caddyfile)

## Context

Most Georgian developers already run a site, usually WordPress: the reference lisihouse.ge is the
WordPress plugin `building_planner` 1.7 (ADR-0014). Today a developer has two ways to put the
Unitforma chooser in front of buyers, and both leave their site:

- **A link to the tenant subdomain** (`acme.unitforma.com/projects/riverside`). The buyer leaves the
  developer's site; the developer's menu, phone number and brand are gone.
- **A custom domain** (`riverside.example`, plan §9.1). It keeps the developer's name but not their
  site: the whole host is served by Unitforma. The lifecycle (add, TXT verification, activation,
  removal with certificate purge) is backlog item 7, plan Phase 6, not built; only the `ask`
  decision and host routing exist (`domains/service.py`, `api/internal.py`).

An iframe of the project page inside the developer's own page is the third path: the chooser sits
under their header, on their URL, with no DNS work. It is a distribution path parallel to custom
domains, not a replacement. What the code does today (read on 2026-10-27):

- **Every portal response forbids framing.** Both Caddyfiles (`deploy/caddy/Caddyfile.prod`,
  `Caddyfile.dev`) have one `(security_headers)` snippet with `X-Frame-Options DENY`, imported by the
  marketing host, the app host, the tenant wildcard and the custom-domain block. The snippet also
  deletes `Server`, so Caddy defers the whole block to response time. `web-portal` is nginx serving
  `index.html` for every path (`frontend/nginx.conf`) and knows no tenant.
- **`X-Frame-Options` has no allow-list.** MDN: `ALLOW-FROM` "is an obsolete directive. Modern
  browsers that encounter response headers with this directive will ignore the header completely.
  The `Content-Security-Policy` HTTP header has a `frame-ancestors` directive which you should use
  instead." (read 2026-10-27). `frame-ancestors` takes `'none'`, `'self'`, scheme and host sources,
  and "is not supported in the `<meta>` element": it must be an HTTP header on the document response.
- **The tenant is resolved from the host.** `api/portal.py::_host` reads `X-Forwarded-Host` or
  `Host`; `publishing/portal.site_for_host` resolves it through `portal_resolve_host` behind a
  5-second per-process cache (`UF_PORTAL_CACHE_SECONDS`) and `site_summary` reads the `Tenant` row
  inside `tenant_session`. The portal API is same-origin with the portal page (`BASE =
  '/api/v1/portal'` in `portal-api.ts`), so a framed page needs no CORS.
- **A tenant-level setting store exists.** `tenants.settings jsonb` is merged key by key by `PATCH
  /tenants/{id}` behind the `tenant.settings` right (tenant admin only, `identity/authz.py` line 33),
  and the Settings page (`admin/pages/settings.page.ts`) holds its first key, `render_prompt`, with
  an audit row per change (ADR-0023).
- **The Publish page knows the portal URL.** `publishing/service.portal_base_url` prefers an active
  custom domain, else the subdomain, and returns `None` when the tenant has no active, verified
  `portal_domains` row; `publish.page.ts` shows "Open portal" from `readiness().portal_url`.
- **The portal keeps state in browser storage.** Favourites (`core/favourites.ts`, `localStorage`
  per host and project, read at line 46 without `try`), the units view key (`uf:units-view`), the
  playground layouts (`playground.model.ts` line 585) and the preview token (`sessionStorage`).
  The plan viewer has a full-screen button (ADR-0017); the playground opens in its own window
  (`window.open`, ADR-0020).
- **Thirty-four absolute links.** `routerLink="/..."` and `['/projects', ...]` appear 34 times in the
  portal pages and header; the header (`ui/portal-header.component.ts`) shows brand, tagline and the
  project navigation on every page.
- **Phase 5 is not built.** The buyer session cookie is planned as `uf_session`, `HttpOnly; Secure;
  SameSite=Lax`, host-only (plan §8.3). Browsers do not send a `Lax` cookie to a cross-site frame.

Third-party facts (read 2026-10-27; sources in plan §21 under "Embedding (ADR-0027)"):

- Caddy `forward_auth`: "If the upstream responds with a 2xx status code, then access is granted and
  the header fields in `copy_headers` are copied to the original request, and handling continues."
  Non-2xx: "the upstream's response is copied back to the client." The `header` directive takes a
  request matcher (`header @GET Cache-Control ...`), has `defer`, and is deferred automatically when
  a field is deleted. The matchers page documents `header <field> [<value>]` on request headers and
  `not`. Whether a placeholder such as `{http.request.header.X-Uf-Frame-Ancestors}` is expanded in a
  `header` directive **value** is not stated on the `header` page: **unverified**, checked in A1.
- `Sec-Fetch-Dest: iframe`: "The destination is an iframe. This might originate from an HTML
  `<iframe>` tag." MDN marks the header "Baseline Widely available ... since March 2023". The
  per-browser version table was not read: **unverified**. The header is browser-controlled (a
  forbidden request header), so a page cannot forge it.
- Storage: Firefox "double-keys all client-side state by the origin of the resource being loaded and
  by the top-level site" (`localStorage`, `sessionStorage`, IndexedDB, cookies through the Storage
  Access API). Chrome's storage partitioning and Safari's third-party cookie blocking were not read
  from a vendor page: **unverified**, assumed equivalent (partitioned, not shared with the portal
  opened top-level).
- WordPress: `unfiltered_html` belongs to Administrator and Editor on a single site and to the Super
  Admin only on Multisite (roles page, modified 2026-09-02). Whether WordPress strips `<iframe>` from
  content saved by a user without it, and the "Custom HTML" block page (404 on 2026-10-27), are
  **unverified**; the guide line says "paste it as an administrator".

## Decision

1. **The embed URL is the portal URL; framing is decided per framed document load, per tenant.**
   There is no `/embed/` path. On the tenant wildcard and the custom-domain blocks of both
   Caddyfiles, a document load whose request carries `Sec-Fetch-Dest: iframe` or `frame` and is
   not under `/api/`, `/auth/` or `/.ory/` goes through `forward_auth api:8000` with `uri
   /internal/embed/policy` and `copy_headers X-Uf-Frame-Ancestors`; the response then gets `header
   Content-Security-Policy "frame-ancestors {http.request.header.X-Uf-Frame-Ancestors}"` (deferred).
   Every other document load on those hosts keeps `X-Frame-Options DENY`, set by a matched `header`
   on the portal blocks (`@top not header Sec-Fetch-Dest iframe`, plus `frame`), no longer by the
   shared snippet. The marketing host and `app.<domain>` keep `DENY` on every response. A browser
   that sends no `Sec-Fetch-Dest` loads the page with `DENY` and the frame stays empty: the control
   fails closed. The SPA, its assets and the API keep being served exactly as today; nothing changes
   for a top-level visit, and a reload or a deep link inside the frame is again a framed load with
   the same policy.
2. **The allow-list is `tenants.settings.embed_origins`, written by the tenant admin, audited.**
   A JSON array of at most 20 strings, each `https://` + host (lower case, punycode through
   `domains/service.normalise_hostname`), an optional `:port`, no path, no query, no user info; the
   host may start with one `*.` label (the `<host-source>` wildcard of the CSP grammar, MDN
   "CSP: Sources", not read on 2026-10-27: **unverified**, checked in A1 with a wildcard entry) so
   `https://*.acme.ge` covers `www.acme.ge` and `acme.ge` is listed on its own; `http://` is refused
   (a developer site without TLS does not get the chooser; the owner may relax this per tenant
   later). The host part goes through `normalise_hostname` first, then the whole value must match
   `^https://(\*\.)?([a-z0-9-]+\.)+[a-z0-9-]+(:[0-9]{1,5})?$` with at least two labels after
   `*.` (no `https://*.ge`, no `https://-`), so the header built from the values cannot carry
   anything else. `GET /tenants/{id}/embed-origins` returns `{origins[], hosts[]}` (`hosts` = the
   tenant's active portal hosts, for the guide text); `PUT` takes `{origins[]}`, merges the key
   (ADR-0023 semantics), writes an audit row (`entity_type = tenant`, `action = embed_origins`,
   before and after) and answers the same shape; both behind `tenant.settings` (tenant admin
   only). The Publish page is opened by every role with `publication` READ (project manager,
   sales, reviewer; `authz.py` lines 66 to 71), so it does not call that GET: the readiness payload
   that already carries `portal_url` (`publishing/service.py` line 227) also carries
   `embed_origins` read-only. A duplicate, an invalid value or a 21st entry is 422
   `embed-origin-invalid`.
3. **`GET /internal/embed/policy` answers the policy for the host in the request.** Internal network
   only (Caddy's `handle /internal/*` already answers 404 from outside). It resolves
   `X-Forwarded-Host` through `site_for_host` (5-second cache), reads `embed_origins` of that tenant
   through `tenant_session` behind a cache with the same TTL keyed by tenant id (bounded by the
   tenant count), and returns 200 with `X-Uf-Frame-Ancestors: <origins joined by one space>`, or
   `'none'` when the list is empty, the host is unknown or the tenant is not active. It never
   answers non-2xx for a known host, so the browser always receives the portal document and the
   browser, not Caddy, refuses the frame. The endpoint carries no shared secret, unlike
   `/internal/domains/ask`: its answer is public by construction (it becomes a response header) and
   the Docker network is its only door. Caddy deletes a client-sent `X-Uf-Frame-Ancestors` with
   `request_header -X-Uf-Frame-Ancestors` before `forward_auth`, so a request can never supply the
   value the placeholder reads. Removing an origin takes effect for the next framed load within
   5 seconds because `frontend/nginx.conf` serves `index.html` with `Cache-Control: no-store`, which
   is also what stops a browser reusing a `DENY` document for a frame; a frame already open stays
   until it reloads.
4. **The portal knows when it is framed and behaves as a widget.** `core/embed-mode.ts` exposes
   `framed = window.self !== window.top` (read once at bootstrap). Framed: the header is replaced by
   a one-line bar with the project name and "Open in a new tab" (`href` = the current URL,
   `target=_blank`, `rel=noopener`), so a buyer can still share a unit; every page otherwise renders
   as today; the playground keeps opening in its own window (the snippet has no `sandbox`, so
   `window.open` works); the plan viewer's full-screen button works because the snippet grants
   `allow="fullscreen"`. Storage reads (`favourites.ts`, `units.page.ts`, `playground.model.ts`,
   `portal-api.ts`) are wrapped in `try`/`catch` and degrade to "not saved" when the browser denies
   storage to the frame. Favourites and playground layouts saved inside the frame are partitioned by
   the developer's site: they are not the ones saved on the portal opened top-level. A preview token
   in the frame's `src` works as it does top-level (the API does not distinguish).
5. **The snippet lives on the Publish page; the list lives on Settings.** The Publish page gets a
   card "Embed on your site", shown when the project has a live publication and `portal_url` is not
   null: a read-only code block with a copy button (the project name HTML-escaped in `title`, so a
   name with quotes pastes whole), the allowed origins as chips, and, when the list is empty, the sentence "Nobody may embed this page yet. A tenant admin adds your site's address
   under Settings → Embedding." with a link. The snippet is one element, no script:

   ```html
   <iframe src="https://acme.unitforma.com/projects/riverside"
     title="Riverside: choose your apartment"
     style="width:100%;height:80vh;border:0"
     allow="fullscreen" loading="lazy"
     referrerpolicy="strict-origin-when-cross-origin"></iframe>
   ```

   The Settings page gets a card "Embedding" (tenant admin): the list of origins with add and
   remove, validation messages from Decision 2, the cap, the sentence that the change reaches
   buyers within 5 seconds and that an open frame reloads first, and the guide text: "Paste the
   snippet from a project's Publish page into a Custom HTML block as an administrator of your
   WordPress site; list the address buyers see in their browser, with `https://`, once per host or
   with `*.`." Both guide entries (`admin/guide/guide-content.ts`) change with the screens.
6. **Costs.** A top-level visit costs nothing new: one in-memory matcher per request at the proxy.
   A framed document load costs one internal subrequest to the API and, at most once per 5 seconds
   per tenant, one `SELECT` on `tenants`. No new table, no migration, no per-request row, no job.
7. **What stays out of the frame.** The embed is anonymous. Buyer accounts (Phase 5) do not work
   inside a cross-site frame with the planned `SameSite=Lax` cookie, and Safari blocks third-party
   cookies; Phase 5 decides between "sign in opens the portal in a new tab" and a partitioned
   (`CHIPS`) cookie. Until then "Open in a new tab" is the way out of the frame.

## Options considered

### Option A: a static policy, every portal host embeddable by anyone (`frame-ancestors *`)
Pro: one Caddyfile line, no API call. Con: any site can frame any developer's chooser and overlay it
(clickjacking of the Phase 5 inquiry form, brand abuse, a competitor's page around a developer's
prices); no tenant control and no audit. Rejected: this is the control the owner asked to keep.

### Option B: Caddy asks the API per framed load and sets the header from the answer (chosen)
Pro: nginx keeps serving the SPA; the policy is one small JSON-less endpoint with a pytest; nothing
changes on the top-level path; the matcher keeps old browsers failing closed. Con: one internal
subrequest per framed document load; relies on `forward_auth` + `copy_headers` + a placeholder in a
`header` value, the last of which is unverified until A1; the Caddyfile grows a matcher and a
second header block on two host blocks in two files.

### Option C: the API serves the portal document for framed loads
Caddy routes `Sec-Fetch-Dest: iframe` document loads to an API endpoint that fetches `index.html`
from `web-portal:8080` (cached in process), sets the CSP header itself and returns the HTML; the
pattern ADR-0026 proposes for crawlers. Pro: the header is set in Python, fully testable, no Caddy
placeholder. Con: the API becomes a second server of the SPA document (a coupling to nginx and to
the build), one extra hop carrying HTML instead of one header. Kept as the fallback if A1 shows
Caddy does not expand the placeholder.

### Option D: a `/embed/` route prefix with its own Caddy block
Pro: no `Sec-Fetch-Dest` dependence; the policy applies by path. Con: the SPA must never leave the
prefix: the 34 absolute links, the header, the share links and every future page need a prefix-aware
link builder, and one missed link reloads the frame with `DENY`; a buyer who copies the frame URL gets
a header-less page. Rejected: more frontend work for a weaker guarantee than Decision 1.

### Option E: per-tenant Caddy configuration through the admin API
Pro: no per-load call. Con: a config push on every list change, Caddy's admin API reachable from the
API container, a reconciliation job when a push fails, state in two places. Rejected: the per-load
call is cheaper than operating a second source of truth.

### Option F: a JavaScript widget (`<script>` + a custom element) instead of an iframe
Pro: no frame, auto height, the developer's fonts. Con: CORS on the portal API, CSS isolation inside
a WordPress theme, the three.js chunk loaded into a foreign page, a versioned loader to keep working
on sites nobody updates; size L. Rejected now; revisit if developers refuse iframes.

### Option G: do nothing; custom domains (backlog item 7) are the way onto a developer's name
Con: a custom domain replaces the developer's site instead of sitting inside it, and item 7 needs
DNS work by each developer and three weeks of lifecycle code. Rejected as the only path; both stay.

## Trade-off analysis

| | A static `*` | B Caddy asks the API (chosen) | C API serves the document | D `/embed/` prefix | E config push | F JS widget |
|---|---|---|---|---|---|---|
| Tenant controls who frames | no | yes | yes | yes | yes | yes (CORS list) |
| Cost on a top-level visit | none | one matcher | one matcher | none | none | none |
| Cost per framed load | none | 1 subrequest + cached SELECT | 1 hop with HTML + cached SELECT | 1 subrequest | none | n API calls with CORS |
| Reload or deep link inside the frame | works | works | works | works only under the prefix | works | n/a |
| Frontend work | none | embed bar, try/catch | same | same + 34 links | same | L |
| Unverified third-party behaviour | none | placeholder in `header` value | none | none | admin API from a container | none |
| Fails closed without `Sec-Fetch-Dest` | n/a | yes (`DENY`) | yes | not needed | not needed | n/a |

## Consequences

**Easier**
- A developer pastes one element into their WordPress page and the chooser runs under their menu,
  on their URL, with no DNS change and no certificate; the tenant subdomain already exists for every
  tenant.
- The allow-list reuses the Settings page, the `tenant.settings` right and the audit row shape of
  ADR-0023: no new role, table or migration.
- Custom domains (item 7) and the embed share the host resolution; a developer may use both.

**Harder**
- Three rules to hold on every Caddyfile review: `X-Frame-Options DENY` stays on the marketing,
  app and `portals.` hosts and on every non-framed portal load; the `(security_headers)` snippet no
  longer carries it, so a new host block must add it on purpose; the `@framed` route deletes the
  client's `X-Uf-Frame-Ancestors` before `forward_auth`. ADR-0026 edits the same portal blocks; the two
  changes land in order, each leaving both Caddyfiles valid (`caddy validate` in CI, item A4).
- A framed load depends on the API being up to get its header; when the API is down the portal is
  down anyway (`/api/*` is proxied to it).
- Clickjacking moves from "nobody" to "the sites this tenant listed": a compromised developer site
  can frame the chooser and overlay it. Today no click inside the portal changes state (inquiries are
  a `mailto`); Phase 5's inquiry form inside a frame inherits this and must keep a visible
  confirmation step.
- Reviewers see the portal in two shapes (framed and top-level); screenshots for ADR-0009 UX passes
  need both.
- Storage inside the frame is partitioned by the developer's site: a buyer's favourites differ
  between the embedded chooser and the portal opened in a new tab. Written in the portal's
  "How to use" page and the admin guide.
- Search engines index the developer's page, not the framed content; ADR-0026's link previews work
  for the portal URL, which is what "Open in a new tab" and the share buttons carry.

**Revisit**
- Auto height: a `postMessage` from the frame with its document height and a listener in the
  snippet with an origin check. A second cross-origin channel; added when developers ask, as its own
  action item with its own test.
- Buyer sign-in inside the frame (Decision 7) when Phase 5 lands.
- `http://` parent sites if a pilot developer has one.
- A CDN in front of the proxy (plan A12) must keep `no-store` on `index.html` or add
  `Vary: Sec-Fetch-Dest`, or a cached `DENY` document would be served to a frame and a cached framed
  document to a top-level visit.
- A hosted WordPress plugin or a Gutenberg block that wraps the snippet, once two developers embed.

**Out of scope here:** custom-domain lifecycle (item 7, plan Phase 6); a JavaScript widget (Option
F); embedding the admin app anywhere (stays `DENY`); per-project allow-lists (the list is per
tenant, the owner's wording); SEO of the framed content.

## Action items

### Phase A: proxy and policy (backend)
- [ ] A1. **Verify on the dev stack** that `forward_auth` + `copy_headers` + `header
      Content-Security-Policy "frame-ancestors {http.request.header.X-Uf-Frame-Ancestors}"` emits the
      expanded value (curl with `Sec-Fetch-Dest: iframe` against `https://<tenant>.unitforma.localhost`).
      If the placeholder is not expanded, switch Decision 1 to Option C and note it here.
- [ ] A2. `deploy/caddy/Caddyfile.prod` and `Caddyfile.dev`: move `X-Frame-Options DENY` out of
      `(security_headers)`; add it unconditionally to every block that imports the snippet and is
      not a portal: prod `{$PLATFORM_DOMAIN}` + `www.`, `app.`, `portals.`; dev `app.` and the
      marketing placeholder. On the tenant wildcard and custom-domain blocks add `@framed` (`header
      Sec-Fetch-Dest iframe` / `frame`, `not path /api/* /auth/* /.ory/* /internal/*`) with
      `request_header -X-Uf-Frame-Ancestors`, `forward_auth` and the CSP header, and `@top` (`not
      header Sec-Fetch-Dest iframe` and `frame`) with `DENY`. Comment the three rules from
      Consequences in the file.
- [ ] A3. `api/internal.py::embed_policy` (`GET /internal/embed/policy`) and
      `publishing/embed.py::frame_ancestors(host)` with the tenant-keyed cache; `tenants/service.py`
      `get_embed_origins`, `set_embed_origins` with validation, merge and audit row; the two
      endpoints on `api/admin.py` behind `tenant.settings`; `embed_origins` added to the readiness
      payload (`publishing/service.py`, `api/admin_publishing.py`, `schemas.py`).
- [ ] A4. CI: `caddy validate --config deploy/caddy/Caddyfile.prod --adapter caddyfile` (and dev)
      with the pinned Caddy image, next to the compose config check.
- [ ] A5. Tests `backend/tests/test_embed_policy.py`: a host with a list gets the joined header; an
      empty list, an unknown host and a disabled tenant get `'none'`; `http://`, a path, a query,
      user info, `*` alone, a 21st entry and a duplicate are 422; the value is normalised (upper
      case, trailing dot, Georgian IDN host to punycode); a client-sent `X-Uf-Frame-Ancestors` is
      not echoed (Caddy check in D2); tenant B's admin cannot read or write tenant A's list (RLS); a
      project manager gets 403 on the two endpoints and sees the list in the readiness payload.

### Phase B: admin
- [ ] B1. `admin/pages/settings.page.ts`: card "Embedding" with add, remove, validation messages,
      the 5-second sentence; `api-client` methods and regenerated OpenAPI types.
- [ ] B2. `admin/pages/publish.page.ts`: card "Embed on your site" with the snippet of Decision 5,
      copy button, origin chips and the empty-list link to Settings; hidden when `portal_url` is
      null or nothing is published.
- [ ] B3. `admin/guide/guide-content.ts`: the two guide entries (Decision 5), including the
      administrator and `https://` lines and the partitioned-favourites note.

### Phase C: portal
- [ ] C1. `portal/src/app/core/embed-mode.ts`; `app.ts` and `ui/portal-header.component.ts` render
      the one-line bar with "Open in a new tab" when framed; `how-to-use.page.ts` gets the
      favourites note.
- [ ] C2. `try`/`catch` around every storage read and write in `core/favourites.ts`,
      `pages/units.page.ts`, `pages/playground.model.ts`, `core/portal-api.ts`, degrading to
      "not saved".
- [ ] C3. Specs: `embed-mode.spec.ts` (bar shown only when framed, link carries the current URL);
      `favourites.spec.ts` (a throwing `localStorage` leaves the page working).

### Phase D: docs and verification
- [ ] D1. Plan §9.1 (the embed as a fourth way onto a developer's name), §9.5 (implementation
      note), §11.2 (Settings card), §21 (sources); README paragraph and the "what the tests prove"
      line; `docs/runbooks` note on the Caddyfile rules; this ADR's status line.
- [ ] D2. **Dev stack:** a local page on `http://localhost:8081` framing
      `https://<tenant>.unitforma.localhost/projects/<slug>`: empty frame before the origin is
      listed, the chooser after, empty again within 5 seconds of removal; the full-screen button and
      the playground window from inside the frame; screenshots for both shapes.
- [ ] D3. **Owner:** paste the snippet into a real WordPress page (the pilot developer's or a test
      site of his) as an administrator; record whether WordPress kept the iframe, which block was
      used, and the phone behaviour (80vh inside a WordPress theme).
