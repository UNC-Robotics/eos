# EOS-branded build of the ZITADEL Login V2 app.
#
# The EOS customizations live in ./overlay (committed to this repo). Upstream
# Zitadel is pinned via ZITADEL_REF and fetched at build time, then the overlay
# is applied on top and the standalone Next.js app is built from source
# (buf generate -> @zitadel/client -> next build).
#
# Build:
#   docker build -t eos-zitadel-login:v4.15.1-eos docker/zitadel/login
#
# The runtime stage mirrors the upstream apps/login/Dockerfile.

# syntax=docker/dockerfile:1

ARG NODE_VERSION=24
ARG ZITADEL_REF=v4.15.1
ARG PNPM_VERSION=10.30.3

# ---------------------------------------------------------------------------
# Stage 1: build the standalone Login app from source + EOS overlay
# ---------------------------------------------------------------------------
FROM node:${NODE_VERSION}-bookworm-slim AS builder
ARG ZITADEL_REF
ARG PNPM_VERSION

ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    NX_DAEMON=false \
    NX_NO_CLOUD=true \
    NEXT_TELEMETRY_DISABLED=1

# git for the sparse clone; build-essential/python for any native deps.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates python3 make g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# Fetch only the parts of the monorepo needed to build the login app.
RUN git clone --depth 1 --branch "${ZITADEL_REF}" --filter=blob:none --sparse \
        https://github.com/zitadel/zitadel.git . \
    && git sparse-checkout set apps/login packages proto

# Apply the EOS overlay (changed source files + logo + trimmed workspace).
COPY overlay/ /src/

# English only: drop the non-en locale bundles.
RUN find apps/login/locales -type f -name '*.json' ! -name 'en.json' -delete

RUN corepack enable && corepack prepare "pnpm@${PNPM_VERSION}" --activate

# Install for the trimmed workspace (proto + client + login). The upstream
# lockfile covers the full monorepo, so resolve fresh for the subset.
RUN pnpm install --no-frozen-lockfile

# buf generate -> @zitadel/client (tsup) -> @zitadel/login (next build standalone)
RUN pnpm exec nx build @zitadel/login

# ---------------------------------------------------------------------------
# Stage 2: slim runtime (mirrors upstream apps/login/Dockerfile)
# ---------------------------------------------------------------------------
FROM node:${NODE_VERSION}-alpine AS runtime
WORKDIR /app

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs
# If /.env-file/.env is mounted, its variables are loaded before the server starts.
RUN mkdir -p /.env-file && touch /.env-file/.env && chown -R nextjs:nodejs /.env-file

COPY --chown=nextjs:nodejs --from=builder /src/apps/login/.next/standalone ./

USER nextjs
ENV HOSTNAME="::" \
    PORT="3000" \
    NODE_ENV="production" \
    NODE_OPTIONS="--use-openssl-ca --require /app/load-ssl-cert-dir.cjs" \
    SSL_CERT_FILE="/etc/ssl/certs/ca-certificates.crt" \
    ZITADEL_TLS_ENABLED="false" \
    OTEL_SERVICE_NAME="zitadel-login" \
    OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ["/usr/local/bin/node", "/app/healthcheck.mjs", "/ui/v2/login/ready"]
ENTRYPOINT ["/app/entrypoint.sh", "node", "apps/login/server.js"]
