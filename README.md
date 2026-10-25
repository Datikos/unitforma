# Unitforma

Multi-tenant real-estate sales and visualisation platform for property developers: upload
drawings and renders, prepare a human-verified unit inventory, attach prices and terms, publish a
branded buyer portal on `{tenant}.unitforma.com` or the developer's own domain, and receive
buyer inquiries authenticated with an email one-time code.

**Status:** Phase 2 (documents and mapping) in progress on top of Phase 1: presigned uploads, document revisions, worker processing (rasterise, text/vector extraction, floor hints), sheet assignment and calibration, unit boundaries → draft units with permanent ids and readable codes, measured areas, review/approve, relabel/split/merge/remove with lineage; admin mapping editor. See the plan in
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
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
../scripts/init-garage.sh                       # first run only: storage layout, bucket, key
docker compose -f compose.yaml -f compose.dev.yaml ps
```

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
