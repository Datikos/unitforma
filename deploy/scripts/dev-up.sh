#!/usr/bin/env bash
# Bring the dev stack up, or rebuild part of it. Idempotent: safe to run after every code change.
# Usage: dev-up.sh                 whole stack (first install and full rebuild are the same command)
#        dev-up.sh api web-admin   rebuild and restart only these services
# Runs, in this order, from deploy/compose:
#   ../scripts/init-secrets.sh                                          (creates missing secret files only)
#   docker compose -f compose.yaml -f compose.dev.yaml up -d storage    (whole-stack run only)
#   ../scripts/init-garage.sh                                           (only when the bucket does not exist yet)
#   docker compose -f compose.yaml -f compose.dev.yaml up -d --build [--no-deps <services>]
#   docker compose -f compose.yaml -f compose.dev.yaml wait db-migrate  (whole-stack run; prints its log and exits 1 on failure)
#   docker compose -f compose.yaml -f compose.dev.yaml ps
set -euo pipefail
cd "$(dirname "$0")/../compose"
COMPOSE="docker compose -f compose.yaml -f compose.dev.yaml"
# api and the workers depend on db-migrate completing, so a failed migration fails `up`; show why.
migrate_failed() {
  echo "dev-up: up failed; last db-migrate log lines:" >&2
  $COMPOSE logs --no-log-prefix --tail 20 db-migrate >&2 || true
  $COMPOSE ps -a >&2 || true
  exit 1
}

../scripts/init-secrets.sh
# No .env in dev: the defaults in compose.yaml are the dev values; .env.example is the production template.
[ -f .env ] && echo "dev-up: .env exists and overrides the dev defaults (production hosts and tags?)" >&2
BUCKET=unitforma; [ -f .env ] && BUCKET=$(grep -E '^S3_BUCKET=' .env | cut -d= -f2- || echo unitforma)

if [ $# -eq 0 ]; then
  $COMPOSE up -d storage
  for _ in $(seq 1 30); do
    $COMPOSE exec -T storage /garage status 2>/dev/null | grep -qE '^[0-9a-f]{16} ' && break
    sleep 1
  done
  if $COMPOSE exec -T storage /garage bucket list 2>/dev/null | grep -qE "[[:space:]]${BUCKET}([[:space:]]|$)"; then
    echo "storage: bucket ${BUCKET} exists, skipping init-garage.sh"
  else
    S3_BUCKET="$BUCKET" ../scripts/init-garage.sh
  fi
  $COMPOSE up -d --build || migrate_failed
  $COMPOSE wait db-migrate >/dev/null || migrate_failed
else
  $COMPOSE up -d --build --no-deps "$@" || migrate_failed
fi
$COMPOSE ps
