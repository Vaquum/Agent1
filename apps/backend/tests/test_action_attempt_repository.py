from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.contracts import ActionAttemptStatus
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import OutboxActionType
from agent1.core.contracts import RuntimeMode
from agent1.db.repositories.action_attempt_repository import ActionAttemptRepository
from agent1.db.repositories.job_repository import JobRepository
from agent1.db.repositories.outbox_repository import OutboxRepository


def _create_job_record(job_id: str) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        entity_key='Vaquum/Agent1#700',
        kind=JobKind.ISSUE,
        state=JobState.READY_TO_EXECUTE,
        idempotency_key=f'idem_{job_id}',
        lease_epoch=0,
        environment=EnvironmentName.DEV,
        mode=RuntimeMode.ACTIVE,
    )


def test_action_attempt_repository_create_get_and_update(
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime(2026, 3, 4, 22, 0, tzinfo=timezone.utc)
    with session_factory() as session:
        job_repository = JobRepository(session)
        outbox_repository = OutboxRepository(session)
        attempt_repository = ActionAttemptRepository(session)
        job_repository.create_job(_create_job_record('job_action_attempt_1'))
        outbox_repository.create_outbox_entry(
            outbox_id='outbox_action_attempt_1',
            job_id='job_action_attempt_1',
            entity_key='Vaquum/Agent1#700',
            environment=EnvironmentName.DEV,
            action_type=OutboxActionType.ISSUE_COMMENT,
            target_identity='Vaquum/Agent1#700:issue',
            payload={'repository': 'Vaquum/Agent1', 'issue_number': 700, 'body': 'attempt'},
            idempotency_key='idem_action_attempt_1',
            job_lease_epoch=0,
        )
        attempt_repository.create_action_attempt(
            attempt_id='outbox_action_attempt_1:1',
            outbox_id='outbox_action_attempt_1',
            job_id='job_action_attempt_1',
            entity_key='Vaquum/Agent1#700',
            environment=EnvironmentName.DEV,
            action_type=OutboxActionType.ISSUE_COMMENT,
            status=ActionAttemptStatus.STARTED,
            error_message=None,
            attempt_started_at=now,
            attempt_completed_at=None,
        )
        session.commit()

    with session_factory() as update_session:
        repository = ActionAttemptRepository(update_session)
        updated = repository.mark_action_attempt_status(
            environment=EnvironmentName.DEV,
            attempt_id='outbox_action_attempt_1:1',
            status=ActionAttemptStatus.SUCCEEDED,
            completion_timestamp=now + timedelta(seconds=1),
        )
        attempt = repository.get_action_attempt(
            environment=EnvironmentName.DEV,
            attempt_id='outbox_action_attempt_1:1',
        )
        attempt_status = attempt.status if attempt is not None else None
        attempt_completed_at = attempt.attempt_completed_at if attempt is not None else None
        update_session.commit()

    assert updated is True
    assert attempt is not None
    assert attempt_status == ActionAttemptStatus.SUCCEEDED
    assert attempt_completed_at is not None


def test_action_attempt_repository_list_for_outbox(
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime(2026, 3, 4, 22, 10, tzinfo=timezone.utc)
    with session_factory() as session:
        job_repository = JobRepository(session)
        outbox_repository = OutboxRepository(session)
        attempt_repository = ActionAttemptRepository(session)
        job_repository.create_job(_create_job_record('job_action_attempt_2'))
        outbox_repository.create_outbox_entry(
            outbox_id='outbox_action_attempt_2',
            job_id='job_action_attempt_2',
            entity_key='Vaquum/Agent1#700',
            environment=EnvironmentName.DEV,
            action_type=OutboxActionType.ISSUE_COMMENT,
            target_identity='Vaquum/Agent1#700:issue',
            payload={'repository': 'Vaquum/Agent1', 'issue_number': 700, 'body': 'attempt'},
            idempotency_key='idem_action_attempt_2',
            job_lease_epoch=0,
        )
        attempt_repository.create_action_attempt(
            attempt_id='outbox_action_attempt_2:1',
            outbox_id='outbox_action_attempt_2',
            job_id='job_action_attempt_2',
            entity_key='Vaquum/Agent1#700',
            environment=EnvironmentName.DEV,
            action_type=OutboxActionType.ISSUE_COMMENT,
            status=ActionAttemptStatus.FAILED,
            error_message='dispatch_failure',
            attempt_started_at=now,
            attempt_completed_at=now + timedelta(seconds=1),
        )
        attempt_repository.create_action_attempt(
            attempt_id='outbox_action_attempt_2:2',
            outbox_id='outbox_action_attempt_2',
            job_id='job_action_attempt_2',
            entity_key='Vaquum/Agent1#700',
            environment=EnvironmentName.DEV,
            action_type=OutboxActionType.ISSUE_COMMENT,
            status=ActionAttemptStatus.SUCCEEDED,
            error_message=None,
            attempt_started_at=now + timedelta(seconds=2),
            attempt_completed_at=now + timedelta(seconds=3),
        )
        session.commit()

    with session_factory() as verification_session:
        repository = ActionAttemptRepository(verification_session)
        attempts = repository.list_action_attempts_for_outbox(
            outbox_id='outbox_action_attempt_2',
            limit=10,
        )
        job_attempts = repository.list_action_attempts_for_job(
            job_id='job_action_attempt_2',
            limit=10,
        )
        job_attempt_count = repository.count_action_attempts_for_job(
            job_id='job_action_attempt_2',
        )

    assert len(attempts) == 2
    assert attempts[0].attempt_id == 'outbox_action_attempt_2:1'
    assert attempts[1].attempt_id == 'outbox_action_attempt_2:2'
    assert len(job_attempts) == 2
    assert job_attempt_count == 2
