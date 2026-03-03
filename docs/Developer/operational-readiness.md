# Operational Readiness Evidence

## Last Updated

- Date: 2026-03-01
- Owner: Agent1 Team
- Environment scope: `dev` sandbox for `Vaquum/Agent1`

## Runbook Currency Confirmation

- Required runbook set is present and maintained:
  - `deploy-and-rollback.md`
  - `migration-failback.md`
  - `lease-and-idempotency-incidents.md`
  - `review-thread-routing-failures.md`
  - `github-rate-limit-and-token-failures.md`
- Runbook index source: `docs/Developer/runbooks/README.md`

## Alert Routing Validation Evidence

- Runtime exception telemetry path is exercised through:
  - `apps/backend/tests/test_sentry_runtime.py`
  - `apps/backend/tests/test_structured_event_logger.py`
  - `apps/backend/tests/test_trace_context.py`
- Alert severity ownership and runbook mapping are tracked in:
  - `docs/Developer/alert-routing-matrix.json`
- CI suites that execute this validation path:
  - `pr-gates` -> `backend-quality`
  - `pr-gates` -> `operational-readiness`
  - `nightly-full-suite` -> `backend-full-suite`
  - `nightly-full-suite` -> `operational-readiness`

## Rollback Rehearsal Evidence

- Rollback containment and failback procedures are defined in:
  - `deploy-and-rollback.md`
  - `migration-failback.md`
- Rehearsal evidence log:
  - `docs/Developer/rollback-rehearsal-log.md`
- Release progression remains gated on deterministic quality checks before promotion.
- First containment step for incident rollback is mode downgrade to `shadow`.

## Incident Lifecycle Evidence

- Incident lifecycle policy source:
  - `docs/Developer/incident-response-policy.md`
- Required coverage in policy:
  - `Sev1` and `Sev2` ownership routing,
  - incident commander assignment and communication cadence,
  - corrective action due date requirements,
  - feedback loop into tests, controls, and runbooks.

## Release Freeze Enforcement Evidence

- Release freeze control source:
  - `docs/Developer/release-control.json`
- Operational readiness gate enforces:
  - release freeze + exception approval consistency,
  - exception approver and mitigation-plan requirements.

## Deployment Availability Evidence

- Docker deployment artifacts:
  - `apps/backend/Dockerfile`
  - `apps/backend/docker/entrypoint.sh`
  - `apps/frontend/Dockerfile`
  - `.dockerignore`
- Render deployment blueprint:
  - `render.yaml`
- Deployment environment contract:
  - `docs/Developer/deployment-environment-contract.md`
- Migration release automation:
  - backend Render `preDeployCommand` executes `alembic upgrade head`.
