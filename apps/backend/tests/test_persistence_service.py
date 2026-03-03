from __future__ import annotations

from datetime import datetime
from datetime import timezone

from _pytest.monkeypatch import MonkeyPatch
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.services import persistence_service as persistence_service_module
from agent1.core.contracts import AgentEvent
from agent1.core.contracts import ActionAttemptRecord
from agent1.core.contracts import ActionAttemptStatus
from agent1.core.contracts import CommentTargetRecord
from agent1.core.contracts import CommentTargetType
from agent1.core.contracts import EntityRecord
from agent1.core.contracts import EntityType
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EventSource
from agent1.core.contracts import EventStatus
from agent1.core.contracts import EventType
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import OutboxActionType
from agent1.core.contracts import OutboxStatus
from agent1.core.contracts import OutboxWriteRequest
from agent1.core.contracts import RuntimeMode
from agent1.core.ingress_contracts import GitHubIngressEvent
from agent1.core.ingress_contracts import IngressEntityType
from agent1.core.ingress_contracts import IngressEventType
from agent1.core.ingress_contracts import IngressOrderingDecision
from agent1.core.services.persistence_service import PersistenceService
from agent1.db.models import EventJournalModel
from agent1.db.models import GitHubEventModel
from agent1.db.models import OutboxEntryModel
from agent1.db.models import CommentTargetModel


def _create_record() -> JobRecord:
    return JobRecord(
        job_id='job_service_1',
        entity_key='Vaquum/Agent1#2',
        kind=JobKind.ISSUE,
        state=JobState.AWAITING_CONTEXT,
        idempotency_key='idem_service_1',
        lease_epoch=0,
        environment=EnvironmentName.DEV,
        mode=RuntimeMode.ACTIVE,
    )


def test_persistence_service_job_and_event_flow(session_factory: sessionmaker[Session]) -> None:
    service = PersistenceService(session_factory=session_factory)

    created = service.create_job(_create_record())
    claimed = service.claim_job_lease(created.job_id, expected_lease_epoch=0)
    updated = service.transition_job_state(
        created.job_id,
        to_state=JobState.EXECUTING,
        reason='service_transition',
    )
    service.append_event(
        AgentEvent(
            timestamp=datetime.now(timezone.utc),
            environment=EnvironmentName.DEV,
            trace_id='trc_service_1',
            job_id=created.job_id,
            entity_key=created.entity_key,
            source=EventSource.AGENT,
            event_type=EventType.STATE_TRANSITION,
            status=EventStatus.OK,
            details={'message': 'service_event'},
        )
    )

    assert claimed is True
    assert updated.state == JobState.EXECUTING

    with session_factory() as verification_session:
        event_count = verification_session.query(EventJournalModel).count()

    assert event_count == 1


def test_persistence_service_entity_create_get_list_and_touch(
    session_factory: sessionmaker[Session],
) -> None:
    service = PersistenceService(session_factory=session_factory)
    created_entity = service.create_entity(
        EntityRecord(
            entity_key='Vaquum/Agent1#2001',
            repository='Vaquum/Agent1',
            entity_number=2001,
            entity_type=EntityType.ISSUE,
            environment=EnvironmentName.DEV,
            is_sandbox=True,
            is_closed=False,
        ),
    )
    fetched_entity = service.get_entity(
        environment=EnvironmentName.DEV,
        entity_key='Vaquum/Agent1#2001',
    )
    listed_entities = service.list_entities(
        environment=EnvironmentName.DEV,
        limit=10,
        include_closed=False,
    )
    touched = service.touch_entity(
        environment=EnvironmentName.DEV,
        entity_key='Vaquum/Agent1#2001',
        event_timestamp=datetime.now(timezone.utc),
    )
    count = service.count_entities(
        environment=EnvironmentName.DEV,
        include_closed=False,
    )

    assert created_entity.entity_key == 'Vaquum/Agent1#2001'
    assert fetched_entity is not None
    assert fetched_entity.entity_type == EntityType.ISSUE
    assert len(listed_entities) == 1
    assert touched is True
    assert count == 1


def test_persistence_service_action_attempt_methods(
    session_factory: sessionmaker[Session],
) -> None:
    service = PersistenceService(session_factory=session_factory)
    created_job = service.create_job(_create_record())
    created_outbox = service.append_outbox_entry(
        OutboxWriteRequest(
            outbox_id='outbox_action_attempt_service_1',
            job_id=created_job.job_id,
            entity_key=created_job.entity_key,
            environment=created_job.environment,
            action_type=OutboxActionType.ISSUE_COMMENT,
            target_identity='Vaquum/Agent1#2:issue',
            payload={
                'repository': 'Vaquum/Agent1',
                'issue_number': 2,
                'body': 'attempt lifecycle',
            },
            idempotency_key='outbox_action_attempt_service_idem_1',
            job_lease_epoch=created_job.lease_epoch,
        ),
    )
    appended_attempt = service.append_action_attempt(
        ActionAttemptRecord(
            attempt_id='outbox_action_attempt_service_1:1',
            outbox_id=created_outbox.outbox_id,
            job_id=created_job.job_id,
            entity_key=created_job.entity_key,
            environment=created_job.environment,
            action_type=OutboxActionType.ISSUE_COMMENT,
            status=ActionAttemptStatus.STARTED,
            error_message=None,
            attempt_started_at=datetime.now(timezone.utc),
            attempt_completed_at=None,
        ),
    )
    marked_failed = service.mark_action_attempt_status(
        environment=created_job.environment,
        attempt_id=appended_attempt.attempt_id,
        status=ActionAttemptStatus.FAILED,
        completion_timestamp=datetime.now(timezone.utc),
        error_message='dispatch_failure',
    )
    fetched_attempt = service.get_action_attempt(
        environment=created_job.environment,
        attempt_id=appended_attempt.attempt_id,
    )
    listed_attempts = service.list_action_attempts_for_outbox(
        outbox_id=created_outbox.outbox_id,
        limit=10,
    )
    listed_job_attempts = service.list_action_attempts_for_job(
        job_id=created_job.job_id,
        limit=10,
    )
    counted_job_attempts = service.count_action_attempts_for_job(
        job_id=created_job.job_id,
    )

    assert appended_attempt.status == ActionAttemptStatus.STARTED
    assert marked_failed is True
    assert fetched_attempt is not None
    assert fetched_attempt.status == ActionAttemptStatus.FAILED
    assert fetched_attempt.error_message == 'dispatch_failure'
    assert len(listed_attempts) == 1
    assert len(listed_job_attempts) == 1
    assert counted_job_attempts == 1


def test_persistence_service_append_comment_target(
    session_factory: sessionmaker[Session],
) -> None:
    service = PersistenceService(session_factory=session_factory)
    created_job = service.create_job(_create_record())
    created_outbox = service.append_outbox_entry(
        OutboxWriteRequest(
            outbox_id='outbox_comment_target_service_1',
            job_id=created_job.job_id,
            entity_key=created_job.entity_key,
            environment=created_job.environment,
            action_type=OutboxActionType.PR_REVIEW_REPLY,
            target_identity='Vaquum/Agent1:pr:2:thread:PRRC_1:9001',
            payload={
                'repository': 'Vaquum/Agent1',
                'pull_number': 2,
                'review_comment_id': 9001,
                'body': 'comment target persistence',
            },
            idempotency_key='outbox_comment_target_service_idem_1',
            job_lease_epoch=created_job.lease_epoch,
        ),
    )
    appended_comment_target = service.append_comment_target(
        CommentTargetRecord(
            target_id='outbox_comment_target_service_1',
            outbox_id=created_outbox.outbox_id,
            job_id=created_job.job_id,
            entity_key=created_job.entity_key,
            environment=created_job.environment,
            target_type=CommentTargetType.PR_REVIEW_THREAD,
            target_identity='Vaquum/Agent1:pr:2:thread:PRRC_1:9001',
            issue_number=None,
            pr_number=2,
            thread_id='PRRC_1',
            review_comment_id=9001,
            path='apps/backend/src/agent1/main.py',
            line=44,
            side='RIGHT',
            resolved_at=datetime.now(timezone.utc),
        ),
    )
    fetched_by_outbox = service.get_comment_target_by_outbox_id(
        environment=created_job.environment,
        outbox_id=created_outbox.outbox_id,
    )
    fetched_by_idempotency_scope = service.get_comment_target_by_idempotency_scope(
        environment=created_job.environment,
        action_type=OutboxActionType.PR_REVIEW_REPLY,
        target_identity='Vaquum/Agent1:pr:2:thread:PRRC_1:9001',
        idempotency_key='outbox_comment_target_service_idem_1',
    )
    listed_for_job = service.list_comment_targets_for_job(
        job_id=created_job.job_id,
        limit=10,
    )
    count_for_job = service.count_comment_targets_for_job(job_id=created_job.job_id)

    with session_factory() as verification_session:
        persisted_comment_target = (
            verification_session.query(CommentTargetModel)
            .filter(CommentTargetModel.target_id == appended_comment_target.target_id)
            .one_or_none()
        )

    assert persisted_comment_target is not None
    assert persisted_comment_target.review_comment_id == 9001
    assert appended_comment_target.target_type == CommentTargetType.PR_REVIEW_THREAD
    assert fetched_by_outbox is not None
    assert fetched_by_idempotency_scope is not None
    assert len(listed_for_job) == 1
    assert count_for_job == 1


def test_persistence_service_append_event_emits_structured_log(
    session_factory: sessionmaker[Session],
    monkeypatch: MonkeyPatch,
) -> None:
    emitted_trace_ids: list[str] = []

    def _capture_event(event: AgentEvent) -> None:
        emitted_trace_ids.append(event.trace_id)

    monkeypatch.setattr(persistence_service_module, 'log_agent_event', _capture_event)
    service = PersistenceService(session_factory=session_factory)
    service.append_event(
        AgentEvent(
            timestamp=datetime.now(timezone.utc),
            environment=EnvironmentName.DEV,
            trace_id='trc_service_logging',
            job_id='job_service_logging',
            entity_key='Vaquum/Agent1#3',
            source=EventSource.AGENT,
            event_type=EventType.STATE_TRANSITION,
            status=EventStatus.OK,
            details={'message': 'log_capture'},
        )
    )

    assert emitted_trace_ids == ['trc_service_logging']


def test_persistence_service_transition_with_outbox_is_atomic(
    session_factory: sessionmaker[Session],
) -> None:
    service = PersistenceService(session_factory=session_factory)
    created = service.create_job(_create_record())
    transitioned_job, outbox_entries = service.transition_job_state_with_outbox(
        job_id=created.job_id,
        to_state=JobState.EXECUTING,
        reason='atomic_outbox_transition',
        outbox_requests=[
            OutboxWriteRequest(
                outbox_id='outbox_service_1',
                job_id=created.job_id,
                entity_key=created.entity_key,
                environment=created.environment,
                action_type=OutboxActionType.ISSUE_COMMENT,
                target_identity='Vaquum/Agent1#2:issue',
                payload={
                    'repository': 'Vaquum/Agent1',
                    'issue_number': 2,
                    'body': 'hello from outbox',
                },
                idempotency_key='outbox_service_idem_1',
                job_lease_epoch=created.lease_epoch,
            ),
        ],
    )

    with session_factory() as verification_session:
        outbox_count = verification_session.query(OutboxEntryModel).count()

    assert transitioned_job.state == JobState.EXECUTING
    assert outbox_count == 1
    assert len(outbox_entries) == 1
    assert outbox_entries[0].status == OutboxStatus.PENDING
    assert outbox_entries[0].job_id == created.job_id


def test_persistence_service_outbox_lifecycle_methods(
    session_factory: sessionmaker[Session],
) -> None:
    service = PersistenceService(session_factory=session_factory)
    created = service.create_job(_create_record())
    created_outbox = service.append_outbox_entry(
        OutboxWriteRequest(
            outbox_id='outbox_service_2',
            job_id=created.job_id,
            entity_key=created.entity_key,
            environment=created.environment,
            action_type=OutboxActionType.ISSUE_COMMENT,
            target_identity='Vaquum/Agent1#2:issue',
            payload={
                'repository': 'Vaquum/Agent1',
                'issue_number': 2,
                'body': 'hello from lifecycle',
            },
            idempotency_key='outbox_service_idem_2',
            job_lease_epoch=created.lease_epoch,
        ),
    )
    dispatchable_entries = service.list_dispatchable_outbox_entries(limit=10)
    sent_updated = service.mark_outbox_entry_sent(
        outbox_id=created_outbox.outbox_id,
        expected_lease_epoch=0,
    )
    failed_updated = service.mark_outbox_entry_failed(
        outbox_id=created_outbox.outbox_id,
        expected_lease_epoch=1,
        error_message='dispatch_failure',
        retry_after_seconds=1,
    )
    dispatchable_after_failure = service.list_dispatchable_outbox_entries(limit=10)
    confirmed_updated = service.mark_outbox_entry_confirmed(
        outbox_id=created_outbox.outbox_id,
        expected_lease_epoch=2,
    )
    by_outbox_id = service.get_outbox_entry_by_outbox_id(created_outbox.outbox_id)
    by_scope = service.get_outbox_entry_by_idempotency_scope(
        environment=created.environment,
        action_type=OutboxActionType.ISSUE_COMMENT,
        target_identity='Vaquum/Agent1#2:issue',
        idempotency_key='outbox_service_idem_2',
    )
    dispatchable_after_confirmation = service.list_dispatchable_outbox_entries(limit=10)

    assert len(dispatchable_entries) == 1
    assert sent_updated is True
    assert failed_updated is True
    assert len(dispatchable_after_failure) == 0
    assert confirmed_updated is True
    assert by_outbox_id is not None
    assert by_scope is not None
    assert by_outbox_id.status == OutboxStatus.CONFIRMED
    assert by_scope.status == OutboxStatus.CONFIRMED
    assert dispatchable_after_confirmation == []


def test_persistence_service_validate_job_lease_epoch(
    session_factory: sessionmaker[Session],
) -> None:
    service = PersistenceService(session_factory=session_factory)
    created = service.create_job(_create_record())
    valid_before_claim = service.validate_job_lease_epoch(created.job_id, expected_lease_epoch=0)
    service.claim_job_lease(created.job_id, expected_lease_epoch=0)
    valid_after_claim = service.validate_job_lease_epoch(created.job_id, expected_lease_epoch=1)
    stale_after_claim = service.validate_job_lease_epoch(created.job_id, expected_lease_epoch=0)

    assert valid_before_claim is True
    assert valid_after_claim is True
    assert stale_after_claim is False


def test_persistence_service_persist_ingress_event_ordering(
    session_factory: sessionmaker[Session],
) -> None:
    service = PersistenceService(session_factory=session_factory)
    newer_event = GitHubIngressEvent(
        event_id='evt_ingress_persist_newer',
        repository='Vaquum/Agent1',
        entity_number=1001,
        entity_type=IngressEntityType.ISSUE,
        actor='mikkokotila',
        event_type=IngressEventType.ISSUE_MENTION,
        timestamp=datetime(2026, 3, 5, 14, 0, tzinfo=timezone.utc),
        details={},
    )
    older_event = GitHubIngressEvent(
        event_id='evt_ingress_persist_older',
        repository='Vaquum/Agent1',
        entity_number=1001,
        entity_type=IngressEntityType.ISSUE,
        actor='mikkokotila',
        event_type=IngressEventType.ISSUE_MENTION,
        timestamp=datetime(2026, 3, 5, 13, 0, tzinfo=timezone.utc),
        details={},
    )
    accepted = service.persist_ingress_event(
        ingress_event=newer_event,
        environment=EnvironmentName.DEV,
    )
    stale = service.persist_ingress_event(
        ingress_event=older_event,
        environment=EnvironmentName.DEV,
    )

    with session_factory() as verification_session:
        event_count = verification_session.query(GitHubEventModel).count()

    assert event_count == 2
    assert accepted.ordering_decision == IngressOrderingDecision.ACCEPTED
    assert stale.ordering_decision == IngressOrderingDecision.STALE
