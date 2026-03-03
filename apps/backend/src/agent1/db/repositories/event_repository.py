from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from agent1.core.contracts import AgentEvent
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EventSource
from agent1.core.contracts import EventStatus
from agent1.core.contracts import EventType
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

    def count_recent_failed_transition_events(
        self,
        window_start: datetime,
    ) -> int:

        '''
        Create count of recent blocked or error transition events.

        Args:
        window_start (datetime): Inclusive lower bound for event timestamps.

        Returns:
        int: Recent failed transition event count.
        '''

        return (
            self._session.query(EventJournalModel)
            .filter(EventJournalModel.timestamp >= window_start)
            .filter(EventJournalModel.event_type == EventType.STATE_TRANSITION)
            .filter(
                EventJournalModel.status.in_(
                    [
                        EventStatus.BLOCKED,
                        EventStatus.ERROR,
                    ],
                ),
            )
            .count()
        )

    def list_events_since(
        self,
        environment: EnvironmentName,
        window_start: datetime,
        source: EventSource | None = None,
    ) -> list[EventJournalModel]:

        '''
        Create environment-scoped event journal rows since one inclusive timestamp.

        Args:
        environment (EnvironmentName): Runtime environment value.
        window_start (datetime): Inclusive lower bound for event timestamps.
        source (EventSource | None): Optional event source filter.

        Returns:
        list[EventJournalModel]: Ordered event journal rows since timestamp.
        '''

        query = (
            self._session.query(EventJournalModel)
            .filter(EventJournalModel.environment == environment)
            .filter(EventJournalModel.timestamp >= window_start)
        )
        if source is not None:
            query = query.filter(EventJournalModel.source == source)

        return query.order_by(EventJournalModel.timestamp.asc()).all()


__all__ = ['EventRepository']
