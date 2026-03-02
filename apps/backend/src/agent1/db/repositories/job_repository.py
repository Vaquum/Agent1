from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import cast

from sqlalchemy import update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.db.models import JobModel
from agent1.db.models import JobTransitionModel


def _utc_now() -> datetime:

    '''
    Create timezone-aware UTC timestamp for persistence updates.

    Returns:
    datetime: Current UTC timestamp.
    '''

    return datetime.now(timezone.utc)


class JobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_job(self, record: JobRecord) -> JobModel:

        '''
        Create persisted job row from typed job contract.

        Args:
        record (JobRecord): Typed job contract for persistence.

        Returns:
        JobModel: Persisted job model instance.
        '''

        model = JobModel(
            job_id=record.job_id,
            entity_key=record.entity_key,
            kind=record.kind,
            state=record.state,
            idempotency_key=record.idempotency_key,
            lease_epoch=record.lease_epoch,
            environment=record.environment,
            mode=record.mode,
        )
        self._session.add(model)
        self._session.flush()
        return model

    def get_job_by_job_id(self, job_id: str) -> JobModel | None:

        '''
        Create job lookup result by external job identifier.

        Args:
        job_id (str): External durable job identifier.

        Returns:
        JobModel | None: Matching job model or None when missing.
        '''

        return self._session.query(JobModel).filter(JobModel.job_id == job_id).one_or_none()

    def claim_job_lease(self, job_id: str, expected_lease_epoch: int) -> bool:

        '''
        Create lease claim outcome using optimistic lease epoch fencing.

        Args:
        job_id (str): External durable job identifier.
        expected_lease_epoch (int): Expected current lease epoch value.

        Returns:
        bool: True when lease claim succeeded, otherwise False.
        '''

        statement = (
            update(JobModel)
            .where(JobModel.job_id == job_id)
            .where(JobModel.lease_epoch == expected_lease_epoch)
            .values(
                lease_epoch=expected_lease_epoch + 1,
                updated_at=_utc_now(),
            )
        )
        result = cast(CursorResult[tuple[object]], self._session.execute(statement))
        return result.rowcount == 1

    def transition_job_state(self, job_id: str, to_state: JobState, reason: str) -> JobTransitionModel:

        '''
        Create job state transition row and update current job state.

        Args:
        job_id (str): External durable job identifier.
        to_state (JobState): Target lifecycle state.
        reason (str): Deterministic transition reason.

        Returns:
        JobTransitionModel: Persisted transition model.
        '''

        job = self.get_job_by_job_id(job_id)
        if job is None:
            message = f'Job not found for transition: {job_id}'
            raise ValueError(message)

        transition = JobTransitionModel(
            job_id=job_id,
            from_state=job.state,
            to_state=to_state,
            reason=reason,
        )
        self._session.add(transition)
        job.state = to_state
        job.updated_at = _utc_now()
        self._session.flush()
        return transition

    def list_recent_jobs(self, limit: int) -> list[JobModel]:

        '''
        Create recent job list ordered by descending update timestamp.

        Args:
        limit (int): Maximum number of rows to return.

        Returns:
        list[JobModel]: Ordered recent job rows.
        '''

        return self._session.query(JobModel).order_by(JobModel.updated_at.desc()).limit(limit).all()

    def list_recent_transitions(self, limit: int) -> list[JobTransitionModel]:

        '''
        Create recent job transition list ordered by descending transition timestamp.

        Args:
        limit (int): Maximum number of rows to return.

        Returns:
        list[JobTransitionModel]: Ordered recent transition rows.
        '''

        return (
            self._session.query(JobTransitionModel)
            .order_by(JobTransitionModel.transition_at.desc())
            .limit(limit)
            .all()
        )


__all__ = ['JobRepository']
