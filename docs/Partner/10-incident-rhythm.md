# 10 - Incident Rhythm

Navigation: Previous `09-sandbox-to-production.md` | Index `README.md` | Next `11-future-horizons.md`

When signals fire, speed matters. Sequence matters more.

## First Five Moves

1. Acknowledge the alert.
2. Contain risk (often `active` -> `shadow`).
3. Anchor on one `trace_id` and one affected scope.
4. Confirm impact boundaries.
5. Execute the matching runbook.

## Typical Incident Families

- Lease and idempotency anomalies.
- Event-chain integrity findings.
- Retention drift or purge mismatch.
- Stop-the-line threshold breach.

## Recovery Standard

Return only when:

- root signal is stable
- gating validations pass
- corrective actions are explicit

A fast rollback with clear evidence beats a slow uncertain fix every time.

## Human Leadership During Incidents

Agent1 provides continuity and diagnostics. You provide priority and judgment.

That division is why response stays calm under pressure.

Related:

- `07-dashboard-signals.md`
- `08-safety-model.md`
- `09-sandbox-to-production.md`

Next: `11-future-horizons.md`
