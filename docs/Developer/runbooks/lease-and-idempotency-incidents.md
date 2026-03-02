# Lease And Idempotency Incidents

## Scope

Incident response for lease contention, stale ownership, and duplicate side-effect anomalies.

## Detection Signals

- Repeated lease-claim failures for the same `job_id`.
- Duplicate side-effect attempts for the same idempotency key.
- Conflicting scope ownership on startup.

## Immediate Containment

1. Switch runtime mode to `shadow` for the affected environment.
2. Preserve logs and event journal records for the incident window.
3. Stop automatic retries for the impacted job scope if retry loops are active.

## Diagnosis

1. Identify impacted `job_id`, `entity_key`, and `trace_id`.
2. Inspect `jobs` and `job_transitions` for lease-epoch behavior and repeated transitions.
3. Inspect event journal entries for repeated outbound action intents.
4. Confirm current scope owner in `runtime_scope_guards`.

## Remediation

1. Resolve stale ownership:
   - release stale scope guard,
   - restart one owner instance only.
2. Resolve duplicate side-effect risk:
   - verify idempotency key mapping,
   - replay only through idempotent path.
3. Resume processing in `active` only after stability checks pass.

## Exit Criteria

- No new lease violations for two full poll cycles.
- No duplicate side-effect emission for reprocessed events.
- Job transitions return to deterministic forward flow.
