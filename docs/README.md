# Agent1 User Docs

This directory contains user-facing documentation for capabilities, configuration, and operations.

Current operations dashboard capability:

- Dashboard UI renders recent jobs, transitions, and events with filter and pagination controls.
- Dashboard data source is `GET /dashboard/overview` with optional filters for `entity_key`, `job_id`, `trace_id`, and `status`.
- Dashboard supports single-job drill-down via `GET /dashboard/jobs/{job_id}/timeline`.
- Timeline drill-down includes event detail inspection with transition correlation and trace-based pivot filtering.
- Ingress processing persists deterministic ordering metadata (`source_event_id`, `source_timestamp_or_seq`, `received_at`) and skips stale/out-of-order events without backward lifecycle transitions.
- Entity metadata is persisted durably in `entities` for stable environment-scoped entity identity.
- Ingress orchestration ensures entities are created and touched continuously as normalized events are processed.
- Mutating GitHub side effects enforce lease-epoch validation to reject stale-owner writes before dispatch.
- Watcher runtime state is persisted durably with stale-watcher reclaim, checkpoint restoration, and explicit operator-required escalation for stuck watchers.
- Runtime alert signals are emitted for lease violations, duplicate side-effect anomalies, comment-routing failures, outbox backlog growth, and elevated failed transition rates.
- Critical alert payloads always include `trace_id`, `job_id`, and runbook linkage.
- Runtime safety policy controls enforce credential-owner preflight checks, read/write credential separation, default-deny GitHub capabilities, and fail-closed policy resolution.
- Operational readiness is tracked in `docs/Developer/operational-readiness.md` and validated by CI gates.
- Service-level and error-budget policy is defined in `docs/Developer/service-level-policy.md` and enforced by operational-readiness validation.
- Alert routing severity and runbook linkage is maintained in `docs/Developer/alert-routing-matrix.json`.
- Incident lifecycle policy is defined in `docs/Developer/incident-response-policy.md`.
- Release freeze and exception control is maintained in `docs/Developer/release-control.json`.
- Rollback rehearsal evidence is recorded in `docs/Developer/rollback-rehearsal-log.md`.
- Docker-on-Render deployment baseline is defined in `render.yaml` with environment contract in `docs/Developer/deployment-environment-contract.md`.
