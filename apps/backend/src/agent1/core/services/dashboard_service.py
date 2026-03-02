from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.api.dashboard_contracts import DashboardEventSummary
from agent1.api.dashboard_contracts import DashboardJobSummary
from agent1.api.dashboard_contracts import DashboardOverviewResponse
from agent1.api.dashboard_contracts import DashboardTransitionSummary
from agent1.db.models import EventJournalModel
from agent1.db.models import JobModel
from agent1.db.models import JobTransitionModel
from agent1.db.repositories.event_repository import EventRepository
from agent1.db.repositories.job_repository import JobRepository
from agent1.db.session import create_session_factory


def _to_job_summary(job_model: JobModel) -> DashboardJobSummary:

    '''
    Create dashboard job summary payload from persisted job row.

    Args:
    job_model (JobModel): Persisted job row.

    Returns:
    DashboardJobSummary: Dashboard job summary payload.
    '''

    return DashboardJobSummary(
        job_id=job_model.job_id,
        entity_key=job_model.entity_key,
        kind=job_model.kind,
        state=job_model.state,
        lease_epoch=job_model.lease_epoch,
        environment=job_model.environment,
        mode=job_model.mode,
        updated_at=job_model.updated_at,
    )


def _to_transition_summary(transition_model: JobTransitionModel) -> DashboardTransitionSummary:

    '''
    Create dashboard transition summary payload from persisted transition row.

    Args:
    transition_model (JobTransitionModel): Persisted transition row.

    Returns:
    DashboardTransitionSummary: Dashboard transition summary payload.
    '''

    return DashboardTransitionSummary(
        job_id=transition_model.job_id,
        from_state=transition_model.from_state,
        to_state=transition_model.to_state,
        reason=transition_model.reason,
        transition_at=transition_model.transition_at,
    )


def _to_event_summary(event_model: EventJournalModel) -> DashboardEventSummary:

    '''
    Create dashboard event summary payload from persisted event journal row.

    Args:
    event_model (EventJournalModel): Persisted event journal row.

    Returns:
    DashboardEventSummary: Dashboard event summary payload.
    '''

    return DashboardEventSummary(
        timestamp=event_model.timestamp,
        trace_id=event_model.trace_id,
        job_id=event_model.job_id,
        entity_key=event_model.entity_key,
        source=event_model.source,
        event_type=event_model.event_type,
        status=event_model.status,
        details=event_model.details,
    )


class DashboardService:
    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self._session_factory = session_factory or create_session_factory()

    def get_overview(self, limit: int) -> DashboardOverviewResponse:

        '''
        Create dashboard overview snapshot for jobs, transitions, and events.

        Args:
        limit (int): Maximum number of rows per section.

        Returns:
        DashboardOverviewResponse: Dashboard overview payload.
        '''

        with self._session_factory() as session:
            job_repository = JobRepository(session)
            event_repository = EventRepository(session)
            jobs = job_repository.list_recent_jobs(limit)
            transitions = job_repository.list_recent_transitions(limit)
            events = event_repository.list_recent_events(limit)
            return DashboardOverviewResponse(
                jobs=[_to_job_summary(job_model) for job_model in jobs],
                transitions=[
                    _to_transition_summary(transition_model)
                    for transition_model in transitions
                ],
                events=[_to_event_summary(event_model) for event_model in events],
            )


__all__ = ['DashboardService']
