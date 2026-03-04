# Deployment Environment Contract

## Overview

Production deployment runs on Render using Docker services defined in `render.yaml`.

- Backend service: `agent1-backend`
- Frontend service: `agent1-frontend`
- Authoritative environment-variable definitions are documented in `docs/Developer/Environment-Variables.md`.

## Backend Environment Variables

Minimum production set:

- `DATABASE_URL`
- `GITHUB_TOKEN`
- `GITHUB_USER`
- `OPENAI_API_KEY`

For exact semantics, precedence, defaults, and scope guidance, use:

- `docs/Developer/Environment-Variables.md`

## Frontend Environment Variables

Required:

- `VITE_AGENT1_API_BASE_URL`: Backend base URL used by dashboard API calls.

`render.yaml` wires this from backend service URL using `fromService`.

For local Docker compose, frontend is built with `/api` and proxied to backend.

## Release Migration Automation

Alembic migration execution is automated in release flow through:

- Render backend `preDeployCommand`: `cd /app/apps/backend && alembic upgrade head`
- Backend container startup command in `apps/backend/docker/entrypoint.sh` (idempotent migration guard by schema state)

Deploy promotion is considered incomplete if migrations fail.
