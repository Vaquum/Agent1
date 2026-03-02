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
