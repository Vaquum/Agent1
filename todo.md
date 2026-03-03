# Agent1 Outstanding TODO

Tracking list of remaining items against `spec.md` acceptance criteria.

## Reliability And Persistence

- [x] P1: `entities` slice 1 - add `EntityRecord` contract, `EntityModel` ORM, and Alembic migration.
- [x] P1: `entities` slice 2 - add `EntityRepository` and `PersistenceService` APIs for create/get/list flows.
- [x] P1: `entities` slice 3 - wire orchestrator/ingress usage and add tests + docs.
- [x] P1: Add `github_events` persistence model, repository, migration, and ingestion integration.
- [x] P1: `action_attempts` slice 1 - add contracts/model + migration linked to job/outbox scopes.
- [x] P1: `action_attempts` slice 2 - persist dispatcher attempt lifecycle (`started`, `succeeded`, `failed`, `aborted`) with error metadata.
- [x] P1: `action_attempts` slice 3 - expose attempt timeline queries and add tests + docs.
- [ ] P3: `audit_runs` slice 1 - add contracts/model + migration for audit run snapshots.
- [ ] P3: `audit_runs` slice 2 - implement repository/service append + list APIs.
- [ ] P3: `audit_runs` slice 3 - wire audit execution flow and add tests + docs.
- [x] P1: `comment_targets` slice 1 - add contracts/model + migration for deterministic routing targets.
- [x] P1: `comment_targets` slice 2 - persist resolved targets from comment routing path.
- [x] P1: `comment_targets` slice 3 - add replay/idempotency lookup APIs and tests + docs.
- [x] P1: Idempotency schema slice 1 - add canonical key builder (`entity_key`, `action_type`, `target_identity`).
- [x] P1: Idempotency schema slice 2 - add normalized payload hash + policy version hash components.
- [x] P1: Idempotency schema slice 3 - enforce schema in outbox write/reconcile paths with migration + tests.
- [x] P1: Implement transactional outbox model and migration.
- [x] P1: Persist side-effect intent atomically with transition commit.
- [x] P1: Implement outbox dispatcher with attempt history and statuses (`sent`, `confirmed`, `failed`, `aborted`).
- [x] P1: Implement outbox restart reconciliation by idempotency key before retry.
- [x] P1: Persist ingress ordering fields (`source_event_id`, `source_timestamp_or_seq`, `received_at`) for each event.
- [x] P1: Implement deterministic per-entity high-water cursor ordering.
- [x] P1: Persist stale and out-of-order events without allowing backward transitions.
- [x] P1: Enforce lease-epoch validation on every mutating side effect path.
- [x] P1: Persist watcher state (`next_check_at`, `last_heartbeat_at`, `idle_cycles`, `watch_deadline_at`, `checkpoint_cursor`).
- [x] P1: Implement watcher sweeper reclaim for stale watchers and checkpoint restoration.
- [x] P1: Add explicit operator-required state for irrecoverably stuck watchers.

## Security And Governance

- [x] P1: Enforce credential-owner preflight binding for mutating side effects.
- [x] P1: Split and enforce read-only watcher credentials vs mutating credentials at runtime.
- [ ] P3: Permission matrix slice 1 - add machine-readable schema and source file under controls.
- [ ] P3: Permission matrix slice 2 - populate component/environment entries and validate at load time.
- [ ] P3: Permission matrix slice 3 - add CI validation and operator documentation.
- [x] P1: Enforce default-deny capability model for GitHub operations.
- [x] P1: Enforce fail-closed runtime behavior when policy resolution is missing or invalid.
- [ ] P3: Protected approval slice 1 - define approval artifact/schema for policy and guardrail mutations.
- [ ] P3: Protected approval slice 2 - enforce approval checks in policy/guardrail update path.
- [ ] P3: Protected approval slice 3 - persist approval audit trail and add tests + docs.
- [ ] P1: Git allowlist slice 1 - define allowed git mutation commands in execution policy.
- [ ] P1: Git allowlist slice 2 - enforce allowlist in codex runtime execution path.
- [ ] P1: Git allowlist slice 3 - add deny-path tests and runbook guidance.
- [ ] P1: Branch namespace slice 1 - define allowed mutation branch patterns per environment.
- [ ] P1: Branch namespace slice 2 - enforce branch pattern checks before mutation/push.
- [ ] P1: Branch namespace slice 3 - add integration tests for allowed and denied namespaces.
- [ ] P3: Actions pinning slice 1 - pin all third-party GitHub Actions to immutable SHAs.
- [ ] P3: Actions pinning slice 2 - add CI check that fails on unpinned Actions.
- [ ] P3: CI token scope slice 1 - set minimal per-job `permissions` in all workflows.
- [ ] P3: CI token scope slice 2 - add validation for permission drift in CI.
- [ ] P3: Dependency gate slice 1 - add dependency vulnerability audit checks for Python and Node.
- [ ] P3: Dependency gate slice 2 - define severity threshold/exception policy and docs.
- [ ] P3: Audit chain slice 1 - extend event persistence with `event_seq`, `prev_event_hash`, `payload_hash`.
- [ ] P3: Audit chain slice 2 - compute and persist chain values transactionally on append.
- [ ] P3: Audit chain slice 3 - add chain verification command and CI gate.
- [ ] P3: Audit chain slice 4 - add backfill strategy/tests/docs for existing records.
- [ ] P3: Anomaly detection slice 1 - detect hash-chain gaps and emit alert signals.
- [ ] P3: Anomaly detection slice 2 - detect idempotency violations across scopes.
- [ ] P3: Anomaly detection slice 3 - expose anomalies in dashboard and runbooks.
- [ ] P3: Retention policy slice 1 - define retention matrix for logs, traces, and artifacts.
- [ ] P3: Retention policy slice 2 - implement purge jobs with dry-run/report mode.
- [ ] P3: Retention policy slice 3 - add controls + CI checks for retention policy drift.
- [ ] P3: Retention policy slice 4 - add integration tests and operator docs.

## Testing And CI

- [ ] P2: Playwright suite slice 1 - scaffold Playwright config, fixtures, and CI browser setup.
- [ ] P2: Playwright suite slice 2 - cover operator flow for overview filters and timeline drill-down.
- [ ] P2: Playwright suite slice 3 - cover operator flow for trace pivot and event detail inspection.
- [ ] P2: Playwright suite slice 4 - stabilize selectors/data and document run instructions.
- [ ] P2: PR smoke gate slice 1 - define minimal E2E smoke scenario set and env contract.
- [ ] P2: PR smoke gate slice 2 - wire smoke execution into `pr-gates` with artifact upload.
- [ ] P2: PR smoke gate slice 3 - document fail policy and rerun procedure.
- [ ] P2: Nightly E2E slice 1 - add browser scenarios to nightly workflow.
- [ ] P2: Nightly E2E slice 2 - add artifact retention and failure summary output.
- [ ] P2: Nightly E2E slice 3 - add schedule/timeout/concurrency guardrails.
- [ ] P2: Scenario direct-assignment slice 1 - implement deterministic pytest scenario.
- [ ] P2: Scenario direct-assignment slice 2 - register explicit scenario ID in catalog.
- [ ] P2: Scenario PR-mention slice 1 - implement deterministic pytest scenario.
- [ ] P2: Scenario PR-mention slice 2 - register explicit scenario ID in catalog.
- [ ] P2: Scenario change-request slice 1 - implement deterministic follow-up scenario.
- [ ] P2: Scenario change-request slice 2 - register explicit scenario ID in catalog.
- [ ] P2: Scenario multi-round lifecycle slice 1 - implement lifecycle scenario through human terminal decision.
- [ ] P2: Scenario multi-round lifecycle slice 2 - assert deterministic state/side-effect progression.
- [ ] P2: Scenario dev+prod isolation slice 1 - build concurrent runtime harness with scoped environments.
- [ ] P2: Scenario dev+prod isolation slice 2 - assert no duplicate side effects across environments.

## Deployment And Rollout

- [x] P0: Add backend Dockerfile for production deployment.
- [x] P0: Add frontend Dockerfile (or unified deployment container strategy) for production deployment.
- [x] P0: Add Render deployment configuration and environment contract.
- [x] P0: Integrate Alembic migration execution into release workflow automation.
- [ ] P1: Progressive rollout slice 1 - define rollout stages and required health signals.
- [ ] P1: Progressive rollout slice 2 - implement stage-gate evaluator in deployment/runtime controls.
- [ ] P1: Progressive rollout slice 3 - add rollback trigger on stage-gate failure with tests + docs.
- [ ] P1: Stop-the-line slice 1 - define severe threshold rules (error rate, lease, duplicate side-effect, policy failure).
- [ ] P1: Stop-the-line slice 2 - implement automatic mode downgrade/pause on threshold breach.
- [ ] P1: Stop-the-line slice 3 - emit stop-the-line alerts and operator acknowledgement flow.
- [ ] P1: Release-promotion slice 1 - define promotion preconditions from readiness evidence + policy state.
- [ ] P1: Release-promotion slice 2 - wire promotion gate into release workflow path.
- [ ] P1: Release-promotion slice 3 - add pass/fail tests and operator documentation.

## Observability And Alerting Runtime

- [x] P1: Emit and verify alert signals for lease violations.
- [x] P1: Emit and verify alert signals for duplicate side-effect anomalies.
- [x] P1: Emit and verify alert signals for comment-routing failures.
- [x] P1: Emit and verify alert signals for outbox backlog growth.
- [x] P1: Emit and verify alert signals for elevated failed transition rates.
- [x] P1: Ensure critical alert payloads always include `trace_id`, `job_id`, and runbook linkage.
