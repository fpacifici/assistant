# syntax=docker/dockerfile:1
#
# Build context is the repo root (needed to reach both frontend/ and
# docker/frontend/nginx.conf.template), e.g.:
#   docker build -f docker/frontend/Dockerfile .

FROM node:22-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ .

# Empty string (the default) means "same origin as the page" — requests go out as
# relative paths (e.g. /auth/login) for nginx to proxy. This is baked into the JS
# bundle at build time, so it must be set here, not at container runtime.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

# Sentry, also baked in at build time. An empty DSN (the default) disables it;
# the DSN is public by design, so shipping it in the bundle is fine. Empty
# sample rates fall back to the defaults in src/lib/sentry.ts.
ARG VITE_SENTRY_DSN=""
ARG VITE_SENTRY_ENVIRONMENT=""
ARG VITE_SENTRY_TRACES_SAMPLE_RATE=""
ARG VITE_SENTRY_REPLAYS_SESSION_SAMPLE_RATE=""
ARG VITE_SENTRY_REPLAYS_ON_ERROR_SAMPLE_RATE=""
ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN
ENV VITE_SENTRY_ENVIRONMENT=$VITE_SENTRY_ENVIRONMENT
ENV VITE_SENTRY_TRACES_SAMPLE_RATE=$VITE_SENTRY_TRACES_SAMPLE_RATE
ENV VITE_SENTRY_REPLAYS_SESSION_SAMPLE_RATE=$VITE_SENTRY_REPLAYS_SESSION_SAMPLE_RATE
ENV VITE_SENTRY_REPLAYS_ON_ERROR_SAMPLE_RATE=$VITE_SENTRY_REPLAYS_ON_ERROR_SAMPLE_RATE
RUN npm run build

FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/frontend/nginx.conf.template /etc/nginx/templates/default.conf.template

# Where nginx proxies /auth, /user, /notebook, /files, /tag (see the template). Point
# these at the backend Service and port in whatever chart/compose file deploys
# this image alongside the backend.
ENV BACKEND_HOST=backend
ENV BACKEND_PORT=8000

EXPOSE 80
