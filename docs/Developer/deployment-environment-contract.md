# Deployment Environment Contract

## Overview

Production deployment runs on Render using Docker services defined in `render.yaml`.

- Backend service: `agent1-backend`
- Frontend service: `agent1-frontend`

## Backend Environment Variables

Required:

- `DATABASE_URL`: Runtime database URL for SQLAlchemy and Alembic.
- `GITHUB_READ_TOKEN`: Read-only token used by ingress scanning and enrichment calls.
- `GITHUB_WRITE_TOKEN`: Mutating token used by outbound comment and thread-reply side effects.

Recommended:

- `GITHUB_USER`: GitHub actor identity. Default is `zero-bang`.
- `GITHUB_API_URL`: GitHub API base URL. Default is `https://api.github.com`.
- `GITHUB_TOKEN`: Legacy fallback token. Keep unset when split credentials are enforced.
- `SENTRY_PYTHON_DSN`: Sentry DSN for runtime exception and trace export.
- `SENTRY_ENVIRONMENT`: Sentry environment label.
- `SENTRY_RELEASE`: Sentry release identifier.
- `SENTRY_TRACES_SAMPLE_RATE`: Sentry trace sampling rate.
- `OTEL_SERVICE_NAME`: OpenTelemetry service name.
- `OTEL_TRACES_SAMPLER`: OpenTelemetry sampler mode.
- `OTEL_PROPAGATORS`: OpenTelemetry propagator list.

## Frontend Environment Variables

Required:

- `VITE_AGENT1_API_BASE_URL`: Backend base URL used by dashboard API calls.

`render.yaml` wires this from backend service URL using `fromService`.

## Release Migration Automation

Alembic migration execution is automated in release flow through:

- Render backend `preDeployCommand`: `cd /app/apps/backend && alembic upgrade head`
- Backend container startup command in `apps/backend/docker/entrypoint.sh` (idempotent migration guard by schema state)

Deploy promotion is considered incomplete if migrations fail.
