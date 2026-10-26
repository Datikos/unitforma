#!/usr/bin/env bash
# Create every secret file with a random value (idempotent: existing files are kept).
set -euo pipefail
cd "$(dirname "$0")/../compose/secrets"
gen() { [ -f "$1" ] || { eval "$2" > "$1"; echo "created $1"; }; }
rand() { openssl rand -base64 48 | tr -d '/+=\n' | cut -c1-"$1"; }
gen postgres_password              'rand 32'
gen postgres_app_owner_password    'rand 32'
gen postgres_app_rw_password       'rand 32'
gen postgres_app_portal_password   'rand 32'
gen postgres_kratos_password       'rand 32'
gen kratos_cookie_secret           'rand 48'
gen kratos_cipher_secret           'rand 32'
gen internal_ask_token             'rand 48'
gen app_session_key                'openssl rand -base64 48'
gen garage_rpc_secret              'openssl rand -hex 32'
gen garage_admin_token             'rand 48'
gen s3_access_key                  'echo GK$(openssl rand -hex 12)'
gen s3_secret_key                  'openssl rand -hex 32'
gen smtp_connection_uri            'echo "smtp://mailpit:1025/?disable_starttls=true"'
[ -f kratos_dsn ] || { echo "postgres://kratos:$(cat postgres_kratos_password)@postgres:5432/kratos?sslmode=disable&max_conns=20&max_idle_conns=4" > kratos_dsn; echo "created kratos_dsn"; }
# External key, never random: an empty file keeps Compose happy and the feature off (ADR-0017)
[ -f ai_image_api_key ] || { : > ai_image_api_key; echo "created ai_image_api_key (empty: paste a Gemini API key and set UF_AI_IMAGE_PROVIDER=gemini to enable generated renders)"; }
chmod 600 ./*
echo "Secrets ready in $(pwd). Edit smtp_connection_uri (and prod-only secrets) as needed."
