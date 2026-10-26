# ADR-0020: Renovation playground: a cleared plan, a furniture and finish catalogue, saved layouts

- **Status:** accepted for Phase A and E1 (2026-10-26, the owner's "next" on the recommendations; implemented 2026-10-26); the picks for the clearing variant (1A to 1D), the catalogue table (2B), the board code length and who opens a board are still awaited
- **Date:** 2026-10-26
- **Deciders:** David Sakhelashvili (platform owner): how the drawn furniture is cleared (cost per layout), whether tenants manage the catalogue, whether a buyer may spend an AI image on their own arrangement, whether saving waits for buyer accounts; for the shared board: the code length (4 symbols or 6 digits) and who may open a board (staff only, or any portal visitor)
- **Plan reference:** §2.2 (finishing catalogue, R2), §2.3 (self-redesign, R3), §7.1 (unit page), §7.2 (favourites), §7.4 (proposals), §10.1 (inquiry payloads), §11.3 (portal budget), §12.3 (`renders.generate`), §3.3 (proxy and rate limits), §4.3 (Postgres queue), ADR-0017 (furniture ruler, generated plan renders), ADR-0016 Decision 4 (media shared by layout code)

## Context

The owner's idea of 2026-10-26: "make the playground for the room renovation: you pick the apartment,
clear all furniture and make it as you wish", with a catalogue of pieces to choose from. What the code
offers today:

- **The unit plan is a picture.** The portal unit page shows a per-unit WEBP crop of the sheet raster
  (`publishing/snapshot.py`, `_plan_asset` with a crop, long edge 2 400 px) with the unit outline as a
  normalised ring. Whatever the architect drew inside the outline is in the picture: furniture, fixtures,
  dimensions, room labels. Nothing in the data model knows where a bed or a sofa is drawn, so nothing
  can hide it.
- **The furniture ruler overlays, it does not replace.** ADR-0017 E6 (`portal/pages/unit.page.ts`,
  `FURNITURE`): seven rectangles hard-coded in metres (two beds, sofa, table, wardrobe, desk, bathtub),
  one instance per entry (the chip toggles it), scale from the outline and the largest stated area
  (`pxPerM`), drag in the viewer's move mode, "Rotate" turns the last piece only, "Clear" removes the
  overlay. Nothing is stored; a reload empties the plan. Rooms inside the unit are not known, so a piece
  can sit on a wall.
- **Two kinds of source.** A PDF plan (every permit import from tas.ge, ADR-0007) is raster only. A DXF
  plan keeps the layer name on every stored entity (`documents/cad_dxf.py`, `"layer"` on each fill and
  segment, counts in `hints.layers`) and its raster is drawn by Pillow from those entities
  (ADR-0006 Decision 2, `rasterize_layout`), so a DXF sheet could be redrawn without chosen layers. No
  real DXF has been accepted yet (ADR-0006 B8 open, backlog #2).
- **An image-editing pipeline exists.** `renders.generate` (ADR-0017 Decision 3 and 4) sends the unit's
  crop to Gemini with a fixed prompt, stores the answer as private `unit_media(kind = plan_render,
  is_ai_generated = true)`, a staff member approves or rejects it, an approved image serves every unit with
  the same layout code. Cost 0.0336 USD per image (plan §21), at most `UF_AI_IMAGE_DAILY_LIMIT` = 40 per
  tenant per day. Only staff can request one; the kinds are a check constraint (migration `0005`:
  `plan_render | interior_render | exterior_render | photo | video | document`).
- **Finishes.** A unit states one wall colour (`units.attributes.wall_colour`, ADR-0017 E5) shown with a
  swatch. The plan's finishing-material catalogue with quotation requests is R2 Phase 11 (§2.2, "view-only,
  platform supplied"), not started.
- **Nothing buyer-side persists but favourites.** `core/favourites.ts` keeps them in localStorage per host
  and project; buyer accounts, inquiries and the `redesign_request` inquiry type are Phase 5 (backlog #6).
- **Walls are out of reach.** Moving partitions is plan §2.3 (R3) and needs the structural-tag editor of
  §7.4 (R3 self-redesign); the mapping has no walls, doors or rooms, only outlines.
- **Budget.** The portal's initial bundle is capped at 300 kB gzipped (§11.3); the unit page is its own
  lazy route (`app.routes.ts`, `loadComponent`), so the editor adds to that chunk, not to the initial bundle.

The owner added two sharing cases the same day: a sales agent on a call with a client says a four-symbol
code, the client joins the same session and both see every change live; and a buyer wants to show the
arrangement to their spouse. What exists for that:

- **No live channel anywhere.** The API has no streaming response and no WebSocket; the portal only
  fetches snapshots. Procrastinate (`jobs/app.py`) already uses Postgres `LISTEN/NOTIFY` on this database,
  so the capability is proven, but no API code listens.
- **Production runs two API replicas** (`compose.prod.yaml`, `replicas: 2`, Caddy `lb_policy round_robin`),
  so two viewers of one board may sit on different processes.
- **Rate limits live in Caddy.** `Caddyfile.prod` already runs the `rate_limit` plugin on `/auth/*` (60
  events per minute per `remote_host`); the API itself has none. uvicorn is started with
  `proxy_headers=True` (`cli.py`), so the client address survives the proxy.
- **No identity on the portal host.** Staff are authenticated on the admin host only; buyers have no
  account until Phase 5. The retention sweep that would delete expired boards is a stub (backlog #5).

So the idea splits into five decisions: how the drawn furniture disappears, where the catalogue lives,
whether and where a buyer's arrangement is saved, what a buyer may ask the image model for, and how an
arrangement is shared with another person, live or by a link.

## Options considered

### 1. Clearing the drawn furniture

**Option 1A: a generated "empty plan" through the existing render pipeline (recommended).**
A second render variant: the same crop, the prompt "remove every piece of furniture and every fixture;
keep walls, doors, windows, dimensions and room labels exactly as drawn; same framing, same size, white
background". The answer is stored as `unit_media(kind = plan_blank, is_ai_generated = true)`, reviewed by
staff like a `plan_render`, shared by layout code, and the unit page gets an "Empty the apartment" switch
that shows the blank image under the pieces. Pros: works for PDF and DXF alike; one image per layout
code (a 200-unit building with 12 layouts costs 0.40 USD); reuses the table, the review, the label, the
cap. Cons: the model may shift or rescale the drawing, so the reviewer must check the outline fit (B3 adds
the outline overlay to the review dialog; today the review shows the image alone); a misread wall is invisible to a buyer; it stays a
picture, rooms are still unknown.

**Option 1B: redraw a DXF sheet without its furniture layers.** A per-sheet list of hidden layer names,
chosen by the reviewer from `hints.layers`, and a second raster without them; the publishing crop takes
that raster for the blank view. Pros: exact, free, deterministic. Cons: DXF only, which excludes every
permit import; layer names are the architect's habit ("A-FURN", "ბ-ავეჯი", "0"), so a reviewer picks them
per document; nothing until ADR-0006 B8 is accepted on a real file. Worth doing after 1A when DXF sources
arrive; the switch then prefers the exact raster over the generated one.

**Option 1C: fade the drawing under the pieces (interim, no backend).** A toggle that paints the unit
interior with the page background at 85 % opacity so the drawn furniture recedes while the outline and the
dragged pieces stay crisp. Pros: an afternoon, no cost, ships with the editor. Cons: inner walls fade with
the furniture; it is not "clear". Kept as the fallback shown when no blank image is approved.

**Option 1D: detect furniture in the raster and inpaint locally (OpenCV or a segmentation model in the
heavy worker).** Pros: no outbound call. Cons: weeks of tuning on drawings of varying style, a new model
dependency in the image, and ADR-0017 Option B already rejected procedural plan understanding for the same
reason.

### 2. The catalogue

**Option 2A: a code list, extended (phase 1).** The seven pieces become a list grouped by room
(bedroom, living, kitchen, bathroom, hall, balcony) with 25 to 35 entries, each a name, a size in metres,
a shape (rectangle, round, L-shape as a polygon in metres), an icon and a category. Pros: no table, no
screen, no seed data (the list is product code, like the RAL table); the same list on every tenant. Cons:
a developer cannot add its own kitchen supplier's sizes or prices.

**Option 2B: a tenant-managed catalogue with the code list as default (recommended as phase 3).**
Table `catalogue_items` (`id`, `tenant_id`, `project_id` nullable, `category`, `name`, `width_m`,
`depth_m`, `shape`, `icon`, `price` and `currency` nullable, `url` nullable, `sort_order`, `is_public`),
RLS like every tenant table, admin screen "Catalogue" under the project menu, published items carried in
the snapshot and merged with the code list on the unit page. Pros: a developer lists the finishes and
packages it actually sells, with prices, which is what turns the playground into a sales tool (§2.2
quotation requests). Cons: a table, a screen, a snapshot field; the plan's "platform supplied" catalogue
would become rows the platform seeds, which the owner's standing rule forbids, so the platform's part
stays in code and the tenant's part in the table.

**Option 2C: an external furniture catalogue (a retailer's API).** Not investigated here: a retailer's
licence terms would have to be read first, and sizes and prices would be someone else's data on the
developer's portal.

### 3. Saving the arrangement

**Option 3A: localStorage per host, project and unit (phase 1).** Like favourites: the arrangement
survives a reload on the same browser, nothing reaches the server. Pros: free, no account, no personal
data. Cons: lost on another device; the developer never sees it.

**Option 3B: account-bound layouts and a `redesign_request` inquiry carrying the arrangement
(after Phase 5).** The arrangement (pieces in metres relative to the unit frame, rotation, chosen wall
colour and catalogue items) is the typed payload of the planned `redesign_request` inquiry (plan §10.1
table, `inquiries.payload`), merged into the buyer's account on login like favourites, and shown to the
sales staff on the lead as the same overlay. Pros: this is the lead: a buyer who furnished the apartment
is further along than one who favourited it. Cons: waits for Phase 5 (backlog #6); the payload is a
stored JSON shape and needs a format marker and a backward-reading test ([[my-release]]).

### 4. A buyer asks the image model for a picture of their arrangement

**Option 4A: not in this ADR (recommended).** Staff-only requests stay; the buyer gets the blank plan
and the overlay. Pros: no anonymous outbound spend, ADR-0017's review gate holds. Cons: the "wow" image
is missing.

**Option 4B: after Phase 5, behind a login, with a per-buyer cap and the "generated" label, unreviewed.**
Pros: the image a buyer remembers. Cons: a money path open to every registered e-mail (cap and daily
tenant limit needed), the model may draw a wall that is not there and nobody reviewed it; it needs its own
ADR item with the cost budget written down.

### 5. Sharing an arrangement with another person

**Option 5A: a share link that carries the arrangement (recommended for the spouse case).** "Share"
puts the Decision 5 shape, compressed and base64url-encoded, into the URL fragment
(`/projects/<slug>/units/<code>#l=...`); the receiver opens it, the page restores the pieces and the wall
colour, each side then edits its own copy. 30 pieces are about 1.5 kB, which every browser and messenger
carries. Pros: no server, no row, no identity, the fragment never leaves the browser, works through
WhatsApp and SMS, and phase 4 (3B) later makes the same shape account-bound. Cons: not live; two people
editing at once do not see each other.

**Option 5B: a live board joined by a short code (recommended for the agent case).** Table `boards`
(`id`, `tenant_id`, `project_id`, `unit_id`, `code` unique per tenant, `state jsonb` in the Decision 5
shape, `version`, `created_by` nullable, `created_at`, `updated_at`, `expires_at`, `ended_at`), RLS like
every tenant table. The state is small, so the whole state travels with a version number: `PUT
/portal/boards/{code}` with `If-Match: <version>` writes it and `NOTIFY`s; a stale write gets 409 and the
client reapplies its move on the latest state (no CRDT, no operational transform). Delivery is a
Server-Sent Events stream `GET /portal/boards/{code}/events` that sends `event: state` with the full
state and `id: <version>`, a comment every 15 s as keepalive, and resumes from `Last-Event-ID`. Fan-out
between the two API replicas is Postgres `LISTEN/NOTIFY` on one dedicated asyncpg connection per API
process (the SQLAlchemy pool cannot hold a `LISTEN`); the payload carries only the board id and the
version, the subscribers are keyed by board id (codes are unique per tenant, not globally, so two tenants
may share `AB7K`), and the stream handler re-reads the row inside `tenant_session` for the host's tenant
so RLS stays the gate. Pros: one held connection per viewer and one small UPDATE per committed move; the same shape as the
browser save and the inquiry; no new container. Cons: the first streaming endpoint, the first held
connection and the first anonymous write path in the API, each with a bound to write down.

**Option 5C: a WebSocket instead of SSE plus PUT.** Pros: bidirectional. Cons: buys nothing because the
client already sends by PUT; the same replica fan-out problem; one more protocol through Caddy. Loses.

**Option 5D: polling every 2 s.** Pros: no new infrastructure. Cons: a SELECT per viewer every 2 s on an
anonymous path is exactly what [[my-high-load]] forbids; a 4-second-old move is not "live". Rejected.

**Option 5E: a third-party realtime service (Liveblocks, PartyKit, Firebase).** Rejected: the
arrangement and the viewers' addresses leave the deployment; an outbound dependency on the request path.

**Sub-choice: the code.** 4 symbols from an alphabet without look-alikes (no 0/O, 1/I/L; 31 symbols)
give about 920 000 codes; 6 digits give 1 000 000 and are easier to say on a phone in Georgian or
English. Either is enumerable in minutes without a limit, so the join path gets a Caddy `rate_limit`
zone (10 attempts per minute per address) and an unknown code answers 404 at constant cost. What a
guesser gains: the furniture arrangement of a published unit (public already) and the ability to move
pieces on a live board for its remaining minutes; no name, no e-mail, no price that is not public.

**Sub-choice: who opens a board.** Staff only, from the admin unit page (authenticated, audited, the
existing `sales` resource) and then the portal with the code; the client joins anonymously. Or any
portal visitor, which needs a creation cap per address and per tenant per day on top. Staff-only now; the
spouse case is served by 5A; anonymous creation revisited after Phase 5 when a buyer has a login.

## Trade-off analysis (sharing)

| Axis | 5A link | 5B SSE + PUT | 5C WebSocket | 5D polling | 5E third party |
|---|---|---|---|---|---|
| Live for two people | no | yes | yes | 2 s late | yes |
| Server state | none | one row per board | one row per board | one row per board | theirs |
| Per viewer while open | nothing | one held connection | one held connection | one SELECT per 2 s | outbound |
| Works across two API replicas | n/a | NOTIFY listener | NOTIFY listener | yes | yes |
| Anonymous door | none | join by code, rate-limited | same | same | same |
| Size | S | M | M | S | S |

## Trade-off analysis (clearing the drawn furniture)

| Axis | 1A generated blank | 1B DXF layers off | 1C fade | 1D local inpainting |
|---|---|---|---|---|
| Works on PDF plans (every permit import) | yes | no | yes | yes |
| Exact walls kept | mostly; reviewer checks | yes | yes, faded | depends on tuning |
| Cost | 0.0336 USD per layout code, once | none | none | worker CPU, weeks of work |
| Staff review needed | yes (as today) | pick layers once per sheet | no | yes |
| Size | M | M, after ADR-0006 B8 | S | L |
| Rooms known afterwards | no | no | no | no |

## Recommendation

Phase 1 ships the editor without a backend (2A, 3A, 1C). Phase 2 adds the generated blank plan (1A).
Phase 3 the tenant catalogue (2B). Phase 4 waits for Phase 5 and binds the arrangement to the lead (3B).
Phase E adds the share link (5A, with phase A) and the live board (5B, staff-opened, after phase A).
Buyer-triggered renders (4B) are not decided here. Walls stay R3.

## Decision

Proposed; the numbered points become the decision on the owner's pick.

1. **The playground is the unit page's plan card in an "edit" state**, not a new page: the same plan
   viewer in move mode, the outline locked, a side panel with the catalogue grouped by room, the wall
   colour, "Empty the apartment", "Clear my pieces", "Save". It stays inside the unit page's lazy chunk; the
   number to watch is that chunk's size, written in the README, not the initial bundle (§11.3).
   *Changed on 2026-10-26 at the owner's request ("open the specific apartment in a new window with the
   corresponding tools"):* the playground is its own page, `/projects/<slug>/units/<code>/playground`,
   its own lazy chunk, opened in a new window by the unit page's "Design this apartment" button; the plan
   fills the window beside a tool panel (catalogue by room, the placed pieces as rows with turn, flip and
   remove, finish, share); the unit page keeps its plan in view mode and shows how many pieces are saved.
   Share links open the playground page. *Same day, second correction ("open only the specific
   apartment without others"):* the viewer's new `clip` input covers everything outside the unit outline
   with the page colour and `focusPadding` 1.15 fits the view on the outline alone; the unit's code label
   is left off the plan there, the header names it. No backend crop: the floor sheet still loads, the
   neighbours are masked in the browser; the fit's zoom cap is lifted when a clip is set, so a 42 m²
   apartment fills a 1 000 px canvas at about 5× the published crop (long edge 2 400 px) and looks
   soft. *Revisit:* a per-unit crop at the sheet's native resolution in the snapshot (S, backend) when
   the owner wants it sharper.
2. **Pieces are many, selectable and shaped.** Any number of instances per catalogue entry; a click
   selects a piece; the selected piece rotates by 90°, flips and is deleted; shapes are polygons in metres
   (rectangle, round, L); a piece shows its name and size on the plan. Scale is `pxPerM` as today; when the
   unit has no stated area the editor says so and stays off.
3. **The drawn furniture disappears through an approved `plan_blank` image** (Option 1A): migration
   `0017` widens the `unit_media.kind` check to `plan_blank`; `RenderRequest.variant = furnished | blank`
   (default `furnished`) picks the prompt; `unit_renders` gets a `variant` column; the admin render review
   overlays the unit outline on the result so a shifted drawing is rejected; the portal switch shows the
   blank image only when one is approved for the unit or its layout code, otherwise the fade (1C).
4. **The catalogue is code first, tenant rows second.** The code list carries the platform pieces by
   room; `catalogue_items` (Option 2B) adds the tenant's own with optional prices and links; nothing is
   seeded; the snapshot carries public items; the unit page merges both.
5. **The arrangement is saved in the browser now and on the lead later.** localStorage key
   `uf:layout:<host>:<project>:<unit>` holding `{v: 1, wall_colour, pieces: [{item, cx_m, cy_m, rot,
   flip}]}` in metres from the outline's bounding box corner, so it survives a re-published plan crop; the
   same shape is the `redesign_request` payload in phase 4, read back by a test with a stored `v: 1`
   example.
6. **No buyer-triggered image generation in this ADR**; a later item under ADR-0017 or a new ADR writes
   its cap and label first.
7. **Nothing synthetic**: no demo arrangement, no platform rows in `catalogue_items`; the portal guide
   entry and the README change with each phase.
8. **Sharing by link carries the arrangement in the URL fragment** (Option 5A): `#l=<base64url of the
   Decision 5 shape, no compression: 30 pieces are about 1.5 kB>`, restored on load, never sent to the server; "Share" copies the link and
   offers the native share sheet on phones.
9. **A live board is a row and a stream** (Option 5B): migration `0019` creates `boards`; `PUT
   /portal/boards/{code}` with `If-Match` (409 on a stale version, 413 over 4 kB of state, 404 for an
   unknown or ended code); `GET /portal/boards/{code}/events` streams the state as SSE with a keepalive
   comment every 15 s; the API process holds one `LISTEN` connection and at most
   `UF_BOARD_MAX_STREAMS` (default 200) open streams, 503 beyond; a move is sent on drop, never on
   pointer move, so the other side sees a piece land, not the drag; no log line per move. The NOTIFY
   payload is the board id and version only; subscribers are keyed by board id; every read goes through
   `tenant_session` of the host's tenant. A board ends 30 minutes after its last change, 24 hours after
   creation at the latest, or when its creator ends it; the retention sweep deletes ended rows after 7
   days. Presence is a count ("2 on the board"); no names, no cursors.
10. **Staff open boards, anyone with the code joins** (sub-choices of section 5): `POST
    /units/{id}/boards` on the admin host (the `sales` resource, audit row) answers the code; the portal
    "Join a board" field on every page and `/join/<code>` resolve the code to its unit on the current host
    and open the unit page in board mode. A board is opened only for a published, listed unit (409 otherwise), or the
    client would join and see nothing. Two Caddy `rate_limit` zones, both per address: 10 per minute on
    the code lookup `GET /api/portal/boards/join/{code}` (the guessing path), 120 per minute on the `PUT`
    and the `/events` stream (an agent placing ten pieces in a minute and a reconnecting stream must not
    be locked out); two replicas do not double them because the limits sit in Caddy. The code length is
    the owner's pick (4 symbols without look-alikes, or 6 digits); the default in the action items is 4.

## Consequences

Easier: a buyer answers "does my bed fit" and "what would I change" on the portal, the arrangement
becomes part of the inquiry, a developer can sell finish packages from the same screen.

Harder: every generated blank plan is one more image a reviewer must check against the outline (a
shifted drawing puts the buyer's bed in the corridor); the stored arrangement is a JSON shape that must
stay readable across releases; the unit page grows a lazily loaded editor and its own spec; two catalogue
sources (code and table) must merge deterministically (tenant rows first, then the code list, duplicates
by name and size dropped); the board brings the API's first held connection, first `LISTEN` connection and
first anonymous write path, each with a bound (streams per process, state size, attempts per minute) that
reviewers must keep on every change; the retention sweep (backlog #5) gains a table to clean.

Revisit: after ADR-0006 B8 accepts a real DXF, add Option 1B so DXF sheets get an exact blank raster;
after the first 20 approved `plan_blank` images, count the rejections and decide whether the prompt or a
second provider (backlog #37) is needed; after Phase 5, decide 4B with a cost budget; after Phase 5, decide whether a buyer with a login may open
a board (anonymous creation) and whether a name may appear on it; after the first month of boards, read
the Caddy rate-limit denials and the 503 count for `UF_BOARD_MAX_STREAMS`.

**Out of scope here (decided 2026-10-26):** moving or removing walls, doors and windows (plan §2.3 R3,
needs the structural-tag editor); room detection inside the outline; 3D interior walk-through; a
finishing-material quotation flow with quantities (plan Phase 11, its own ADR); an external retailer's
catalogue; buyer-triggered AI renders (Option 4B); cursors, per-piece locks or operational transform on
the board; voice or chat on the board; boards across tenants; anonymous board creation (until Phase 5).

## Action items

Phase A: the editor, no backend (S to M)
- [x] A1 `portal/pages/unit.page.ts`: split the furniture part into `unit-playground.component.ts`:
      many instances per entry, select, rotate, flip, delete, L and round shapes, catalogue grouped by
      room, counts per room on the chips, "Clear my pieces". Moved the same day to its own page
      `playground.page.ts` (route `projects/:slug/units/:code/playground`, new window) per the owner's
      correction under Decision 1; the unit page keeps a view-mode plan and the button.
      *Found while implementing (2026-10-26):* the on-plan label is the piece's name only (the viewer
      shrinks a label to fit its polygon, and "Double bed 160×200 cm" inside 1.6 m was unreadable); the
      size is in the tooltip, the chip and the selection toolbar. R, F, Delete and Escape work on the
      selected piece. A tap on the unit outline deselects.
- [x] A2 The code catalogue: `portal/pages/playground.model.ts` (the repo's `*.model.ts` precedent, not
      `catalogue.ts`) with 37 pieces by room, common retail sizes to be confirmed by the owner, no prices;
      `pieceLabel` and `pieceSize` moved there; spec `playground.model.spec.ts` (33 portal tests with the
      building model). The former `unit.page.spec.ts` was folded into it.
- [x] A3 Fade toggle (Option 1C): "Empty the apartment" sets the locked unit polygon's `fill` to the page
      background at 85 % until a blank image exists; no viewer change. *Found while using:* the drawn
      furniture recedes but stays legible; inner walls fade with it, as the option said.
- [x] A4 localStorage save and restore (Decision 5), the `v: 1` example read by a test; the key is
      `uf:layout:<host>:<project>:<unit>`; the stored shape carries no ids (the component assigns them);
      the wall colour chosen by the buyer tints the outline and its stroke on the plan only.
- [x] A5 Portal guide entry and `frontend/README.md`; `ng build portal`: initial 389.5 kB raw / 98.8 kB
      transfer, the playground page chunk 21.3 kB raw / 6.5 kB, the unit page chunk 18.9 kB raw. The plan §11.3 budget line says "≤ 300 kB
      gzipped"; the transfer size is under it, the raw size is not, as before this change. *Found while
      building:* the planner's 26 icons in `UF_ICONS` pushed the admin's initial bundle over its 500 kB
      warning budget (506.5 kB), so they are registered on the component instead (admin back at
      496.0 kB, 0 warnings). Checked in headless Chrome on the published sample project (unit A-1).

Phase B: the generated blank plan (M)
- [ ] B1 Migration `0017`: `unit_media.kind` check widened to `plan_blank`; `unit_renders.variant`
      (`furnished | blank`, default `furnished`); expand only.
- [ ] B2 `renders/service.py`: `variant` on `RenderRequest`, the blank prompt, `store_result` writes
      `kind = plan_blank` with the disclosure text "Furniture removed from the floor plan by AI — check the
      walls against the drawing"; `test_unit_renders.py` covers both variants.
- [ ] B3 Admin `unit-renders.component.ts`: a "Blank plan" button next to the render button, the review
      dialog overlays the unit outline on the result, reject reason "shifted".
- [ ] B4 Publishing: the snapshot's `UnitDoc.plan_blank` (asset, width, height) from the approved image of
      the unit or its layout code; `portal-api.ts` type; the switch of A3 prefers it.
- [ ] B5 Plan §7.1, §12.3 and the admin guide; ADR-0017 Decision 6 cross-reference.

Phase C: the tenant catalogue (M)
- [ ] C1 Migration `0018`: `catalogue_items` with RLS (`backend/migrations/rls.py`), `project_id` nullable.
- [ ] C2 `sales` module: CRUD under the `sales` resource, `is_public` flag, audit rows; API tests.
- [ ] C3 Admin page "Catalogue" in the project menu with a guide entry: list, form, reorder, public toggle.
- [ ] C4 Snapshot carries public items; the unit page merges tenant rows before the code list.
- [ ] C5 MCP tools `list_catalogue_items` and `upsert_catalogue_item` (ADR-0015 pattern).

Phase D: after Phase 5 (M)
- [ ] D1 `redesign_request` inquiry payload = the arrangement of Decision 5, Pydantic-validated, format
      marker `v`; backward-reading test on the stored example.
- [ ] D2 Account merge of browser layouts on login, like favourites (plan §7.2).
- [ ] D3 The lead page shows the arrangement as the same overlay on the unit plan.

Phase E: sharing (S for the link, M for the board; the link ships with phase A)
- [x] E1 Share link (Decision 8): `unit-playground.component.ts` encodes and restores `#l=`; the spec
      proves a 30-piece arrangement round-trips under 2 kB; guide entry "Share". *Found while
      implementing:* the fragment holds a compact array form (`{v, w, p: [[item, cx, cy, rot, flip]]}`)
      of the Decision 5 shape, since the readable form reached 3 kB; the receiver sees a banner, their
      saved arrangement is untouched until their first change; without a clipboard the link is shown in
      a field to copy; phones get the native share sheet.
- [ ] E2 Migration `0019`: `boards` with RLS; `rls.py` entry; expand only.
- [ ] E3 `boards` module (`backend/src/unitforma/boards/`): create (staff, admin host, audit, 409 for a
      unit that is not published and listed), join lookup, get, put
      with `If-Match`, end; code generator from the 31-symbol alphabet (or 6 digits on the owner's pick);
      expiry rules of Decision 9; API tests for stale write, unknown code, ended board, state over 4 kB.
- [ ] E4 SSE stream: `GET /portal/boards/{code}/events`, one `LISTEN` connection per process
      (`core/notify.py`, asyncpg, reconnect with backoff), in-process subscribers keyed by board id,
      payload = board id and version, the row re-read in `tenant_session` (a test with two tenants
      sharing one code proves neither sees the other),
      `UF_BOARD_MAX_STREAMS`, keepalive; a test with two subscribers and one NOTIFY.
- [ ] E5 Caddy: two `rate_limit` zones per address, 10 per minute on `/api/portal/boards/join/*` and
      120 per minute on the rest of `/api/portal/boards/*`, in `Caddyfile.prod` and `.dev`; check in the Caddy docs that `reverse_proxy` flushes
      `text/event-stream` without a `flush_interval` setting and what its idle timeout is, write the
      finding into the plan §3.3 with the date; `deploy/compose` validated with `config`.
- [ ] E6 Admin unit page: "Open a board" button, the code shown large with "copy" and "open the portal
      with it"; "End board"; guide entry.
- [ ] E7 Portal: "Join a board" field in the header and `/join/<code>`; board mode on the unit page
      (banner with the code, the count of people, "Leave"); moves sent on drop with `If-Match`; 409
      reapplies; reconnect from `Last-Event-ID`; spec.
- [ ] E8 Retention sweep deletes boards ended more than 7 days ago (with backlog #5); plan §7.1, §12.3
      and §3.3 updated; README sentence; the my-high-load answers (held connections, statements per
      move, log lines) written into this ADR under *Found while implementing*.
