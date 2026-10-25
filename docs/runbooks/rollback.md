# Rollback

- Application modules: `deploy/scripts/rollback.sh <previous-tag> [service...]`. Migrations are expand/contract, so the previous code runs against the new schema.
- A migration itself failed (`db-migrate` exit ≠ 0): the transaction rolled back; `api` refuses readiness; fix forward or deploy the previous tag.
- Kratos: set the previous `KRATOS_VERSION` only if Ory's release notes allow downgrade; otherwise restore the `kratos` database from the pre-upgrade dump.
- Proxy config: `git checkout <previous> -- deploy/caddy/Caddyfile.prod && docker compose exec proxy caddy reload --config /etc/caddy/Caddyfile`.
