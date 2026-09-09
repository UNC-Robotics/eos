#!/bin/sh
# Generate /etc/caddy/Caddyfile from ZITADEL_TLS_MODE, then run Caddy.
#   none      plain HTTP (dev, or behind your own TLS proxy)
#   internal  self-signed cert for ZITADEL_DOMAIN (isolated LANs; trust Caddy's root CA on clients)
#   custom    mounted certificate at /tls/cert.pem and /tls/key.pem
#   acme      automatic Let's Encrypt for a public ZITADEL_DOMAIN (set ZITADEL_ACME_EMAIL)
set -e

domain="${ZITADEL_DOMAIN:-localhost}"
case "${ZITADEL_TLS_MODE:-internal}" in
	none)     public=":80";     tls="" ;;
	internal) public="$domain"; tls="tls internal" ;;
	custom)   public="$domain"; tls="tls /tls/cert.pem /tls/key.pem" ;;
	acme)     public="$domain"; tls="${ZITADEL_ACME_EMAIL:+tls $ZITADEL_ACME_EMAIL}" ;;
	*) echo "Unknown ZITADEL_TLS_MODE: $ZITADEL_TLS_MODE" >&2; exit 1 ;;
esac

routes='
	@login path /ui/v2/login*
	handle @login {
		reverse_proxy zitadel-login:3000
	}
	handle {
		reverse_proxy h2c://zitadel:8080
	}'

# Host-facing site (TLS per mode) plus a network-internal plaintext :8080 for in-cluster
# clients such as the deploy bootstrap.
{
	printf '%s {\n' "$public"
	[ -n "$tls" ] && printf '\t%s\n' "$tls"
	printf '%s\n}\n' "$routes"
	printf ':8080 {%s\n}\n' "$routes"
} > /etc/caddy/Caddyfile

exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
