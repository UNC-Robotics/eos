# =========================================
# Build Stage
# =========================================
FROM node:22-alpine AS builder

WORKDIR /app

ARG DATABASE_URL
ARG ORCHESTRATOR_API_URL
ARG NEXT_PUBLIC_APP_URL
ARG EOS_S3_BUCKET
ARG EOS_S3_ENDPOINT_URL
ARG EOS_S3_ACCESS_KEY_ID
ARG EOS_S3_SECRET_ACCESS_KEY

ENV DATABASE_URL=$DATABASE_URL \
    ORCHESTRATOR_API_URL=$ORCHESTRATOR_API_URL \
    NEXT_PUBLIC_APP_URL=$NEXT_PUBLIC_APP_URL \
    EOS_S3_BUCKET=$EOS_S3_BUCKET \
    EOS_S3_ENDPOINT_URL=$EOS_S3_ENDPOINT_URL \
    EOS_S3_ACCESS_KEY_ID=$EOS_S3_ACCESS_KEY_ID \
    EOS_S3_SECRET_ACCESS_KEY=$EOS_S3_SECRET_ACCESS_KEY

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

RUN npm run build

# =========================================
# Run Stage
# =========================================
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public 

EXPOSE 3000

CMD ["node", "server.js"]