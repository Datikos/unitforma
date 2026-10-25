#!/usr/bin/env bash
# Roll out new image tags module by module without redeploying the whole platform.
# Usage: deploy.sh <tag> [service ...]   (default: backend + frontend services)
# Order: migrate → workers → api → frontends (plan §17.6).
set -euo pipefail
TAG=${1:?image tag}; shift || true
cd "$(dirname "$0")/../compose"
COMPOSE="docker compose -f compose.yaml -f compose.prod.yaml --env-file .env"
sed -i -E "s/^(BACKEND_TAG|FRONTEND_TAG|PROXY_TAG|BACKUP_TAG)=.*/\1=${TAG}/" .env
SERVICES=("$@"); [ ${#SERVICES[@]} -eq 0 ] && SERVICES=(db-migrate worker-light worker-heavy scheduler api web-admin web-portal)
$COMPOSE pull "${SERVICES[@]}"
for s in "${SERVICES[@]}"; do
  if [ "$s" = "db-migrate" ]; then $COMPOSE up -d db-migrate; $COMPOSE wait db-migrate; continue; fi
  echo "[deploy] updating $s"
  $COMPOSE up -d --no-deps "$s"
  for _ in $(seq 1 30); do
    status=$($COMPOSE ps --format '{{.Health}}' "$s" | head -1)
    [ "$status" = "healthy" ] || [ -z "$status" ] && break
    sleep 2
  done
done
$COMPOSE ps
