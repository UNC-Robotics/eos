# =========================================
# Build Stage
# =========================================
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

RUN npm run build

# =========================================
# Run Stage
# =========================================
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

COPY --from=builder /app ./

RUN npm ci --omit=dev

EXPOSE 3000

CMD ["npm", "start", "--", "-H", "0.0.0.0"]