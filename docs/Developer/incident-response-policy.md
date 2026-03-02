# Incident Response Lifecycle Policy

## Last Updated

- Date: 2026-03-01
- Owner: Agent1 Team
- Scope: `dev`, `prod`, `ci`

## Severity Levels And Ownership Routing

- `Sev1`:
  - impact: critical service integrity or unsafe automation behavior,
  - owner: `agent1-oncall-primary`,
  - escalation path: repository write owners + incident commander activation.
- `Sev2`:
  - impact: major degradation with bounded operational fallback,
  - owner: `agent1-oncall-secondary`,
  - escalation path: primary on-call if recovery target is exceeded.

## Response-Time Targets

- `Sev1`:
  - acknowledge within 15 minutes,
  - containment decision within 30 minutes.
- `Sev2`:
  - acknowledge within 30 minutes,
  - containment decision within 60 minutes.

## Incident Commander And Communication Cadence

- `Sev1` and `Sev2` incidents require explicit incident commander assignment.
- Communication cadence:
  - `Sev1`: status update every 15 minutes until containment,
  - `Sev2`: status update every 30 minutes until containment.
- Every status update includes current impact, containment state, next action, and ETA.

## Post-Incident Review And Corrective Action

- Every `Sev1` and `Sev2` incident requires post-incident review.
- Post-incident record must include:
  - root cause,
  - permanent corrective actions,
  - explicit due date for each corrective action owner.

## Corrective Action Feedback Loop

- Corrective actions must feed back into:
  - tests,
  - controls,
  - runbooks.
- Release progression remains constrained by operational-readiness gate until corrective actions are documented and tracked.
