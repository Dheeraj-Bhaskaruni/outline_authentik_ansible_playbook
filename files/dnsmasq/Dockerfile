# Minimal dnsmasq for the private path. Runs in the foreground, drops to the
# dnsmasq user itself; the container only gets NET_BIND_SERVICE/SETUID/SETGID.
ARG ALPINE_IMAGE=alpine:3.20
FROM ${ALPINE_IMAGE}
RUN apk add --no-cache dnsmasq
ENTRYPOINT ["dnsmasq", "--keep-in-foreground", "--conf-file=/etc/dnsmasq.conf"]
