# Environment Variables

This document is the source of truth for Agent1 runtime environment configuration.

## Resolution Order

- Backend runtime (`Settings` / Pydantic):
  - process environment variables override `.env`,
  - `.env` provides local fallback values.
- Docker Compose interpolation:
  - shell environment values are used first,
  - missing values fall back to `.env`,
  - no hardcoded variable defaults are defined in `docker-compose.yml`.
- Frontend build variable:
  - `VITE_AGENT1_API_BASE_URL` is resolved at frontend image build time.

## GitHub Token Model

### Current behavior in Agent1

- `GITHUB_TOKEN` is used for ingress and enrichment reads:
  - `GET /notifications`,
  - `GET /repos/{owner}/{repo}/issues/{number}`,
  - `GET /repos/{owner}/{repo}/pulls/{number}`,
  - `GET /repos/{owner}/{repo}/issues/{number}/timeline`,
  - `GET /repos/{owner}/{repo}/commits/{sha}/check-runs`.
- `GITHUB_TOKEN` is used for mutating side effects:
  - `POST /repos/{owner}/{repo}/issues/{number}/comments`,
  - `POST /repos/{owner}/{repo}/pulls/{number}/comments/{comment_id}/replies`.
- `GITHUB_TOKEN` is also used for preflight owner validation:
  - `GET /user` (used to verify token owner against policy).

### Policy constraints that matter

- `GITHUB_TOKEN` must be set for runtime GitHub API access.
- Mutating token owner must match `mutating_credential_owner_by_environment`.
- Agent self-trigger filtering uses `agent_actor`.

### Classic PAT scopes (recommended minimum)

For **private repository** operation:

- `GITHUB_TOKEN`:
  - `repo`.

Important clarification for classic PATs:

- `repo` is a broad scope bundle.
- Selecting top-level `repo` includes all `repo:*` capabilities (`repo:status`, `repo_deployment`, `public_repo`, `repo:invite`, `security_events`).
- Because Agent1 currently uses classic PATs and writes to private repositories, `GITHUB_TOKEN` requires `repo`.
- Scope-level least privilege is limited with classic PATs because write/comment and private-repo read are bundled under `repo`.
- `notifications` is not additionally required for private-repo mode when `repo` is already granted (`/notifications` accepts `notifications` or `repo`).

For **public-only repository** operation:

- `GITHUB_TOKEN`:
  - `public_repo`,
  - `notifications`.

Notes:

- If your organization uses SSO enforcement, authorize `GITHUB_TOKEN` for the organization.

## Bit-mis Migration Checklist

If moving Agent1 identity to `bit-mis`:

1. Set `GITHUB_USER=bit-mis`.
2. Issue one classic PAT under `bit-mis` using the scope guidance above.
3. Set `GITHUB_TOKEN` in `.env`.
4. Align controls:
   - `controls/policies/default.json`:
     - `agent_actor`,
     - `mutating_credential_owner_by_environment.dev`,
     - `mutating_credential_owner_by_environment.prod`,
     - `mutating_credential_owner_by_environment.ci`.
5. After any protected control change, update `controls/policies/protected-approval.json` snapshot hashes and approval trail.

## Variable Reference

### Core backend runtime

- `DATABASE_URL`:
  - SQLAlchemy + Alembic database URL.
  - Required for non-dev deployments.
- `GITHUB_API_URL`:
  - GitHub API base URL.
  - Default: `https://api.github.com`.
- `GITHUB_USER`:
  - User-Agent identity used in GitHub API headers.
  - Should match operational actor identity (`bit-mis` for current setup).
- `GITHUB_TOKEN`:
  - Shared token for scanner, enrichment, comment/reply side effects, and owner preflight.
  - Required.
- `GITHUB_HTTP_TIMEOUT_SECONDS`:
  - HTTP timeout for GitHub client calls.
  - Default: `30`.

### Codex execution

- `OPENAI_API_KEY`:
  - Credential used by Codex CLI runtime when configured for OpenAI-backed execution.
- `CODEX_CLI_COMMAND`:
  - Codex CLI binary.
  - Default: `codex`.
- `CODEX_CLI_TIMEOUT_SECONDS`:
  - Task timeout ceiling for Codex execution.
  - Default: `900`.

### Runtime identity and mode overrides

- `RUNTIME_INSTANCE_ID`:
  - Optional explicit runtime instance identifier.
  - If empty, runtime auto-generates one.
- `RUNTIME_ENVIRONMENT`:
  - Optional explicit environment override (`dev`, `prod`, `ci`).
  - Docker entrypoint sets safe defaults per `AGENT1_DOCKER_MODE`.
- `RUNTIME_MODE_OVERRIDE`:
  - Optional explicit runtime mode override (`active`, `shadow`, `dry_run`).
  - Docker entrypoint sets safe defaults per `AGENT1_DOCKER_MODE`.
- `AGENT1_DOCKER_MODE`:
  - Docker preset mode selector.
  - `dev`: safe local mode (`dev` + `shadow` + local SQLite).
  - `active`: production-like mode (`prod` + `active`).
- `PORT`:
  - Backend bind port.
  - Default: `8000`.

### Observability

- `SENTRY_PYTHON_DSN`:
  - Sentry DSN for runtime exceptions and traces.
- `SENTRY_ENVIRONMENT`:
  - Sentry environment label.
  - Default: `dev`.
- `SENTRY_RELEASE`:
  - Sentry release version tag.
- `SENTRY_TRACES_SAMPLE_RATE`:
  - Sentry trace sample rate.
  - Default: `0.0`.
- `OTEL_SERVICE_NAME`:
  - OpenTelemetry service name.
  - Default: `agent1-backend`.
- `OTEL_TRACES_SAMPLER`:
  - OpenTelemetry sampler.
  - Default: `always_on`.
- `OTEL_PROPAGATORS`:
  - OpenTelemetry propagators list.
  - Default: `tracecontext,baggage`.

### Frontend runtime wiring

- `VITE_AGENT1_API_BASE_URL`:
  - Frontend API base URL.
  - In local compose flow this is set to `/api` and proxied to backend.
  - In Render this is sourced from backend service URL.
