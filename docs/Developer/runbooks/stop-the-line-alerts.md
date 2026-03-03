# Stop-The-Line Alerts

## Scope

Incident response for stop-the-line threshold breaches and operator acknowledgement handling.

## Detection Signals

- `stop_the_line_threshold_breach` alert events in event journal.
- Runtime decision indicates `rollback_triggered=true` and `target_mode=shadow`.

## Immediate Containment

1. Confirm runtime mode downgrade status for affected environment (`active` -> `shadow`).
2. Assign incident commander and acknowledge alert with operator identity.
3. Preserve event and transition evidence for the full threshold evaluation window.

## Operator Acknowledgement

1. Submit acknowledgement through `POST /dashboard/alerts/stop-the-line/acknowledge`.
2. Include `trace_id`, `alert_id`, `operator_id`, and deterministic acknowledgement note.
3. Verify persisted acknowledgement event with `action=acknowledge_stop_the_line_alert`.

## Exit Criteria

- Alert acknowledgement event is persisted and linked to triggering `alert_id`.
- Containment decision is documented and communication cadence is active.
- Rollout progression resumes only after policy-compliant health recovery.
