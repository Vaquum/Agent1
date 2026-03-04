FROM node:20-slim AS base

WORKDIR /app

ENV PNPM_HOME=/pnpm
ENV PATH="$PNPM_HOME:$PATH"

RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json /app/
COPY apps/frontend/package.json /app/apps/frontend/package.json

RUN pnpm install --frozen-lockfile --filter @agent1/frontend...

COPY apps/frontend /app/apps/frontend

FROM base AS dev

WORKDIR /app/apps/frontend

CMD ["pnpm", "dev", "--host", "0.0.0.0", "--port", "8080"]

FROM base AS build

ARG VITE_AGENT1_API_BASE_URL='http://localhost:8000'
ENV VITE_AGENT1_API_BASE_URL="$VITE_AGENT1_API_BASE_URL"

RUN pnpm --filter @agent1/frontend build

FROM nginx:1.27-alpine AS production

COPY --from=build /app/apps/frontend/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
