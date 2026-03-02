from __future__ import annotations

from datetime import datetime
from datetime import timezone

from agent1.core.contracts import AgentEvent
from agent1.core.contracts import EventSource
from agent1.core.contracts import EventStatus
from agent1.core.contracts import EventType
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.services.persistence_service import PersistenceService
from agent1.core.workflow import require_transition


def _utc_now() -> datetime:

    '''
    Create current UTC timestamp for orchestrator event timestamps.

    Returns:
    datetime: Current UTC timestamp.
    '''

    return datetime.now(timezone.utc)


class JobOrchestrator:
    def __init__(self, persistence_service: PersistenceService | None = None) -> None:
        self._persistence_service = persistence_service or PersistenceService()

    def create_job(self, job_record: JobRecord, trace_id: str) -> JobRecord:

        '''
        Create new durable job and append corresponding creation event.

        Args:
        job_record (JobRecord): Job contract to persist.
        trace_id (str): Correlation trace identifier.

        Returns:
        JobRecord: Created durable job contract.
        '''

        created_job = self._persistence_service.create_job(job_record)
        self._persistence_service.append_event(
            AgentEvent(
                timestamp=_utc_now(),
                environment=created_job.environment,
                trace_id=trace_id,
                job_id=created_job.job_id,
                entity_key=created_job.entity_key,
                source=EventSource.AGENT,
                event_type=EventType.STATE_TRANSITION,
                status=EventStatus.OK,
                details={
                    'action': 'create_job',
                    'state': created_job.state.value,
                },
            )
        )
        return created_job

    def get_job(self, job_id: str) -> JobRecord | None:

        '''
        Create durable job lookup result by job identifier.

        Args:
        job_id (str): Durable job identifier.

        Returns:
        JobRecord | None: Durable job record or None when missing.
        '''

        return self._persistence_service.get_job(job_id)

    def claim_job(self, job_id: str, trace_id: str) -> bool:

        '''
        Create lease claim attempt and append lease-claim event result.

        Args:
        job_id (str): Durable job identifier.
        trace_id (str): Correlation trace identifier.

        Returns:
        bool: True when claim succeeded, otherwise False.
        '''

        existing_job = self._persistence_service.get_job(job_id)
        if existing_job is None:
            message = f'Job not found for claim: {job_id}'
            raise ValueError(message)

        claimed = self._persistence_service.claim_job_lease(job_id, existing_job.lease_epoch)
        self._persistence_service.append_event(
            AgentEvent(
                timestamp=_utc_now(),
                environment=existing_job.environment,
                trace_id=trace_id,
                job_id=existing_job.job_id,
                entity_key=existing_job.entity_key,
                source=EventSource.WATCHER,
                event_type=EventType.STATE_TRANSITION,
                status=EventStatus.OK if claimed else EventStatus.RETRY,
                details={
                    'action': 'claim_job_lease',
                    'expected_lease_epoch': existing_job.lease_epoch,
                    'claimed': claimed,
                },
            )
        )
        return claimed

    def transition_job(self, job_id: str, to_state: JobState, reason: str, trace_id: str) -> JobRecord:

        '''
        Create deterministic job transition after workflow-policy validation.

        Args:
        job_id (str): Durable job identifier.
        to_state (JobState): Target lifecycle state.
        reason (str): Deterministic transition reason.
        trace_id (str): Correlation trace identifier.

        Returns:
        JobRecord: Updated durable job contract.
        '''

        current_job = self._persistence_service.get_job(job_id)
        if current_job is None:
            message = f'Job not found for transition: {job_id}'
            raise ValueError(message)

        try:
            require_transition(current_job.state, to_state)
        except ValueError:
            self._persistence_service.append_event(
                AgentEvent(
                    timestamp=_utc_now(),
                    environment=current_job.environment,
                    trace_id=trace_id,
                    job_id=current_job.job_id,
                    entity_key=current_job.entity_key,
                    source=EventSource.POLICY,
                    event_type=EventType.STATE_TRANSITION,
                    status=EventStatus.BLOCKED,
                    details={
                        'action': 'transition_job',
                        'from_state': current_job.state.value,
                        'to_state': to_state.value,
                        'reason': reason,
                    },
                )
            )
            raise

        updated_job = self._persistence_service.transition_job_state(job_id, to_state, reason)
        self._persistence_service.append_event(
            AgentEvent(
                timestamp=_utc_now(),
                environment=updated_job.environment,
                trace_id=trace_id,
                job_id=updated_job.job_id,
                entity_key=updated_job.entity_key,
                source=EventSource.AGENT,
                event_type=EventType.STATE_TRANSITION,
                status=EventStatus.OK,
                details={
                    'action': 'transition_job',
                    'from_state': current_job.state.value,
                    'to_state': updated_job.state.value,
                    'reason': reason,
                },
            )
        )
        return updated_job


__all__ = ['JobOrchestrator']
