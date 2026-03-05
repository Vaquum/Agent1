from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

import pytest

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EntityType
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
from agent1.core.ingress_contracts import NormalizedIngressEvent
from agent1.core.orchestrator import JobOrchestrator
from agent1.core.services.dashboard_service import DashboardService
from agent1.core.services.persistence_service import PersistenceService


def _create_record(job_id: str) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        entity_key='Vaquum/Agent1#11',
        kind=JobKind.ISSUE,
        state=JobState.AWAITING_CONTEXT,
        idempotency_key=f'idem_{job_id}',
        lease_epoch=0,
        environment=EnvironmentName.DEV,
        mode=RuntimeMode.ACTIVE,
    )


def test_orchestrator_create_claim_transition_flow(session_factory: sessionmaker[Session]) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)

    created = orchestrator.create_job(_create_record('job_orch_1'), trace_id='trc_orch_1')
    claimed = orchestrator.claim_job(created.job_id, trace_id='trc_orch_1')
    updated = orchestrator.transition_job(
        created.job_id,
        to_state=JobState.READY_TO_EXECUTE,
        reason='context_sufficient',
        trace_id='trc_orch_1',
    )

    assert claimed is True
    assert updated.state == JobState.READY_TO_EXECUTE


def test_orchestrator_rejects_invalid_transition(session_factory: sessionmaker[Session]) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)

    created = orchestrator.create_job(_create_record('job_orch_2'), trace_id='trc_orch_2')
    orchestrator.transition_job(
        created.job_id,
        to_state=JobState.READY_TO_EXECUTE,
        reason='context_sufficient',
        trace_id='trc_orch_2',
    )
    updated = orchestrator.transition_job(
        created.job_id,
        to_state=JobState.COMPLETED,
        reason='no_action_needed',
        trace_id='trc_orch_2',
    )

    assert updated.state == JobState.COMPLETED

    with pytest.raises(ValueError):
        orchestrator.transition_job(
            created.job_id,
            to_state=JobState.EXECUTING,
            reason='invalid_after_complete',
            trace_id='trc_orch_2',
        )


def test_orchestrator_transition_with_outbox(session_factory: sessionmaker[Session]) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)

    created = orchestrator.create_job(_create_record('job_orch_3'), trace_id='trc_orch_3')
    ready = orchestrator.transition_job(
        created.job_id,
        to_state=JobState.READY_TO_EXECUTE,
        reason='context_sufficient',
        trace_id='trc_orch_3',
    )
    transitioned, outbox_records = orchestrator.transition_job_with_outbox(
        ready.job_id,
        to_state=JobState.EXECUTING,
        reason='mention_action_started',
        trace_id='trc_orch_3',
        outbox_requests=[
            OutboxWriteRequest(
                outbox_id='outbox_orch_1',
                job_id=ready.job_id,
                entity_key=ready.entity_key,
                environment=ready.environment,
                action_type=OutboxActionType.ISSUE_COMMENT,
                target_identity='Vaquum/Agent1#11:issue',
                payload={
                    'repository': 'Vaquum/Agent1',
                    'issue_number': 11,
                    'body': 'outbox orchestrated',
                },
                idempotency_key='orch_outbox_idem_1',
                job_lease_epoch=ready.lease_epoch,
            ),
        ],
    )

    assert transitioned.state == JobState.EXECUTING
    assert len(outbox_records) == 1
    assert outbox_records[0].status == OutboxStatus.PENDING


def test_orchestrator_blocked_transition_includes_default_details(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    dashboard_service = DashboardService(session_factory=session_factory)
    created = orchestrator.create_job(_create_record('job_orch_blocked_details'), trace_id='trc_orch_blocked')
    ready = orchestrator.transition_job(
        created.job_id,
        to_state=JobState.READY_TO_EXECUTE,
        reason='context_sufficient',
        trace_id='trc_orch_blocked',
    )
    orchestrator.transition_job(
        ready.job_id,
        to_state=JobState.BLOCKED,
        reason='reviewer_response_failed',
        trace_id='trc_orch_blocked',
    )
    timeline = dashboard_service.get_job_timeline(
        job_id=ready.job_id,
        limit=20,
        offset=0,
    )

    assert timeline is not None
    blocked_transition_event = next(
        event for event in timeline.events
        if event.details.get('action') == 'transition_job'
        and event.details.get('to_state') == JobState.BLOCKED.value
    )
    transition_details = blocked_transition_event.details.get('transition_details')
    assert isinstance(transition_details, dict)
    assert transition_details.get('error_type') == 'UnknownBlockedTransition'
    assert transition_details.get('error_message') == (
        'Blocked transition without explicit error details. reason=reviewer_response_failed'
    )


def test_orchestrator_persist_ingress_event_and_validate_mutating_lease(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(_create_record('job_orch_4'), trace_id='trc_orch_4')
    ingress_event = GitHubIngressEvent(
        event_id='evt_orch_ingress_1',
        repository='Vaquum/Agent1',
        entity_number=11,
        entity_type=IngressEntityType.ISSUE,
        actor='mikkokotila',
        event_type=IngressEventType.ISSUE_MENTION,
        timestamp=datetime.now(timezone.utc),
        details={},
    )

    persisted_ingress_event = orchestrator.persist_ingress_event(
        ingress_event=ingress_event,
        environment=EnvironmentName.DEV,
    )
    valid_before_claim = orchestrator.validate_mutating_lease(
        created.job_id,
        expected_lease_epoch=0,
        trace_id='trc_orch_4',
    )
    orchestrator.claim_job(created.job_id, trace_id='trc_orch_4')
    stale_after_claim = orchestrator.validate_mutating_lease(
        created.job_id,
        expected_lease_epoch=0,
        trace_id='trc_orch_4',
    )

    assert persisted_ingress_event.ordering_decision == IngressOrderingDecision.ACCEPTED
    assert valid_before_claim is True
    assert stale_after_claim is False


def test_orchestrator_ensures_entity_create_and_touch(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    normalized_event = NormalizedIngressEvent(
        event_id='evt_orch_entity_1',
        trace_id='trc_orch_entity_1',
        environment=EnvironmentName.DEV,
        repository='Vaquum/Agent1',
        entity_number=11,
        entity_key='Vaquum/Agent1#11',
        job_id='Vaquum_Agent1#11:issue',
        job_kind=JobKind.ISSUE,
        initial_state=JobState.READY_TO_EXECUTE,
        should_claim_lease=True,
        transition_to=JobState.READY_TO_EXECUTE,
        transition_reason='issue_mention',
        idempotency_key='idem_evt_orch_entity_1',
        details={
            'actor': 'mikkokotila',
            'ingress_event_type': 'issue_mention',
            'is_sandbox_scope': True,
        },
    )

    first_entity = orchestrator.ensure_entity(normalized_event)
    second_entity = orchestrator.ensure_entity(normalized_event)

    assert first_entity.entity_key == 'Vaquum/Agent1#11'
    assert first_entity.entity_type == EntityType.ISSUE
    assert first_entity.is_sandbox is True
    assert second_entity.last_event_at is not None
