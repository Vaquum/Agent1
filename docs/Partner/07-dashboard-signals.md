# 07 - Dashboard Signals

Navigation: Previous `06-pr-journey.md` | Index `README.md` | Next `08-safety-model.md`

The dashboard is your shared reality with Agent1.

## Three Views To Watch

- **Overview**: active jobs, transitions, and recent events.
- **Timeline**: one job's detailed progression.
- **Anomalies**: policy and integrity alerts needing attention.

## Signals That Matter Most

- Repeated failed transitions.
- Growing outbox backlog.
- Hash-chain gap anomalies.
- Idempotency scope violations.
- Stop-the-line threshold breach alerts.

## Read A Timeline Like A Story

Look for:

1. trigger source
2. state transitions
3. side-effect attempts
4. final status or block reason

If you can narrate this in one minute, observability is healthy.

## Use Trace IDs As Anchors

When uncertain, pivot by `trace_id` and follow one continuous chain.

That keeps diagnosis factual and fast.

Related:

- `10-incident-rhythm.md`
- `08-safety-model.md`
- `05-issue-journey.md`

Next: `08-safety-model.md`
