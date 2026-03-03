from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.contracts import AuditRunRecord
from agent1.core.contracts import AuditRunStatus
from agent1.core.contracts import EnvironmentName
from agent1.db.models import AuditRunModel
from agent1.db.repositories.audit_run_repository import AuditRunRepository


def test_audit_run_repository_create_audit_run(
    session_factory: sessionmaker[Session],
) -> None:
    started_at = datetime(2026, 3, 5, 11, 0, tzinfo=timezone.utc)
    with session_factory() as session:
        repository = AuditRunRepository(session)
        created = repository.create_audit_run(
            AuditRunRecord(
                audit_run_id='audit_run_repo_1',
                environment=EnvironmentName.DEV,
                audit_type='operational_readiness',
                status=AuditRunStatus.STARTED,
                started_at=started_at,
                completed_at=None,
                snapshot={'phase': 'start'},
            ),
        )
        session.commit()
        persisted = (
            session.query(AuditRunModel)
            .filter(AuditRunModel.environment == EnvironmentName.DEV)
            .filter(AuditRunModel.audit_run_id == 'audit_run_repo_1')
            .one_or_none()
        )

    assert created.audit_run_id == 'audit_run_repo_1'
    assert persisted is not None
    assert persisted.audit_type == 'operational_readiness'
    assert persisted.status == AuditRunStatus.STARTED


def test_audit_run_repository_list_audit_runs_with_filters(
    session_factory: sessionmaker[Session],
) -> None:
    started_at = datetime(2026, 3, 5, 11, 0, tzinfo=timezone.utc)
    with session_factory() as session:
        repository = AuditRunRepository(session)
        repository.create_audit_run(
            AuditRunRecord(
                audit_run_id='audit_run_repo_2',
                environment=EnvironmentName.DEV,
                audit_type='operational_readiness',
                status=AuditRunStatus.STARTED,
                started_at=started_at,
                completed_at=None,
                snapshot={'phase': 'start'},
            ),
        )
        repository.create_audit_run(
            AuditRunRecord(
                audit_run_id='audit_run_repo_3',
                environment=EnvironmentName.DEV,
                audit_type='operational_readiness',
                status=AuditRunStatus.SUCCEEDED,
                started_at=started_at.replace(hour=12),
                completed_at=started_at.replace(hour=12, minute=3),
                snapshot={'phase': 'done'},
            ),
        )
        repository.create_audit_run(
            AuditRunRecord(
                audit_run_id='audit_run_repo_4',
                environment=EnvironmentName.PROD,
                audit_type='release_promotion_gate',
                status=AuditRunStatus.FAILED,
                started_at=started_at.replace(hour=13),
                completed_at=started_at.replace(hour=13, minute=4),
                snapshot={'phase': 'failed'},
            ),
        )
        session.commit()

    with session_factory() as verification_session:
        repository = AuditRunRepository(verification_session)
        listed_dev = repository.list_audit_runs(
            environment=EnvironmentName.DEV,
            limit=10,
        )
        listed_dev_succeeded = repository.list_audit_runs(
            environment=EnvironmentName.DEV,
            limit=10,
            status=AuditRunStatus.SUCCEEDED,
        )
        listed_dev_type = repository.list_audit_runs(
            environment=EnvironmentName.DEV,
            limit=10,
            audit_type='operational_readiness',
        )

    assert len(listed_dev) == 2
    assert listed_dev[0].audit_run_id == 'audit_run_repo_3'
    assert listed_dev[1].audit_run_id == 'audit_run_repo_2'
    assert len(listed_dev_succeeded) == 1
    assert listed_dev_succeeded[0].audit_run_id == 'audit_run_repo_3'
    assert len(listed_dev_type) == 2
