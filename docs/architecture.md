# Architecture

Canonical architecture intent remains in `spec.md`. This document tracks the current implemented shape in one concise view.

## System Shape

Agent1 is a control-plane-driven backend + dashboard system with durable orchestration:

- **Ingress and normalization**: GitHub notifications, timelines, and check-run signals are normalized into deterministic ingress events.
- **Workflow orchestration**: Jobs and watchers progress through explicit state transitions with lease-fenced mutation paths.
- **Execution adapters**: Codex execution and GitHub side effects are mediated through policy checks, idempotency, and outbox dispatch.
- **Durable transparency**: Event journal, action attempts, audit runs, and dashboard APIs expose runtime behavior and operator evidence.

## Runtime Components

- **Core runtime**:
  - `apps/backend/src/agent1/core/ingress_coordinator.py`
  - `apps/backend/src/agent1/core/services/ingress_worker.py`
  - `apps/backend/src/agent1/core/services/mention_action_executor.py`
  - `apps/backend/src/agent1/core/services/outbox_dispatcher.py`
- **Safety and governance**:
  - `apps/backend/src/agent1/core/control_loader.py`
  - `apps/backend/src/agent1/core/control_schemas.py`
  - `apps/backend/src/agent1/core/services/runtime_scope_guard.py`
  - `apps/backend/src/agent1/core/services/stop_the_line_service.py`
  - `apps/backend/src/agent1/core/services/rollout_guard_service.py`
  - `apps/backend/src/agent1/core/services/release_promotion_gate_service.py`
- **Retention and anomaly controls**:
  - `apps/backend/src/agent1/core/services/retention_purge_service.py`
  - `tests/operations/retention_policy_validation.py`
  - `tests/operations/retention_purge_run.py`
  - `apps/backend/src/agent1/core/services/alert_signal_service.py`

## Data and Evidence Plane

- **Durable stores**:
  - `jobs`, `job_transitions`, `entities`, `github_events`, `outbox_entries`, `action_attempts`, `comment_targets`, `audit_runs`, `event_journal`
- **Evidence and operations**:
  - `docs/Developer/operational-readiness.md`
  - `docs/Developer/runbooks/`
  - `tests/operations/run.py`

## Dashboard Contract

- **Overview and anomalies**:
  - `GET /dashboard/overview`
- **Timeline drill-down**:
  - `GET /dashboard/jobs/{job_id}/timeline`
- **Stop-the-line acknowledgement**:
  - `POST /dashboard/alerts/stop-the-line/acknowledge`

## Drift Policy

- If implementation and this document diverge, update this file and `spec.md` in the same change.
