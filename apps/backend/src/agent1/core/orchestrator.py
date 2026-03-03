from __future__ import annotations

from datetime import datetime
from datetime import timezone

from agent1.core.contracts import AgentEvent
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EventSource
from agent1.core.contracts import EventStatus
from agent1.core.contracts import EventType
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import OutboxRecord
from agent1.core.contracts import OutboxWriteRequest
from agent1.core.ingress_contracts import GitHubIngressEvent
from agent1.core.ingress_contracts import IngressOrderingDecision
from agent1.core.ingress_contracts import PersistedIngressEvent
from agent1.core.services.alert_signal_service import AlertSignalService
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
        self._alert_signal_service = AlertSignalService(self._persistence_service)

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

    def validate_mutating_lease(self, job_id: str, expected_lease_epoch: int, trace_id: str) -> bool:

        '''
        Create mutating lease validation outcome and append lease-fencing event result.

        Args:
        job_id (str): Durable job identifier.
        expected_lease_epoch (int): Expected lease epoch for mutating side effects.
        trace_id (str): Correlation trace identifier.

        Returns:
        bool: True when lease validation succeeded, otherwise False.
        '''

        existing_job = self._persistence_service.get_job(job_id)
        if existing_job is None:
            message = f'Job not found for lease validation: {job_id}'
            raise ValueError(message)

        valid = self._persistence_service.validate_job_lease_epoch(job_id, expected_lease_epoch)
        self._persistence_service.append_event(
            AgentEvent(
                timestamp=_utc_now(),
                environment=existing_job.environment,
                trace_id=trace_id,
                job_id=existing_job.job_id,
                entity_key=existing_job.entity_key,
                source=EventSource.POLICY,
                event_type=EventType.API_CALL,
                status=EventStatus.OK if valid else EventStatus.BLOCKED,
                details={
                    'action': 'validate_mutating_lease',
                    'expected_lease_epoch': expected_lease_epoch,
                    'current_lease_epoch': existing_job.lease_epoch,
                    'valid': valid,
                },
            )
        )
        if valid is False:
            self._alert_signal_service.emit_lease_violation(
                environment=existing_job.environment,
                trace_id=trace_id,
                job_id=existing_job.job_id,
                entity_key=existing_job.entity_key,
                expected_lease_epoch=expected_lease_epoch,
                current_lease_epoch=existing_job.lease_epoch,
            )
        return valid

    def emit_comment_routing_failure_alert(
        self,
        environment: EnvironmentName,
        trace_id: str,
        job_id: str,
        entity_key: str,
        error_message: str,
    ) -> None:

        '''
        Create comment-routing failure alert signal for strict review-thread routing incidents.

        Args:
        environment (EnvironmentName): Runtime environment value.
        trace_id (str): Correlation trace identifier.
        job_id (str): Durable job identifier.
        entity_key (str): Entity key associated with the alert.
        error_message (str): Deterministic routing failure summary.
        '''

        self._alert_signal_service.emit_comment_routing_failure(
            environment=environment,
            trace_id=trace_id,
            job_id=job_id,
            entity_key=entity_key,
            error_message=error_message,
        )

    def persist_ingress_event(
        self,
        ingress_event: GitHubIngressEvent,
        environment: EnvironmentName,
    ) -> PersistedIngressEvent:

        '''
        Create persisted ingress event ordering record and append ingest audit event.

        Args:
        ingress_event (GitHubIngressEvent): Raw ingress event payload.
        environment (EnvironmentName): Runtime environment value.

        Returns:
        PersistedIngressEvent: Persisted ingress ordering decision payload.
        '''

        persisted_event = self._persistence_service.persist_ingress_event(
            ingress_event=ingress_event,
            environment=environment,
        )
        status = EventStatus.OK
        if persisted_event.ordering_decision == IngressOrderingDecision.STALE:
            status = EventStatus.RETRY

        self._persistence_service.append_event(
            AgentEvent(
                timestamp=persisted_event.received_at,
                environment=environment,
                trace_id=f"trc_{ingress_event.event_id}",
                job_id=f"ingress:{ingress_event.event_id}",
                entity_key=persisted_event.entity_key,
                source=EventSource.GITHUB,
                event_type=EventType.API_CALL,
                status=status,
                details={
                    'action': 'persist_ingress_event',
                    'source_event_id': persisted_event.source_event_id,
                    'source_timestamp_or_seq': persisted_event.source_timestamp_or_seq,
                    'received_at': persisted_event.received_at.isoformat(),
                    'ordering_decision': persisted_event.ordering_decision.value,
                    'stale_reason': persisted_event.stale_reason,
                },
            )
        )
        return persisted_event

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

    def transition_job_with_outbox(
        self,
        job_id: str,
        to_state: JobState,
        reason: str,
        trace_id: str,
        outbox_requests: list[OutboxWriteRequest],
    ) -> tuple[JobRecord, list[OutboxRecord]]:

        '''
        Create deterministic job transition with atomic outbox intent persistence.

        Args:
        job_id (str): Durable job identifier.
        to_state (JobState): Target lifecycle state.
        reason (str): Deterministic transition reason.
        trace_id (str): Correlation trace identifier.
        outbox_requests (list[OutboxWriteRequest]): Outbox intents to persist atomically.

        Returns:
        tuple[JobRecord, list[OutboxRecord]]: Updated job and persisted outbox intents.
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
                        'action': 'transition_job_with_outbox',
                        'from_state': current_job.state.value,
                        'to_state': to_state.value,
                        'reason': reason,
                    },
                )
            )
            raise

        updated_job, outbox_records = self._persistence_service.transition_job_state_with_outbox(
            job_id,
            to_state,
            reason,
            outbox_requests,
        )
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
                    'action': 'transition_job_with_outbox',
                    'from_state': current_job.state.value,
                    'to_state': updated_job.state.value,
                    'reason': reason,
                    'outbox_count': len(outbox_records),
                },
            )
        )
        return updated_job, outbox_records


__all__ = ['JobOrchestrator']
