from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.contracts import AgentEvent
from agent1.core.contracts import ActionAttemptRecord
from agent1.core.contracts import ActionAttemptStatus
from agent1.core.contracts import AuditRunRecord
from agent1.core.contracts import AuditRunStatus
from agent1.core.contracts import CommentTargetRecord
from agent1.core.contracts import EntityRecord
from agent1.core.contracts import EntityType
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EventSource
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import OutboxActionType
from agent1.core.contracts import OutboxRecord
from agent1.core.contracts import OutboxWriteRequest
from agent1.core.contracts import WatcherStatus
from agent1.core.ingress_contracts import GitHubIngressEvent
from agent1.core.ingress_contracts import PersistedIngressEvent
from agent1.core.watcher import WatcherState
from agent1.core.services.structured_event_logger import log_agent_event
from agent1.db.models import ActionAttemptModel
from agent1.db.models import AuditRunModel
from agent1.db.models import CommentTargetModel
from agent1.db.models import EventJournalModel
from agent1.db.models import JobModel
from agent1.db.models import EntityModel
from agent1.db.models import OutboxEntryModel
from agent1.db.models import WatcherStateModel
from agent1.db.repositories.action_attempt_repository import ActionAttemptRepository
from agent1.db.repositories.audit_run_repository import AuditRunRepository
from agent1.db.repositories.comment_target_repository import CommentTargetRepository
from agent1.db.repositories.entity_repository import EntityRepository
from agent1.db.repositories.event_repository import EventRepository
from agent1.db.repositories.github_event_repository import GitHubEventRepository
from agent1.db.repositories.job_repository import JobRepository
from agent1.db.repositories.outbox_repository import OutboxRepository
from agent1.db.repositories.outbox_repository import IdempotencyScopeViolation
from agent1.db.repositories.watcher_repository import WatcherRepository
from agent1.db.session import create_session_factory


def _to_agent_event(model: EventJournalModel) -> AgentEvent:

    '''
    Create typed agent-event contract from persisted event-journal model row.

    Args:
    model (EventJournalModel): Persisted event-journal model row.

    Returns:
    AgentEvent: Typed event contract payload.
    '''

    return AgentEvent(
        timestamp=model.timestamp,
        environment=model.environment,
        event_seq=model.event_seq,
        prev_event_hash=model.prev_event_hash,
        payload_hash=model.payload_hash,
        trace_id=model.trace_id,
        job_id=model.job_id,
        entity_key=model.entity_key,
        source=model.source,
        event_type=model.event_type,
        status=model.status,
        details=model.details,
    )


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


def _to_entity_record(model: EntityModel) -> EntityRecord:

    '''
    Create typed entity contract from persisted entity model.

    Args:
    model (EntityModel): Persisted entity model row.

    Returns:
    EntityRecord: Typed entity contract.
    '''

    return EntityRecord(
        entity_key=model.entity_key,
        repository=model.repository,
        entity_number=model.entity_number,
        entity_type=model.entity_type,
        environment=model.environment,
        is_sandbox=model.is_sandbox,
        is_closed=model.is_closed,
        last_event_at=model.last_event_at,
    )


def _to_action_attempt_record(model: ActionAttemptModel) -> ActionAttemptRecord:

    '''
    Create typed action-attempt contract from persisted action-attempt model.

    Args:
    model (ActionAttemptModel): Persisted action-attempt model row.

    Returns:
    ActionAttemptRecord: Typed action-attempt contract.
    '''

    return ActionAttemptRecord(
        attempt_id=model.attempt_id,
        outbox_id=model.outbox_id,
        job_id=model.job_id,
        entity_key=model.entity_key,
        environment=model.environment,
        action_type=model.action_type,
        status=model.status,
        error_message=model.error_message,
        attempt_started_at=model.attempt_started_at,
        attempt_completed_at=model.attempt_completed_at,
    )


def _to_audit_run_record(model: AuditRunModel) -> AuditRunRecord:

    '''
    Create typed audit-run contract from persisted audit-run model.

    Args:
    model (AuditRunModel): Persisted audit-run model row.

    Returns:
    AuditRunRecord: Typed audit-run contract.
    '''

    return AuditRunRecord(
        audit_run_id=model.audit_run_id,
        environment=model.environment,
        audit_type=model.audit_type,
        status=model.status,
        started_at=model.started_at,
        completed_at=model.completed_at,
        snapshot=model.snapshot,
    )


def _to_comment_target_record(model: CommentTargetModel) -> CommentTargetRecord:

    '''
    Create typed comment-target contract from persisted comment-target model.

    Args:
    model (CommentTargetModel): Persisted comment-target model row.

    Returns:
    CommentTargetRecord: Typed comment-target contract.
    '''

    return CommentTargetRecord(
        target_id=model.target_id,
        outbox_id=model.outbox_id,
        job_id=model.job_id,
        entity_key=model.entity_key,
        environment=model.environment,
        target_type=model.target_type,
        target_identity=model.target_identity,
        issue_number=model.issue_number,
        pr_number=model.pr_number,
        thread_id=model.thread_id,
        review_comment_id=model.review_comment_id,
        path=model.path,
        line=model.line,
        side=model.side,
        resolved_at=model.resolved_at,
    )


def _to_outbox_record(model: OutboxEntryModel) -> OutboxRecord:

    '''
    Create typed outbox contract from persisted outbox model.

    Args:
    model (OutboxEntryModel): Persisted outbox model row.

    Returns:
    OutboxRecord: Typed outbox contract.
    '''

    return OutboxRecord(
        outbox_id=model.outbox_id,
        job_id=model.job_id,
        entity_key=model.entity_key,
        environment=model.environment,
        action_type=model.action_type,
        target_identity=model.target_identity,
        payload=model.payload,
        idempotency_key=model.idempotency_key,
        idempotency_schema_version=model.idempotency_schema_version,
        idempotency_payload_hash=model.idempotency_payload_hash,
        idempotency_policy_version_hash=model.idempotency_policy_version_hash,
        job_lease_epoch=model.job_lease_epoch,
        status=model.status,
        attempt_count=model.attempt_count,
        lease_epoch=model.lease_epoch,
        next_attempt_at=model.next_attempt_at,
        last_attempt_at=model.last_attempt_at,
        last_error=model.last_error,
    )


def _to_watcher_state(model: WatcherStateModel) -> WatcherState:

    '''
    Create typed watcher state contract from persisted watcher model.

    Args:
    model (WatcherStateModel): Persisted watcher model row.

    Returns:
    WatcherState: Typed watcher state contract.
    '''

    return WatcherState(
        entity_key=model.entity_key,
        job_id=model.job_id,
        next_check_at=model.next_check_at,
        last_heartbeat_at=model.last_heartbeat_at,
        idle_cycles=model.idle_cycles,
        watch_deadline_at=model.watch_deadline_at,
        checkpoint_cursor=model.checkpoint_cursor,
        status=model.status,
        reclaim_count=model.reclaim_count,
        operator_required_at=model.operator_required_at,
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

    def create_entity(self, record: EntityRecord) -> EntityRecord:

        '''
        Create persisted entity and return normalized typed entity contract.

        Args:
        record (EntityRecord): Typed entity contract to persist.

        Returns:
        EntityRecord: Typed persisted entity contract.
        '''

        with self._session_factory() as session:
            repository = EntityRepository(session)
            model = repository.create_entity(record)
            session.commit()
            return _to_entity_record(model)

    def get_entity(self, environment: EnvironmentName, entity_key: str) -> EntityRecord | None:

        '''
        Create typed entity lookup result by environment-scoped entity key.

        Args:
        environment (EnvironmentName): Runtime environment value.
        entity_key (str): Durable entity key.

        Returns:
        EntityRecord | None: Typed entity contract when found, otherwise None.
        '''

        with self._session_factory() as session:
            repository = EntityRepository(session)
            model = repository.get_entity_by_key(environment=environment, entity_key=entity_key)
            if model is None:
                return None

            return _to_entity_record(model)

    def list_entities(
        self,
        environment: EnvironmentName,
        limit: int,
        offset: int = 0,
        repository: str | None = None,
        entity_type: EntityType | None = None,
        include_closed: bool = True,
    ) -> list[EntityRecord]:

        '''
        Create typed entity list for environment and optional filters.

        Args:
        environment (EnvironmentName): Runtime environment value.
        limit (int): Maximum number of rows to return.
        offset (int): Pagination offset.
        repository (str | None): Optional repository filter.
        entity_type (EntityType | None): Optional entity type filter.
        include_closed (bool): Include closed rows when True.

        Returns:
        list[EntityRecord]: Typed entity rows.
        '''

        with self._session_factory() as session:
            entity_repository = EntityRepository(session)
            models = entity_repository.list_entities(
                environment=environment,
                limit=limit,
                offset=offset,
                repository=repository,
                entity_type=entity_type,
                include_closed=include_closed,
            )
            return [_to_entity_record(model) for model in models]

    def count_entities(
        self,
        environment: EnvironmentName,
        repository: str | None = None,
        entity_type: EntityType | None = None,
        include_closed: bool = True,
    ) -> int:

        '''
        Create entity count for environment and optional filters.

        Args:
        environment (EnvironmentName): Runtime environment value.
        repository (str | None): Optional repository filter.
        entity_type (EntityType | None): Optional entity type filter.
        include_closed (bool): Include closed rows when True.

        Returns:
        int: Entity row count matching filters.
        '''

        with self._session_factory() as session:
            entity_repository = EntityRepository(session)
            return entity_repository.count_entities(
                environment=environment,
                repository=repository,
                entity_type=entity_type,
                include_closed=include_closed,
            )

    def touch_entity(self, environment: EnvironmentName, entity_key: str, event_timestamp: datetime) -> bool:

        '''
        Compute entity last-event update outcome by entity key.

        Args:
        environment (EnvironmentName): Runtime environment value.
        entity_key (str): Durable entity key.
        event_timestamp (datetime): Last event timestamp.

        Returns:
        bool: True when update succeeded, otherwise False.
        '''

        with self._session_factory() as session:
            entity_repository = EntityRepository(session)
            touched = entity_repository.touch_entity(
                environment=environment,
                entity_key=entity_key,
                event_timestamp=event_timestamp,
            )
            session.commit()
            return touched

    def append_audit_run(self, record: AuditRunRecord) -> AuditRunRecord:

        '''
        Create persisted audit-run row from typed audit-run contract.

        Args:
        record (AuditRunRecord): Typed audit-run contract to persist.

        Returns:
        AuditRunRecord: Persisted typed audit-run contract.
        '''

        with self._session_factory() as session:
            repository = AuditRunRepository(session)
            model = repository.create_audit_run(record)
            session.commit()
            return _to_audit_run_record(model)

    def list_audit_runs(
        self,
        environment: EnvironmentName,
        limit: int,
        offset: int = 0,
        audit_type: str | None = None,
        status: AuditRunStatus | None = None,
    ) -> list[AuditRunRecord]:

        '''
        Create typed audit-run list for one environment and optional filters.

        Args:
        environment (EnvironmentName): Runtime environment value.
        limit (int): Maximum row count to return.
        offset (int): Pagination offset.
        audit_type (str | None): Optional audit type filter.
        status (AuditRunStatus | None): Optional audit-run status filter.

        Returns:
        list[AuditRunRecord]: Ordered typed audit-run rows.
        '''

        with self._session_factory() as session:
            repository = AuditRunRepository(session)
            models = repository.list_audit_runs(
                environment=environment,
                limit=limit,
                offset=offset,
                audit_type=audit_type,
                status=status,
            )
            return [_to_audit_run_record(model) for model in models]

    def append_comment_target(self, record: CommentTargetRecord) -> CommentTargetRecord:

        '''
        Create persisted comment-target row from resolved routing-target contract.

        Args:
        record (CommentTargetRecord): Typed comment-target contract to persist.

        Returns:
        CommentTargetRecord: Persisted typed comment-target contract.
        '''

        with self._session_factory() as session:
            repository = CommentTargetRepository(session)
            model = repository.create_comment_target(record)
            session.commit()
            return _to_comment_target_record(model)

    def get_comment_target_by_outbox_id(
        self,
        environment: EnvironmentName,
        outbox_id: str,
    ) -> CommentTargetRecord | None:

        '''
        Create comment-target lookup result by environment and outbox identifier.

        Args:
        environment (EnvironmentName): Runtime environment value.
        outbox_id (str): Durable outbox identifier.

        Returns:
        CommentTargetRecord | None: Typed comment-target contract or None when missing.
        '''

        with self._session_factory() as session:
            repository = CommentTargetRepository(session)
            model = repository.get_comment_target_by_outbox_id(
                environment=environment,
                outbox_id=outbox_id,
            )
            if model is None:
                return None

            return _to_comment_target_record(model)

    def get_comment_target_by_idempotency_scope(
        self,
        environment: EnvironmentName,
        action_type: OutboxActionType,
        target_identity: str,
        idempotency_key: str,
    ) -> CommentTargetRecord | None:

        '''
        Create comment-target lookup result by deterministic idempotency scope.

        Args:
        environment (EnvironmentName): Runtime environment value.
        action_type (OutboxActionType): Outbox side-effect action type.
        target_identity (str): Deterministic target identity.
        idempotency_key (str): Deterministic idempotency key.

        Returns:
        CommentTargetRecord | None: Typed comment-target contract or None when missing.
        '''

        with self._session_factory() as session:
            repository = CommentTargetRepository(session)
            model = repository.get_comment_target_by_idempotency_scope(
                environment=environment,
                action_type=action_type,
                target_identity=target_identity,
                idempotency_key=idempotency_key,
            )
            if model is None:
                return None

            return _to_comment_target_record(model)

    def list_comment_targets_for_job(
        self,
        job_id: str,
        limit: int,
        offset: int = 0,
    ) -> list[CommentTargetRecord]:

        '''
        Create comment-target list for one job identifier.

        Args:
        job_id (str): Durable job identifier.
        limit (int): Maximum row count to return.
        offset (int): Pagination offset.

        Returns:
        list[CommentTargetRecord]: Ordered typed comment-target rows.
        '''

        with self._session_factory() as session:
            repository = CommentTargetRepository(session)
            models = repository.list_comment_targets_for_job(
                job_id=job_id,
                limit=limit,
                offset=offset,
            )
            return [_to_comment_target_record(model) for model in models]

    def count_comment_targets_for_job(self, job_id: str) -> int:

        '''
        Create comment-target count for one job identifier.

        Args:
        job_id (str): Durable job identifier.

        Returns:
        int: Comment-target row count for the provided job.
        '''

        with self._session_factory() as session:
            repository = CommentTargetRepository(session)
            return repository.count_comment_targets_for_job(job_id=job_id)

    def append_action_attempt(self, record: ActionAttemptRecord) -> ActionAttemptRecord:

        '''
        Create persisted action-attempt row from typed attempt contract.

        Args:
        record (ActionAttemptRecord): Typed action-attempt contract to persist.

        Returns:
        ActionAttemptRecord: Persisted typed action-attempt contract.
        '''

        with self._session_factory() as session:
            repository = ActionAttemptRepository(session)
            model = repository.create_action_attempt(
                attempt_id=record.attempt_id,
                outbox_id=record.outbox_id,
                job_id=record.job_id,
                entity_key=record.entity_key,
                environment=record.environment,
                action_type=record.action_type,
                status=record.status,
                error_message=record.error_message,
                attempt_started_at=record.attempt_started_at,
                attempt_completed_at=record.attempt_completed_at,
            )
            session.commit()
            return _to_action_attempt_record(model)

    def get_action_attempt(
        self,
        environment: EnvironmentName,
        attempt_id: str,
    ) -> ActionAttemptRecord | None:

        '''
        Create action-attempt lookup result by environment and attempt identifier.

        Args:
        environment (EnvironmentName): Runtime environment value.
        attempt_id (str): Durable attempt identifier.

        Returns:
        ActionAttemptRecord | None: Typed action-attempt contract or None when missing.
        '''

        with self._session_factory() as session:
            repository = ActionAttemptRepository(session)
            model = repository.get_action_attempt(environment=environment, attempt_id=attempt_id)
            if model is None:
                return None

            return _to_action_attempt_record(model)

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
        bool: True when status update succeeded, otherwise False.
        '''

        with self._session_factory() as session:
            repository = ActionAttemptRepository(session)
            updated = repository.mark_action_attempt_status(
                environment=environment,
                attempt_id=attempt_id,
                status=status,
                completion_timestamp=completion_timestamp,
                error_message=error_message,
            )
            session.commit()
            return updated

    def list_action_attempts_for_outbox(
        self,
        outbox_id: str,
        limit: int,
        offset: int = 0,
    ) -> list[ActionAttemptRecord]:

        '''
        Create action-attempt list for one outbox identifier.

        Args:
        outbox_id (str): Durable outbox identifier.
        limit (int): Maximum row count to return.
        offset (int): Pagination offset.

        Returns:
        list[ActionAttemptRecord]: Ordered typed action-attempt rows.
        '''

        with self._session_factory() as session:
            repository = ActionAttemptRepository(session)
            models = repository.list_action_attempts_for_outbox(
                outbox_id=outbox_id,
                limit=limit,
                offset=offset,
            )
            return [_to_action_attempt_record(model) for model in models]

    def list_action_attempts_for_job(
        self,
        job_id: str,
        limit: int,
        offset: int = 0,
    ) -> list[ActionAttemptRecord]:

        '''
        Create action-attempt list for one job identifier.

        Args:
        job_id (str): Durable job identifier.
        limit (int): Maximum row count to return.
        offset (int): Pagination offset.

        Returns:
        list[ActionAttemptRecord]: Ordered typed action-attempt rows.
        '''

        with self._session_factory() as session:
            repository = ActionAttemptRepository(session)
            models = repository.list_action_attempts_for_job(
                job_id=job_id,
                limit=limit,
                offset=offset,
            )
            return [_to_action_attempt_record(model) for model in models]

    def count_action_attempts_for_job(self, job_id: str) -> int:

        '''
        Create action-attempt count for one job identifier.

        Args:
        job_id (str): Durable job identifier.

        Returns:
        int: Action-attempt row count for the provided job.
        '''

        with self._session_factory() as session:
            repository = ActionAttemptRepository(session)
            return repository.count_action_attempts_for_job(job_id=job_id)

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

    def list_jobs_by_kind_and_states(
        self,
        kind: JobKind,
        states: list[JobState],
        limit: int,
    ) -> list[JobRecord]:

        '''
        Create typed job list filtered by job kind and lifecycle states.

        Args:
        kind (JobKind): Job kind filter.
        states (list[JobState]): Allowed lifecycle states.
        limit (int): Maximum rows to return.

        Returns:
        list[JobRecord]: Ordered typed job rows.
        '''

        with self._session_factory() as session:
            repository = JobRepository(session)
            models = repository.list_jobs_by_kind_and_states(
                kind=kind,
                states=states,
                limit=limit,
            )
            return [_to_job_record(model) for model in models]

    def validate_job_lease_epoch(self, job_id: str, expected_lease_epoch: int) -> bool:

        '''
        Create job lease-epoch validation result for mutating side-effect fencing.

        Args:
        job_id (str): Durable job identifier.
        expected_lease_epoch (int): Expected current lease epoch.

        Returns:
        bool: True when current lease epoch matches expectation, otherwise False.
        '''

        with self._session_factory() as session:
            repository = JobRepository(session)
            model = repository.get_job_by_job_id(job_id)
            if model is None:
                return False

            return model.lease_epoch == expected_lease_epoch

    def persist_ingress_event(
        self,
        ingress_event: GitHubIngressEvent,
        environment: EnvironmentName,
        received_at: datetime | None = None,
    ) -> PersistedIngressEvent:

        '''
        Create persisted ingress event ordering record for deterministic processing gates.

        Args:
        ingress_event (GitHubIngressEvent): Raw GitHub ingress event payload.
        environment (EnvironmentName): Runtime environment value.
        received_at (datetime | None): Optional receive timestamp override.

        Returns:
        PersistedIngressEvent: Persisted ingress event ordering payload.
        '''

        with self._session_factory() as session:
            repository = GitHubEventRepository(session)
            persisted_event = repository.persist_ingress_event(
                ingress_event=ingress_event,
                environment=environment,
                received_at=received_at,
            )
            session.commit()
            return persisted_event

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

    def transition_job_state_with_outbox(
        self,
        job_id: str,
        to_state: JobState,
        reason: str,
        outbox_requests: list[OutboxWriteRequest],
    ) -> tuple[JobRecord, list[OutboxRecord]]:

        '''
        Create atomic job transition commit with persisted outbox intent rows.

        Args:
        job_id (str): Durable job identifier.
        to_state (JobState): Target lifecycle state.
        reason (str): Deterministic transition reason.
        outbox_requests (list[OutboxWriteRequest]): Outbox intents to persist atomically.

        Returns:
        tuple[JobRecord, list[OutboxRecord]]: Updated job and persisted outbox intents.
        '''

        with self._session_factory() as session:
            job_repository = JobRepository(session)
            outbox_repository = OutboxRepository(session)
            job_repository.transition_job_state(job_id, to_state, reason)
            model = job_repository.get_job_by_job_id(job_id)
            if model is None:
                message = f'Job not found after transition: {job_id}'
                raise ValueError(message)

            outbox_models = [
                outbox_repository.create_outbox_entry(
                    outbox_id=outbox_request.outbox_id,
                    job_id=outbox_request.job_id,
                    entity_key=outbox_request.entity_key,
                    environment=outbox_request.environment,
                    action_type=outbox_request.action_type,
                    target_identity=outbox_request.target_identity,
                    payload=outbox_request.payload,
                    idempotency_key=outbox_request.idempotency_key,
                    idempotency_policy_version=outbox_request.idempotency_policy_version,
                    idempotency_schema_version=outbox_request.idempotency_schema_version,
                    idempotency_payload_hash=outbox_request.idempotency_payload_hash,
                    idempotency_policy_version_hash=outbox_request.idempotency_policy_version_hash,
                    job_lease_epoch=outbox_request.job_lease_epoch,
                    next_attempt_at=outbox_request.next_attempt_at,
                )
                for outbox_request in outbox_requests
            ]
            session.commit()
            return (
                _to_job_record(model),
                [_to_outbox_record(outbox_model) for outbox_model in outbox_models],
            )

    def append_event(self, event: AgentEvent) -> None:

        '''
        Create persisted event journal row from typed event contract.

        Args:
        event (AgentEvent): Typed event contract to persist.
        '''

        with self._session_factory() as session:
            repository = EventRepository(session)
            model = repository.append_event(event)
            session.commit()
            log_agent_event(_to_agent_event(model))

    def rebuild_event_chain(self, environment: EnvironmentName | None = None) -> int:

        '''
        Create deterministic event-chain values for existing journal rows.

        Args:
        environment (EnvironmentName | None): Optional environment filter.

        Returns:
        int: Number of rebuilt event-journal rows.
        '''

        with self._session_factory() as session:
            repository = EventRepository(session)
            rebuilt_count = repository.rebuild_event_chain(environment=environment)
            session.commit()
            return rebuilt_count

    def verify_event_chain(self, environment: EnvironmentName | None = None) -> list[str]:

        '''
        Create tamper-evident chain verification findings for journal rows.

        Args:
        environment (EnvironmentName | None): Optional environment filter.

        Returns:
        list[str]: Human-readable chain verification findings.
        '''

        with self._session_factory() as session:
            repository = EventRepository(session)
            return repository.verify_event_chain(environment=environment)

    def append_outbox_entry(self, request: OutboxWriteRequest) -> OutboxRecord:

        '''
        Create persisted outbox intent row from typed outbox write request.

        Args:
        request (OutboxWriteRequest): Typed outbox intent write request.

        Returns:
        OutboxRecord: Persisted typed outbox row.
        '''

        with self._session_factory() as session:
            repository = OutboxRepository(session)
            model = repository.create_outbox_entry(
                outbox_id=request.outbox_id,
                job_id=request.job_id,
                entity_key=request.entity_key,
                environment=request.environment,
                action_type=request.action_type,
                target_identity=request.target_identity,
                payload=request.payload,
                idempotency_key=request.idempotency_key,
                idempotency_policy_version=request.idempotency_policy_version,
                idempotency_schema_version=request.idempotency_schema_version,
                idempotency_payload_hash=request.idempotency_payload_hash,
                idempotency_policy_version_hash=request.idempotency_policy_version_hash,
                job_lease_epoch=request.job_lease_epoch,
                next_attempt_at=request.next_attempt_at,
            )
            session.commit()
            return _to_outbox_record(model)

    def get_outbox_entry_by_outbox_id(self, outbox_id: str) -> OutboxRecord | None:

        '''
        Create outbox lookup result by durable outbox identifier.

        Args:
        outbox_id (str): Durable outbox identifier.

        Returns:
        OutboxRecord | None: Typed outbox contract or None when missing.
        '''

        with self._session_factory() as session:
            repository = OutboxRepository(session)
            model = repository.get_outbox_entry_by_outbox_id(outbox_id)
            if model is None:
                return None

            return _to_outbox_record(model)

    def get_outbox_entry_by_idempotency_scope(
        self,
        environment: EnvironmentName,
        action_type: OutboxActionType,
        target_identity: str,
        idempotency_key: str,
        idempotency_schema_version: str | None = None,
        idempotency_payload_hash: str | None = None,
        idempotency_policy_version_hash: str | None = None,
    ) -> OutboxRecord | None:

        '''
        Create outbox lookup result by deterministic idempotency scope.

        Args:
        environment (EnvironmentName): Runtime environment value.
        action_type (OutboxActionType): Outbox side-effect action type.
        target_identity (str): Deterministic target identity.
        idempotency_key (str): Deterministic idempotency key.
        idempotency_schema_version (str | None): Optional idempotency schema version filter.
        idempotency_payload_hash (str | None): Optional payload hash filter.
        idempotency_policy_version_hash (str | None): Optional policy-version hash filter.

        Returns:
        OutboxRecord | None: Typed outbox contract or None when missing.
        '''

        with self._session_factory() as session:
            repository = OutboxRepository(session)
            model = repository.get_outbox_entry_by_idempotency_scope(
                environment=environment,
                action_type=action_type,
                target_identity=target_identity,
                idempotency_key=idempotency_key,
                idempotency_schema_version=idempotency_schema_version,
                idempotency_payload_hash=idempotency_payload_hash,
                idempotency_policy_version_hash=idempotency_policy_version_hash,
            )
            if model is None:
                return None

            return _to_outbox_record(model)

    def list_dispatchable_outbox_entries(
        self,
        limit: int,
        reference_timestamp: datetime | None = None,
    ) -> list[OutboxRecord]:

        '''
        Create dispatchable outbox entry list for deterministic dispatcher cycles.

        Args:
        limit (int): Maximum number of entries to return.
        reference_timestamp (datetime | None): Optional dispatch reference timestamp.

        Returns:
        list[OutboxRecord]: Dispatchable typed outbox entries.
        '''

        with self._session_factory() as session:
            repository = OutboxRepository(session)
            models = repository.list_dispatchable_entries(
                limit=limit,
                reference_timestamp=reference_timestamp,
            )
            return [_to_outbox_record(model) for model in models]

    def mark_outbox_entry_sent(
        self,
        outbox_id: str,
        expected_lease_epoch: int,
        attempt_timestamp: datetime | None = None,
    ) -> bool:

        '''
        Compute sent-status update outcome for one outbox entry attempt.

        Args:
        outbox_id (str): Durable outbox identifier.
        expected_lease_epoch (int): Expected lease epoch fencing value.
        attempt_timestamp (datetime | None): Optional attempt timestamp override.

        Returns:
        bool: True when status update succeeded, otherwise False.
        '''

        with self._session_factory() as session:
            repository = OutboxRepository(session)
            updated = repository.mark_entry_sent(
                outbox_id=outbox_id,
                expected_lease_epoch=expected_lease_epoch,
                attempt_timestamp=attempt_timestamp,
            )
            session.commit()
            return updated

    def mark_outbox_entry_confirmed(
        self,
        outbox_id: str,
        expected_lease_epoch: int,
        confirmation_timestamp: datetime | None = None,
    ) -> bool:

        '''
        Compute confirmed-status update outcome for one outbox entry.

        Args:
        outbox_id (str): Durable outbox identifier.
        expected_lease_epoch (int): Expected lease epoch fencing value.
        confirmation_timestamp (datetime | None): Optional confirmation timestamp override.

        Returns:
        bool: True when status update succeeded, otherwise False.
        '''

        with self._session_factory() as session:
            repository = OutboxRepository(session)
            updated = repository.mark_entry_confirmed(
                outbox_id=outbox_id,
                expected_lease_epoch=expected_lease_epoch,
                confirmation_timestamp=confirmation_timestamp,
            )
            session.commit()
            return updated

    def mark_outbox_entry_failed(
        self,
        outbox_id: str,
        expected_lease_epoch: int,
        error_message: str,
        retry_after_seconds: int,
        failure_timestamp: datetime | None = None,
    ) -> bool:

        '''
        Compute failed-status update outcome for one outbox entry.

        Args:
        outbox_id (str): Durable outbox identifier.
        expected_lease_epoch (int): Expected lease epoch fencing value.
        error_message (str): Deterministic failure summary.
        retry_after_seconds (int): Retry delay in seconds.
        failure_timestamp (datetime | None): Optional failure timestamp override.

        Returns:
        bool: True when status update succeeded, otherwise False.
        '''

        with self._session_factory() as session:
            repository = OutboxRepository(session)
            updated = repository.mark_entry_failed(
                outbox_id=outbox_id,
                expected_lease_epoch=expected_lease_epoch,
                error_message=error_message,
                retry_after_seconds=retry_after_seconds,
                failure_timestamp=failure_timestamp,
            )
            session.commit()
            return updated

    def mark_outbox_entry_aborted(
        self,
        outbox_id: str,
        expected_lease_epoch: int,
        abort_reason: str,
        abort_timestamp: datetime | None = None,
    ) -> bool:

        '''
        Compute aborted-status update outcome for one outbox entry.

        Args:
        outbox_id (str): Durable outbox identifier.
        expected_lease_epoch (int): Expected lease epoch fencing value.
        abort_reason (str): Deterministic abort summary.
        abort_timestamp (datetime | None): Optional abort timestamp override.

        Returns:
        bool: True when status update succeeded, otherwise False.
        '''

        with self._session_factory() as session:
            repository = OutboxRepository(session)
            updated = repository.mark_entry_aborted(
                outbox_id=outbox_id,
                expected_lease_epoch=expected_lease_epoch,
                abort_reason=abort_reason,
                abort_timestamp=abort_timestamp,
            )
            session.commit()
            return updated

    def count_outbox_backlog(self) -> int:

        '''
        Create outbox backlog count across dispatchable statuses.

        Returns:
        int: Outbox backlog row count.
        '''

        with self._session_factory() as session:
            repository = OutboxRepository(session)
            return repository.count_backlog_entries()

    def list_idempotency_scope_violations(
        self,
        environment: EnvironmentName,
        limit: int = 50,
    ) -> list[IdempotencyScopeViolation]:

        '''
        Create idempotency-scope violation list for one environment.

        Args:
        environment (EnvironmentName): Runtime environment value.
        limit (int): Maximum number of violations to return.

        Returns:
        list[IdempotencyScopeViolation]: Deterministic idempotency-scope violations.
        '''

        with self._session_factory() as session:
            repository = OutboxRepository(session)
            return repository.list_idempotency_scope_violations(
                environment=environment,
                limit=limit,
            )

    def count_recent_failed_transition_events(self, window_start: datetime) -> int:

        '''
        Create count of recent blocked or error transition events.

        Args:
        window_start (datetime): Inclusive lower bound for transition event timestamps.

        Returns:
        int: Recent failed transition event count.
        '''

        with self._session_factory() as session:
            repository = EventRepository(session)
            return repository.count_recent_failed_transition_events(window_start)

    def list_events_since(
        self,
        environment: EnvironmentName,
        window_start: datetime,
        source: EventSource | None = None,
    ) -> list[AgentEvent]:

        '''
        Create typed event list for one environment since one inclusive timestamp.

        Args:
        environment (EnvironmentName): Runtime environment value.
        window_start (datetime): Inclusive lower bound for event timestamps.
        source (EventSource | None): Optional event source filter.

        Returns:
        list[AgentEvent]: Ordered typed events since timestamp.
        '''

        with self._session_factory() as session:
            repository = EventRepository(session)
            models = repository.list_events_since(
                environment=environment,
                window_start=window_start,
                source=source,
            )
            return [_to_agent_event(model) for model in models]

    def upsert_watcher_state(
        self,
        environment: EnvironmentName,
        watcher_state: WatcherState,
    ) -> WatcherState:

        '''
        Create persisted watcher row by inserting or updating typed watcher state.

        Args:
        environment (EnvironmentName): Runtime environment value.
        watcher_state (WatcherState): Typed watcher state payload.

        Returns:
        WatcherState: Persisted typed watcher state payload.
        '''

        with self._session_factory() as session:
            repository = WatcherRepository(session)
            model = repository.upsert_watcher_state(environment=environment, watcher_state=watcher_state)
            session.commit()
            return _to_watcher_state(model)

    def list_stale_watchers(
        self,
        environment: EnvironmentName,
        reference_time: datetime,
        stale_after_seconds: int,
    ) -> list[WatcherState]:

        '''
        Create stale watcher list eligible for reclaim operations.

        Args:
        environment (EnvironmentName): Runtime environment value.
        reference_time (datetime): Current reference timestamp.
        stale_after_seconds (int): Allowed heartbeat age before stale status.

        Returns:
        list[WatcherState]: Typed stale watcher payloads.
        '''

        with self._session_factory() as session:
            repository = WatcherRepository(session)
            models = repository.list_stale_watchers(
                environment=environment,
                reference_time=reference_time,
                stale_after_seconds=stale_after_seconds,
            )
            return [_to_watcher_state(model) for model in models]

    def list_reclaimed_watchers_due(
        self,
        environment: EnvironmentName,
        reference_time: datetime,
    ) -> list[WatcherState]:

        '''
        Create reclaimed watcher list due for checkpoint restoration.

        Args:
        environment (EnvironmentName): Runtime environment value.
        reference_time (datetime): Current reference timestamp.

        Returns:
        list[WatcherState]: Typed reclaimed watcher payloads due now.
        '''

        with self._session_factory() as session:
            repository = WatcherRepository(session)
            models = repository.list_reclaimed_watchers_due(
                environment=environment,
                reference_time=reference_time,
            )
            return [_to_watcher_state(model) for model in models]

    def mark_watcher_reclaimed(
        self,
        environment: EnvironmentName,
        job_id: str,
        reference_time: datetime,
        max_reclaim_attempts: int,
    ) -> WatcherState | None:

        '''
        Create stale watcher reclaim update and operator-required escalation when needed.

        Args:
        environment (EnvironmentName): Runtime environment value.
        job_id (str): Durable job identifier.
        reference_time (datetime): Current reference timestamp.
        max_reclaim_attempts (int): Maximum reclaim attempts before escalation.

        Returns:
        WatcherState | None: Updated typed watcher payload or None when missing.
        '''

        with self._session_factory() as session:
            repository = WatcherRepository(session)
            model = repository.mark_watcher_reclaimed(
                environment=environment,
                job_id=job_id,
                reference_time=reference_time,
                max_reclaim_attempts=max_reclaim_attempts,
            )
            session.commit()
            if model is None:
                return None

            return _to_watcher_state(model)

    def restore_reclaimed_watcher(
        self,
        environment: EnvironmentName,
        job_id: str,
        reference_time: datetime,
        next_check_at: datetime,
    ) -> WatcherState | None:

        '''
        Create checkpoint restoration update for reclaimed watcher rows.

        Args:
        environment (EnvironmentName): Runtime environment value.
        job_id (str): Durable job identifier.
        reference_time (datetime): Current reference timestamp.
        next_check_at (datetime): Next check timestamp after restoration.

        Returns:
        WatcherState | None: Updated typed watcher payload or None when missing.
        '''

        with self._session_factory() as session:
            repository = WatcherRepository(session)
            model = repository.restore_reclaimed_watcher(
                environment=environment,
                job_id=job_id,
                reference_time=reference_time,
                next_check_at=next_check_at,
            )
            session.commit()
            if model is None:
                return None

            return _to_watcher_state(model)

    def close_watcher(
        self,
        environment: EnvironmentName,
        job_id: str,
        closed_at: datetime,
    ) -> bool:

        '''
        Compute close-state update outcome for one watcher row.

        Args:
        environment (EnvironmentName): Runtime environment value.
        job_id (str): Durable job identifier.
        closed_at (datetime): Close timestamp.

        Returns:
        bool: True when close-state update succeeded, otherwise False.
        '''

        with self._session_factory() as session:
            repository = WatcherRepository(session)
            closed = repository.close_watcher(
                environment=environment,
                job_id=job_id,
                closed_at=closed_at,
            )
            session.commit()
            return closed

    def count_watchers_by_status(
        self,
        environment: EnvironmentName,
        status: WatcherStatus,
    ) -> int:

        '''
        Create watcher row count for one status value.

        Args:
        environment (EnvironmentName): Runtime environment value.
        status (WatcherStatus): Watcher status value.

        Returns:
        int: Watcher row count matching status.
        '''

        with self._session_factory() as session:
            repository = WatcherRepository(session)
            return repository.count_watchers_by_status(environment=environment, status=status)


__all__ = ['PersistenceService']
