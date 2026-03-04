from __future__ import annotations

from functools import lru_cache
import os
import socket

from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


def _default_runtime_instance_id() -> str:
    host_name = socket.gethostname().strip()
    process_id = os.getpid()
    return f'{host_name}:{process_id}'


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )

    database_url: str = 'sqlite+pysqlite:///./agent1.db'
    github_api_url: str = 'https://api.github.com'
    github_user: str = 'zero-bang'
    github_token: str = ''
    github_read_token: str = ''
    github_write_token: str = ''
    github_http_timeout_seconds: int = 30
    codex_cli_command: str = 'codex'
    codex_cli_timeout_seconds: int = 900
    runtime_instance_id: str = Field(default_factory=_default_runtime_instance_id)
    runtime_environment: str = 'dev'
    runtime_mode_override: str = ''
    sentry_python_dsn: str = ''
    sentry_environment: str = 'dev'
    sentry_release: str = ''
    sentry_traces_sample_rate: float = 0.0
    otel_service_name: str = 'agent1-backend'
    otel_traces_sampler: str = 'always_on'
    otel_propagators: str = 'tracecontext,baggage'


@lru_cache(maxsize=1)
def get_settings() -> Settings:

    '''
    Create cached runtime settings from environment configuration.

    Returns:
    Settings: Runtime settings object for Agent1 backend.
    '''

    return Settings()


__all__ = ['Settings', 'get_settings']
