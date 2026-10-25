# Caddy with the DNS-01 provider module used for the *.unitforma.com wildcard certificate.
# Swap the module for your DNS provider (https://caddyserver.com/docs/modules/ - dns.providers.*).
ARG CADDY_VERSION=2.11
FROM caddy:${CADDY_VERSION}-builder AS builder
RUN xcaddy build \
    --with github.com/caddy-dns/cloudflare \
    --with github.com/mholt/caddy-ratelimit

FROM caddy:${CADDY_VERSION}
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
COPY Caddyfile.prod /etc/caddy/Caddyfile
