# Deploy a release (single host, Docker Compose)

1. CI has pushed images tagged `sha-<short>` for backend, frontends, proxy, backup.
2. On the host: `cd /srv/unitforma/deploy && git pull` (Compose files, Caddyfile, Kratos config).
3. Review changes to `deploy/kratos/kratos.yaml` and `.env.example`; update `.env` if new variables appeared.
4. Roll out: `./scripts/deploy.sh sha-<short>` (order: db-migrate → workers → api → frontends, waits for health).
5. Verify: `docker compose -f compose/compose.yaml -f compose/compose.prod.yaml --env-file compose/.env ps`,
   `curl -fsS https://app.<domain>/api/v1/portal/branding -H 'Host: <tenant>.<domain>'`, log in, open a portal.
6. If anything is wrong: `./scripts/rollback.sh <previous-tag>` (no down-migration needed; schemas are backward compatible for one release).

Kratos upgrades: bump `KRATOS_VERSION` in `.env`, run `docker compose up -d kratos-migrate && docker compose wait kratos-migrate`, then `up -d --no-deps kratos kratos-courier`. Read Ory release notes first.

## Heavy worker image

`worker-heavy` runs the `runtime-ifc` target of `backend/Dockerfile` (image `unitforma-backend-ifc`), which adds IfcOpenShell for IFC ingestion; `api`, `worker-light` and `scheduler` run the plain `runtime` target. Both targets come from one `uv.lock`; build and tag them together per release. The heavy worker keeps its 4 GB memory limit in `compose.prod.yaml` for IFC tessellation (ADR-0006 Phase C).
