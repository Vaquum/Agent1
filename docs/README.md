# Agent1 User Docs

This directory contains user-facing documentation for capabilities, configuration, and operations.

Current operations dashboard capability:

- Dashboard UI renders recent jobs, transitions, and events with filter and pagination controls.
- Dashboard data source is `GET /dashboard/overview` with optional filters for `entity_key`, `job_id`, `trace_id`, and `status`.
- Dashboard supports single-job drill-down via `GET /dashboard/jobs/{job_id}/timeline`.
- Timeline drill-down includes event detail inspection with transition correlation and trace-based pivot filtering.
- Operational readiness is tracked in `docs/Developer/operational-readiness.md` and validated by CI gates.
- Service-level and error-budget policy is defined in `docs/Developer/service-level-policy.md` and enforced by operational-readiness validation.
- Alert routing severity and runbook linkage is maintained in `docs/Developer/alert-routing-matrix.json`.
- Incident lifecycle policy is defined in `docs/Developer/incident-response-policy.md`.
- Release freeze and exception control is maintained in `docs/Developer/release-control.json`.
- Rollback rehearsal evidence is recorded in `docs/Developer/rollback-rehearsal-log.md`.
