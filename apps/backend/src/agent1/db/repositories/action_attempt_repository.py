from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session

from agent1.core.contracts import ActionAttemptStatus
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import OutboxActionType
from agent1.db.models import ActionAttemptModel


def _utc_now() -> datetime:

    '''
    Create timezone-aware UTC timestamp for action-attempt persistence updates.

    Returns:
    datetime: Current UTC timestamp.
    '''

    return datetime.now(timezone.utc)


def _ensure_utc_timestamp(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)

    return timestamp.astimezone(timezone.utc)


class ActionAttemptRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_action_attempt(
        self,
        attempt_id: str,
        outbox_id: str,
        job_id: str,
        entity_key: str,
        environment: EnvironmentName,
        action_type: OutboxActionType,
        status: ActionAttemptStatus,
        error_message: str | None,
        attempt_started_at: datetime,
        attempt_completed_at: datetime | None = None,
    ) -> ActionAttemptModel:

        '''
        Create persisted action-attempt row from attempt lifecycle fields.

        Args:
        attempt_id (str): Durable attempt identifier.
        outbox_id (str): Durable outbox identifier.
        job_id (str): Durable job identifier.
        entity_key (str): Entity key for audit context.
        environment (EnvironmentName): Runtime environment value.
        action_type (OutboxActionType): Outbox action type value.
        status (ActionAttemptStatus): Attempt lifecycle status value.
        error_message (str | None): Optional deterministic failure summary.
        attempt_started_at (datetime): Attempt start timestamp.
        attempt_completed_at (datetime | None): Optional attempt completion timestamp.

        Returns:
        ActionAttemptModel: Persisted action-attempt model.
        '''

        normalized_started_at = _ensure_utc_timestamp(attempt_started_at)
        normalized_completed_at: datetime | None = None
        if attempt_completed_at is not None:
            normalized_completed_at = _ensure_utc_timestamp(attempt_completed_at)

        model = ActionAttemptModel(
            attempt_id=attempt_id,
            outbox_id=outbox_id,
            job_id=job_id,
            entity_key=entity_key,
            environment=environment,
            action_type=action_type,
            status=status,
            error_message=error_message,
            attempt_started_at=normalized_started_at,
            attempt_completed_at=normalized_completed_at,
        )
        self._session.add(model)
        self._session.flush()
        return model

    def get_action_attempt(
        self,
        environment: EnvironmentName,
        attempt_id: str,
    ) -> ActionAttemptModel | None:

        '''
        Create action-attempt lookup result by environment and attempt identifier.

        Args:
        environment (EnvironmentName): Runtime environment value.
        attempt_id (str): Durable attempt identifier.

        Returns:
        ActionAttemptModel | None: Matching action-attempt row or None when missing.
        '''

        return (
            self._session.query(ActionAttemptModel)
            .filter(ActionAttemptModel.environment == environment)
            .filter(ActionAttemptModel.attempt_id == attempt_id)
            .one_or_none()
        )

    def mark_action_attempt_status(
        self,
        environment: EnvironmentName,
        attempt_id: str,
        status: ActionAttemptStatus,
        completion_timestamp: datetime,
        error_message: str | None = None,
    ) -> bool:

        '''
        Compute action-attempt status update outcome with completion metadata.

        Args:
        environment (EnvironmentName): Runtime environment value.
        attempt_id (str): Durable attempt identifier.
        status (ActionAttemptStatus): Target attempt lifecycle status.
        completion_timestamp (datetime): Completion timestamp.
        error_message (str | None): Optional deterministic failure summary.

        Returns:
        bool: True when update succeeded, otherwise False.
        '''

        model = self.get_action_attempt(environment=environment, attempt_id=attempt_id)
        if model is None:
            return False

        model.status = status
        model.error_message = error_message
        model.attempt_completed_at = _ensure_utc_timestamp(completion_timestamp)
        model.updated_at = _utc_now()
        self._session.flush()
        return True

    def list_action_attempts_for_outbox(
        self,
        outbox_id: str,
        limit: int,
        offset: int = 0,
    ) -> list[ActionAttemptModel]:

        '''
        Create action-attempt list for one outbox identifier.

        Args:
        outbox_id (str): Durable outbox identifier.
        limit (int): Maximum row count to return.
        offset (int): Pagination offset.

        Returns:
        list[ActionAttemptModel]: Ordered action-attempt rows.
        '''

        return (
            self._session.query(ActionAttemptModel)
            .filter(ActionAttemptModel.outbox_id == outbox_id)
            .order_by(ActionAttemptModel.attempt_started_at.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def list_action_attempts_for_job(
        self,
        job_id: str,
        limit: int,
        offset: int = 0,
    ) -> list[ActionAttemptModel]:

        '''
        Create action-attempt list for one job identifier.

        Args:
        job_id (str): Durable job identifier.
        limit (int): Maximum row count to return.
        offset (int): Pagination offset.

        Returns:
        list[ActionAttemptModel]: Ordered action-attempt rows.
        '''

        return (
            self._session.query(ActionAttemptModel)
            .filter(ActionAttemptModel.job_id == job_id)
            .order_by(ActionAttemptModel.attempt_started_at.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_action_attempts_for_job(self, job_id: str) -> int:

        '''
        Create action-attempt count for one job identifier.

        Args:
        job_id (str): Durable job identifier.

        Returns:
        int: Action-attempt row count for the provided job.
        '''

        return (
            self._session.query(ActionAttemptModel)
            .filter(ActionAttemptModel.job_id == job_id)
            .count()
        )


__all__ = ['ActionAttemptRepository']
