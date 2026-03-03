# 06 - PR Journey

Navigation: Previous `05-issue-journey.md` | Index `README.md` | Next `07-dashboard-signals.md`

PRs have two modes, and each has a different rhythm.

## Author Mode

Agent1 authored the PR and continues follow-up through:

- review feedback
- change requests
- CI failures
- further commits

Until the human terminal decision: merge or close.

## Reviewer Mode

Agent1 reviews PRs authored by others when requested.

It can re-review after relevant updates and continue until no pending review obligation remains.

## Non-Negotiable Behavior

If context comes from a review thread, reply must stay in that same thread.

No silent top-level fallback.

## Human Control Point

Only humans decide merge or close. Agent1 informs, proposes, and executes follow-up, but does not replace that decision.

Related:

- `07-dashboard-signals.md`
- `08-safety-model.md`
- `09-sandbox-to-production.md`

Next: `07-dashboard-signals.md`
