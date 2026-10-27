# ADR-0026: Link previews and share buttons on the portal: messenger crawlers get a server-rendered shell, buyers keep the SPA, no Angular SSR

- **Status:** proposed (2026-10-27)
- **Date:** 2026-10-27
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §4 (decision table, SSR row), §9.3 (publication snapshot and assets), §9.4 (SEO and
  sharing, R2), §9.5 (implementation notes, "Not yet"), §11.3 (portal screens), ADR-0016 Decision 1
  (gallery and cover), ADR-0017 (the `plan_render` leads the unit page), ADR-0018 (live price),
  ADR-0020 Decision 8 (the playground share link), ADR-0022 (layout media), ADR-0024 (plan types)

## Context

Georgian buyers pass apartments around by messenger: a unit link goes from the buyer to the family on
WhatsApp, Telegram, Viber or Facebook Messenger, and the family decides from the preview card. This is how
a developer's portal spreads. What the code does today (read on 2026-10-27):

- **The portal is a static SPA.** `frontend/Dockerfile.portal` builds the Angular app and `nginx.conf`
  serves `index.html` for every path with `Cache-Control: no-store`. `index.html` has `<title>Portal</title>`,
  a viewport and a favicon; nothing else. The pages set `document.title` after their data loads
  (`unit.page.ts:658`, `project.page.ts:895`, `plans.page.ts:269`, `playground.page.ts:112`).
- **Messenger crawlers do not run JavaScript.** Facebook's, WhatsApp's and Telegram's fetchers read the
  HTML they get and look for `<title>`, `og:title`, `og:description`, `og:image` and `og:url`; tags
  injected by Angular's `Meta` service are never seen (sources in §21 of the plan). A unit link pasted
  into WhatsApp today shows the bare hostname and nothing else. Nothing in the portal builds a share
  message either; the only share link is the playground's arrangement link (ADR-0020 Decision 8, E1).
- **Caddy is the single entry point** (`deploy/caddy/Caddyfile.prod`): per host block, `import api_routes`
  handles `/api/*` and `/auth/*` to `api:8000`, then a catch-all `handle { reverse_proxy web-portal:8080 }`.
  Two blocks serve portals, the wildcard `*.{$PLATFORM_DOMAIN}` and the on-demand `https://` block for
  custom domains; `Caddyfile.dev` mirrors them for `*.unitforma.localhost`. `handle` blocks are evaluated
  in the order written, so a matcher placed before the catch-all can send a request elsewhere.
- **Everything a preview needs is already public JSON.** `GET /api/v1/portal/projects/{slug}` returns
  the document (`project.name`, `description`, `branding`, `gallery[]` whose first item is the cover,
  `buildings[]` with `code`, `name`, `construction_status`, `layouts[]` with `media[]`);
  `GET .../units/{code}` returns the unit view with `code`, `unit_type`, `rooms`, `area`, `floor_level`,
  `building_code`, `availability`, the live `price` (ADR-0018) and `media[]` (`url`, `mime`, `kind`,
  own items first, then the layout's, ADR-0022). Host and live-publication lookups are cached 5 s per
  process, the document is an LRU in memory (`publishing/portal.py` `load_doc`), the unit is one
  `published_units` row. The hero rule lives in `unit.page.ts:598`: the first `plan_render` image, else
  the first image.
- **Assets are a redirect.** `GET .../assets/{name}` answers 302 to a presigned URL on `s3.<domain>`
  valid 1 h. Renders are WebP re-encoded to ≤ 2 400 px (§9.5); a 2 400 px WebP of a render is typically
  several hundred kB. Whether every messenger follows the redirect, accepts WebP and what file size it
  still shows as a large card is not documented by the vendors (third-party guides say WhatsApp drops
  the large card above 300 kB or 600 kB, and that Facebook's WebP support is "spotty"; marked unverified
  in §21).
- **Preview links carry a secret.** Staff preview a publication through `?preview=<HMAC token, 1 h>`
  (§9.3). A staff member who pastes such a link into a messenger hands the token to that messenger's
  crawler.
- **The plan still says SSR.** §4 ("`@angular/ssr` not in MVP; added in R2 for SEO"), §9.4
  ("Prerender/SSR for project and unit pages"), §9.5 "Not yet" and Phase 10 ("SSR/SEO + analytics") all
  state that the portal will gain server-side rendering. The portal is per-host branded, every page is
  lazy, three.js and `localStorage` (favourites, the playground) run on the browser only, and the price
  is live; SSR would be a Node runtime per portal container, server-side HTTP calls to the API on every
  page view and browser-only guards in every page, to put four meta tags in front of a crawler.

## Decision

1. **The portal stays a static SPA; Angular SSR is not adopted.** Buyers keep nginx and `index.html`.
   Machine readers that do not run JavaScript get a small server-rendered HTML shell from the API. This
   reverses the plan's SSR row (§4), §9.4, §9.5 "Not yet" and Phase 10; the same shell is the base on
   which search-engine content and a `sitemap.xml` are added later (Revisit), still without SSR.
2. **Caddy routes link-preview crawlers to the API.** A snippet `(link_previews)` in `Caddyfile.prod`
   and `Caddyfile.dev`, imported in the wildcard block, the on-demand `https://` block and the dev portal
   block *before* the catch-all `handle`:
   ```
   @preview {
       method GET HEAD
       path / /projects/*
       header_regexp ua User-Agent (?i)(WhatsApp|TelegramBot|facebookexternalhit|Facebot|Viber|Twitterbot|LinkedInBot|Slackbot|Discordbot|SkypeUriPreview)
   }
   handle @preview {
       rate_limit {
           zone preview_by_ip {
               key {remote_host}
               events 60
               window 1m
           }
       }
       rewrite * /api/v1/portal/share{uri}
       reverse_proxy api:8000
   }
   ```
   `HEAD` is matched because some fetchers probe with it before the `GET`.
   The list carries the date and the source of each token in a comment. Search engines (`Googlebot`,
   `Bingbot`) are **not** in the list: they render JavaScript, a thin shell would index worse than the
   SPA, and Google calls serving crawlers different content "dynamic rendering", a workaround it no
   longer recommends (§21). Indexing is R2 (Revisit). Anyone can spoof the user agent; they get the same
   facts the JSON API already gives, at the same cost, behind the rate limit.
3. **One endpoint renders the shell.** `GET /api/v1/portal/share/{path:path}` in `api/portal.py` calls
   `publishing/share.py` (`describe(site, path) -> Shell`, `html(shell) -> str`), the only two homes of
   the preview texts. The path is the portal route, query string ignored:

   | Path | Title | Description | Image |
   |---|---|---|---|
   | `/` | branding display name or tenant name | the live projects' names | first live project's cover |
   | `/projects/{slug}` | project name — site name | `project.description` (first 300 characters), else the stats ("N units, from X") | cover (first gallery item) |
   | `/projects/{slug}/plans`, `/units` | "Plan types — project", "Units — project" | the stats | cover |
   | `/projects/{slug}/units/{code}` (and `/playground`) | `{code} — project name` | unit type, rooms, area (m²), floor, building, availability, live price and currency, `price_note`; every absent fact is left out, never 0 | the unit's hero (Decision 5) |
   | `/projects/{slug}/buildings/{code}` | `Building {code} — project name` | building name, construction status, completion, "N of M units available" | the building's `share_image`, else the cover |
   | any other path | the `/` shell | | |

   A hidden unit (reachable by direct link, §9.5) renders like a listed one. An unknown slug or code
   answers 404 with the `/` shell as body; a host without a live publication answers the "coming soon"
   shell (tenant name, no image). **The shell never serves a preview publication:** `?preview=` and
   `X-Unitforma-Preview` are ignored and a project with only a preview answers "coming soon", so a token
   pasted into a messenger shows nothing that is not public. Every tenant text goes through
   `html.escape`. The body holds the title, the description and a link to the same URL ("Open in the
   portal") for a human who arrives with a spoofed user agent. Headers: `Content-Type: text/html;
   charset=utf-8`, `Cache-Control: public, max-age=300`, `Vary: Host, X-Forwarded-Host`.
4. **The tags.** `<title>`, `<meta name="description">`, `og:type` `website`, `og:site_name`,
   `og:title`, `og:description`, `og:url` (`https://{requesting host}{path}` without query),
   `og:image` (absolute, Decision 5) with `og:image:width`, `og:image:height`, `og:image:type`,
   `twitter:card` `summary_large_image`. No `og:locale`: the texts are English until the portal is localised (Revisit). `og:url` names the requesting host; the
   §9.4 rule "custom domain preferred when active" waits for the custom-domain lifecycle (E8, not
   implemented, §9.5).
5. **Share images are built at publish time and served directly.** `publishing/snapshot.py` writes one
   JPEG per *source* image, 1 200 × 630 px, centre-cropped to cover, quality lowered from 85 until the
   file is ≤ 300 kB (the conservative third-party WhatsApp figure, Action item D2 measures the real one),
   as `share-{source id hex}.jpg` in the publication's assets. Sources: the cover (first gallery sheet),
   each listed unit's hero by the rule of `unit.page.ts:598` (first `plan_render` image, else the first
   image, own media before the layout's) and each layout's first image; units that share a layout render
   share one file, so a project with six plan types makes about eight files, not one per unit. The
   documents carry the asset name: `project.share_image`, `buildings[].share_image` (the cover),
   `layouts[].share_image`, and `share_image` on each unit document; a unit without any image inherits the
   cover. `schema` stays 1 (additive); documents published before this release have no key and the shell
   renders without an image until the next publication. `GET /api/v1/portal/projects/{slug}/share-image/{name}`
   streams the bytes (`image/jpeg`, `Cache-Control: public, max-age=86400`) instead of the 302 the other
   assets use, so the preview does not depend on a crawler following a redirect to a signed URL that
   expires in 1 h; the bytes are ≤ 300 kB by construction and crawlers fetch once and cache.
6. **Share buttons on the unit page and the building page.** A `ui/share-buttons.ts` component in the
   unit page's sticky action bar and the building page's header: **WhatsApp**
   (`https://wa.me/?text=<text>%0A<url>`), **Telegram** (`https://t.me/share/url?url=<url>&text=<text>`)
   and **Copy link** (the Clipboard API writes the URL alone, the button shows "Copied" for 2 s; the
   preview carries the text, so a link pasted anywhere is enough). On a device that offers
   `navigator.share` a **Share…** button comes first and opens the system sheet with title, text and URL;
   this is the one way to reach Viber, Messenger, SMS and Facebook from a phone with the text filled in
   (Facebook's web sharer ignores a text parameter). The shared URL is the canonical page URL
   (`/projects/{slug}/units/{code}`; the building page keeps `?floor=` when a floor is selected) with
   any preview token stripped. The text comes from a pure `pages/share.model.ts`
   (`unitShareText(unit, doc)`, `buildingShareText(building, doc)`), the same facts in the same order as
   Decision 3's description, in the portal's language (English until the portal is localised).
7. **Cost.** A crawler request costs what `GET /projects/{slug}` plus `GET .../units/{code}` cost today
   (cached host, cached document, one indexed row); the response is under 4 kB; no table, no job, no
   per-request write. A publication grows by the share images (≈ 8 × ≤ 300 kB on a typical project),
   built in the same synchronous publish as the other assets (§9.5).

## Options considered

### Option A: do nothing, or set the tags from Angular at runtime
Pro: nothing to build. Con: messenger crawlers do not execute JavaScript, so Angular's `Meta` service
changes nothing for them; a pasted link stays a bare hostname.

### Option B: Angular SSR (`@angular/ssr`) with per-route render modes, as the plan foresaw
Pro: the real page for every reader, hydration, the base for full SEO. Con: a Node server replaces nginx
in the portal image; every page view (not only crawlers) renders on the server with HTTP calls to the
API; three.js, WebGL detection, `localStorage` (favourites, playground), `location.host` need guards in
every page; a second runtime to size, watch and upgrade; weeks of work to serve four meta tags.

### Option C: prerender static HTML per route at publish time
Pro: no runtime, plain files. Con: one file per unit per publication; the description freezes the price
although it is live (ADR-0018); nginx serves one tree for every host and custom domain; crawlers still
need routing to those files, or humans get the static page.

### Option D: Caddy routes crawler user agents to an API shell (chosen)
Pro: no new container or runtime; one endpoint, one service, reads the data the portal API already
serves; the price in the preview is live; the same shell grows into the SEO base. Con: a user-agent
allow-list to maintain; the hero rule and the share sentence exist in the backend and the portal; a
spoofed agent sees the shell (same facts as the JSON API).

### Option E: the same routing in the portal's nginx
Pro: Caddy untouched. Con: nginx in `web-portal` has no upstream to `api`, the rule would live in the
image (and `ng serve` has none); Caddy is already the single entry point with the `api` upstream in
every portal block.

### Image: the existing 302 asset versus a share JPEG served directly
The 302 reuses what exists but points crawlers at a 1 h presigned URL on another host, as a WebP of
unverified size; whether each messenger follows it and shows a large card is unverified. A 1 200 × 630
JPEG ≤ 300 kB served by the API is the documented Facebook shape, the conservative WhatsApp size, and
has no redirect to doubt. Chosen: the JPEG.

## Trade-off analysis

| | A nothing | B Angular SSR | C prerender files | D Caddy → API shell | E nginx → API shell |
|---|---|---|---|---|---|
| Preview in messengers | no | yes | yes | yes | yes |
| Live price in the preview | — | yes | no | yes | yes |
| New runtime or container | none | Node per portal | none | none | none |
| Cost per buyer page view | unchanged | server render + API calls | unchanged | unchanged | unchanged |
| Cost per crawler request | — | render | file read | 2 cached reads + 1 row | same |
| Cost per publication | — | — | N unit files | ≈ 8 JPEGs | same |
| Rule to maintain | — | browser guards in every page | file tree per host | UA list in one snippet | UA list in the image |
| Effort | 0 | L | M | M | M |

## Consequences

**Easier:** a unit pasted into WhatsApp, Telegram or Facebook shows its render, code, area, floor and live
price; a sales agent sends a unit from the phone in two taps; a buyer's family sees the apartment before
opening anything; search-engine content and a sitemap can be added on the shell later without a new
runtime.

**Harder:** the user-agent list is an allow-list: a messenger not on it gets no preview until a line is
added (the Caddyfile comment names the date and source of each token, Action item D2 records what was
seen on the real host). Two rules now live in two homes and reviewers keep them in step on purpose: the
hero rule (`unit.page.ts` and `publishing/share.py`) and the share sentence (`share.model.ts` and
`publishing/share.py`). Share images are structure: a changed render reaches the preview with the next
publication, and documents from before this release show no image until republished. Messengers cache
previews (Facebook at least 24 h, refreshed with its Sharing Debugger; Telegram via `@WebpageBot`;
WhatsApp per device, unverified), so a changed render shows late in a chat that already saw the link.
The crawler path is one more public, unauthenticated door; it serves published data only, ignores
preview tokens, escapes every text and sits behind a 60/min/IP limit.

**Revisit:** search-engine content in the shell (body text per page) and `sitemap.xml` per host, still
without SSR (R2, plan §9.4); `og:url` and a canonical on the custom domain once E8 lands; a share image
per building from its facade drawing (ADR-0014 bands) instead of the cover; Georgian share text when the
portal is localised; a share button on the plan-type card (ADR-0024); measuring the real WhatsApp size
limit and dropping the 300 kB cap if it is higher.

**Out of scope here:** indexing by search engines and a sitemap (R2); share buttons in the admin app;
QR codes for print; counting shares (analytics, R2); an inquiry started from a shared link (Phase 5);
localisation of the portal.

## Action items

### Phase A: backend

- [ ] A1 `publishing/share_image.py`: `share_jpeg(bytes) -> bytes` (Pillow: 1 200 × 630, centre-crop
      cover, quality from 85 down until ≤ 300 kB). `publishing/snapshot.py`: one `share-{source}.jpg`
      per source (cover, each listed unit's hero, each layout's first image), `share_image` on
      `project`, `buildings[]`, `layouts[]` and each unit document. Tests in `tests/test_share_preview.py`:
      dimensions and size of the JPEG; two units of one layout share one file; a unit without media
      inherits the cover; a project without a gallery publishes without `share_image`.
- [ ] A2 `publishing/share.py`: path parsing (the table of Decision 3), `describe`, `html` with
      `html.escape`; `api/portal.py`: `GET /api/v1/portal/share/{path:path}` (text/html, max-age 300,
      preview ignored) and `GET /api/v1/portal/projects/{slug}/share-image/{name}` (streams the JPEG,
      only names in the served publication). Tests: the unit, building, project, plans, units-list and
      home shells; a hidden unit; unknown unit → 404 with the home shell; a host with only a preview →
      coming soon even with a valid token; `<script>` in a project name arrives escaped; an unknown
      path → the home shell; `openapi.json` regenerated.

### Phase B: proxy

- [ ] B1 `deploy/caddy/Caddyfile.prod` and `Caddyfile.dev`: the `(link_previews)` snippet of Decision 2
      with the dated, sourced user-agent list, imported before the portal `handle` in the wildcard, the
      on-demand and the dev portal blocks; `rate_limit` zone `preview_by_ip`. Validate with
      `docker compose -f compose.yaml -f compose.prod.yaml --env-file .env.example config` and
      `caddy validate --config Caddyfile.prod --adapter caddyfile` in the proxy image (plan §19).
- [ ] B2 On the dev stack: `curl -k -A "WhatsApp/2.23.20.0" https://<tenant>.unitforma.localhost/projects/<slug>/units/<code>`
      returns the shell with the four `og:` tags and the image URL answers `image/jpeg`; the same URL
      with a browser user agent returns the SPA `index.html`; `/api/v1/portal/share/...` called with
      `?preview=<valid token>` returns the live shell.

### Phase C: portal

- [ ] C1 `pages/share.model.ts` + `share.model.spec.ts`: `unitShareText`, `buildingShareText`,
      `canonicalUrl` (strips `preview`), `whatsappHref`, `telegramHref`; the spec checks the sentence
      with every fact, with facts missing, and the URL encoding of Georgian text.
- [ ] C2 `ui/share-buttons.ts`: Share… (only when `navigator.share` exists), WhatsApp, Telegram, Copy
      link with the "Copied" state and a select-to-copy fallback when the Clipboard API is unavailable;
      placed in `unit.page.ts` (sticky action bar) and `building.page.ts` (header); icons from the
      portal's icon set; `guide/portal-guide.ts` gets a "Share a unit" entry (shown by
      `how-to-use.page.ts`).
- [ ] C3 Gate: `npx ng lint && npx ng test --watch=false && npx ng build portal` within the 300 kB
      initial budget (§11.3).

### Phase D: docs and verification on the real host

- [ ] D1 Plan §11.3 (share buttons on the unit and building pages) and §9.4 marked implemented; README
      status paragraph; `docs/BACKLOG.md` rows removed as items are ticked.
      *Done with this ADR on 2026-10-27:* the plan's SSR lines (§4 row, §9.4, §9.5 "Not yet", the R2
      scope line, Phase 10) rewritten to this decision, §21 sources for the user agents and image limits
      with what is unverified.
- [ ] D2 On the production host, paste one unit link into WhatsApp, Telegram, Facebook (Sharing
      Debugger, "Scrape again"), Viber and Messenger; record per messenger whether title, description
      and the large image showed, the user agent each one sent (from the Caddy access log) and, for
      WhatsApp, the largest JPEG that still shows as a large card; write the result here as
      "*Found while implementing*" and in §21, and adjust the list and the 300 kB cap.
