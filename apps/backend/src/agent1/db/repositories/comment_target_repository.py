from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session

from agent1.core.contracts import CommentTargetRecord
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import OutboxActionType
from agent1.db.models import CommentTargetModel
from agent1.db.models import OutboxEntryModel


def _utc_now() -> datetime:

    '''
    Create timezone-aware UTC timestamp for comment-target persistence updates.

    Returns:
    datetime: Current UTC timestamp.
    '''

    return datetime.now(timezone.utc)


def _ensure_utc_timestamp(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)

    return timestamp.astimezone(timezone.utc)


class CommentTargetRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_comment_target(self, record: CommentTargetRecord) -> CommentTargetModel:

        '''
        Create persisted comment-target row from resolved routing-target contract.

        Args:
        record (CommentTargetRecord): Typed comment-target contract to persist.

        Returns:
        CommentTargetModel: Persisted comment-target model row.
        '''

        model = CommentTargetModel(
            target_id=record.target_id,
            outbox_id=record.outbox_id,
            job_id=record.job_id,
            entity_key=record.entity_key,
            environment=record.environment,
            target_type=record.target_type,
            target_identity=record.target_identity,
            issue_number=record.issue_number,
            pr_number=record.pr_number,
            thread_id=record.thread_id,
            review_comment_id=record.review_comment_id,
            path=record.path,
            line=record.line,
            side=record.side,
            resolved_at=_ensure_utc_timestamp(record.resolved_at),
            updated_at=_utc_now(),
        )
        self._session.add(model)
        self._session.flush()
        return model

    def get_comment_target_by_outbox_id(
        self,
        environment: EnvironmentName,
        outbox_id: str,
    ) -> CommentTargetModel | None:

        '''
        Create comment-target lookup result by environment and outbox identifier.

        Args:
        environment (EnvironmentName): Runtime environment value.
        outbox_id (str): Durable outbox identifier.

        Returns:
        CommentTargetModel | None: Matching comment-target row or None when missing.
        '''

        return (
            self._session.query(CommentTargetModel)
            .filter(CommentTargetModel.environment == environment)
            .filter(CommentTargetModel.outbox_id == outbox_id)
            .one_or_none()
        )

    def get_comment_target_by_idempotency_scope(
        self,
        environment: EnvironmentName,
        action_type: OutboxActionType,
        target_identity: str,
        idempotency_key: str,
    ) -> CommentTargetModel | None:

        '''
        Create comment-target lookup result by deterministic idempotency scope.

        Args:
        environment (EnvironmentName): Runtime environment value.
        action_type (OutboxActionType): Outbox side-effect action type.
        target_identity (str): Deterministic target identity.
        idempotency_key (str): Deterministic idempotency key.

        Returns:
        CommentTargetModel | None: Matching comment-target row or None when missing.
        '''

        return (
            self._session.query(CommentTargetModel)
            .join(
                OutboxEntryModel,
                OutboxEntryModel.outbox_id == CommentTargetModel.outbox_id,
            )
            .filter(CommentTargetModel.environment == environment)
            .filter(CommentTargetModel.target_identity == target_identity)
            .filter(OutboxEntryModel.environment == environment)
            .filter(OutboxEntryModel.action_type == action_type)
            .filter(OutboxEntryModel.idempotency_key == idempotency_key)
            .order_by(CommentTargetModel.resolved_at.desc())
            .first()
        )

    def list_comment_targets_for_job(
        self,
        job_id: str,
        limit: int,
        offset: int = 0,
    ) -> list[CommentTargetModel]:

        '''
        Create comment-target list for one job identifier.

        Args:
        job_id (str): Durable job identifier.
        limit (int): Maximum row count to return.
        offset (int): Pagination offset.

        Returns:
        list[CommentTargetModel]: Ordered comment-target rows.
        '''

        return (
            self._session.query(CommentTargetModel)
            .filter(CommentTargetModel.job_id == job_id)
            .order_by(CommentTargetModel.resolved_at.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_comment_targets_for_job(self, job_id: str) -> int:

        '''
        Create comment-target count for one job identifier.

        Args:
        job_id (str): Durable job identifier.

        Returns:
        int: Comment-target row count for the provided job.
        '''

        return (
            self._session.query(CommentTargetModel)
            .filter(CommentTargetModel.job_id == job_id)
            .count()
        )


__all__ = ['CommentTargetRepository']
