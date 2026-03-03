from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session

from agent1.db.models import IngestionCursorModel


def _utc_now() -> datetime:

    '''
    Create timezone-aware UTC timestamp for cursor update writes.

    Returns:
    datetime: Current UTC timestamp.
    '''

    return datetime.now(timezone.utc)


def _ensure_utc_timestamp(cursor_timestamp: datetime) -> datetime:

    '''
    Create timezone-normalized UTC timestamp for cursor persistence paths.

    Args:
    cursor_timestamp (datetime): Timestamp candidate for normalization.

    Returns:
    datetime: Timezone-aware UTC timestamp.
    '''

    if cursor_timestamp.tzinfo is None:
        return cursor_timestamp.replace(tzinfo=timezone.utc)

    return cursor_timestamp.astimezone(timezone.utc)


class IngestionCursorRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_cursor(self, source_key: str) -> datetime | None:

        '''
        Create cursor timestamp lookup result for ingestion source key.

        Args:
        source_key (str): Ingestion source key identifier.

        Returns:
        datetime | None: Stored cursor timestamp or None when missing.
        '''

        cursor_model = (
            self._session.query(IngestionCursorModel)
            .filter(IngestionCursorModel.source_key == source_key)
            .one_or_none()
        )
        if cursor_model is None:
            return None

        return _ensure_utc_timestamp(cursor_model.cursor_timestamp)

    def set_cursor(self, source_key: str, cursor_timestamp: datetime) -> IngestionCursorModel:

        '''
        Create cursor upsert result for ingestion source key.

        Args:
        source_key (str): Ingestion source key identifier.
        cursor_timestamp (datetime): Cursor timestamp to persist.

        Returns:
        IngestionCursorModel: Persisted cursor model.
        '''

        cursor_model = (
            self._session.query(IngestionCursorModel)
            .filter(IngestionCursorModel.source_key == source_key)
            .one_or_none()
        )
        if cursor_model is None:
            cursor_model = IngestionCursorModel(
                source_key=source_key,
                cursor_timestamp=_ensure_utc_timestamp(cursor_timestamp),
            )
            self._session.add(cursor_model)
        else:
            cursor_model.cursor_timestamp = _ensure_utc_timestamp(cursor_timestamp)
            cursor_model.updated_at = _utc_now()

        self._session.flush()
        return cursor_model


__all__ = ['IngestionCursorRepository']
