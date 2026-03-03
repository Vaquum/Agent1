# Agent1 Backend

FastAPI backend for Agent1 orchestration, APIs, and adapters.

## Local commands

- Install: `pip install -e ".[dev]"`
- Run API: `uvicorn agent1.main:app --reload`
- Lint: `ruff check src`
- Typecheck: `mypy src`
- Migrate: `alembic upgrade head`

## Container runtime

- Build image from repository root: `docker build -f apps/backend/Dockerfile .`
- Container startup runs `alembic upgrade head` before serving API traffic.
