from __future__ import annotations

from datetime import datetime
from datetime import timezone

from _pytest.monkeypatch import MonkeyPatch
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.services import persistence_service as persistence_service_module
from agent1.core.contracts import AgentEvent
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EventSource
from agent1.core.contracts import EventStatus
from agent1.core.contracts import EventType
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import RuntimeMode
from agent1.core.services.persistence_service import PersistenceService
from agent1.db.models import EventJournalModel


def _create_record() -> JobRecord:
    return JobRecord(
        job_id='job_service_1',
        entity_key='Vaquum/Agent1#2',
        kind=JobKind.ISSUE,
        state=JobState.AWAITING_CONTEXT,
        idempotency_key='idem_service_1',
        lease_epoch=0,
        environment=EnvironmentName.DEV,
        mode=RuntimeMode.ACTIVE,
    )


def test_persistence_service_job_and_event_flow(session_factory: sessionmaker[Session]) -> None:
    service = PersistenceService(session_factory=session_factory)

    created = service.create_job(_create_record())
    claimed = service.claim_job_lease(created.job_id, expected_lease_epoch=0)
    updated = service.transition_job_state(
        created.job_id,
        to_state=JobState.EXECUTING,
        reason='service_transition',
    )
    service.append_event(
        AgentEvent(
            timestamp=datetime.now(timezone.utc),
            environment=EnvironmentName.DEV,
            trace_id='trc_service_1',
            job_id=created.job_id,
            entity_key=created.entity_key,
            source=EventSource.AGENT,
            event_type=EventType.STATE_TRANSITION,
            status=EventStatus.OK,
            details={'message': 'service_event'},
        )
    )

    assert claimed is True
    assert updated.state == JobState.EXECUTING

    with session_factory() as verification_session:
        event_count = verification_session.query(EventJournalModel).count()

    assert event_count == 1


def test_persistence_service_append_event_emits_structured_log(
    session_factory: sessionmaker[Session],
    monkeypatch: MonkeyPatch,
) -> None:
    emitted_trace_ids: list[str] = []

    def _capture_event(event: AgentEvent) -> None:
        emitted_trace_ids.append(event.trace_id)

    monkeypatch.setattr(persistence_service_module, 'log_agent_event', _capture_event)
    service = PersistenceService(session_factory=session_factory)
    service.append_event(
        AgentEvent(
            timestamp=datetime.now(timezone.utc),
            environment=EnvironmentName.DEV,
            trace_id='trc_service_logging',
            job_id='job_service_logging',
            entity_key='Vaquum/Agent1#3',
            source=EventSource.AGENT,
            event_type=EventType.STATE_TRANSITION,
            status=EventStatus.OK,
            details={'message': 'log_capture'},
        )
    )

    assert emitted_trace_ids == ['trc_service_logging']
