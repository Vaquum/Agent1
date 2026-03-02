from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.db.repositories.ingestion_cursor_repository import IngestionCursorRepository
from agent1.db.session import create_session_factory


class IngressCursorStore(Protocol):
    def get_cursor(self, source_key: str) -> datetime | None:
        ...

    def set_cursor(self, source_key: str, cursor_timestamp: datetime) -> None:
        ...


class PersistenceIngressCursorStore:
    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self._session_factory = session_factory or create_session_factory()

    def get_cursor(self, source_key: str) -> datetime | None:

        '''
        Create cursor lookup result for an ingress source key.

        Args:
        source_key (str): Ingress source key identifier.

        Returns:
        datetime | None: Persisted cursor timestamp or None when missing.
        '''

        with self._session_factory() as session:
            repository = IngestionCursorRepository(session)
            return repository.get_cursor(source_key)

    def set_cursor(self, source_key: str, cursor_timestamp: datetime) -> None:

        '''
        Create persisted cursor update for an ingress source key.

        Args:
        source_key (str): Ingress source key identifier.
        cursor_timestamp (datetime): Cursor timestamp to persist.
        '''

        with self._session_factory() as session:
            repository = IngestionCursorRepository(session)
            repository.set_cursor(source_key, cursor_timestamp)
            session.commit()


__all__ = ['IngressCursorStore', 'PersistenceIngressCursorStore']
