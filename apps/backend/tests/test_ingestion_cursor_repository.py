from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.db.repositories.ingestion_cursor_repository import IngestionCursorRepository


def test_get_cursor_returns_none_when_missing(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        repository = IngestionCursorRepository(session)

        cursor = repository.get_cursor('github_notifications')

        assert cursor is None


def test_set_cursor_creates_and_updates_cursor(session_factory: sessionmaker[Session]) -> None:
    first_timestamp = datetime(2026, 3, 3, 10, 0, 0, tzinfo=timezone.utc)
    second_timestamp = datetime(2026, 3, 3, 11, 0, 0, tzinfo=timezone.utc)

    with session_factory() as session:
        repository = IngestionCursorRepository(session)
        repository.set_cursor('github_notifications', first_timestamp)
        session.commit()

        first_read = repository.get_cursor('github_notifications')
        assert first_read == first_timestamp

        repository.set_cursor('github_notifications', second_timestamp)
        session.commit()

        second_read = repository.get_cursor('github_notifications')
        assert second_read == second_timestamp
