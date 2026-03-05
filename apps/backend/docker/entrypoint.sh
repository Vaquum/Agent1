#!/usr/bin/env sh
set -eu

docker_mode="${AGENT1_DOCKER_MODE:-active}"
case "$docker_mode" in
  active)
    default_runtime_environment='prod'
    default_runtime_mode_override='active'
    ;;
  dev)
    echo 'dev mode use is prohibited for the time being' >&2
    exit 1
    ;;
  *)
    echo "Unsupported AGENT1_DOCKER_MODE: $docker_mode" >&2
    exit 1
    ;;
esac

export RUNTIME_ENVIRONMENT="${RUNTIME_ENVIRONMENT:-$default_runtime_environment}"
export RUNTIME_MODE_OVERRIDE="${RUNTIME_MODE_OVERRIDE:-$default_runtime_mode_override}"
if [ "${RUNTIME_INSTANCE_ID:-}" = '' ]; then
  unset RUNTIME_INSTANCE_ID
fi

if ! alembic upgrade head; then
  echo 'Alembic migration failed; backend startup is blocked (fail-closed).' >&2
  echo 'Run a manual migration repair, then rerun the same docker compose startup command.' >&2
  exit 1
fi

missing_event_chain_columns="$(
  python - <<'PY'
from __future__ import annotations
from sqlalchemy import create_engine
from sqlalchemy import inspect
from agent1.config.settings import get_settings

required_columns = {'event_seq', 'prev_event_hash', 'payload_hash'}
inspector = inspect(create_engine(get_settings().database_url))
if not inspector.has_table('event_journal'):
    print('1')
else:
    existing = {column['name'] for column in inspector.get_columns('event_journal')}
    print('1' if not required_columns.issubset(existing) else '0')
PY
)"
if [ "$missing_event_chain_columns" = '1' ]; then
  echo 'Detected missing event_journal chain columns; replaying migration 20260306_000012.'
  alembic stamp 20260305_000011
  alembic upgrade head
fi

exec uvicorn agent1.main:app --host 0.0.0.0 --port "${PORT:-8000}"
