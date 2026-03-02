from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.contracts import AgentEvent
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.services.structured_event_logger import log_agent_event
from agent1.db.models import JobModel
from agent1.db.repositories.event_repository import EventRepository
from agent1.db.repositories.job_repository import JobRepository
from agent1.db.session import create_session_factory


def _to_job_record(model: JobModel) -> JobRecord:

    '''
    Create typed job contract from persisted job model.

    Args:
    model (JobModel): Persisted job model row.

    Returns:
    JobRecord: Typed job contract.
    '''

    return JobRecord(
        job_id=model.job_id,
        entity_key=model.entity_key,
        kind=model.kind,
        state=model.state,
        idempotency_key=model.idempotency_key,
        lease_epoch=model.lease_epoch,
        environment=model.environment,
        mode=model.mode,
    )


class PersistenceService:
    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self._session_factory = session_factory or create_session_factory()

    def create_job(self, record: JobRecord) -> JobRecord:

        '''
        Create persisted job and return normalized typed job contract.

        Args:
        record (JobRecord): Typed job contract to persist.

        Returns:
        JobRecord: Typed persisted job contract.
        '''

        with self._session_factory() as session:
            repository = JobRepository(session)
            model = repository.create_job(record)
            session.commit()
            return _to_job_record(model)

    def get_job(self, job_id: str) -> JobRecord | None:

        '''
        Create typed job lookup result by durable job identifier.

        Args:
        job_id (str): Durable job identifier.

        Returns:
        JobRecord | None: Typed job contract when found, otherwise None.
        '''

        with self._session_factory() as session:
            repository = JobRepository(session)
            model = repository.get_job_by_job_id(job_id)
            if model is None:
                return None

            return _to_job_record(model)

    def claim_job_lease(self, job_id: str, expected_lease_epoch: int) -> bool:

        '''
        Create lease claim attempt and return claim outcome.

        Args:
        job_id (str): Durable job identifier.
        expected_lease_epoch (int): Expected current lease epoch.

        Returns:
        bool: True when lease claim succeeded, otherwise False.
        '''

        with self._session_factory() as session:
            repository = JobRepository(session)
            claimed = repository.claim_job_lease(job_id, expected_lease_epoch)
            session.commit()
            return claimed

    def transition_job_state(self, job_id: str, to_state: JobState, reason: str) -> JobRecord:

        '''
        Create job state transition and return updated typed job contract.

        Args:
        job_id (str): Durable job identifier.
        to_state (JobState): Target lifecycle state.
        reason (str): Deterministic transition reason.

        Returns:
        JobRecord: Updated typed job contract.
        '''

        with self._session_factory() as session:
            repository = JobRepository(session)
            repository.transition_job_state(job_id, to_state, reason)
            model = repository.get_job_by_job_id(job_id)
            if model is None:
                message = f'Job not found after transition: {job_id}'
                raise ValueError(message)

            session.commit()
            return _to_job_record(model)

    def append_event(self, event: AgentEvent) -> None:

        '''
        Create persisted event journal row from typed event contract.

        Args:
        event (AgentEvent): Typed event contract to persist.
        '''

        with self._session_factory() as session:
            repository = EventRepository(session)
            repository.append_event(event)
            session.commit()
            log_agent_event(event)


__all__ = ['PersistenceService']
