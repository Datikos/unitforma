#!/bin/bash
# Nightly backup: logical dumps of both databases + object storage data + Caddy certificates,
# encrypted with age and copied offsite with rclone. Retention applied on the remote.
set -euo pipefail
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DEST=/backup/${STAMP}
mkdir -p "${DEST}"
export PGPASSWORD=$(tr -d '\n' < "${PGPASSWORD_FILE}")
RECIPIENT=$(tr -d '\n' < /run/secrets/backup_age_recipient)

echo "[backup] ${STAMP} dumping databases"
pg_dump -Fc -d unitforma -f "${DEST}/unitforma.dump"
pg_dump -Fc -d kratos -f "${DEST}/kratos.dump"
echo "[backup] archiving caddy data"
tar -czf "${DEST}/caddy_data.tgz" -C /mnt/caddy_data .
echo "[backup] encrypting"
for f in "${DEST}"/*; do age -r "${RECIPIENT}" -o "${f}.age" "${f}" && rm -f "${f}"; done
echo "[backup] uploading"
rclone --config /run/secrets/backup_rclone_conf copy "${DEST}" "${RCLONE_REMOTE}/db/${STAMP}"
echo "[backup] syncing object storage (incremental)"
rclone --config /run/secrets/backup_rclone_conf sync /mnt/garage_data "${RCLONE_REMOTE}/garage_data"
echo "[backup] applying retention (${RETENTION_DAYS} days)"
rclone --config /run/secrets/backup_rclone_conf delete --min-age "${RETENTION_DAYS}d" "${RCLONE_REMOTE}/db"
rclone --config /run/secrets/backup_rclone_conf rmdirs --leave-root "${RCLONE_REMOTE}/db"
rm -rf "${DEST}"
echo "[backup] done ${STAMP}"
