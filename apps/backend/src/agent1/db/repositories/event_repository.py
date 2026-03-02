from __future__ import annotations

from sqlalchemy.orm import Session

from agent1.core.contracts import AgentEvent
from agent1.core.contracts import EventStatus
from agent1.db.models import EventJournalModel


class EventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_event(self, event: AgentEvent) -> EventJournalModel:

        '''
        Create persisted event journal row from typed event contract.

        Args:
        event (AgentEvent): Typed event contract for journaling.

        Returns:
        EventJournalModel: Persisted event journal model.
        '''

        model = EventJournalModel(
            timestamp=event.timestamp,
            environment=event.environment,
            trace_id=event.trace_id,
            job_id=event.job_id,
            entity_key=event.entity_key,
            source=event.source,
            event_type=event.event_type,
            status=event.status,
            details=event.details,
        )
        self._session.add(model)
        self._session.flush()
        return model

    def list_recent_events(
        self,
        limit: int,
        offset: int = 0,
        entity_key: str | None = None,
        job_id: str | None = None,
        trace_id: str | None = None,
        status: EventStatus | None = None,
    ) -> list[EventJournalModel]:

        '''
        Create recent event journal list ordered by descending timestamp.

        Args:
        limit (int): Maximum number of recent rows to return.
        offset (int): Pagination offset for recent rows.
        entity_key (str | None): Optional entity key filter.
        job_id (str | None): Optional job identifier filter.
        trace_id (str | None): Optional trace identifier filter.
        status (EventStatus | None): Optional event status filter.

        Returns:
        list[EventJournalModel]: Ordered recent event journal rows.
        '''

        query = self._session.query(EventJournalModel)
        if entity_key is not None and entity_key.strip() != '':
            query = query.filter(EventJournalModel.entity_key == entity_key.strip())
        if job_id is not None and job_id.strip() != '':
            query = query.filter(EventJournalModel.job_id == job_id.strip())
        if trace_id is not None and trace_id.strip() != '':
            query = query.filter(EventJournalModel.trace_id == trace_id.strip())
        if status is not None:
            query = query.filter(EventJournalModel.status == status)

        return query.order_by(EventJournalModel.timestamp.desc()).offset(offset).limit(limit).all()

    def count_events(
        self,
        entity_key: str | None = None,
        job_id: str | None = None,
        trace_id: str | None = None,
        status: EventStatus | None = None,
    ) -> int:

        '''
        Create event journal row count for optional dashboard filters.

        Args:
        entity_key (str | None): Optional entity key filter.
        job_id (str | None): Optional job identifier filter.
        trace_id (str | None): Optional trace identifier filter.
        status (EventStatus | None): Optional event status filter.

        Returns:
        int: Event journal row count matching provided filters.
        '''

        query = self._session.query(EventJournalModel)
        if entity_key is not None and entity_key.strip() != '':
            query = query.filter(EventJournalModel.entity_key == entity_key.strip())
        if job_id is not None and job_id.strip() != '':
            query = query.filter(EventJournalModel.job_id == job_id.strip())
        if trace_id is not None and trace_id.strip() != '':
            query = query.filter(EventJournalModel.trace_id == trace_id.strip())
        if status is not None:
            query = query.filter(EventJournalModel.status == status)

        return query.count()


__all__ = ['EventRepository']
