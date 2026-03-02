from __future__ import annotations

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

from agent1.config.settings import Settings
from agent1.config.settings import get_settings


def initialize_sentry(settings: Settings | None = None) -> bool:

    '''
    Create Sentry SDK runtime initialization for FastAPI error and trace capture.

    Args:
    settings (Settings | None): Optional runtime settings override.

    Returns:
    bool: True when Sentry initialization is enabled, otherwise False.
    '''

    runtime_settings = settings or get_settings()
    dsn = runtime_settings.sentry_python_dsn.strip()
    if dsn == '':
        return False

    release = runtime_settings.sentry_release.strip()
    sentry_sdk.init(
        dsn=dsn,
        environment=runtime_settings.sentry_environment,
        release=release if release != '' else None,
        integrations=[FastApiIntegration()],
        traces_sample_rate=runtime_settings.sentry_traces_sample_rate,
        send_default_pii=False,
    )
    return True


__all__ = ['initialize_sentry']
