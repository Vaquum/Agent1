# Runbooks

Operational runbooks for deployment, rollback, migration, and incident response.

- `deploy-and-rollback.md`: standard deploy sequence, containment, and rollback.
- `migration-failback.md`: migration safety protocol and failback procedure.
- `lease-and-idempotency-incidents.md`: response to lease and duplicate side-effect incidents.
- `review-thread-routing-failures.md`: response to review-thread routing failures.
- `github-rate-limit-and-token-failures.md`: response to token and API quota failures.
- `git-mutation-policy-denials.md`: response to codex-runtime git command policy denials.
- `stop-the-line-alerts.md`: response to stop-the-line threshold breaches and acknowledgement flow.
- `release-promotion-gate.md`: release-promotion gate execution and failure handling procedure.
- `pr-smoke-failures-and-reruns.md`: PR smoke failure policy and rerun procedure.
- `permission-matrix-validation.md`: response to permission-matrix control validation failures.
- `protected-mutation-approvals.md`: response to protected policy/guardrail mutation approval failures.
- `event-journal-chain-validation.md`: response to tamper-evident event-chain validation failures and backfill procedure.
- `ci-supply-chain-hardening.md`: response to action pinning, token-permission drift, and dependency-gate failures.
