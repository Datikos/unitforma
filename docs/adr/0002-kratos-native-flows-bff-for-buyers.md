# ADR-0002: Buyer authentication through a backend-for-frontend over Kratos native flows

- **Status:** accepted (pending PoC V1)
- **Date:** 2026-10-25
- **Plan reference:** §8.3, §8.4

## Context
Buyers authenticate on tenant subdomains and on unrelated developer-owned domains. Kratos session
cookies cannot span unrelated domains (Ory: Multibrand is Ory Network/Enterprise only), self-hosted
Kratos has no unified login-or-register flow, and its login flow reveals whether an email exists.

## Decision
The portal calls our API on the same host; the API drives Kratos native (API) flows over the internal
network (existence check via admin API → login or registration code flow → code verification →
`session_token`), then issues a host-scoped application session cookie. Kratos tokens never reach the
browser. Staff keep standard Kratos browser flows at `app.<domain>/.ory/`.

## Alternatives considered
Shared cookie (only works on subdomains); Kratos per domain (unmanageable); Ory Hydra OIDC (extra
component and redirects for our own backend); central login host plus one-time handoff code
(fallback if PoC V1 fails).

## Consequences
We own buyer session cookie and CSRF handling; no SSO between portals (privacy by default); passkeys
unavailable to buyers (acceptable); PoC V1 must confirm the registration `session` hook and the
`credentials_identifier` lookup on `oryd/kratos:v26.2.0`.
