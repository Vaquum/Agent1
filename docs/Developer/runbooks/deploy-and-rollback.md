# Deploy And Rollback

## Scope

Deploy and rollback procedure for `apps/backend` and `apps/frontend` with safety-first containment.

## Deploy Procedure

1. Validate local quality gates before release:
   - `source venv/bin/activate`
   - `cd apps/backend`
   - `ruff check .`
   - `MYPYPATH=src mypy -p agent1`
   - `pytest -q`
   - `cd ../..`
   - `pnpm lint && pnpm typecheck && pnpm test`
2. Apply pending migrations in release flow:
   - `cd apps/backend`
   - `alembic upgrade head`
3. Deploy the new artifact to the target environment.
4. Verify runtime health:
   - API health endpoint returns success.
   - Ingress worker is running.
   - No startup scope conflict (`RuntimeScopeConflictError`) in logs.
5. Verify behavioral safety:
   - Review-thread replies still route in-thread.
   - No duplicate side effects for repeated ingress events.

## Rollback Procedure

1. Contain writes immediately by switching runtime mode to `shadow`.
2. Roll back to the previous known-good artifact.
3. If migration is backward compatible, keep schema and restore service first.
4. If migration failback is required, follow `migration-failback.md`.
5. Re-validate health and core runtime checks.
6. Keep `shadow` until confidence checks pass, then restore `active`.

## Required Evidence

- Gate outputs for lint, typecheck, and tests.
- Migration version before/after deploy.
- Health verification result.
- Incident notes when rollback is executed.
