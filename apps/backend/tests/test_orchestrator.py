from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

import pytest

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import RuntimeMode
from agent1.core.orchestrator import JobOrchestrator
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
