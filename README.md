# Unitforma

Multi-tenant real-estate sales and visualisation platform for property developers: upload
drawings and renders, prepare a human-verified unit inventory, attach prices and terms, publish a
branded buyer portal on `{tenant}.unitforma.com` or the developer's own domain, and receive
buyer inquiries authenticated with an email one-time code.

**Status:** Phase 4 (publishing and buyer portal) complete on top of Phases 1–3: readiness checklist, unit publication flags, immutable publication snapshots with a filterable read model, signed preview links, atomic publish and unpublish, host-based tenant and single-project portals, and the buyer portal (site plan and 3D massing, buildings and floor plans coloured by availability, unit list with filters, unit pages with labelled media, favourites). Mapping handles split-level and multi-block sheets (one sheet showing several floors, each with its region), takes unit outlines from the drawing's filled zones (ArchiCAD zones, hatches) or grows labelled rooms to the printed area, suggests floors from level markers matched to floor elevations, reads Georgian lettered in legacy CAD fonts, recognises parking stalls and numbered storage rooms, stores the areas printed on the drawing as documented areas, and lets reviewers exclude reprinted plan sets. The buyer picks a floor on the 3D building, then the unit on that floor's plan (ADR-0006 Phase A). A project can start from a Tbilisi building permit: paste the tas.ge address, preview the record, import the project with its address, parcel and current drawings; personal data in the permit is never stored (ADR-0007). DXF exported from AutoCAD or ArchiCAD uploads like a PDF: one sheet per layout, zones and hatches as unit outlines, scale from the drawing units, so the sheet arrives calibrated (ADR-0006 Phase B; acceptance on a real ArchiCAD export still open). Documents upload several at once and classify themselves from the file name and the page content; the kind shows with its origin and is confirmed or fixed on the card (ADR-0008). After processing, each building proposes its floors from the drawings' level markers, with elevations and heights, accepted in one click (ADR-0010). Blocks drawn side by side on the sheets are detected and become separate buildings with their own floors (ADR-0014). The 3D massing follows the mapping: every outline change queues a rebuild, drafts show translucent in the admin viewer, buyers see only listed units (ADR-0011). An IFC export filed under a building becomes the architect's 3D model: the heavy worker converts it, the reviewer links its spaces to the units on the 3D massing page, and the portal shows it for that building instead of the massing, Draco-compressed by glTF-Transform in the heavy worker image (ADR-0006 Phase C). The admin app has a side menu with workspace and project sections, breadcrumbs, one status vocabulary with colours and icons on every page and in the grid, dialogs instead of browser prompts, and a guide entry per screen; the buyer portal shares the tokens and gains navigation, filter chips and a sticky unit action bar (ADR-0009). A project is archived (hidden, nothing lost) or, by the tenant admin with the slug typed in, deleted permanently with its files; a document, an empty building or a floor no unit uses is deleted from its card; archiving or deleting a published project takes its portal offline first, a mapped document asks before detaching its units, and the audit log keeps every delete (ADR-0012). The portal shows what Georgian developers' sites show: a building's facade drawing becomes a clickable floor picker from its level markers, units carry an entrance, buildings a construction status, completion and terms, prices a settlement note, and the unit list has a table view (ADR-0014). A developer's staff can work from an AI assistant: the MCP server at `app.<domain>/mcp` exposes tools for projects, buildings, floors, site features, units (found by the codes people type), documents, generated plan renders, plan types and the setup checklist and solver behind personal API tokens created on the "API tokens" page, with the role matrix, RLS and audit rows of the admin API (ADR-0015, ADR-0028 Phase C). The assistant can also map a drawing (sheets, floors, scale, suggested outlines, approval) and delete a floor, an empty building or a document with a `confirm` argument equal to what the card shows; a buyer's assistant gets a read-only MCP server at `/mcp` on every portal host with the published projects, units and plan types (ADR-0034). The portal shows the building: pages of render documents marked public form a gallery and the project cover, the architect's elevation drawings are mapped onto the sides of the 3D massing, site features drawn on the site plan become grass, roads, paving and trees in 3D, units sharing a layout code share their renders, the unit page focuses its plan and lights the unit in 3D, an OpenStreetMap embed shows the location, a permit import stuck for 20 minutes is closed by the next refresh, and a file left queued by a lost worker is queued again by the next refresh, by a 10-minute sweep or at once by "Process again" on its card, which also re-reads a processed file with the current drawing reader (ADR-0016). The selected apartment is drawn on top of the floor plan, the massing has neutral roofs with facade drawings and a buyer-side switch for availability colours, a staff member can ask an image model for a furnished 3D cutaway of a unit's plan and publish it after review with a visible "generated" label (shared by layout code), and a setup checklist shows the order of work and what each project still lacks (ADR-0017). A sale or a price change reaches the portal at once, without a new version; structure and texts stay versioned (ADR-0018). The plan viewer has zoom, fit and full-screen buttons, the selected unit gets an "Open" callout on the plan, and a unit label shrinks to fit its outline (a parking stall 2.5 m wide keeps "P-10" inside). The unit page opens a renovation playground in its own window: the plan beside the tools, pieces from a catalogue by room at true scale, dragged, turned and flipped on the plan, the architect's furniture faded on request, a wall colour to try, the arrangement kept in the browser and shareable as a link (ADR-0020 Phase A). A daily sweep removes what nobody can reach any more: upload intents never completed, expired invitations and tokens, old render crops, storage prefixes whose rows are gone and the images of retired publications, each behind a grace period, with a count-only switch for the first run (ADR-0021). A project keeps a registry of its plan types on the "Layouts & renders" page: one code per layout with a name, the units linked to it, the renders and photos every linked unit shows after its own, and one generated 3D plan render per layout under review; the inventory and the unit form pick the layout from that registry (ADR-0022). The workspace has a "Settings" page: the tenant admin sets the base prompt every generated plan render starts from, with the built-in text pre-filled and a reset; each change is an audit row (ADR-0023). Buyers see the plan types: the project page lists them with their renders, a "Plan types" page shows each with rooms, area range, lowest price and the live number of units left, and the units list filters by plan type (ADR-0024). A project can set itself up: the Projects page takes the address, currency, first building and drawings (or a permit), and a solver job applies the confident proposals after every processed document: floors from the level markers, sheets to their floors, scale from the printed 1:N, unit outlines the drawing names clearly (0.9 or more, approved when every printed label is covered and the person asked for it), the site plan, the building's placement by footprint match, facade drawings by width, render documents to the gallery, the address on the map (behind `UF_GEOCODER`), and proposed plan types that share nothing until confirmed; the setup checklist shows every decision with its confidence and what was left for the person; an optional vision pass names the kind of unclassified drawing pages behind `UF_AI_CLASSIFY` (ADR-0025); "Publish with defaults", one click on the checklist or a switch at intake, ends the solver's run with a live portal (drafts approved, plan types confirmed, a first description, every active unit listed, a version published), a person's calibration of one page serves the other pages of its document, and every "needs you" line says what to do (ADR-0029). An IFC export without zones still gives a clickable building: the approved plan outlines become its spaces, placed on the model by fitting the lowest floor to its storey's slab and confirmed in one click; the file's own export settings are read and turned into advice for the architect, and a re-upload of the same file is noted instead of converted again (ADR-0030). Drawing sets that print no scale ("NTS") are scaled page by page from their own dimension chains, small labels lettered in rows ("ბინა" / "221" / "43.9 მ2") read as units with their printed areas, and hatching, grid axes and dimension lines no longer cut rooms apart (ADR-0031). The architect's 3D model keeps the file's own colours (orange panels, grey walls, dark railings, glass) and drops pipes and ducts before any part of the facade to fit its budget (ADR-0032). The viewer draws that model as a BIM viewer does, a line on every edge of every element and a darkening where surfaces meet, with nothing added to the model and a lighter tier for phones (ADR-0033). A placed building is drawn on the portal's site plan with the outline the architect's site plan gives it, not the hull of its apartments, and re-running an IFC conversion keeps the confirmed spaces that did not move (ADR-0035). Next: ADR-0006 B8 (acceptance on a real ArchiCAD DXF, owner's file) and Phase D (DWG, owner's converter decision), then Phase 5 (buyer accounts and inquiries). See the plan in
[`docs/architecture/plan-v0.1.md`](docs/architecture/plan-v0.1.md) and the decisions in
[`docs/adr/`](docs/adr/).

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | Python 3.14 / FastAPI modular monolith; one image, roles `api`, `worker`, `scheduler`, `migrate` |
| `frontend/` | Angular 22 workspace: `admin` (app.unitforma.com), `portal` (tenant portals + custom domains), shared libraries |
| `deploy/compose/` | Docker Compose: `compose.yaml` (base), `compose.dev.yaml`, `compose.prod.yaml`, `compose.observability.yaml`, `.env.example`, `secrets/` |
| `deploy/caddy/` | Reverse proxy (Caddy) with on-demand TLS for custom domains |
| `deploy/kratos/` | Ory Kratos configuration, identity schema, email templates |
| `deploy/postgres/` | Role/database bootstrap and production tuning |
| `deploy/garage/` | S3-compatible object storage configuration |
| `deploy/backup/`, `deploy/scripts/` | Backup/restore image, `dev-up.sh` (dev stack), deploy, rollback and init scripts |
| `docs/` | Architecture plan, ADRs, runbooks |
| `.github/workflows/` | CI: backend, frontend, compose validation, image builds |

## Local development (Docker)

Prerequisites: Docker Engine 27+ with Compose v2.30+, and hostnames `app.unitforma.localhost`,
`unitforma.localhost`, `demo.unitforma.localhost` resolving to 127.0.0.1 (most systems resolve
`*.localhost` automatically; otherwise add them to `/etc/hosts`).

```bash
deploy/scripts/dev-up.sh                        # first install and every rebuild (Windows: deploy\scripts\dev-up.ps1)
deploy/scripts/dev-up.sh api worker-light       # rebuild only the named services
```

The dev stack runs without a `.env`: the defaults in `compose.yaml` are the dev values
(`*.unitforma.localhost`, tag `dev`), and `.env.example` is the production template (`unitforma.com`,
`UF_ENVIRONMENT=production`), so do not copy it for development. The script is idempotent: it
creates missing secrets (`init-secrets.sh`), starts `storage` and runs `init-garage.sh` only when the
bucket does not exist yet, then runs `docker compose -f compose.yaml -f compose.dev.yaml up -d --build`,
waits for `db-migrate` (its log is printed when it fails) and ends with `ps`. The header of the
script lists every command, so each step can also be typed by hand. Order matters on a fresh install:
`api` and the workers wait for a healthy `storage`, and `storage` is healthy only after
`init-garage.sh` has applied the layout; the script keeps that order.

| URL | What |
|---|---|
| https://app.unitforma.localhost | Developer workspace (Caddy internal CA; trust it or accept the warning) |
| https://app.unitforma.localhost/.ory/health/ready | Kratos public API (same host as the admin UI) |
| http://127.0.0.1:8000/api/docs | API docs (dev only) |
| http://127.0.0.1:8025 | Mailpit: every email, including login codes |
| https://app.unitforma.localhost/mcp | MCP server for staff assistants (ADR-0015); answers 401 until a token from the "API tokens" page is sent as `Authorization: Bearer` |

The dev stack stores uploaded files in the `local_storage` volume (`UF_STORAGE_BACKEND=local`), not
in Garage. A volume created by an image built before 2026-10-25 is owned by root and every upload
fails with `Permission denied: '/data/storage/t'`. Fix the ownership once, then rebuild:
`docker compose -f compose.yaml -f compose.dev.yaml run --rm --no-deps -u root --entrypoint chown api 10001:10001 /data/storage`
and `deploy/scripts/dev-up.sh api worker-light worker-heavy`.

Update one module without touching the rest: `deploy/scripts/dev-up.sh api`.

## First platform administrator

1. Sign in once at `https://app.<domain>/login` (creates the Kratos identity and the user row).
2. `docker compose ... exec api unitforma bootstrap-admin you@example.com`
3. Reload: the **Platform** entry appears; create a tenant and copy the first admin's invitation link.

## Without Docker

Backend: see [`backend/README.md`](backend/README.md). Frontend: `cd frontend && npm ci && npx ng serve admin`.

## Production

`deploy/compose/compose.prod.yaml` with pinned image tags from `.env`; rollout with
`deploy/scripts/deploy.sh <tag>` (migrate → workers → api → frontends), rollback with
`deploy/scripts/rollback.sh <previous-tag>`. Runbooks in `docs/runbooks/`.

## Licence

Proprietary — all rights reserved (to be decided by the owner).
