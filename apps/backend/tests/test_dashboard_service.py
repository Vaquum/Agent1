from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.contracts import AgentEvent
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EventSource
from agent1.core.contracts import EventStatus
from agent1.core.contracts import EventType
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import RuntimeMode
from agent1.core.services.dashboard_service import DashboardService
from agent1.core.services.persistence_service import PersistenceService


def _create_job_record(job_id: str, entity_key: str) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        entity_key=entity_key,
        kind=JobKind.ISSUE,
        state=JobState.AWAITING_CONTEXT,
        idempotency_key=f'idem_{job_id}',
        lease_epoch=0,
        environment=EnvironmentName.DEV,
        mode=RuntimeMode.ACTIVE,
    )


def test_dashboard_service_returns_recent_snapshot(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    persistence_service.create_job(_create_job_record('job_dashboard_1', 'Vaquum/Agent1#101'))
    persistence_service.create_job(_create_job_record('job_dashboard_2', 'Vaquum/Agent1#102'))
    persistence_service.transition_job_state(
        'job_dashboard_1',
        to_state=JobState.EXECUTING,
        reason='start_one',
    )
    persistence_service.transition_job_state(
        'job_dashboard_2',
        to_state=JobState.EXECUTING,
        reason='start_two',
    )
    now = datetime.now(timezone.utc)
    persistence_service.append_event(
        AgentEvent(
            timestamp=now - timedelta(minutes=1),
            environment=EnvironmentName.DEV,
            trace_id='trc_dashboard_1',
            job_id='job_dashboard_1',
            entity_key='Vaquum/Agent1#101',
            source=EventSource.AGENT,
            event_type=EventType.STATE_TRANSITION,
            status=EventStatus.OK,
            details={'reason': 'start_one'},
        )
    )
    persistence_service.append_event(
        AgentEvent(
            timestamp=now,
            environment=EnvironmentName.DEV,
            trace_id='trc_dashboard_2',
            job_id='job_dashboard_2',
            entity_key='Vaquum/Agent1#102',
            source=EventSource.AGENT,
            event_type=EventType.STATE_TRANSITION,
            status=EventStatus.OK,
            details={'reason': 'start_two'},
        )
    )

    dashboard_service = DashboardService(session_factory=session_factory)
    overview = dashboard_service.get_overview(limit=1)

    assert len(overview.jobs) == 1
    assert len(overview.transitions) == 1
    assert len(overview.events) == 1
    assert overview.jobs[0].job_id == 'job_dashboard_2'
    assert overview.transitions[0].job_id == 'job_dashboard_2'
    assert overview.events[0].trace_id == 'trc_dashboard_2'
