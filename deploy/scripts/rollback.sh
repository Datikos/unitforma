#!/usr/bin/env bash
# Roll a module back to a previous tag: rollback.sh <previous-tag> [service ...]
# Migrations are backward compatible for one release, so no down-migration is run.
set -euo pipefail
exec "$(dirname "$0")/deploy.sh" "$@"
