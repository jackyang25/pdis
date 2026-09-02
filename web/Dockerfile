FROM node:22-alpine AS dependencies

WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder

WORKDIR /app/web
COPY --from=dependencies /app/web/node_modules ./node_modules
COPY web/ ./
# Copy shared artifacts file by file. A directory copy would also pull in this
# package's server-side provider clients, because Docker's `*` ignore rule
# matches only top-level entries and cannot gate inside shared/.
# Publishing a new artifact means adding it here and in copy-shared.mjs.
COPY shared/product_knowledge.json /app/shared/product_knowledge.json
COPY shared/prompt_reference.json /app/shared/prompt_reference.json

ARG NEXT_PUBLIC_PDIS_API_URL
ARG NEXT_PUBLIC_PDIS_API_HOST
ENV NEXT_PUBLIC_PDIS_API_URL=${NEXT_PUBLIC_PDIS_API_URL}
ENV NEXT_PUBLIC_PDIS_API_HOST=${NEXT_PUBLIC_PDIS_API_HOST}

RUN mkdir -p public && npm run build

FROM node:22-alpine AS runtime

WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

COPY --from=builder /app/web/public ./public
COPY --from=builder /app/web/.next/standalone ./
COPY --from=builder /app/web/.next/static ./.next/static

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1:${PORT:-3000}/ || exit 1

CMD ["node", "server.js"]
