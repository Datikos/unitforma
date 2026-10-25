#!/bin/bash
# Runs once when the pgdata volume is empty (official postgres image entrypoint).
# Creates the application databases and roles. Passwords come from Docker secrets.
set -euo pipefail
read_secret() { tr -d '\n' < "$1"; }
APP_OWNER_PW=$(read_secret "${APP_OWNER_PASSWORD_FILE}")
APP_RW_PW=$(read_secret "${APP_RW_PASSWORD_FILE}")
APP_PORTAL_PW=$(read_secret "${APP_PORTAL_PASSWORD_FILE}")
KRATOS_PW=$(read_secret "${KRATOS_PASSWORD_FILE}")

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
-- Schema owner: runs migrations, owns all tables. Not a superuser, no BYPASSRLS.
CREATE ROLE app_owner LOGIN PASSWORD '${APP_OWNER_PW}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
-- Runtime role for api/workers: subject to row-level security.
CREATE ROLE app_rw LOGIN PASSWORD '${APP_RW_PW}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
-- Read-only role for public portal read models.
CREATE ROLE app_portal LOGIN PASSWORD '${APP_PORTAL_PW}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
-- Ory Kratos has its own database.
CREATE ROLE kratos LOGIN PASSWORD '${KRATOS_PW}' NOSUPERUSER NOCREATEDB NOCREATEROLE;

CREATE DATABASE unitforma OWNER app_owner;
CREATE DATABASE kratos OWNER kratos;
REVOKE ALL ON DATABASE unitforma FROM PUBLIC;
GRANT CONNECT ON DATABASE unitforma TO app_rw, app_portal;
SQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname unitforma <<SQL
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO app_owner;
GRANT USAGE ON SCHEMA public TO app_rw, app_portal;
-- Future tables created by app_owner (migrations) are readable/writable by app_rw automatically.
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO app_rw;
SQL
