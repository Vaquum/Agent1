from __future__ import annotations

from agent1.db import session as session_module


def test_create_db_engine_is_cached() -> None:
    session_module.create_session_factory.cache_clear()
    session_module.create_db_engine.cache_clear()

    first_engine = session_module.create_db_engine()
    second_engine = session_module.create_db_engine()

    assert first_engine is second_engine


def test_create_session_factory_is_cached() -> None:
    session_module.create_session_factory.cache_clear()
    session_module.create_db_engine.cache_clear()

    first_session_factory = session_module.create_session_factory()
    second_session_factory = session_module.create_session_factory()

    assert first_session_factory is second_session_factory
