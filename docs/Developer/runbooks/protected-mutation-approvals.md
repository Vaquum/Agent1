# Protected Mutation Approvals

Run this procedure when protected mutation approval validation fails for policy or guardrail controls.

## Scope

- Protected controls:
  - `controls/policies/default.json`
  - `controls/policies/permission-matrix.json`
  - `controls/runtime/default.json`
- Approval artifacts:
  - `controls/policies/protected-approval.json`
  - `tests/operations/protected_mutation_approval_validation.py`

## Validation Steps

1. Run the protected approval validation command from repository root:
   - `python tests/operations/protected_mutation_approval_validation.py`
2. Confirm `active_snapshot.protected_files` contains exactly:
   - `policies/default.json`
   - `policies/permission-matrix.json`
   - `runtime/default.json`
3. Confirm every `sha256` value in `active_snapshot.protected_files` matches the current file content digest.
4. Confirm `audit_trail` contains the active `approval_id` and the latest decision is `approved`.
5. Re-run backend checks after any update:
   - `ruff check apps/backend`
   - `MYPYPATH=apps/backend/src mypy -p agent1`
   - `pytest -q apps/backend/tests`

## Mutation Procedure

1. Apply policy or guardrail change in protected controls.
2. Recompute each protected file `sha256` in `controls/policies/protected-approval.json`.
3. Create new `approval_id` and update `active_snapshot` metadata (`change_ticket`, `approved_by`, `approved_at`, `reason`).
4. Append one `audit_trail` event for the new `approval_id` with `decision=approved`.
5. Run protected approval validation and commit all related files together.
