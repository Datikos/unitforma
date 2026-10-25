#!/bin/bash
# Restore a database dump: restore.sh <STAMP> [unitforma|kratos]
# Requires the age identity file at /run/secrets/backup_age_identity and the containers postgres
# + storage running. See docs/runbooks/restore.md for the full procedure.
set -euo pipefail
STAMP=${1:?stamp}; DB=${2:-unitforma}
export PGPASSWORD=$(tr -d '\n' < "${PGPASSWORD_FILE}")
WORK=/backup/restore-${STAMP}; mkdir -p "${WORK}"
rclone --config /run/secrets/backup_rclone_conf copy "${RCLONE_REMOTE}/db/${STAMP}/${DB}.dump.age" "${WORK}"
age -d -i /run/secrets/backup_age_identity -o "${WORK}/${DB}.dump" "${WORK}/${DB}.dump.age"
pg_restore --clean --if-exists --no-owner --role=app_owner -d "${DB}" "${WORK}/${DB}.dump"
echo "[restore] ${DB} restored from ${STAMP}"
