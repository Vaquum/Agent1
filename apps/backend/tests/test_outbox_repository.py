from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import OutboxActionType
from agent1.core.contracts import OutboxStatus
from agent1.core.contracts import RuntimeMode
from agent1.core.services.idempotency_schema import build_canonical_idempotency_scope
from agent1.db.repositories.job_repository import JobRepository
from agent1.db.repositories.outbox_repository import OutboxRepository


def _create_job_record(job_id: str, idempotency_key: str) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        entity_key='Vaquum/Agent1#500',
        kind=JobKind.ISSUE,
        state=JobState.READY_TO_EXECUTE,
        idempotency_key=idempotency_key,
        lease_epoch=0,
        environment=EnvironmentName.DEV,
        mode=RuntimeMode.ACTIVE,
    )


def test_outbox_repository_create_lookup_and_dispatchable_filters(
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime(2026, 3, 4, 12, 0, tzinfo=timezone.utc)
    with session_factory() as session:
        job_repository = JobRepository(session)
        outbox_repository = OutboxRepository(session)
        job_repository.create_job(_create_job_record('job_outbox_1', 'idem_outbox_1'))
        outbox_repository.create_outbox_entry(
            outbox_id='outbox_1',
            job_id='job_outbox_1',
            entity_key='Vaquum/Agent1#500',
            environment=EnvironmentName.DEV,
            action_type=OutboxActionType.ISSUE_COMMENT,
            target_identity='Vaquum/Agent1#500:issue',
            payload={'repository': 'Vaquum/Agent1', 'issue_number': 500, 'body': 'hello'},
            idempotency_key='idem_side_effect_1',
            job_lease_epoch=0,
        )
        outbox_repository.create_outbox_entry(
            outbox_id='outbox_2',
            job_id='job_outbox_1',
            entity_key='Vaquum/Agent1#500',
            environment=EnvironmentName.DEV,
            action_type=OutboxActionType.ISSUE_COMMENT,
            target_identity='Vaquum/Agent1#500:issue',
            payload={'repository': 'Vaquum/Agent1', 'issue_number': 500, 'body': 'later'},
            idempotency_key='idem_side_effect_2',
            job_lease_epoch=0,
            next_attempt_at=now + timedelta(minutes=10),
        )
        outbox_repository.create_outbox_entry(
            outbox_id='outbox_3',
            job_id='job_outbox_1',
            entity_key='Vaquum/Agent1#500',
            environment=EnvironmentName.DEV,
            action_type=OutboxActionType.PR_REVIEW_REPLY,
            target_identity='Vaquum/Agent1#500:review:99',
            payload={
                'repository': 'Vaquum/Agent1',
                'pull_number': 500,
                'review_comment_id': 99,
                'body': 'reply',
            },
            idempotency_key='idem_side_effect_3',
            job_lease_epoch=0,
        )
        outbox_repository.mark_entry_sent(
            outbox_id='outbox_3',
            expected_lease_epoch=0,
            attempt_timestamp=now,
        )
        outbox_repository.mark_entry_confirmed(
            outbox_id='outbox_3',
            expected_lease_epoch=1,
            confirmation_timestamp=now,
        )
        session.commit()

    with session_factory() as verification_session:
        repository = OutboxRepository(verification_session)
        dispatchable_entries = repository.list_dispatchable_entries(
            limit=10,
            reference_timestamp=now,
        )
        backlog_count = repository.count_backlog_entries()
        lookup_entry = repository.get_outbox_entry_by_idempotency_scope(
            environment=EnvironmentName.DEV,
            action_type=OutboxActionType.ISSUE_COMMENT,
            target_identity='Vaquum/Agent1#500:issue',
            idempotency_key='idem_side_effect_1',
        )

    assert [entry.outbox_id for entry in dispatchable_entries] == ['outbox_1']
    assert backlog_count == 2
    assert lookup_entry is not None
    assert lookup_entry.outbox_id == 'outbox_1'
    assert lookup_entry.status == OutboxStatus.PENDING


def test_outbox_repository_status_updates_increment_lease_and_attempt_count(
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime(2026, 3, 4, 13, 0, tzinfo=timezone.utc)
    with session_factory() as session:
        job_repository = JobRepository(session)
        outbox_repository = OutboxRepository(session)
        job_repository.create_job(_create_job_record('job_outbox_2', 'idem_outbox_2'))
        outbox_repository.create_outbox_entry(
            outbox_id='outbox_status_1',
            job_id='job_outbox_2',
            entity_key='Vaquum/Agent1#500',
            environment=EnvironmentName.DEV,
            action_type=OutboxActionType.ISSUE_COMMENT,
            target_identity='Vaquum/Agent1#500:issue',
            payload={'repository': 'Vaquum/Agent1', 'issue_number': 500, 'body': 'hello'},
            idempotency_key='idem_status_1',
            job_lease_epoch=0,
        )
        session.commit()

    with session_factory() as sent_session:
        repository = OutboxRepository(sent_session)
        sent_updated = repository.mark_entry_sent(
            outbox_id='outbox_status_1',
            expected_lease_epoch=0,
            attempt_timestamp=now,
        )
        sent_session.commit()

    with session_factory() as failed_session:
        repository = OutboxRepository(failed_session)
        failed_updated = repository.mark_entry_failed(
            outbox_id='outbox_status_1',
            expected_lease_epoch=1,
            error_message='dispatch_error',
            retry_after_seconds=15,
            failure_timestamp=now + timedelta(seconds=1),
        )
        stale_confirm_updated = repository.mark_entry_confirmed(
            outbox_id='outbox_status_1',
            expected_lease_epoch=1,
            confirmation_timestamp=now + timedelta(seconds=2),
        )
        failed_session.commit()

    with session_factory() as aborted_session:
        repository = OutboxRepository(aborted_session)
        aborted_updated = repository.mark_entry_aborted(
            outbox_id='outbox_status_1',
            expected_lease_epoch=2,
            abort_reason='operator_abort',
            abort_timestamp=now + timedelta(seconds=3),
        )
        aborted_session.commit()

    with session_factory() as verification_session:
        repository = OutboxRepository(verification_session)
        entry = repository.get_outbox_entry_by_outbox_id('outbox_status_1')

    assert sent_updated is True
    assert failed_updated is True
    assert stale_confirm_updated is False
    assert aborted_updated is True
    assert entry is not None
    assert entry.status == OutboxStatus.ABORTED
    assert entry.attempt_count == 1
    assert entry.lease_epoch == 3
    assert entry.last_error == 'operator_abort'


def test_outbox_repository_enforces_idempotency_schema_when_components_provided(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        job_repository = JobRepository(session)
        outbox_repository = OutboxRepository(session)
        job_repository.create_job(_create_job_record('job_outbox_schema_1', 'idem_outbox_schema_1'))
        canonical_scope = build_canonical_idempotency_scope(
            entity_key='Vaquum/Agent1#500',
            action_type=OutboxActionType.ISSUE_COMMENT,
            target_identity='Vaquum/Agent1#500:issue',
            payload={'repository': 'Vaquum/Agent1', 'issue_number': 500, 'body': 'schema'},
            policy_version='0.1.0',
        )
        entry = outbox_repository.create_outbox_entry(
            outbox_id='outbox_schema_1',
            job_id='job_outbox_schema_1',
            entity_key='Vaquum/Agent1#500',
            environment=EnvironmentName.DEV,
            action_type=OutboxActionType.ISSUE_COMMENT,
            target_identity='Vaquum/Agent1#500:issue',
            payload={'repository': 'Vaquum/Agent1', 'issue_number': 500, 'body': 'schema'},
            idempotency_key=canonical_scope.idempotency_key,
            job_lease_epoch=0,
            idempotency_policy_version='0.1.0',
            idempotency_schema_version=canonical_scope.schema_version,
            idempotency_payload_hash=canonical_scope.payload_hash,
            idempotency_policy_version_hash=canonical_scope.policy_version_hash,
        )
        entry_schema_version = entry.idempotency_schema_version
        entry_payload_hash = entry.idempotency_payload_hash
        entry_policy_version_hash = entry.idempotency_policy_version_hash

        with pytest.raises(ValueError):
            outbox_repository.create_outbox_entry(
                outbox_id='outbox_schema_2',
                job_id='job_outbox_schema_1',
                entity_key='Vaquum/Agent1#500',
                environment=EnvironmentName.DEV,
                action_type=OutboxActionType.ISSUE_COMMENT,
                target_identity='Vaquum/Agent1#500:issue',
                payload={'repository': 'Vaquum/Agent1', 'issue_number': 500, 'body': 'schema'},
                idempotency_key='invalid_key',
                job_lease_epoch=0,
                idempotency_policy_version='0.1.0',
                idempotency_schema_version=canonical_scope.schema_version,
                idempotency_payload_hash=canonical_scope.payload_hash,
                idempotency_policy_version_hash=canonical_scope.policy_version_hash,
            )

        session.commit()

    assert entry_schema_version == canonical_scope.schema_version
    assert entry_payload_hash == canonical_scope.payload_hash
    assert entry_policy_version_hash == canonical_scope.policy_version_hash
