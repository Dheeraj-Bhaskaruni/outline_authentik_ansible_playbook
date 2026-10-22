# Rebuild the official Caddy image with the Cloudflare DNS module so TLS
# certificates are issued over DNS-01: no inbound port 80/443 is ever opened.
ARG CADDY_BUILDER_IMAGE=caddy:2-builder
ARG CADDY_IMAGE=caddy:2

FROM ${CADDY_BUILDER_IMAGE} AS builder
RUN xcaddy build --with github.com/caddy-dns/cloudflare

FROM ${CADDY_IMAGE}
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
