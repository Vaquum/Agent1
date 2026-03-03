# Frontend Playwright E2E

## Local Run

1. Install browser dependencies:
   - `pnpm --filter @agent1/frontend exec playwright install --with-deps chromium`
2. Run frontend Playwright suite:
   - `pnpm --filter @agent1/frontend test:e2e`

## Selector Stability Contract

- Job timeline action button: `data-testid='select-job-timeline'`
- Timeline event inspect button: `data-testid='inspect-timeline-event'`
- Trace pivot action button: `data-testid='apply-trace-filter'`
- Overview job-id cell: `data-testid='job-id-cell'`
- Overview trace cell: `data-testid='overview-trace-cell'`

## CI Execution

- PR workflow: `.github/workflows/pr-gates.yml` job `frontend-playwright`
- Nightly workflow: `.github/workflows/nightly-full-suite.yml` job `frontend-playwright`
