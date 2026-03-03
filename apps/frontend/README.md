# Agent1 Frontend

TypeScript + Vite operations dashboard.

## Local commands

- Install dependencies from monorepo root with `pnpm install`.
- Dev server: `pnpm --filter @agent1/frontend dev`
- Build: `pnpm --filter @agent1/frontend build`

Dashboard API configuration:

- Optional `VITE_AGENT1_API_BASE_URL` (defaults to `http://localhost:8000`).
- Overview endpoint: `GET /dashboard/overview` with `limit`, `offset`, `entity_key`, `job_id`, `trace_id`, `status`.
- Timeline endpoint: `GET /dashboard/jobs/{job_id}/timeline` with `limit` and `offset`.
- Timeline UI supports event inspection, reason-based transition correlation, and trace filter pivot back to overview.

## Container runtime

- Build image from repository root: `docker build -f apps/frontend/Dockerfile .`
