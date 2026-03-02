from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import RuntimeMode
from agent1.db.models import JobTransitionModel
from agent1.db.repositories.job_repository import JobRepository


def _create_record(job_id: str) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        entity_key='Vaquum/Agent1#1',
        kind=JobKind.ISSUE,
        state=JobState.AWAITING_CONTEXT,
        idempotency_key=f'idem_{job_id}',
        lease_epoch=0,
        environment=EnvironmentName.DEV,
        mode=RuntimeMode.ACTIVE,
    )


def test_create_job_and_get_by_id(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        repository = JobRepository(session)
        repository.create_job(_create_record('job_1'))
        session.commit()

        fetched = repository.get_job_by_job_id('job_1')

        assert fetched is not None
        assert fetched.job_id == 'job_1'
        assert fetched.state == JobState.AWAITING_CONTEXT


def test_claim_job_lease_uses_epoch_fencing(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        repository = JobRepository(session)
        repository.create_job(_create_record('job_2'))
        session.commit()

        first_claim = repository.claim_job_lease('job_2', 0)
        session.commit()

        stale_claim = repository.claim_job_lease('job_2', 0)
        session.commit()

        assert first_claim is True
        assert stale_claim is False


def test_transition_job_state_records_transition(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        repository = JobRepository(session)
        repository.create_job(_create_record('job_3'))
        session.commit()

        repository.transition_job_state('job_3', JobState.EXECUTING, 'start_execution')
        session.commit()

        fetched = repository.get_job_by_job_id('job_3')
        transition_count = session.query(JobTransitionModel).count()

        assert fetched is not None
        assert fetched.state == JobState.EXECUTING
        assert transition_count == 1


def test_list_recent_jobs_orders_by_updated_at_desc(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repository = JobRepository(session)
        repository.create_job(_create_record('job_recent_1'))
        repository.create_job(_create_record('job_recent_2'))
        session.commit()
        repository.transition_job_state('job_recent_2', JobState.EXECUTING, 'recent_two')
        session.commit()

        recent_jobs = repository.list_recent_jobs(limit=1)

        assert len(recent_jobs) == 1
        assert recent_jobs[0].job_id == 'job_recent_2'


def test_list_recent_transitions_orders_by_transition_at_desc(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repository = JobRepository(session)
        repository.create_job(_create_record('job_transition_1'))
        repository.create_job(_create_record('job_transition_2'))
        session.commit()
        repository.transition_job_state('job_transition_1', JobState.EXECUTING, 'first_transition')
        session.commit()
        repository.transition_job_state('job_transition_2', JobState.EXECUTING, 'second_transition')
        session.commit()

        recent_transitions = repository.list_recent_transitions(limit=1)

        assert len(recent_transitions) == 1
        assert recent_transitions[0].job_id == 'job_transition_2'


def test_recent_list_queries_apply_filters_and_counts(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repository = JobRepository(session)
        repository.create_job(_create_record('job_filter_1'))
        repository.create_job(
            JobRecord(
                job_id='job_filter_2',
                entity_key='Vaquum/Agent1#2',
                kind=JobKind.ISSUE,
                state=JobState.AWAITING_CONTEXT,
                idempotency_key='idem_job_filter_2',
                lease_epoch=0,
                environment=EnvironmentName.DEV,
                mode=RuntimeMode.ACTIVE,
            )
        )
        session.commit()
        repository.transition_job_state('job_filter_1', JobState.EXECUTING, 'first')
        session.commit()
        repository.transition_job_state('job_filter_2', JobState.EXECUTING, 'second')
        session.commit()

        filtered_jobs = repository.list_recent_jobs(
            limit=10,
            offset=0,
            entity_key='Vaquum/Agent1#2',
        )
        filtered_transitions = repository.list_recent_transitions(
            limit=10,
            offset=0,
            entity_key='Vaquum/Agent1#2',
        )
        filtered_job_count = repository.count_jobs(entity_key='Vaquum/Agent1#2')
        filtered_transition_count = repository.count_transitions(entity_key='Vaquum/Agent1#2')

        assert len(filtered_jobs) == 1
        assert filtered_jobs[0].job_id == 'job_filter_2'
        assert len(filtered_transitions) == 1
        assert filtered_transitions[0].job_id == 'job_filter_2'
        assert filtered_job_count == 1
        assert filtered_transition_count == 1
