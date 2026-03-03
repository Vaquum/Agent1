FROM node:20-slim AS build

WORKDIR /app

ENV PNPM_HOME=/pnpm
ENV PATH="$PNPM_HOME:$PATH"

RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json /app/
COPY apps/frontend/package.json /app/apps/frontend/package.json

RUN pnpm install --frozen-lockfile --filter @agent1/frontend...

COPY apps/frontend /app/apps/frontend

RUN pnpm --filter @agent1/frontend build

FROM nginx:1.27-alpine

COPY --from=build /app/apps/frontend/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
