# Event Journal Chain Validation

Run this procedure when tamper-evident event-journal chain validation fails.

## Scope

- Event-journal persistence and chain fields:
  - `apps/backend/src/agent1/db/models.py`
  - `apps/backend/src/agent1/db/repositories/event_repository.py`
  - `apps/backend/src/agent1/core/services/persistence_service.py`
- Event-journal schema migration and backfill:
  - `apps/backend/alembic/versions/20260306_000012_event_journal_chain.py`
- Chain validation command:
  - `tests/operations/event_journal_chain_validation.py`

## Validation Commands

1. Run chain verification from repository root:
   - `python tests/operations/event_journal_chain_validation.py`
2. Run scoped verification for one environment:
   - `python tests/operations/event_journal_chain_validation.py --environment dev`
3. Confirm dashboard anomaly feed includes `hash_chain_gap_anomalies` when validation fails.

## Backfill Procedure

1. Stop mutating runtime workers for the target environment.
2. Rebuild chain fields for existing rows:
   - `python tests/operations/event_journal_chain_validation.py --environment dev --backfill-missing`
3. Re-run strict verification without backfill flag:
   - `python tests/operations/event_journal_chain_validation.py --environment dev`
4. Run backend checks before re-enabling workers:
   - `ruff check apps/backend`
   - `MYPYPATH=apps/backend/src mypy -p agent1`
   - `pytest -q apps/backend/tests`
