from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.contracts import AuditRunStatus
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EventSource
from agent1.core.contracts import EventStatus
from agent1.core.contracts import EventType
from agent1.core.control_schemas import RetentionPolicyControl
from agent1.core.services.retention_purge_service import RetentionPurgeMode
from agent1.core.services.retention_purge_service import RetentionPurgeService
from agent1.core.services.retention_purge_service import render_retention_purge_report
from agent1.db.models import AuditRunModel
from agent1.db.models import EventJournalModel
from agent1.db.models import GitHubEventModel
from agent1.db.repositories.event_repository import EventRepository


def _create_retention_policy() -> RetentionPolicyControl:
    return RetentionPolicyControl.model_validate(
        {
            'entries': [
                {
                    'artifact_type': 'logs',
                    'environment': 'dev',
                    'retention_days': 7,
                },
                {
                    'artifact_type': 'logs',
                    'environment': 'prod',
                    'retention_days': 30,
                },
                {
                    'artifact_type': 'logs',
                    'environment': 'ci',
                    'retention_days': 7,
                },
                {
                    'artifact_type': 'traces',
                    'environment': 'dev',
                    'retention_days': 7,
                },
                {
                    'artifact_type': 'traces',
                    'environment': 'prod',
                    'retention_days': 30,
                },
                {
                    'artifact_type': 'traces',
                    'environment': 'ci',
                    'retention_days': 7,
                },
                {
                    'artifact_type': 'test_artifacts',
                    'environment': 'dev',
                    'retention_days': 7,
                },
                {
                    'artifact_type': 'test_artifacts',
                    'environment': 'prod',
                    'retention_days': 30,
                },
                {
                    'artifact_type': 'test_artifacts',
                    'environment': 'ci',
                    'retention_days': 7,
                },
            ],
        }
    )


def _seed_retention_rows(
    session_factory: sessionmaker[Session],
    reference_timestamp: datetime,
) -> None:
    old_timestamp = reference_timestamp - timedelta(days=8)
    recent_timestamp = reference_timestamp - timedelta(days=2)
    with session_factory() as session:
        session.add(
            EventJournalModel(
                timestamp=old_timestamp,
                environment=EnvironmentName.DEV,
                trace_id='trace_log_old_dev',
                job_id='job_log_old_dev',
                entity_key='Vaquum/Agent1#7001',
                source=EventSource.AGENT,
                event_type=EventType.STATE_TRANSITION,
                status=EventStatus.OK,
                details={'entry': 'old_dev'},
                event_seq=1,
                prev_event_hash=None,
                payload_hash='1' * 64,
            )
        )
        session.add(
            EventJournalModel(
                timestamp=recent_timestamp,
                environment=EnvironmentName.DEV,
                trace_id='trace_log_recent_dev',
                job_id='job_log_recent_dev',
                entity_key='Vaquum/Agent1#7002',
                source=EventSource.AGENT,
                event_type=EventType.STATE_TRANSITION,
                status=EventStatus.OK,
                details={'entry': 'recent_dev'},
                event_seq=2,
                prev_event_hash='1' * 64,
                payload_hash='2' * 64,
            )
        )
        session.add(
            EventJournalModel(
                timestamp=old_timestamp,
                environment=EnvironmentName.PROD,
                trace_id='trace_log_old_prod',
                job_id='job_log_old_prod',
                entity_key='Vaquum/Agent1#7003',
                source=EventSource.AGENT,
                event_type=EventType.STATE_TRANSITION,
                status=EventStatus.OK,
                details={'entry': 'old_prod'},
                event_seq=1,
                prev_event_hash=None,
                payload_hash='3' * 64,
            )
        )

        session.add(
            GitHubEventModel(
                source_event_id='trace_event_old_dev',
                source_timestamp_or_seq='2026-03-02T12:00:00Z',
                source_timestamp=old_timestamp,
                received_at=old_timestamp,
                environment=EnvironmentName.DEV,
                repository='Vaquum/Agent1',
                entity_number=7001,
                entity_key='Vaquum/Agent1#7001',
                actor='mikkokotila',
                ingress_event_type='issue_mention',
                ordering_decision='accepted',
                is_stale=False,
                stale_reason=None,
                details={'entry': 'old_dev'},
            )
        )
        session.add(
            GitHubEventModel(
                source_event_id='trace_event_recent_dev',
                source_timestamp_or_seq='2026-03-08T12:00:00Z',
                source_timestamp=recent_timestamp,
                received_at=recent_timestamp,
                environment=EnvironmentName.DEV,
                repository='Vaquum/Agent1',
                entity_number=7002,
                entity_key='Vaquum/Agent1#7002',
                actor='mikkokotila',
                ingress_event_type='issue_mention',
                ordering_decision='accepted',
                is_stale=False,
                stale_reason=None,
                details={'entry': 'recent_dev'},
            )
        )
        session.add(
            GitHubEventModel(
                source_event_id='trace_event_old_prod',
                source_timestamp_or_seq='2026-03-02T12:00:00Z',
                source_timestamp=old_timestamp,
                received_at=old_timestamp,
                environment=EnvironmentName.PROD,
                repository='Vaquum/Agent1',
                entity_number=7003,
                entity_key='Vaquum/Agent1#7003',
                actor='mikkokotila',
                ingress_event_type='issue_mention',
                ordering_decision='accepted',
                is_stale=False,
                stale_reason=None,
                details={'entry': 'old_prod'},
            )
        )

        session.add(
            AuditRunModel(
                audit_run_id='audit_old_dev',
                environment=EnvironmentName.DEV,
                audit_type='retention',
                status=AuditRunStatus.SUCCEEDED,
                started_at=old_timestamp,
                completed_at=old_timestamp + timedelta(minutes=1),
                snapshot={'entry': 'old_dev'},
            )
        )
        session.add(
            AuditRunModel(
                audit_run_id='audit_recent_dev',
                environment=EnvironmentName.DEV,
                audit_type='retention',
                status=AuditRunStatus.SUCCEEDED,
                started_at=recent_timestamp,
                completed_at=recent_timestamp + timedelta(minutes=1),
                snapshot={'entry': 'recent_dev'},
            )
        )
        session.add(
            AuditRunModel(
                audit_run_id='audit_old_prod',
                environment=EnvironmentName.PROD,
                audit_type='retention',
                status=AuditRunStatus.SUCCEEDED,
                started_at=old_timestamp,
                completed_at=old_timestamp + timedelta(minutes=1),
                snapshot={'entry': 'old_prod'},
            )
        )
        session.commit()


def test_retention_purge_service_dry_run_reports_candidates_without_deleting(
    session_factory: sessionmaker[Session],
) -> None:
    reference_timestamp = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
    _seed_retention_rows(session_factory, reference_timestamp)
    service = RetentionPurgeService(
        retention_policy=_create_retention_policy(),
        session_factory=session_factory,
    )

    report = service.run(
        environment=EnvironmentName.DEV,
        mode=RetentionPurgeMode.DRY_RUN,
        reference_timestamp=reference_timestamp,
    )
    serialized_report = render_retention_purge_report(report)

    assert report.total_candidates == 3
    assert report.total_purged == 0
    assert [artifact_report.artifact_type for artifact_report in report.artifact_reports] == [
        'logs',
        'traces',
        'test_artifacts',
    ]
    assert [artifact_report.candidate_count for artifact_report in report.artifact_reports] == [1, 1, 1]
    assert [artifact_report.purged_count for artifact_report in report.artifact_reports] == [0, 0, 0]
    assert serialized_report == render_retention_purge_report(report)
    assert '"mode":"dry_run"' in serialized_report
    assert '"total_candidates":3' in serialized_report

    with session_factory() as session:
        assert (
            session.query(EventJournalModel)
            .filter(EventJournalModel.environment == EnvironmentName.DEV)
            .count()
        ) == 2
        assert (
            session.query(GitHubEventModel)
            .filter(GitHubEventModel.environment == EnvironmentName.DEV)
            .count()
        ) == 2
        assert (
            session.query(AuditRunModel)
            .filter(AuditRunModel.environment == EnvironmentName.DEV)
            .count()
        ) == 2


def test_retention_purge_service_execute_deletes_candidates_and_preserves_scope(
    session_factory: sessionmaker[Session],
) -> None:
    reference_timestamp = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
    _seed_retention_rows(session_factory, reference_timestamp)
    service = RetentionPurgeService(
        retention_policy=_create_retention_policy(),
        session_factory=session_factory,
    )

    report = service.run(
        environment=EnvironmentName.DEV,
        mode=RetentionPurgeMode.EXECUTE,
        reference_timestamp=reference_timestamp,
    )

    logs_report = next(
        artifact_report
        for artifact_report in report.artifact_reports
        if artifact_report.artifact_type == 'logs'
    )

    assert report.total_candidates == 3
    assert report.total_purged == 3
    assert [artifact_report.candidate_count for artifact_report in report.artifact_reports] == [1, 1, 1]
    assert [artifact_report.purged_count for artifact_report in report.artifact_reports] == [1, 1, 1]
    assert logs_report.post_purge_rebuild_rows == 1

    with session_factory() as session:
        event_repository = EventRepository(session)
        assert (
            session.query(EventJournalModel)
            .filter(EventJournalModel.environment == EnvironmentName.DEV)
            .count()
        ) == 1
        assert (
            session.query(GitHubEventModel)
            .filter(GitHubEventModel.environment == EnvironmentName.DEV)
            .count()
        ) == 1
        assert (
            session.query(AuditRunModel)
            .filter(AuditRunModel.environment == EnvironmentName.DEV)
            .count()
        ) == 1
        assert (
            session.query(EventJournalModel)
            .filter(EventJournalModel.environment == EnvironmentName.PROD)
            .count()
        ) == 1
        assert (
            session.query(GitHubEventModel)
            .filter(GitHubEventModel.environment == EnvironmentName.PROD)
            .count()
        ) == 1
        assert (
            session.query(AuditRunModel)
            .filter(AuditRunModel.environment == EnvironmentName.PROD)
            .count()
        ) == 1
        assert event_repository.verify_event_chain(environment=EnvironmentName.DEV) == []


def test_retention_purge_service_blocks_prod_execute_without_explicit_acknowledgement(
    session_factory: sessionmaker[Session],
) -> None:
    service = RetentionPurgeService(
        retention_policy=_create_retention_policy(),
        session_factory=session_factory,
    )

    with pytest.raises(ValueError, match='allow_prod_execute=True'):
        service.run(
            environment=EnvironmentName.PROD,
            mode=RetentionPurgeMode.EXECUTE,
            reference_timestamp=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
        )


def test_retention_purge_service_validates_policy_scope_coverage(
    session_factory: sessionmaker[Session],
) -> None:
    retention_policy = _create_retention_policy()
    malformed_policy = RetentionPolicyControl.model_construct(
        entries=[
            entry
            for entry in retention_policy.entries
            if not (
                entry.artifact_type == 'logs'
                and entry.environment == EnvironmentName.CI
            )
        ]
    )

    with pytest.raises(ValueError, match='Retention purge policy scope coverage is invalid'):
        RetentionPurgeService(
            retention_policy=malformed_policy,
            session_factory=session_factory,
        )
