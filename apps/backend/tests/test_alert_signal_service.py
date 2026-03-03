from __future__ import annotations

from datetime import datetime
from datetime import timezone

import pytest
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
from agent1.core.contracts import OutboxActionType
from agent1.core.contracts import OutboxWriteRequest
from agent1.core.contracts import RuntimeMode
from agent1.core.services.alert_signal_service import COMMENT_ROUTING_FAILURES_ALERT
from agent1.core.services.alert_signal_service import ELEVATED_FAILED_TRANSITION_RATES_ALERT
from agent1.core.services.alert_signal_service import OUTBOX_BACKLOG_GROWTH_ALERT
from agent1.core.services.alert_signal_service import STOP_THE_LINE_THRESHOLD_BREACH_ALERT
from agent1.core.services.alert_signal_service import AlertSignalService
from agent1.core.services.stop_the_line_service import StopTheLineBreach
from agent1.core.services.stop_the_line_service import StopTheLineDecision
from agent1.core.services.persistence_service import PersistenceService
from agent1.db.models import EventJournalModel


def _create_job_record(job_id: str) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        entity_key='Vaquum/Agent1#980',
        kind=JobKind.ISSUE,
        state=JobState.READY_TO_EXECUTE,
        idempotency_key=f'idem_{job_id}',
        lease_epoch=0,
        environment=EnvironmentName.DEV,
        mode=RuntimeMode.ACTIVE,
    )


def test_alert_signal_service_emits_comment_routing_failure_with_required_payload(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    alert_signal_service = AlertSignalService(persistence_service=persistence_service)

    alert_signal_service.emit_comment_routing_failure(
        environment=EnvironmentName.DEV,
        trace_id='trc_alert_comment_route',
        job_id='job_alert_comment_route',
        entity_key='Vaquum/Agent1#980',
        error_message='review-thread metadata missing',
    )

    with session_factory() as session:
        rows = session.query(EventJournalModel).order_by(EventJournalModel.id.asc()).all()

    assert len(rows) == 1
    assert rows[0].trace_id == 'trc_alert_comment_route'
    assert rows[0].job_id == 'job_alert_comment_route'
    assert rows[0].details['alert_name'] == COMMENT_ROUTING_FAILURES_ALERT
    assert rows[0].details['runbook'] == 'docs/Developer/runbooks/review-thread-routing-failures.md'


def test_alert_signal_service_emits_outbox_backlog_growth_signal(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    persistence_service.create_job(_create_job_record('job_alert_outbox_1'))
    persistence_service.append_outbox_entry(
        OutboxWriteRequest(
            outbox_id='outbox_alert_1',
            job_id='job_alert_outbox_1',
            entity_key='Vaquum/Agent1#980',
            environment=EnvironmentName.DEV,
            action_type=OutboxActionType.ISSUE_COMMENT,
            target_identity='Vaquum/Agent1#980:issue',
            payload={'repository': 'Vaquum/Agent1', 'issue_number': 980, 'body': 'hello'},
            idempotency_key='idem_outbox_alert_1',
            job_lease_epoch=0,
        ),
    )
    alert_signal_service = AlertSignalService(
        persistence_service=persistence_service,
        outbox_backlog_alert_threshold=1,
    )

    emitted = alert_signal_service.maybe_emit_outbox_backlog_growth(
        environment=EnvironmentName.DEV,
        trace_id='trc_alert_outbox_backlog',
    )

    with session_factory() as session:
        rows = session.query(EventJournalModel).order_by(EventJournalModel.id.asc()).all()

    assert emitted is True
    assert rows[-1].details['alert_name'] == OUTBOX_BACKLOG_GROWTH_ALERT
    assert rows[-1].details['trace_id'] == 'trc_alert_outbox_backlog'
    assert rows[-1].details['job_id'] == 'system:outbox'
    assert rows[-1].details['runbook'] == 'docs/Developer/runbooks/lease-and-idempotency-incidents.md'


def test_alert_signal_service_emits_failed_transition_rate_signal(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    persistence_service.append_event(
        AgentEvent(
            timestamp=datetime.now(timezone.utc),
            environment=EnvironmentName.DEV,
            trace_id='trc_failed_transition_1',
            job_id='job_failed_transition_1',
            entity_key='Vaquum/Agent1#981',
            source=EventSource.AGENT,
            event_type=EventType.STATE_TRANSITION,
            status=EventStatus.ERROR,
            details={'action': 'transition_job'},
        ),
    )
    alert_signal_service = AlertSignalService(
        persistence_service=persistence_service,
        failed_transition_alert_threshold=1,
        failed_transition_window_seconds=300,
    )

    emitted = alert_signal_service.maybe_emit_elevated_failed_transition_rates(
        environment=EnvironmentName.DEV,
        trace_id='trc_alert_failed_transition_rate',
    )

    with session_factory() as session:
        rows = session.query(EventJournalModel).order_by(EventJournalModel.id.asc()).all()

    assert emitted is True
    assert rows[-1].details['alert_name'] == ELEVATED_FAILED_TRANSITION_RATES_ALERT
    assert rows[-1].details['trace_id'] == 'trc_alert_failed_transition_rate'
    assert rows[-1].details['job_id'] == 'system:transitions'
    assert rows[-1].details['runbook'] == 'docs/Developer/runbooks/github-rate-limit-and-token-failures.md'


def test_alert_signal_service_emits_stop_the_line_threshold_breach_signal(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    alert_signal_service = AlertSignalService(persistence_service=persistence_service)
    decision = StopTheLineDecision(
        triggered=True,
        rollback_triggered=True,
        current_mode=RuntimeMode.ACTIVE,
        target_mode=RuntimeMode.SHADOW,
        reason='stop_the_line_triggered_mode_downgrade',
        breached_rules=[
            StopTheLineBreach(
                signal_id='error_rate',
                comparator='gte',
                threshold=0.05,
                observed_value=0.10,
            )
        ],
    )

    alert_id = alert_signal_service.maybe_emit_stop_the_line_threshold_breach(
        environment=EnvironmentName.DEV,
        trace_id='trc_stop_line_1',
        decision=decision,
        signal_values={
            'error_rate': 0.10,
            'lease_violation_rate': 0.0,
            'duplicate_side_effect_rate': 0.0,
            'policy_enforcement_failure_rate': 0.0,
        },
    )

    with session_factory() as session:
        rows = session.query(EventJournalModel).order_by(EventJournalModel.id.asc()).all()

    assert alert_id is not None
    assert rows[-1].details['alert_name'] == STOP_THE_LINE_THRESHOLD_BREACH_ALERT
    assert rows[-1].details['alert_id'] == alert_id
    assert rows[-1].details['trace_id'] == 'trc_stop_line_1'
    assert rows[-1].details['job_id'] == 'system:stop_the_line'
    assert rows[-1].details['rollback_triggered'] is True
    assert rows[-1].details['runbook'] == 'docs/Developer/runbooks/stop-the-line-alerts.md'


def test_alert_signal_service_records_stop_the_line_acknowledgement(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    alert_signal_service = AlertSignalService(persistence_service=persistence_service)

    acknowledged_at = alert_signal_service.acknowledge_stop_the_line_alert(
        environment=EnvironmentName.DEV,
        trace_id='trc_stop_line_ack_1',
        alert_id='stop_line:trc_stop_line_ack_1:123',
        operator_id='agent1-oncall-primary',
        acknowledgement_note='Incident commander assigned and containment started.',
    )

    with session_factory() as session:
        rows = session.query(EventJournalModel).order_by(EventJournalModel.id.asc()).all()

    assert rows[-1].details['action'] == 'acknowledge_stop_the_line_alert'
    assert rows[-1].details['alert_name'] == STOP_THE_LINE_THRESHOLD_BREACH_ALERT
    assert rows[-1].details['alert_id'] == 'stop_line:trc_stop_line_ack_1:123'
    assert rows[-1].details['operator_id'] == 'agent1-oncall-primary'
    assert (
        rows[-1].details['acknowledgement_note']
        == 'Incident commander assigned and containment started.'
    )
    assert rows[-1].details['runbook'] == 'docs/Developer/runbooks/stop-the-line-alerts.md'
    assert rows[-1].timestamp.replace(tzinfo=timezone.utc) == acknowledged_at


def test_alert_signal_service_collects_stop_the_line_signal_values(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    alert_signal_service = AlertSignalService(persistence_service=persistence_service)
    now = datetime.now(timezone.utc)
    persistence_service.append_event(
        AgentEvent(
            timestamp=now,
            environment=EnvironmentName.DEV,
            trace_id='trc_stop_line_collect_1',
            job_id='job_stop_line_collect_1',
            entity_key='Vaquum/Agent1#990',
            source=EventSource.AGENT,
            event_type=EventType.STATE_TRANSITION,
            status=EventStatus.OK,
            details={'action': 'transition_job'},
        ),
    )
    persistence_service.append_event(
        AgentEvent(
            timestamp=now,
            environment=EnvironmentName.DEV,
            trace_id='trc_stop_line_collect_2',
            job_id='job_stop_line_collect_2',
            entity_key='Vaquum/Agent1#991',
            source=EventSource.AGENT,
            event_type=EventType.STATE_TRANSITION,
            status=EventStatus.ERROR,
            details={'action': 'transition_job'},
        ),
    )
    persistence_service.append_event(
        AgentEvent(
            timestamp=now,
            environment=EnvironmentName.DEV,
            trace_id='trc_stop_line_collect_3',
            job_id='job_stop_line_collect_3',
            entity_key='Vaquum/Agent1#992',
            source=EventSource.POLICY,
            event_type=EventType.API_CALL,
            status=EventStatus.ERROR,
            details={'reason': 'mutating_lease_validation_failed'},
        ),
    )
    persistence_service.append_event(
        AgentEvent(
            timestamp=now,
            environment=EnvironmentName.DEV,
            trace_id='trc_stop_line_collect_4',
            job_id='job_stop_line_collect_4',
            entity_key='Vaquum/Agent1#993',
            source=EventSource.POLICY,
            event_type=EventType.API_CALL,
            status=EventStatus.ERROR,
            details={'reason': 'outbox_reconciliation_detected_confirmed_duplicate'},
        ),
    )
    persistence_service.append_event(
        AgentEvent(
            timestamp=now,
            environment=EnvironmentName.DEV,
            trace_id='trc_stop_line_collect_5',
            job_id='job_stop_line_collect_5',
            entity_key='Vaquum/Agent1#994',
            source=EventSource.POLICY,
            event_type=EventType.API_CALL,
            status=EventStatus.ERROR,
            details={'reason': 'codex_git_command_policy_blocked'},
        ),
    )

    signal_values = alert_signal_service.collect_stop_the_line_signal_values(
        environment=EnvironmentName.DEV,
        window_seconds=300,
    )

    assert signal_values['error_rate'] == pytest.approx(0.5)
    assert signal_values['lease_violation_rate'] == pytest.approx(1 / 3)
    assert signal_values['duplicate_side_effect_rate'] == pytest.approx(1 / 3)
    assert signal_values['policy_enforcement_failure_rate'] == pytest.approx(1 / 3)
