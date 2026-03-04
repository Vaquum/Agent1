#!/usr/bin/env sh
set -eu

docker_mode="${AGENT1_DOCKER_MODE:-dev}"
case "$docker_mode" in
  active)
    default_runtime_environment='prod'
    default_runtime_mode_override='active'
    ;;
  dev)
    default_runtime_environment='dev'
    default_runtime_mode_override='shadow'
    export DATABASE_URL='sqlite+pysqlite:////data/agent1-dev.db'
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

alembic upgrade head
exec uvicorn agent1.main:app --host 0.0.0.0 --port "${PORT:-8000}"
