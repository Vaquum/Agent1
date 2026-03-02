from __future__ import annotations

from sqlalchemy.orm import Session

from agent1.core.contracts import AgentEvent
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


__all__ = ['EventRepository']
