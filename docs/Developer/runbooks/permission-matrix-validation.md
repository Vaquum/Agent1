# Permission Matrix Validation

Run this procedure when `tests/operations/permission_matrix_validation.py` fails in CI or local checks.

## Scope

- Policy controls:
  - `controls/policies/default.json`
  - `controls/policies/permission-matrix.json`
- Runtime schema validation:
  - `apps/backend/src/agent1/core/control_schemas.py`
  - `apps/backend/src/agent1/core/control_loader.py`

## Validation Steps

1. Run the validation command from repository root:
   - `python tests/operations/permission_matrix_validation.py`
2. Confirm matrix coverage includes one entry for every component/environment pair:
   - components: `api`, `worker`, `watcher`, `dashboard`, `ci`
   - environments: `dev`, `prod`, `ci`
3. Confirm each entry has a non-empty `permissions` list with no duplicates.
4. Confirm `persistence_roles` includes non-empty entries for:
   - `migrator`
   - `runtime`
   - `readonly_analytics`
5. Re-run backend checks after any change:
   - `ruff check apps/backend`
   - `MYPYPATH=apps/backend/src mypy -p agent1`
   - `pytest -q apps/backend/tests`

## Remediation Notes

- Missing component/environment pairs fail control loading at startup.
- Duplicate permissions or duplicate component/environment pairs fail control validation.
- Missing `controls/policies/permission-matrix.json` fails fail-closed startup checks.
