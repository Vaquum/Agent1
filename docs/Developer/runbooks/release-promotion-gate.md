# Release Promotion Gate

## Scope

Operator procedure for release-promotion precondition evaluation and gate-failure response.

## Gate Execution

1. Run `python tests/operations/release_promotion_gate.py`.
2. Confirm output reports `Release promotion gate passed.` before promotion.
3. If gate fails, capture failed precondition identifiers from output.
4. Confirm one `audit_runs` snapshot was persisted for the execution (`audit_type=release_promotion_gate`).

## Failure Response

1. Resolve failed readiness artifacts via `python tests/operations/run.py`.
2. Resolve `stop_the_line_clear` evidence by containing active threshold breaches.
3. Resolve `rollout_stage_gate_passed` evidence by re-running stage-gate evaluation.

## Exit Criteria

- Release-promotion gate passes with no failed preconditions.
- Required readiness artifacts and policy state evidence are current.
- Promotion decision and evidence are recorded in operator release notes.
