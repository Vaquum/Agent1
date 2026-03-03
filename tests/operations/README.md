# Operations Gates

Operational-readiness validation runners.

- `run.py`: validates required runbooks, readiness evidence, and service-level/error-budget policy artifacts.
- `run.py`: validates alert-routing severity/runbook matrix integrity and required alert coverage.
- `run.py`: validates incident lifecycle policy coverage and release-freeze exception enforcement artifacts.
- `run.py`: validates rollback-rehearsal evidence log content and required runbook linkage.
- `run.py`: validates Docker/Render deployment artifacts and deployment environment contract coverage.
- `release_promotion_gate.py`: evaluates release-promotion preconditions from readiness evidence and policy state.
- `release_promotion_gate.py`: persists one `audit_runs` snapshot per execution (`audit_type=release_promotion_gate`).
- `permission_matrix_validation.py`: validates machine-readable permission-matrix coverage and persistence-role entries from policy controls.
- `protected_mutation_approval_validation.py`: validates protected approval snapshot and audit-trail integrity for policy and guardrail controls.
- `event_journal_chain_validation.py`: validates tamper-evident event-journal chain integrity and supports chain backfill execution.
- `retention_policy_validation.py`: validates machine-readable retention policy coverage and drift guards for `logs`, `traces`, and `test_artifacts`.
- `retention_purge_run.py`: executes retention purge in `dry_run` or `execute` mode and emits deterministic report payloads for operator review.
- `workflow_supply_chain_validation.py`: validates immutable action SHA pinning and workflow job-permission policy drift.
- `dependency_vulnerability_gate.py`: validates python and node dependency vulnerability gates with threshold and exception policy.
