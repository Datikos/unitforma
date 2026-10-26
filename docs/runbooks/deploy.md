# Deploy a release (single host, Docker Compose)

1. CI has pushed images tagged `sha-<short>` for backend, frontends, proxy, backup.
2. On the host: `cd /srv/unitforma/deploy && git pull` (Compose files, Caddyfile, Kratos config).
3. Review changes to `deploy/kratos/kratos.yaml` and `.env.example`; update `.env` if new variables appeared.
4. Roll out: `./scripts/deploy.sh sha-<short>` (order: db-migrate → workers → api → frontends, waits for health). Stopping a worker waits for its running jobs: up to 5 min for `worker-light` (a permit download is capped at 300 s), up to 15 min for `worker-heavy` (IFC conversion); `docker compose stop` returns only then. A revision a killed worker left `queued` or `processing` is queued again by `documents.requeue_stuck` within 25 min (ADR-0016 Decision 8).
5. Verify: `docker compose -f compose/compose.yaml -f compose/compose.prod.yaml --env-file compose/.env ps`,
   `curl -fsS https://app.<domain>/api/v1/portal/branding -H 'Host: <tenant>.<domain>'`, log in, open a portal.
6. If anything is wrong: `./scripts/rollback.sh <previous-tag>` (no down-migration needed; schemas are backward compatible for one release).

Kratos upgrades: bump `KRATOS_VERSION` in `.env`, run `docker compose up -d kratos-migrate && docker compose wait kratos-migrate`, then `up -d --no-deps kratos kratos-courier`. Read Ory release notes first.

## MCP endpoint

`app.<domain>/mcp` is the MCP server for staff assistants (ADR-0015). The Caddyfile proxies it only on the app host, with a 1 MB body limit and the `mcp_by_ip` rate limit zone (120 requests per minute per IP); tenant hosts serve the portal for that path. It takes bearer API tokens created on the "API tokens" page, never a cookie. `UF_MCP_ENABLED=false` in `.env` turns it off (404) without a redeploy of the proxy. Check after a rollout: `curl -sS -o /dev/null -w '%{http_code}\n' https://app.<domain>/mcp` prints `401`.

## Heavy worker image

`worker-heavy` runs the `runtime-ifc` target of `backend/Dockerfile` (image `unitforma-backend-ifc`), which adds IfcOpenShell for IFC ingestion and Node 22 with the glTF-Transform CLI for Draco compression of the resulting models (ADR-0006 C2a); `api`, `worker-light` and `scheduler` run the plain `runtime` target. Both targets come from one `uv.lock`; build and tag them together per release. The heavy worker keeps its 4 GB memory limit in `compose.prod.yaml` for IFC tessellation (ADR-0006 Phase C).

## Upgrade notes

**Upgrading past ADR-0017 (migration 0014, 2026-10-26):** `compose.yaml` now mounts the secret file
`secrets/ai_image_api_key` on `api` and both workers. Run `scripts/init-secrets.sh` (it creates the file
empty) or create it by hand before `docker compose up`, or Compose refuses to start. An empty file keeps
generated 3D plan renders off; a Gemini API key in it plus `UF_AI_IMAGE_PROVIDER=gemini` turns them on.

**`db-migrate` fails with "Can't locate revision identified by 'NNNN'":** the database is ahead of the
migrations inside the backend image (a migration was added on the host and applied by hand, or the image
was built before it). The dev stack mounts `backend/migrations` into `api` only; `db-migrate` runs the
image's copy. Rebuild the image with `deploy/scripts/dev-up.sh api` (the migrate container shares it), then
`up` again. Seen on 2026-10-26 after migrations 0014 and 0015.

## OpenStreetMap embed (ADR-0016 E4)

The portal project page embeds `openstreetmap.org/export/embed.html` around the project's position. The
OSMF tile usage policy has no numeric limit but may withdraw access from commercial services without
notice. What to do when that happens, or when portal traffic grows past a few thousand page views a day:

1. Set `UF_PORTAL_MAP_EMBED=false` in `deploy/compose/.env` and recreate `api` (`docker compose up -d api`):
   the portal shows the address and an "Open in OpenStreetMap" link only, no tiles are loaded. No deploy.
2. Pick a hosted tile provider (https://switch2osm.org/providers/) or self-host tiles (http://switch2osm.org/);
   that replaces the iframe with a slippy-map library and a tile URL, a frontend change (ADR-0016 Revisit).

Attribution stays "© OpenStreetMap contributors" linked to https://www.openstreetmap.org/copyright in
both modes.
