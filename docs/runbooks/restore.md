# Restore from backup (drill quarterly)

Prerequisites: a host with Docker, the repository, the secrets directory (from the password manager),
the age identity used for backup encryption, and access to the offsite rclone remote.

1. `cd deploy/compose && docker compose -f compose.yaml -f compose.prod.yaml --env-file .env up -d postgres storage`
2. Wait for `postgres` to be healthy; it creates roles/databases from `deploy/postgres/initdb` on an empty volume.
3. `docker compose run --rm -v $PWD/secrets/backup_age_identity:/run/secrets/backup_age_identity:ro backup restore.sh <STAMP> unitforma`
   and again with `kratos`.
4. Restore objects: `docker compose run --rm backup rclone --config /run/secrets/backup_rclone_conf sync <remote>/garage_data /mnt/garage_data` (run with the garage volume writable) — or restore a managed bucket with its provider tools.
5. Restore Caddy certificates (optional; otherwise they are re-issued): extract `caddy_data.tgz` into the `caddy_data` volume.
6. `docker compose ... up -d kratos-migrate db-migrate && docker compose ... up -d`
7. Smoke test: staff login, open a published portal, submit a test inquiry on a demo tenant.
8. Record RPO achieved (timestamp of the restored dump) and RTO (wall clock) in the drill log.
