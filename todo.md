# Agent1 Outstanding TODO

Tracking list of remaining items against `spec.md` acceptance criteria.

## Reliability And Persistence

- [ ] P1: Add `entities` persistence model, repository, migration, and service integration.
- [x] P1: Add `github_events` persistence model, repository, migration, and ingestion integration.
- [ ] P1: Add `action_attempts` persistence model, repository, migration, and side-effect integration.
- [ ] P3: Add `audit_runs` persistence model, repository, migration, and audit flow integration.
- [ ] P1: Add `comment_targets` persistence model, repository, migration, and routing persistence integration.
- [ ] P1: Implement deterministic idempotency-key schema including `entity_key`, `action_type`, `target_identity`, normalized payload hash, and policy version hash.
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
- [ ] P3: Add machine-readable least-privilege permission matrix by component and environment.
- [x] P1: Enforce default-deny capability model for GitHub operations.
- [x] P1: Enforce fail-closed runtime behavior when policy resolution is missing or invalid.
- [ ] P3: Implement protected approval path for policy and guardrail changes.
- [ ] P1: Enforce safe git mutation allowlist in execution policy/runtime.
- [ ] P1: Enforce branch namespace restrictions for mutations (`agent1/*`, `sandbox/*`).
- [ ] P3: Pin GitHub Actions in CI workflows to immutable SHAs.
- [ ] P3: Enforce least-privilege CI job tokens.
- [ ] P3: Add dependency vulnerability gate to CI.
- [ ] P3: Implement append-only tamper-evident audit chain (`event_seq`, `prev_event_hash`, `payload_hash`).
- [ ] P3: Add anomaly detection for hash-chain gaps and idempotency violations.
- [ ] P3: Define and implement retention/purge policy execution for logs, traces, and test artifacts.

## Testing And CI

- [ ] P2: Add Playwright E2E suite for critical operator flows.
- [ ] P2: Add PR E2E smoke gate execution in CI.
- [ ] P2: Add nightly full E2E suite execution on `main` with browser scenarios.
- [ ] P2: Add scenario coverage for direct assignment execution path as explicit scenario ID.
- [ ] P2: Add scenario coverage for PR mention response as explicit scenario ID.
- [ ] P2: Add scenario coverage for change-request follow-up as explicit scenario ID.
- [ ] P2: Add scenario coverage for multi-round lifecycle until human merge/close terminal state.
- [ ] P2: Add scenario coverage for concurrent dev+prod runtime isolation with no duplicate side effects.

## Deployment And Rollout

- [x] P0: Add backend Dockerfile for production deployment.
- [x] P0: Add frontend Dockerfile (or unified deployment container strategy) for production deployment.
- [x] P0: Add Render deployment configuration and environment contract.
- [x] P0: Integrate Alembic migration execution into release workflow automation.
- [ ] P1: Implement progressive rollout checkpoints with health-signal gates.
- [ ] P1: Implement stop-the-line automation for severe error-rate, lease, duplicate side-effect, and policy failures.
- [ ] P1: Add release-promotion gate wiring to operational-readiness evidence and policy state.

## Observability And Alerting Runtime

- [x] P1: Emit and verify alert signals for lease violations.
- [x] P1: Emit and verify alert signals for duplicate side-effect anomalies.
- [x] P1: Emit and verify alert signals for comment-routing failures.
- [x] P1: Emit and verify alert signals for outbox backlog growth.
- [x] P1: Emit and verify alert signals for elevated failed transition rates.
- [x] P1: Ensure critical alert payloads always include `trace_id`, `job_id`, and runbook linkage.
