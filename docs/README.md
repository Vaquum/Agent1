# Agent1 User Docs

This directory contains user-facing documentation for capabilities, configuration, and operations.

Current operations dashboard capability:

- Dashboard UI renders recent jobs, transitions, and events with filter and pagination controls.
- Dashboard data source is `GET /dashboard/overview` with optional filters for `entity_key`, `job_id`, `trace_id`, and `status`.
- Dashboard supports single-job drill-down via `GET /dashboard/jobs/{job_id}/timeline`.
- Timeline drill-down includes event detail inspection with transition correlation, trace-based pivot filtering, and action-attempt lifecycle visibility.
- Ingress processing persists deterministic ordering metadata (`source_event_id`, `source_timestamp_or_seq`, `received_at`) and skips stale/out-of-order events without backward lifecycle transitions.
- Entity metadata is persisted durably in `entities` for stable environment-scoped entity identity.
- Ingress orchestration ensures entities are created and touched continuously as normalized events are processed.
- Mutating GitHub side effects enforce lease-epoch validation to reject stale-owner writes before dispatch.
- Side-effect attempt lifecycle is persisted in `action_attempts` with `started`, `succeeded`, `failed`, and `aborted` statuses linked to job/outbox scope.
- Deterministic comment routing targets are now durably scaffolded in `comment_targets` with job/outbox linkage.
- Comment-target replay and idempotency lookups are available via outbox-scope and idempotency-scope persistence APIs.
- Canonical idempotency key generation now uses deterministic side-effect scope fields with payload/policy hashing (`entity_key`, `action_type`, `target_identity`, `payload_hash`, `policy_version_hash`).
- Outbox reconciliation now applies schema-component scope filtering (`idempotency_schema_version`, `idempotency_payload_hash`, `idempotency_policy_version_hash`) when available.
- Watcher runtime state is persisted durably with stale-watcher reclaim, checkpoint restoration, and explicit operator-required escalation for stuck watchers.
- Runtime alert signals are emitted for lease violations, duplicate side-effect anomalies, comment-routing failures, outbox backlog growth, and elevated failed transition rates.
- Critical alert payloads always include `trace_id`, `job_id`, and runbook linkage.
- Runtime safety policy controls enforce credential-owner preflight checks, read/write credential separation, default-deny GitHub capabilities, and fail-closed policy resolution.
- Runtime safety policy controls now include an explicit allowlist for permitted git mutation commands.
- Runtime safety policy controls now include per-environment branch mutation namespace patterns.
- Codex runtime execution now blocks explicit disallowed git mutation commands before task dispatch.
- Codex runtime execution now blocks explicit branch create/push commands that target branch namespaces outside the current environment policy.
- Runtime controls define progressive rollout stages with required health signals in machine-readable policy form.
- Runtime bootstrapping now includes rollout stage-gate evaluation for deployment/runtime control checks.
- Failed rollout stage gates now trigger deterministic rollback decisions with active-mode downgrade to shadow mode.
- Runtime controls define severe stop-the-line thresholds for error rate, lease violations, duplicate side effects, and policy enforcement failures.
- Stop-the-line threshold breaches now trigger deterministic automatic active-to-shadow mode downgrade decisions.
- Stop-the-line threshold breaches now emit dedicated operational alerts, and operators can persist acknowledgements through `POST /dashboard/alerts/stop-the-line/acknowledge`.
- Runtime controls define machine-readable release-promotion preconditions linked to operational readiness evidence and policy state.
- Release workflow path now includes release-promotion precondition gate execution through `tests/operations/release_promotion_gate.py`.
- Operator release-promotion gate procedure is documented in `docs/Developer/runbooks/release-promotion-gate.md`.
- Playwright E2E scaffold is available for dashboard operator flows with CI browser setup and smoke execution.
- Playwright suite now covers operator overview-filter and timeline drill-down flow using deterministic mocked dashboard APIs.
- Playwright suite now covers operator trace-pivot and selected-event detail inspection flow.
- Playwright local and CI run instructions are documented in `apps/frontend/tests/e2e/README.md`.
- PR smoke scenario/spec selection and environment contract are defined in `tests/scenarios/pr-smoke-catalog.json` and `tests/scenarios/pr-smoke-env-contract.md`.
- PR gates run backend PR smoke via `tests/scenarios/pr_smoke_run.py` and upload backend/frontend smoke artifacts.
- PR smoke fail policy and rerun procedure are documented in `docs/Developer/runbooks/pr-smoke-failures-and-reruns.md`.
- Nightly workflow now retains Playwright artifacts, emits failure summaries, and applies timeout/concurrency guardrails for E2E reliability.
- Operational readiness is tracked in `docs/Developer/operational-readiness.md` and validated by CI gates.
- Service-level and error-budget policy is defined in `docs/Developer/service-level-policy.md` and enforced by operational-readiness validation.
- Alert routing severity and runbook linkage is maintained in `docs/Developer/alert-routing-matrix.json`.
- Incident lifecycle policy is defined in `docs/Developer/incident-response-policy.md`.
- Release freeze and exception control is maintained in `docs/Developer/release-control.json`.
- Rollback rehearsal evidence is recorded in `docs/Developer/rollback-rehearsal-log.md`.
- Docker-on-Render deployment baseline is defined in `render.yaml` with environment contract in `docs/Developer/deployment-environment-contract.md`.
