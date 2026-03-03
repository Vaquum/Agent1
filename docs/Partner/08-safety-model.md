# 08 - Safety Model

Navigation: Previous `07-dashboard-signals.md` | Index `README.md` | Next `09-sandbox-to-production.md`

Agent1 is trustworthy because safety is encoded, validated, and observable.

## Runtime Modes

- `active`: writes allowed in scoped environment.
- `shadow`: full processing, zero writes.
- `dry_run`: deterministic simulation.

## Core Guardrails

- Credential-owner binding before mutation.
- Lease-epoch validation before side effects.
- Idempotency enforcement for replay-safe execution.
- Default-deny capability model.
- Protected approval for policy and guardrail mutations.

## Why This Matters

Safety is not "be careful." Safety is a system contract.

You can audit it. You can test it. You can gate releases on it.

## Practical Rule

If confidence drops, downgrade to `shadow`, observe, then re-enter `active` deliberately.

Related:

- `09-sandbox-to-production.md`
- `10-incident-rhythm.md`
- `07-dashboard-signals.md`

Next: `09-sandbox-to-production.md`
