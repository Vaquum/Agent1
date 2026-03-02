from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.contracts import AgentEvent
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EventSource
from agent1.core.contracts import EventStatus
from agent1.core.contracts import EventType
from agent1.db.models import EventJournalModel
from agent1.db.repositories.event_repository import EventRepository


def test_append_event_creates_event_journal_row(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        repository = EventRepository(session)
        repository.append_event(
            AgentEvent(
                timestamp=datetime.now(timezone.utc),
                environment=EnvironmentName.DEV,
                trace_id='trc_1',
                job_id='job_1',
                entity_key='Vaquum/Agent1#1',
                source=EventSource.GITHUB,
                event_type=EventType.STATE_TRANSITION,
                status=EventStatus.OK,
                details={'message': 'event_persisted'},
            )
        )
        session.commit()

        row_count = session.query(EventJournalModel).count()

        assert row_count == 1


def test_list_recent_events_orders_descending_by_timestamp(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repository = EventRepository(session)
        repository.append_event(
            AgentEvent(
                timestamp=datetime.now(timezone.utc),
                environment=EnvironmentName.DEV,
                trace_id='trc_recent_1',
                job_id='job_recent_1',
                entity_key='Vaquum/Agent1#11',
                source=EventSource.GITHUB,
                event_type=EventType.STATE_TRANSITION,
                status=EventStatus.OK,
                details={'message': 'first'},
            )
        )
        repository.append_event(
            AgentEvent(
                timestamp=datetime.now(timezone.utc),
                environment=EnvironmentName.DEV,
                trace_id='trc_recent_2',
                job_id='job_recent_2',
                entity_key='Vaquum/Agent1#12',
                source=EventSource.AGENT,
                event_type=EventType.EXECUTION_RESULT,
                status=EventStatus.OK,
                details={'message': 'second'},
            )
        )
        session.commit()

        recent_events = repository.list_recent_events(limit=1)

        assert len(recent_events) == 1
        assert recent_events[0].trace_id == 'trc_recent_2'
