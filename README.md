# Agent1

Agent1 is an autonomous GitHub engineering agent.

This repository is organized as a pnpm workspace with Turborepo orchestration:

- `apps/backend`: FastAPI backend runtime.
- `apps/frontend`: TypeScript + Vite operations UI.
- `controls`: Human-editable prompts, policies, styles, and runtime rules.
- `docs`: User-facing documentation.
- `docs/Developer`: Developer-facing architecture and runbooks.
- `tests`: Unit, integration, live, scenario, and operational-readiness test suites.
- `docs/Developer/service-level-policy.md`: service-level and error-budget policy contract.
- `docs/Developer/alert-routing-matrix.json`: machine-readable alert-routing contract.
- `docs/Developer/incident-response-policy.md`: incident lifecycle and corrective-action contract.
- `docs/Developer/release-control.json`: release freeze and exception control contract.
- `docs/Developer/rollback-rehearsal-log.md`: rollback rehearsal evidence log.
- `render.yaml`: Docker-on-Render deployment blueprint.

Canonical architecture and behavior contract: `spec.md`.
