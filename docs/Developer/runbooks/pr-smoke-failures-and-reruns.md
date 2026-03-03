# PR Smoke Failures And Reruns

## Scope

Operator policy for handling PR smoke failures and deterministic rerun procedure.

## Fail Policy

1. Any failing backend PR smoke scenario blocks merge.
2. Any failing frontend Playwright PR smoke spec blocks merge.
3. Merge remains blocked until failing smoke checks pass on rerun with updated commit.

## Triage Inputs

1. Backend artifact: `pr-backend-smoke` junit report from `pr-gates`.
2. Frontend artifact: `pr-frontend-playwright` report and test-results bundle from `pr-gates`.
3. PR smoke scope definition:
   - `tests/scenarios/pr-smoke-catalog.json`
   - `tests/scenarios/pr-smoke-env-contract.md`

## Rerun Procedure

1. Reproduce backend smoke locally:
   - `source venv/bin/activate`
   - `python tests/scenarios/pr_smoke_run.py`
2. Reproduce frontend smoke locally:
   - `pnpm --filter @agent1/frontend test:e2e`
3. Apply fix, push new commit, and re-run `pr-gates`.

## Exit Criteria

- Backend PR smoke runner exits zero.
- Frontend Playwright PR smoke suite exits zero.
- Updated PR check suite has no failing smoke jobs.
