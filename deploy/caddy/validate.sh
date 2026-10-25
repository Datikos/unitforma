#!/bin/sh
# Validate the Caddyfiles. The production file uses plugin directives (rate_limit, dns provider)
# that only exist in the custom image built from deploy/caddy/Dockerfile; with a stock `caddy`
# binary those blocks are stripped before validation so the rest of the syntax is still checked.
# Usage: validate.sh [caddy-binary]   (default: caddy on PATH)
set -eu
cd "$(dirname "$0")"
CADDY=${1:-caddy}
echo "== Caddyfile.dev"
"$CADDY" validate --config Caddyfile.dev --adapter caddyfile >/dev/null 2>&1 && echo "valid" || { "$CADDY" validate --config Caddyfile.dev --adapter caddyfile; exit 1; }
echo "== Caddyfile.prod (plugin directives stripped)"
TMP=$(mktemp)
# remove rate_limit { ... } blocks; replace the dns provider line with a stock tls subdirective
awk '
  /^[[:space:]]*rate_limit[[:space:]]*\{/ { depth=1; next }
  depth>0 { n=gsub(/\{/,"{"); m=gsub(/\}/,"}"); depth+=n-m; next }
  /^[[:space:]]*dns [a-z]+ / { sub(/dns .*/, "ca https://acme-staging-v02.api.letsencrypt.org/directory"); print; next }
  { print }
' Caddyfile.prod > "$TMP"
export PLATFORM_DOMAIN=${PLATFORM_DOMAIN:-example.com} ACME_EMAIL=${ACME_EMAIL:-ops@example.com}
"$CADDY" validate --config "$TMP" --adapter caddyfile >/dev/null 2>&1 && echo "valid" || { "$CADDY" validate --config "$TMP" --adapter caddyfile; rm -f "$TMP"; exit 1; }
rm -f "$TMP"
