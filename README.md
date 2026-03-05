<h1 align='center'>
  <br>
  <a href='https://github.com/Vaquum'><img src='https://github.com/Vaquum/Home/raw/main/assets/Logo.png' alt='Vaquum' width='150'></a>
  <br>
</h1>

<h3 align='center'>Agent1 is an autonomous GitHub engineering partner with deterministic workflows and safety-first controls.</h3>

<p align='center'>
  <a href='#value-proposition'>Value Proposition</a> •
  <a href='#quick-start'>Quick Start</a> •
  <a href='#contributing'>Contributing</a> •
  <a href='#license'>License</a>
</p>
<hr>

# Value Proposition

Agent1 collapses issue and PR lifecycle handling, policy-governed execution, and operator-grade transparency into one cohesive system with durable state, deterministic transitions, and strict environment isolation.

# Quick Start

Run backend and dashboard together from repository root with one Docker command. Once started, your frontend is exposed on:

http://localhost:8080/ — main dashboard UI
http://localhost:8080/<any-spa-path> — same app (nginx falls back to index.html)

Frontend API proxy endpoint:
http://localhost:8080/api/* — proxied to backend `http://backend:$PORT/*` inside compose (`PORT` default `8000`)

Useful examples through the frontend:
http://localhost:8080/api/health -> backend /health
http://localhost:8080/api/docs -> backend /docs
http://localhost:8080/api/openapi.json -> backend /openapi.json

Environment resolution for Docker is explicit:

- Compose reads values from shell environment first.
- Missing values fall back to `.env`.
- A complete starter template is in `.env.example`.

1) `active` mode (currently supported)

```bash
AGENT1_DOCKER_MODE=active docker compose up --build
```

- Backend API: `http://localhost:${PORT:-8000}`
- Backend health: `http://localhost:${PORT:-8000}/health`
- Backend API docs: `http://localhost:${PORT:-8000}/docs`
- Dashboard: `http://localhost:8080`
- Dashboard-to-backend API proxy: `http://localhost:8080/api/*`
- Runtime behavior: `prod` environment + `active` mode.
- Uses runtime credentials and database settings from `.env`.
- `GITHUB_TOKEN` must be set for Agent1 runtime.
- Fork note: set `GITHUB_USER` to your bot account and align `controls/policies/default.json` (`agent_actor` and `mutating_credential_owner_by_environment`) to that same account.
- Full variable-by-variable guidance: `docs/Developer/Environment-Variables.md`.
- Startup remains a single command; migration failures now fail closed (no automatic Alembic stamping).
- If startup fails on migrations, run:
  - `docker compose run --rm --entrypoint sh backend -lc 'alembic upgrade head'`
  - then rerun `AGENT1_DOCKER_MODE=active docker compose up --build`.

2) `dev` mode (currently unsupported)

- `AGENT1_DOCKER_MODE=dev` is intentionally blocked by runtime entrypoint safeguards.
- This mode will be re-enabled after adding a dedicated dev runtime user/token and additional isolation controls to keep dev and active behavior strictly separated.

Stop the stack:

```bash
docker compose down
```

For partner-facing usage flow, see [User Docs](docs/README.md).  
For architecture and implementation baseline, see [Architecture](docs/architecture.md) and [Developer Docs](docs/Developer/README.md).

# Contributing

The simplest way to contribute is by joining open discussions or picking up an issue:

- [Open discussions](https://github.com/Vaquum/Agent1/issues?q=is%3Aissue%20state%3Aopen%20label%3Aquestion%2Fdiscussion)
- [Open issues](https://github.com/Vaquum/Agent1/issues)

Before contributing, start with [Developer Docs](docs/Developer/README.md).

# Vulnerabilities

Report vulnerabilities privately through [GitHub Security Advisories](https://github.com/Vaquum/Agent1/security/advisories/new).

# Citations

If you use Agent1 for published work, please cite:

Agent1 [Computer software]. (2026). Retrieved from http://github.com/vaquum/agent1.

# License

[MIT License](LICENSE).
