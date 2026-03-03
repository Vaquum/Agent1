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

        persisted_row = session.query(EventJournalModel).one_or_none()

        assert persisted_row is not None
        assert persisted_row.event_seq == 1
        assert persisted_row.prev_event_hash is None
        assert persisted_row.payload_hash is not None
        assert len(persisted_row.payload_hash) == 64


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


def test_append_event_chain_increments_sequence_and_links_previous_hash(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repository = EventRepository(session)
        repository.append_event(
            AgentEvent(
                timestamp=datetime.now(timezone.utc),
                environment=EnvironmentName.DEV,
                trace_id='trc_chain_1',
                job_id='job_chain_1',
                entity_key='Vaquum/Agent1#3001',
                source=EventSource.AGENT,
                event_type=EventType.STATE_TRANSITION,
                status=EventStatus.OK,
                details={'message': 'chain_first'},
            )
        )
        repository.append_event(
            AgentEvent(
                timestamp=datetime.now(timezone.utc),
                environment=EnvironmentName.DEV,
                trace_id='trc_chain_2',
                job_id='job_chain_2',
                entity_key='Vaquum/Agent1#3002',
                source=EventSource.AGENT,
                event_type=EventType.STATE_TRANSITION,
                status=EventStatus.OK,
                details={'message': 'chain_second'},
            )
        )
        session.commit()
        rows = (
            session.query(EventJournalModel)
            .filter(EventJournalModel.environment == EnvironmentName.DEV)
            .order_by(EventJournalModel.event_seq.asc())
            .all()
        )

    assert len(rows) == 2
    assert rows[0].event_seq == 1
    assert rows[0].prev_event_hash is None
    assert rows[1].event_seq == 2
    assert rows[1].prev_event_hash == rows[0].payload_hash


def test_list_recent_events_applies_filters_and_count(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repository = EventRepository(session)
        repository.append_event(
            AgentEvent(
                timestamp=datetime.now(timezone.utc),
                environment=EnvironmentName.DEV,
                trace_id='trc_filter_1',
                job_id='job_filter_1',
                entity_key='Vaquum/Agent1#21',
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
                trace_id='trc_filter_2',
                job_id='job_filter_2',
                entity_key='Vaquum/Agent1#22',
                source=EventSource.AGENT,
                event_type=EventType.EXECUTION_RESULT,
                status=EventStatus.ERROR,
                details={'message': 'second'},
            )
        )
        session.commit()

        filtered_events = repository.list_recent_events(
            limit=10,
            offset=0,
            entity_key='Vaquum/Agent1#22',
            trace_id='trc_filter_2',
            status=EventStatus.ERROR,
        )
        filtered_count = repository.count_events(
            entity_key='Vaquum/Agent1#22',
            trace_id='trc_filter_2',
            status=EventStatus.ERROR,
        )

        assert len(filtered_events) == 1
        assert filtered_events[0].job_id == 'job_filter_2'
        assert filtered_count == 1


def test_count_recent_failed_transition_events(
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        repository = EventRepository(session)
        repository.append_event(
            AgentEvent(
                timestamp=now - timedelta(minutes=10),
                environment=EnvironmentName.DEV,
                trace_id='trc_old',
                job_id='job_old',
                entity_key='Vaquum/Agent1#23',
                source=EventSource.AGENT,
                event_type=EventType.STATE_TRANSITION,
                status=EventStatus.BLOCKED,
                details={'message': 'old'},
            )
        )
        repository.append_event(
            AgentEvent(
                timestamp=now,
                environment=EnvironmentName.DEV,
                trace_id='trc_recent_failed',
                job_id='job_recent_failed',
                entity_key='Vaquum/Agent1#24',
                source=EventSource.AGENT,
                event_type=EventType.STATE_TRANSITION,
                status=EventStatus.ERROR,
                details={'message': 'recent_failed'},
            )
        )
        repository.append_event(
            AgentEvent(
                timestamp=now,
                environment=EnvironmentName.DEV,
                trace_id='trc_recent_ok',
                job_id='job_recent_ok',
                entity_key='Vaquum/Agent1#25',
                source=EventSource.AGENT,
                event_type=EventType.STATE_TRANSITION,
                status=EventStatus.OK,
                details={'message': 'recent_ok'},
            )
        )
        session.commit()

        failed_count = repository.count_recent_failed_transition_events(
            window_start=now - timedelta(minutes=5),
        )

        assert failed_count == 1


def test_list_events_since_filters_by_environment_and_window(
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        repository = EventRepository(session)
        repository.append_event(
            AgentEvent(
                timestamp=now - timedelta(minutes=10),
                environment=EnvironmentName.DEV,
                trace_id='trc_old_dev',
                job_id='job_old_dev',
                entity_key='Vaquum/Agent1#30',
                source=EventSource.AGENT,
                event_type=EventType.STATE_TRANSITION,
                status=EventStatus.OK,
                details={'message': 'old_dev'},
            )
        )
        repository.append_event(
            AgentEvent(
                timestamp=now,
                environment=EnvironmentName.DEV,
                trace_id='trc_recent_dev',
                job_id='job_recent_dev',
                entity_key='Vaquum/Agent1#31',
                source=EventSource.POLICY,
                event_type=EventType.API_CALL,
                status=EventStatus.ERROR,
                details={'reason': 'mutating_lease_validation_failed'},
            )
        )
        repository.append_event(
            AgentEvent(
                timestamp=now,
                environment=EnvironmentName.PROD,
                trace_id='trc_recent_prod',
                job_id='job_recent_prod',
                entity_key='Vaquum/Agent1#32',
                source=EventSource.POLICY,
                event_type=EventType.API_CALL,
                status=EventStatus.ERROR,
                details={'reason': 'mutating_lease_validation_failed'},
            )
        )
        session.commit()

        recent_dev_events = repository.list_events_since(
            environment=EnvironmentName.DEV,
            window_start=now - timedelta(minutes=5),
        )
        recent_dev_policy_events = repository.list_events_since(
            environment=EnvironmentName.DEV,
            window_start=now - timedelta(minutes=5),
            source=EventSource.POLICY,
        )

        assert len(recent_dev_events) == 1
        assert recent_dev_events[0].trace_id == 'trc_recent_dev'
        assert len(recent_dev_policy_events) == 1
        assert recent_dev_policy_events[0].trace_id == 'trc_recent_dev'


def test_rebuild_event_chain_backfills_legacy_rows(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        first_legacy = EventJournalModel(
            timestamp=datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc),
            environment=EnvironmentName.DEV,
            trace_id='trc_legacy_1',
            job_id='job_legacy_1',
            entity_key='Vaquum/Agent1#4001',
            source=EventSource.AGENT,
            event_type=EventType.STATE_TRANSITION,
            status=EventStatus.OK,
            details={'message': 'legacy_first'},
        )
        second_legacy = EventJournalModel(
            timestamp=datetime(2026, 3, 6, 12, 1, tzinfo=timezone.utc),
            environment=EnvironmentName.DEV,
            trace_id='trc_legacy_2',
            job_id='job_legacy_2',
            entity_key='Vaquum/Agent1#4002',
            source=EventSource.AGENT,
            event_type=EventType.STATE_TRANSITION,
            status=EventStatus.OK,
            details={'message': 'legacy_second'},
        )
        session.add(first_legacy)
        session.add(second_legacy)
        session.commit()

        repository = EventRepository(session)
        rebuilt_count = repository.rebuild_event_chain(environment=EnvironmentName.DEV)
        session.commit()
        rows = (
            session.query(EventJournalModel)
            .filter(EventJournalModel.environment == EnvironmentName.DEV)
            .order_by(EventJournalModel.event_seq.asc())
            .all()
        )

    assert rebuilt_count == 2
    assert len(rows) == 2
    assert rows[0].event_seq == 1
    assert rows[0].payload_hash is not None
    assert rows[1].event_seq == 2
    assert rows[1].prev_event_hash == rows[0].payload_hash
    assert rows[1].payload_hash is not None


def test_verify_event_chain_detects_tampered_payload_hash(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repository = EventRepository(session)
        repository.append_event(
            AgentEvent(
                timestamp=datetime(2026, 3, 6, 13, 0, tzinfo=timezone.utc),
                environment=EnvironmentName.DEV,
                trace_id='trc_verify_1',
                job_id='job_verify_1',
                entity_key='Vaquum/Agent1#5001',
                source=EventSource.AGENT,
                event_type=EventType.STATE_TRANSITION,
                status=EventStatus.OK,
                details={'message': 'verify_first'},
            )
        )
        repository.append_event(
            AgentEvent(
                timestamp=datetime(2026, 3, 6, 13, 1, tzinfo=timezone.utc),
                environment=EnvironmentName.DEV,
                trace_id='trc_verify_2',
                job_id='job_verify_2',
                entity_key='Vaquum/Agent1#5002',
                source=EventSource.AGENT,
                event_type=EventType.STATE_TRANSITION,
                status=EventStatus.OK,
                details={'message': 'verify_second'},
            )
        )
        session.commit()
        tampered_row = (
            session.query(EventJournalModel)
            .filter(EventJournalModel.environment == EnvironmentName.DEV)
            .filter(EventJournalModel.event_seq == 2)
            .one()
        )
        tampered_row.payload_hash = '0' * 64
        session.flush()
        findings = repository.verify_event_chain(environment=EnvironmentName.DEV)

    assert len(findings) >= 1
    assert any('payload hash mismatch' in finding for finding in findings)


def test_list_recent_anomaly_events_filters_alert_signal_rows(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repository = EventRepository(session)
        repository.append_event(
            AgentEvent(
                timestamp=datetime(2026, 3, 6, 14, 0, tzinfo=timezone.utc),
                environment=EnvironmentName.DEV,
                trace_id='trc_anomaly_1',
                job_id='system:event_chain',
                entity_key='system:event_chain',
                source=EventSource.POLICY,
                event_type=EventType.API_CALL,
                status=EventStatus.ERROR,
                details={
                    'action': 'emit_alert_signal',
                    'alert_name': 'hash_chain_gap_anomalies',
                    'severity': 'sev1',
                    'reason': 'event_journal_chain_validation_failed',
                    'runbook': 'docs/Developer/runbooks/event-journal-chain-validation.md',
                },
            )
        )
        repository.append_event(
            AgentEvent(
                timestamp=datetime(2026, 3, 6, 14, 1, tzinfo=timezone.utc),
                environment=EnvironmentName.DEV,
                trace_id='trc_non_anomaly_1',
                job_id='job_non_anomaly_1',
                entity_key='Vaquum/Agent1#7001',
                source=EventSource.POLICY,
                event_type=EventType.API_CALL,
                status=EventStatus.ERROR,
                details={
                    'action': 'validate_mutating_lease',
                    'reason': 'mutating_lease_validation_failed',
                },
            )
        )
        session.commit()

        anomaly_events = repository.list_recent_anomaly_events(limit=10)
        anomaly_count = repository.count_anomaly_events()

    assert len(anomaly_events) == 1
    assert anomaly_events[0].trace_id == 'trc_anomaly_1'
    assert anomaly_count == 1
