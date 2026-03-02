# Agent1

Agent1 is an autonomous GitHub engineering agent.

This repository is organized as a pnpm workspace with Turborepo orchestration:

- `apps/backend`: FastAPI backend runtime.
- `apps/frontend`: TypeScript + Vite operations UI.
- `controls`: Human-editable prompts, policies, styles, and runtime rules.
- `docs`: User-facing documentation.
- `docs/Developer`: Developer-facing architecture and runbooks.
- `tests`: Unit, integration, live, and scenario test suites.

Canonical architecture and behavior contract: `spec.md`.
