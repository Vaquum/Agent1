# PR Smoke Environment Contract

## Scope

Minimal environment contract for PR smoke execution across backend scenario harness and frontend Playwright smoke suite.

## Backend Scenario Harness Inputs

- `AGENT1_SCENARIO_IDS`:
  - Optional comma-delimited override for selected scenario IDs.
  - Default smoke set is defined in `tests/scenarios/pr-smoke-catalog.json`.

## Frontend Playwright Inputs

- `VITE_AGENT1_API_BASE_URL`:
  - Optional dashboard API base URL override for browser tests.
  - Default frontend runtime value remains `http://localhost:8000`.

- `PLAYWRIGHT_BASE_URL`:
  - Optional browser base URL override.
  - Default local runner starts frontend dev server from `apps/frontend/playwright.config.ts`.

## CI Contract Notes

- CI runner must install Chromium via `playwright install --with-deps chromium`.
- CI runner must execute both backend smoke scenarios and frontend Playwright smoke specs listed in `tests/scenarios/pr-smoke-catalog.json`.
- Backend PR smoke runner path is `tests/scenarios/pr_smoke_run.py`.
- Backend junit artifact output defaults to `tests/scenarios/artifacts/pr-smoke-backend-junit.xml`.
