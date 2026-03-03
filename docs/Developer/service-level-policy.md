# Service Level And Error Budget Policy

## Last Updated

- Date: 2026-03-01
- Owner: Agent1 Team
- Scope: `dev`, `prod`, and `ci` runtime policy

## Service Level Objectives

- `trigger-to-first-action latency`
  - target: p95 <= 180 seconds for actionable events in `active` mode.
- `side-effect success rate`
  - target: >= 99.0% successful outbound side effects over rolling 7 days.
- `duplicate side-effect rate`
  - target: <= 0.1% duplicate side-effect attempts over rolling 7 days.
- `mean-time-to-recovery`
  - target: <= 30 minutes for Sev1 incidents and <= 120 minutes for Sev2 incidents.

## Error Budget Policy

- Side-effect success rate error budget: 1.0% failure budget over rolling 7 days.
- Duplicate side-effect error budget: 0.1% duplicate budget over rolling 7 days.
- MTTR budget breach on Sev1 or Sev2 incidents is treated as policy exhaustion.
- Error budget burn is reviewed daily during active release windows.

## Release Freeze And Recovery Rules

- Release freeze is mandatory when:
  - side-effect success budget is exhausted,
  - duplicate side-effect budget is exhausted,
  - MTTR objective for Sev1/Sev2 is breached.
- Freeze exit requires:
  - active incident containment complete,
  - relevant runbook remediation steps executed,
  - validation gates green in CI (`backend-quality`, `environment-safety`, `scenario-smoke`, `operational-readiness`).

## Exception Approval Path

- Temporary release freeze exceptions require explicit human approval from repository write owners.
- Exception record must include:
  - justification for risk acceptance,
  - mitigation plan with due date,
  - linked incident or risk tracking context.
