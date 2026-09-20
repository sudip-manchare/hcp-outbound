# syntax=docker/dockerfile:1

FROM node:22-alpine AS base
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

FROM base AS dependencies
COPY package.json package-lock.json ./
# Keep lifecycle scripts out of the dependency-install layer.
RUN npm ci --ignore-scripts

FROM base AS builder
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
WORKDIR /app

# Do not run the web server as root.
RUN addgroup --system --gid 1001 nextjs \
  && adduser --system --uid 1001 nextjs

# Next standalone output contains only traced runtime dependencies.
COPY --from=builder --chown=nextjs:nextjs /app/public ./public
COPY --from=builder --chown=nextjs:nextjs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nextjs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

CMD ["node", "server.js"]
