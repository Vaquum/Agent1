from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.contracts import CommentTargetRecord
from agent1.core.contracts import CommentTargetType
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import OutboxActionType
from agent1.core.contracts import RuntimeMode
from agent1.db.models import CommentTargetModel
from agent1.db.repositories.comment_target_repository import CommentTargetRepository
from agent1.db.repositories.job_repository import JobRepository
from agent1.db.repositories.outbox_repository import OutboxRepository


def _create_job_record(job_id: str) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        entity_key='Vaquum/Agent1#900',
        kind=JobKind.ISSUE,
        state=JobState.READY_TO_EXECUTE,
        idempotency_key=f'idem_{job_id}',
        lease_epoch=0,
        environment=EnvironmentName.DEV,
        mode=RuntimeMode.ACTIVE,
    )


def test_comment_target_repository_create_comment_target(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        job_repository = JobRepository(session)
        outbox_repository = OutboxRepository(session)
        comment_target_repository = CommentTargetRepository(session)
        job_repository.create_job(_create_job_record('job_comment_target_repo_1'))
        outbox_repository.create_outbox_entry(
            outbox_id='outbox_comment_target_repo_1',
            job_id='job_comment_target_repo_1',
            entity_key='Vaquum/Agent1#900',
            environment=EnvironmentName.DEV,
            action_type=OutboxActionType.PR_REVIEW_REPLY,
            target_identity='Vaquum/Agent1:pr:900:thread:PRRC_1:7001',
            payload={
                'repository': 'Vaquum/Agent1',
                'pull_number': 900,
                'review_comment_id': 7001,
                'body': 'reply',
            },
            idempotency_key='idem_comment_target_repo_1',
            job_lease_epoch=0,
        )
        created = comment_target_repository.create_comment_target(
            CommentTargetRecord(
                target_id='outbox_comment_target_repo_1',
                outbox_id='outbox_comment_target_repo_1',
                job_id='job_comment_target_repo_1',
                entity_key='Vaquum/Agent1#900',
                environment=EnvironmentName.DEV,
                target_type=CommentTargetType.PR_REVIEW_THREAD,
                target_identity='Vaquum/Agent1:pr:900:thread:PRRC_1:7001',
                issue_number=None,
                pr_number=900,
                thread_id='PRRC_1',
                review_comment_id=7001,
                path='apps/backend/src/agent1/main.py',
                line=12,
                side='RIGHT',
                resolved_at=datetime(2026, 3, 5, 0, 30, tzinfo=timezone.utc),
            ),
        )
        session.commit()
        persisted = (
            session.query(CommentTargetModel)
            .filter(CommentTargetModel.target_id == created.target_id)
            .one_or_none()
        )
        fetched_by_outbox = comment_target_repository.get_comment_target_by_outbox_id(
            environment=EnvironmentName.DEV,
            outbox_id='outbox_comment_target_repo_1',
        )
        fetched_by_idempotency_scope = comment_target_repository.get_comment_target_by_idempotency_scope(
            environment=EnvironmentName.DEV,
            action_type=OutboxActionType.PR_REVIEW_REPLY,
            target_identity='Vaquum/Agent1:pr:900:thread:PRRC_1:7001',
            idempotency_key='idem_comment_target_repo_1',
        )
        listed_for_job = comment_target_repository.list_comment_targets_for_job(
            job_id='job_comment_target_repo_1',
            limit=10,
        )
        count_for_job = comment_target_repository.count_comment_targets_for_job(
            job_id='job_comment_target_repo_1',
        )

    assert persisted is not None
    assert persisted.target_type == CommentTargetType.PR_REVIEW_THREAD
    assert persisted.review_comment_id == 7001
    assert fetched_by_outbox is not None
    assert fetched_by_idempotency_scope is not None
    assert len(listed_for_job) == 1
    assert count_for_job == 1
