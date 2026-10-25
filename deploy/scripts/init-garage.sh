#!/usr/bin/env bash
# First-time Garage layout + bucket + key, run after `docker compose up -d storage`.
# Uses the access/secret key from the secrets directory so the backend can use them directly.
set -euo pipefail
cd "$(dirname "$0")/../compose"
G="docker compose exec storage /garage"
NODE=$($G status | awk 'NR>2 && $1 ~ /^[0-9a-f]+$/ {print $1; exit}')
$G layout assign -z dc1 -c 100G "$NODE"
$G layout apply --version 1 || true
$G bucket create "${S3_BUCKET:-unitforma}" || true
$G key import --yes -n backend "$(cat secrets/s3_access_key)" "$(cat secrets/s3_secret_key)" || true
$G bucket allow --read --write --owner "${S3_BUCKET:-unitforma}" --key backend
echo "Garage bucket ${S3_BUCKET:-unitforma} ready."
