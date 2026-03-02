from __future__ import annotations

from _pytest.monkeypatch import MonkeyPatch
import sentry_sdk

from agent1.config.settings import Settings
from agent1.core.services.sentry_runtime import initialize_sentry


def test_initialize_sentry_returns_false_without_dsn(monkeypatch: MonkeyPatch) -> None:
    called = {'value': False}

    def _fake_init(**_: object) -> None:
        called['value'] = True

    monkeypatch.setattr(sentry_sdk, 'init', _fake_init)
    enabled = initialize_sentry(settings=Settings(sentry_python_dsn=''))

    assert enabled is False
    assert called['value'] is False


def test_initialize_sentry_calls_sdk_with_expected_payload(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_init(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(sentry_sdk, 'init', _fake_init)
    enabled = initialize_sentry(
        settings=Settings(
            sentry_python_dsn='https://public@example.ingest.sentry.io/123',
            sentry_environment='dev',
            sentry_release='0.1.0',
            sentry_traces_sample_rate=0.25,
        )
    )

    assert enabled is True
    assert captured['dsn'] == 'https://public@example.ingest.sentry.io/123'
    assert captured['environment'] == 'dev'
    assert captured['release'] == '0.1.0'
    assert captured['traces_sample_rate'] == 0.25
    assert captured['send_default_pii'] is False
    assert isinstance(captured['integrations'], list)
    assert len(captured['integrations']) == 1
