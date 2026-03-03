from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.contracts import AgentEvent
from agent1.core.contracts import ActionAttemptRecord
from agent1.core.contracts import ActionAttemptStatus
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EventSource
from agent1.core.contracts import EventStatus
from agent1.core.contracts import EventType
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import OutboxActionType
from agent1.core.contracts import OutboxWriteRequest
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
    assert overview.jobs_page.total == 2
    assert overview.transitions_page.total == 2
    assert overview.events_page.total == 2
    assert overview.filters.entity_key is None
    assert overview.filters.job_id is None
    assert overview.filters.trace_id is None
    assert overview.filters.status is None
    assert overview.jobs[0].job_id == 'job_dashboard_2'
    assert overview.transitions[0].job_id == 'job_dashboard_2'
    assert overview.events[0].trace_id == 'trc_dashboard_2'


def test_dashboard_service_applies_overview_filters(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    persistence_service.create_job(_create_job_record('job_dashboard_filter_1', 'Vaquum/Agent1#201'))
    persistence_service.create_job(_create_job_record('job_dashboard_filter_2', 'Vaquum/Agent1#202'))
    persistence_service.transition_job_state(
        'job_dashboard_filter_1',
        to_state=JobState.EXECUTING,
        reason='filter_one',
    )
    persistence_service.transition_job_state(
        'job_dashboard_filter_2',
        to_state=JobState.EXECUTING,
        reason='filter_two',
    )
    now = datetime.now(timezone.utc)
    persistence_service.append_event(
        AgentEvent(
            timestamp=now - timedelta(minutes=1),
            environment=EnvironmentName.DEV,
            trace_id='trc_dashboard_filter_1',
            job_id='job_dashboard_filter_1',
            entity_key='Vaquum/Agent1#201',
            source=EventSource.AGENT,
            event_type=EventType.STATE_TRANSITION,
            status=EventStatus.OK,
            details={'reason': 'filter_one'},
        )
    )
    persistence_service.append_event(
        AgentEvent(
            timestamp=now,
            environment=EnvironmentName.DEV,
            trace_id='trc_dashboard_filter_2',
            job_id='job_dashboard_filter_2',
            entity_key='Vaquum/Agent1#202',
            source=EventSource.AGENT,
            event_type=EventType.STATE_TRANSITION,
            status=EventStatus.ERROR,
            details={'reason': 'filter_two'},
        )
    )

    dashboard_service = DashboardService(session_factory=session_factory)
    overview = dashboard_service.get_overview(
        limit=10,
        offset=0,
        entity_key='Vaquum/Agent1#202',
        trace_id='trc_dashboard_filter_2',
        status=EventStatus.ERROR,
    )

    assert len(overview.jobs) == 1
    assert overview.jobs[0].job_id == 'job_dashboard_filter_2'
    assert len(overview.transitions) == 1
    assert overview.transitions[0].job_id == 'job_dashboard_filter_2'
    assert len(overview.events) == 1
    assert overview.events[0].trace_id == 'trc_dashboard_filter_2'
    assert overview.filters.entity_key == 'Vaquum/Agent1#202'
    assert overview.filters.trace_id == 'trc_dashboard_filter_2'
    assert overview.filters.status == EventStatus.ERROR


def test_dashboard_service_returns_job_timeline(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    persistence_service.create_job(_create_job_record('job_dashboard_timeline_1', 'Vaquum/Agent1#301'))
    persistence_service.transition_job_state(
        'job_dashboard_timeline_1',
        to_state=JobState.EXECUTING,
        reason='timeline_start',
    )
    now = datetime.now(timezone.utc)
    persistence_service.append_event(
        AgentEvent(
            timestamp=now,
            environment=EnvironmentName.DEV,
            trace_id='trc_dashboard_timeline_1',
            job_id='job_dashboard_timeline_1',
            entity_key='Vaquum/Agent1#301',
            source=EventSource.AGENT,
            event_type=EventType.STATE_TRANSITION,
            status=EventStatus.OK,
            details={'reason': 'timeline_start'},
        )
    )
    created_outbox = persistence_service.append_outbox_entry(
        OutboxWriteRequest(
            outbox_id='outbox_dashboard_timeline_1',
            job_id='job_dashboard_timeline_1',
            entity_key='Vaquum/Agent1#301',
            environment=EnvironmentName.DEV,
            action_type=OutboxActionType.ISSUE_COMMENT,
            target_identity='Vaquum/Agent1#301:issue',
            payload={
                'repository': 'Vaquum/Agent1',
                'issue_number': 301,
                'body': 'timeline attempt',
            },
            idempotency_key='idem_outbox_dashboard_timeline_1',
            job_lease_epoch=0,
        ),
    )
    persistence_service.append_action_attempt(
        ActionAttemptRecord(
            attempt_id='outbox_dashboard_timeline_1:1',
            outbox_id=created_outbox.outbox_id,
            job_id='job_dashboard_timeline_1',
            entity_key='Vaquum/Agent1#301',
            environment=EnvironmentName.DEV,
            action_type=OutboxActionType.ISSUE_COMMENT,
            status=ActionAttemptStatus.SUCCEEDED,
            error_message=None,
            attempt_started_at=now,
            attempt_completed_at=now + timedelta(seconds=1),
        ),
    )

    dashboard_service = DashboardService(session_factory=session_factory)
    timeline = dashboard_service.get_job_timeline(
        job_id='job_dashboard_timeline_1',
        limit=10,
        offset=0,
    )

    assert timeline is not None
    assert timeline.job.job_id == 'job_dashboard_timeline_1'
    assert timeline.transitions_page.total == 1
    assert timeline.events_page.total == 1
    assert timeline.action_attempts_page.total == 1
    assert len(timeline.transitions) == 1
    assert len(timeline.events) == 1
    assert len(timeline.action_attempts) == 1
    assert timeline.action_attempts[0].status == ActionAttemptStatus.SUCCEEDED


def test_dashboard_service_returns_none_for_missing_timeline_job(
    session_factory: sessionmaker[Session],
) -> None:
    dashboard_service = DashboardService(session_factory=session_factory)

    timeline = dashboard_service.get_job_timeline(
        job_id='missing_job',
        limit=10,
        offset=0,
    )

    assert timeline is None
