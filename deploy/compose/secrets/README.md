# Secrets

Each file in this directory holds exactly one secret value and is mounted into containers
as `/run/secrets/<name>` (Compose file-based secrets). **Never commit real values.** The
directory is git-ignored except for this README and `.gitkeep`.

Generate a complete set for a new environment:

```bash
cd deploy/compose
../scripts/init-secrets.sh            # creates every file below with random values
# then edit the ones that need external values:
$EDITOR secrets/smtp_connection_uri   # smtps://user:pass@smtp.provider.example:465/?from=... (Kratos courier format)
$EDITOR secrets/dns_provider_token    # Caddy DNS-01 provider token for the *.unitforma.com wildcard (prod)
$EDITOR secrets/backup_rclone_conf    # rclone.conf with the "offsite" remote (prod)
$EDITOR secrets/backup_age_recipient  # age public key used to encrypt dumps (prod)
```

| File | Used by | Notes |
|---|---|---|
| postgres_password | postgres, backup | superuser |
| postgres_app_owner_password | db-migrate (Alembic) | schema owner role `app_owner` |
| postgres_app_rw_password | api, workers, scheduler | runtime role `app_rw` (subject to RLS) |
| postgres_app_portal_password | api (portal read models, later) | role `app_portal` |
| postgres_kratos_password | kratos | role `kratos`, database `kratos` |
| kratos_dsn | kratos, kratos-migrate, kratos-courier | `postgres://kratos:<pw>@postgres:5432/kratos?sslmode=disable&max_conns=20` |
| kratos_cookie_secret | kratos | ≥ 32 random chars; rotating logs out all staff |
| kratos_cipher_secret | kratos | exactly 32 chars |
| smtp_connection_uri | kratos, kratos-courier (and api via env) | dev: `smtp://mailpit:1025/?disable_starttls=true` |
| s3_access_key / s3_secret_key | api, workers | Garage key created by `scripts/init-garage.sh` |
| garage_rpc_secret | storage | 64 hex chars |
| garage_admin_token | storage, init script | random |
| internal_ask_token | api, proxy | shared header value for Caddy's `ask` endpoint |
| app_session_key | api | ≥ 32 random bytes, base64 |
| dns_provider_token | proxy (prod) | provider specific |
| backup_rclone_conf | backup (prod) | full rclone.conf |
| backup_age_recipient | backup (prod) | age1... public key |
