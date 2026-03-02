# Migration Failback

## Scope

Database migration execution and failback protocol for `apps/backend` Alembic migrations.

## Pre-Migration Safety

1. Confirm migration order and compatibility window (expand before contract).
2. Confirm backup or snapshot availability for the target database.
3. Run pre-check query set for affected tables.
4. Validate app compatibility with both old and new schema during rollout.

## Migration Execution

1. Activate runtime environment:
   - `source venv/bin/activate`
   - `cd apps/backend`
2. Apply migration:
   - `alembic upgrade head`
3. Run post-migration verification:
   - schema objects exist,
   - key indexes exist,
   - service startup succeeds,
   - smoke tests pass.

## Failback Triggers

- Migration command fails.
- Startup fails due to schema mismatch.
- Critical query paths regress after migration.

## Failback Procedure

1. Switch runtime mode to `shadow` to stop mutating side effects.
2. Roll back artifact if required to restore schema compatibility.
3. Execute migration failback:
   - `alembic downgrade -1` for immediate previous revision when safe,
   - restore snapshot when downgrade is unsafe or data shape changed.
4. Re-run verification queries and service health checks.
5. Keep runtime in `shadow` until end-to-end checks are green.

## Required Evidence

- Migration revision moved from and to values.
- Verification query outputs.
- Decision record for downgrade versus snapshot restore.
