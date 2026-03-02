from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.api.dashboard_contracts import DashboardEventSummary
from agent1.api.dashboard_contracts import DashboardJobTimelineResponse
from agent1.api.dashboard_contracts import DashboardJobSummary
from agent1.api.dashboard_contracts import DashboardOverviewFilters
from agent1.api.dashboard_contracts import DashboardOverviewResponse
from agent1.api.dashboard_contracts import DashboardPageSummary
from agent1.api.dashboard_contracts import DashboardTransitionSummary
from agent1.core.contracts import EventStatus
from agent1.db.models import EventJournalModel
from agent1.db.models import JobModel
from agent1.db.models import JobTransitionModel
from agent1.db.repositories.event_repository import EventRepository
from agent1.db.repositories.job_repository import JobRepository
from agent1.db.session import create_session_factory


def _normalize_optional_filter(value: str | None) -> str | None:

    '''
    Create normalized optional filter string with empty values removed.

    Args:
    value (str | None): Optional raw filter input.

    Returns:
    str | None: Trimmed filter string, or None when empty.
    '''

    if value is None:
        return None

    normalized = value.strip()
    if normalized == '':
        return None

    return normalized


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

    def get_overview(
        self,
        limit: int,
        offset: int = 0,
        entity_key: str | None = None,
        job_id: str | None = None,
        trace_id: str | None = None,
        status: EventStatus | None = None,
    ) -> DashboardOverviewResponse:

        '''
        Create dashboard overview snapshot for jobs, transitions, and events.

        Args:
        limit (int): Maximum number of rows per section.
        offset (int): Pagination offset for each section.
        entity_key (str | None): Optional entity key filter.
        job_id (str | None): Optional job identifier filter.
        trace_id (str | None): Optional trace identifier filter.
        status (EventStatus | None): Optional event status filter.

        Returns:
        DashboardOverviewResponse: Dashboard overview payload.
        '''

        normalized_entity_key = _normalize_optional_filter(entity_key)
        normalized_job_id = _normalize_optional_filter(job_id)
        normalized_trace_id = _normalize_optional_filter(trace_id)

        with self._session_factory() as session:
            job_repository = JobRepository(session)
            event_repository = EventRepository(session)
            jobs = job_repository.list_recent_jobs(
                limit=limit,
                offset=offset,
                entity_key=normalized_entity_key,
                job_id=normalized_job_id,
            )
            transitions = job_repository.list_recent_transitions(
                limit=limit,
                offset=offset,
                entity_key=normalized_entity_key,
                job_id=normalized_job_id,
            )
            events = event_repository.list_recent_events(
                limit=limit,
                offset=offset,
                entity_key=normalized_entity_key,
                job_id=normalized_job_id,
                trace_id=normalized_trace_id,
                status=status,
            )
            jobs_total = job_repository.count_jobs(
                entity_key=normalized_entity_key,
                job_id=normalized_job_id,
            )
            transitions_total = job_repository.count_transitions(
                entity_key=normalized_entity_key,
                job_id=normalized_job_id,
            )
            events_total = event_repository.count_events(
                entity_key=normalized_entity_key,
                job_id=normalized_job_id,
                trace_id=normalized_trace_id,
                status=status,
            )
            return DashboardOverviewResponse(
                filters=DashboardOverviewFilters(
                    entity_key=normalized_entity_key,
                    job_id=normalized_job_id,
                    trace_id=normalized_trace_id,
                    status=status,
                ),
                jobs_page=DashboardPageSummary(
                    limit=limit,
                    offset=offset,
                    total=jobs_total,
                ),
                transitions_page=DashboardPageSummary(
                    limit=limit,
                    offset=offset,
                    total=transitions_total,
                ),
                events_page=DashboardPageSummary(
                    limit=limit,
                    offset=offset,
                    total=events_total,
                ),
                jobs=[_to_job_summary(job_model) for job_model in jobs],
                transitions=[
                    _to_transition_summary(transition_model)
                    for transition_model in transitions
                ],
                events=[_to_event_summary(event_model) for event_model in events],
            )

    def get_job_timeline(
        self,
        job_id: str,
        limit: int,
        offset: int = 0,
    ) -> DashboardJobTimelineResponse | None:

        '''
        Create single-job timeline snapshot for transition and event drill-down views.

        Args:
        job_id (str): Durable job identifier for timeline lookup.
        limit (int): Maximum number of rows per timeline section.
        offset (int): Pagination offset for timeline sections.

        Returns:
        DashboardJobTimelineResponse | None: Timeline payload, or None when job is missing.
        '''

        normalized_job_id = _normalize_optional_filter(job_id)
        if normalized_job_id is None:
            return None

        with self._session_factory() as session:
            job_repository = JobRepository(session)
            event_repository = EventRepository(session)
            job_model = job_repository.get_job_by_job_id(normalized_job_id)
            if job_model is None:
                return None

            transitions = job_repository.list_recent_transitions(
                limit=limit,
                offset=offset,
                job_id=normalized_job_id,
            )
            events = event_repository.list_recent_events(
                limit=limit,
                offset=offset,
                job_id=normalized_job_id,
            )
            transitions_total = job_repository.count_transitions(job_id=normalized_job_id)
            events_total = event_repository.count_events(job_id=normalized_job_id)
            return DashboardJobTimelineResponse(
                job=_to_job_summary(job_model),
                transitions_page=DashboardPageSummary(
                    limit=limit,
                    offset=offset,
                    total=transitions_total,
                ),
                events_page=DashboardPageSummary(
                    limit=limit,
                    offset=offset,
                    total=events_total,
                ),
                transitions=[
                    _to_transition_summary(transition_model)
                    for transition_model in transitions
                ],
                events=[_to_event_summary(event_model) for event_model in events],
            )


__all__ = ['DashboardService']
