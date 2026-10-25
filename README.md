# Unitforma

Multi-tenant real-estate sales and visualisation platform for property developers: upload
drawings and renders, prepare a human-verified unit inventory, attach prices and terms, publish a
branded buyer portal on `{tenant}.unitforma.com` or the developer's own domain, and receive
buyer inquiries authenticated with an email one-time code.

**Status:** Phase 4 (publishing and buyer portal) complete on top of Phases 1–3: readiness checklist, unit publication flags, immutable publication snapshots with a filterable read model, signed preview links, atomic publish and unpublish, host-based tenant and single-project portals, and the buyer portal (site plan and 3D massing, buildings and floor plans coloured by availability, unit list with filters, unit pages with labelled media, favourites). Mapping handles split-level and multi-block sheets (one sheet showing several floors, each with its region), takes unit outlines from the drawing's filled zones (ArchiCAD zones, hatches) or grows labelled rooms to the printed area, suggests floors from level markers matched to floor elevations, reads Georgian lettered in legacy CAD fonts, recognises parking stalls and numbered storage rooms, stores the areas printed on the drawing as documented areas, and lets reviewers exclude reprinted plan sets. The buyer picks a floor on the 3D building, then the unit on that floor's plan (ADR-0006 Phase A). A project can start from a Tbilisi building permit: paste the tas.ge address, preview the record, import the project with its address, parcel and current drawings; personal data in the permit is never stored (ADR-0007). DXF exported from AutoCAD or ArchiCAD uploads like a PDF: one sheet per layout, zones and hatches as unit outlines, scale from the drawing units, so the sheet arrives calibrated (ADR-0006 Phase B; acceptance on a real ArchiCAD export still open). Next: ADR-0006 Phase C (IFC) or D (DWG) by decision, then Phase 5 (buyer accounts and inquiries). See the plan in
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
| `deploy/backup/`, `deploy/scripts/` | Backup/restore image, deploy, rollback and init scripts |
| `docs/` | Architecture plan, ADRs, runbooks |
| `.github/workflows/` | CI: backend, frontend, compose validation, image builds |

## Local development (Docker)

Prerequisites: Docker Engine 27+ with Compose v2.30+, and hostnames `app.unitforma.localhost`,
`unitforma.localhost`, `demo.unitforma.localhost` resolving to 127.0.0.1 (most systems resolve
`*.localhost` automatically; otherwise add them to `/etc/hosts`).

```bash
cd deploy
./scripts/init-secrets.sh                       # random secrets for a dev stack (git-ignored)
cd compose && cp .env.example .env              # dev values are fine as defaults
docker compose -f compose.yaml -f compose.dev.yaml up -d storage
../scripts/init-garage.sh                       # first run only: storage layout, bucket, key
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
docker compose -f compose.yaml -f compose.dev.yaml ps
```

Order matters on a fresh install: `storage` reports unhealthy until `init-garage.sh` has applied
the layout, and `api` and the workers wait for a healthy `storage`. If `up` was started first and
stopped with "dependency failed to start", run `init-garage.sh` and repeat `up -d --build`.

| URL | What |
|---|---|
| https://app.unitforma.localhost | Developer workspace (Caddy internal CA; trust it or accept the warning) |
| https://app.unitforma.localhost/.ory/health/ready | Kratos public API (same host as the admin UI) |
| http://127.0.0.1:8000/api/docs | API docs (dev only) |
| http://127.0.0.1:8025 | Mailpit: every email, including login codes |

Update one module without touching the rest: `docker compose -f compose.yaml -f compose.dev.yaml up -d --no-deps --build api`.

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
