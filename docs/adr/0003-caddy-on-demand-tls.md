# ADR-0003: Caddy with On-Demand TLS as the single public entry point

- **Status:** accepted
- **Date:** 2026-10-25
- **Plan reference:** §4.5, §9

## Decision
Caddy terminates TLS for all hosts. Tenant subdomains use a wildcard certificate (DNS-01). Custom
domains get certificates on demand, gated by the API's `/internal/domains/ask` endpoint which
answers 200 only for verified, active `portal_domains`. Unknown hosts fail the TLS handshake and
get HTTP 421 on plain HTTP.

## Alternatives considered
Traefik (certificates only for pre-configured routers; no on-demand issuance for unknown hosts);
nginx + certbot (manual orchestration).

## Consequences
Caddy's certificate storage volume must be backed up; removal of a domain purges its certificate;
Let's Encrypt limits (50 certificates per registered domain per week) shape activation pacing.
