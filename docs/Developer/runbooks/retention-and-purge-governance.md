# Retention And Purge Governance

Run this procedure when retention-policy drift is detected or purge execution needs operator intervention.

## Scope

- Retention policy source of truth:
  - `controls/runtime/default.json` (`retention_policy`)
- Retention policy drift gate:
  - `tests/operations/retention_policy_validation.py`
- Retention purge execution runner:
  - `tests/operations/retention_purge_run.py`
- Retention purge service and repository:
  - `apps/backend/src/agent1/core/services/retention_purge_service.py`
  - `apps/backend/src/agent1/db/repositories/retention_repository.py`

## Validation Commands

1. Run retention drift validation from repository root:
   - `python tests/operations/retention_policy_validation.py`
2. Run dry-run purge report for one environment:
   - `python tests/operations/retention_purge_run.py --environment dev --mode dry_run`
3. Run deterministic dry-run report for one reference timestamp:
   - `python tests/operations/retention_purge_run.py --environment dev --mode dry_run --reference-timestamp 2026-03-10T12:00:00Z`

## Purge Procedure

1. Start with `dry_run` and review candidate counts by artifact class.
2. Confirm cutoff semantics before execute:
   - only rows with timestamps strictly older than cutoff (`< cutoff`) are purge candidates,
   - rows exactly at cutoff are retained.
3. Execute purge for non-production:
   - `python tests/operations/retention_purge_run.py --environment dev --mode execute`
4. Execute purge for production only with explicit acknowledgement:
   - `python tests/operations/retention_purge_run.py --environment prod --mode execute --allow-prod-execute`
5. Re-run validation and integrity checks:
   - `python tests/operations/retention_policy_validation.py`
   - `python tests/operations/event_journal_chain_validation.py --environment dev`

## Incident Response

1. If drift validation fails:
   - restore `controls/runtime/default.json` retention matrix coverage for all required artifact/environment pairs,
   - verify `prod` retention is not shorter than `dev` or `ci` for each artifact class.
2. If purge runner reports schema validation errors:
   - execute migration baseline update before rerun:
     - `alembic upgrade head`
   - rerun purge in `dry_run` mode first for deterministic candidate verification.
3. If purge execute removes unexpected rows:
   - stop further execute runs,
   - rerun `dry_run` with fixed reference timestamp for reproducible diagnosis,
   - capture report payload and affected environment scope.
4. If chain integrity checks fail after log purge:
   - run chain validation and backfill procedure from `event-journal-chain-validation.md`,
   - keep runtime in `shadow` until validation passes.

## Exit Criteria

- Retention drift validation passes.
- Dry-run and execute report payloads match expected scope and cutoff semantics.
- Event-journal chain verification passes for affected environment.
