from __future__ import annotations

from datetime import datetime
from datetime import timezone

from _pytest.monkeypatch import MonkeyPatch
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.services import persistence_service as persistence_service_module
from agent1.core.contracts import AgentEvent
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
