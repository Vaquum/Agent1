from __future__ import annotations

from datetime import datetime
from datetime import timezone

from fastapi import FastAPI
from fastapi import HTTPException
import pytest

from agent1.api.dashboard import get_dashboard_job_timeline
from agent1.api.dashboard import get_dashboard_overview
from agent1.api.dashboard import get_dashboard_service
from agent1.api.dashboard import router
from agent1.api.dashboard_contracts import DashboardEventSummary
from agent1.api.dashboard_contracts import DashboardJobTimelineResponse
from agent1.api.dashboard_contracts import DashboardJobSummary
from agent1.api.dashboard_contracts import DashboardOverviewFilters
from agent1.api.dashboard_contracts import DashboardOverviewResponse
from agent1.api.dashboard_contracts import DashboardPageSummary
from agent1.api.dashboard_contracts import DashboardTransitionSummary
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EventSource
from agent1.core.contracts import EventStatus
from agent1.core.contracts import EventType
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobState
from agent1.core.contracts import RuntimeMode


class _FakeDashboardService:
    def __init__(self) -> None:
        self.received_limit = 0
        self.received_offset = 0
        self.received_entity_key: str | None = None
        self.received_job_id: str | None = None
        self.received_trace_id: str | None = None
        self.received_status: EventStatus | None = None
        self.received_timeline_job_id: str | None = None
        self.received_timeline_limit = 0
        self.received_timeline_offset = 0

    def get_overview(
        self,
        limit: int,
        offset: int = 0,
        entity_key: str | None = None,
        job_id: str | None = None,
        trace_id: str | None = None,
        status: EventStatus | None = None,
    ) -> DashboardOverviewResponse:
        self.received_limit = limit
        self.received_offset = offset
        self.received_entity_key = entity_key
        self.received_job_id = job_id
        self.received_trace_id = trace_id
        self.received_status = status
        now = datetime.now(timezone.utc)
        return DashboardOverviewResponse(
            filters=DashboardOverviewFilters(
                entity_key=entity_key,
                job_id=job_id,
                trace_id=trace_id,
                status=status,
            ),
            jobs_page=DashboardPageSummary(limit=limit, offset=offset, total=1),
            transitions_page=DashboardPageSummary(limit=limit, offset=offset, total=1),
            events_page=DashboardPageSummary(limit=limit, offset=offset, total=1),
            jobs=[
                DashboardJobSummary(
                    job_id='job_dashboard_api_1',
                    entity_key='Vaquum/Agent1#201',
                    kind=JobKind.ISSUE,
                    state=JobState.READY_TO_EXECUTE,
                    lease_epoch=1,
                    environment=EnvironmentName.DEV,
                    mode=RuntimeMode.ACTIVE,
                    updated_at=now,
                )
            ],
            transitions=[
                DashboardTransitionSummary(
                    job_id='job_dashboard_api_1',
                    from_state=JobState.AWAITING_CONTEXT,
                    to_state=JobState.READY_TO_EXECUTE,
                    reason='context_refreshed',
                    transition_at=now,
                )
            ],
            events=[
                DashboardEventSummary(
                    timestamp=now,
                    trace_id='trc_dashboard_api_1',
                    job_id='job_dashboard_api_1',
                    entity_key='Vaquum/Agent1#201',
                    source=EventSource.AGENT,
                    event_type=EventType.STATE_TRANSITION,
                    status=EventStatus.OK,
                    details={'reason': 'context_refreshed'},
                )
            ],
        )

    def get_job_timeline(
        self,
        job_id: str,
        limit: int,
        offset: int = 0,
    ) -> DashboardJobTimelineResponse | None:
        self.received_timeline_job_id = job_id
        self.received_timeline_limit = limit
        self.received_timeline_offset = offset
        if job_id == 'missing_job':
            return None

        now = datetime.now(timezone.utc)
        return DashboardJobTimelineResponse(
            job=DashboardJobSummary(
                job_id=job_id,
                entity_key='Vaquum/Agent1#201',
                kind=JobKind.ISSUE,
                state=JobState.READY_TO_EXECUTE,
                lease_epoch=1,
                environment=EnvironmentName.DEV,
                mode=RuntimeMode.ACTIVE,
                updated_at=now,
            ),
            transitions_page=DashboardPageSummary(limit=limit, offset=offset, total=1),
            events_page=DashboardPageSummary(limit=limit, offset=offset, total=1),
            transitions=[
                DashboardTransitionSummary(
                    job_id=job_id,
                    from_state=JobState.AWAITING_CONTEXT,
                    to_state=JobState.READY_TO_EXECUTE,
                    reason='context_refreshed',
                    transition_at=now,
                )
            ],
            events=[
                DashboardEventSummary(
                    timestamp=now,
                    trace_id='trc_dashboard_api_1',
                    job_id=job_id,
                    entity_key='Vaquum/Agent1#201',
                    source=EventSource.AGENT,
                    event_type=EventType.STATE_TRANSITION,
                    status=EventStatus.OK,
                    details={'reason': 'context_refreshed'},
                )
            ],
        )


def test_dashboard_router_exposes_overview_path() -> None:
    application = FastAPI()
    application.include_router(router)
    route_paths = {route.path for route in application.routes}

    assert '/dashboard/overview' in route_paths
    assert '/dashboard/jobs/{job_id}/timeline' in route_paths


def test_get_dashboard_overview_uses_dashboard_service() -> None:
    fake_service = _FakeDashboardService()

    response = get_dashboard_overview(
        limit=7,
        offset=4,
        entity_key='Vaquum/Agent1#201',
        job_id='job_dashboard_api_1',
        trace_id='trc_dashboard_api_1',
        status=EventStatus.OK,
        dashboard_service=fake_service,
    )

    assert fake_service.received_limit == 7
    assert fake_service.received_offset == 4
    assert fake_service.received_entity_key == 'Vaquum/Agent1#201'
    assert fake_service.received_job_id == 'job_dashboard_api_1'
    assert fake_service.received_trace_id == 'trc_dashboard_api_1'
    assert fake_service.received_status == EventStatus.OK
    assert len(response.jobs) == 1
    assert len(response.transitions) == 1
    assert len(response.events) == 1
    assert response.jobs[0].job_id == 'job_dashboard_api_1'


def test_get_dashboard_job_timeline_uses_dashboard_service() -> None:
    fake_service = _FakeDashboardService()

    response = get_dashboard_job_timeline(
        job_id='job_dashboard_api_1',
        limit=9,
        offset=3,
        dashboard_service=fake_service,
    )

    assert fake_service.received_timeline_job_id == 'job_dashboard_api_1'
    assert fake_service.received_timeline_limit == 9
    assert fake_service.received_timeline_offset == 3
    assert response.job.job_id == 'job_dashboard_api_1'
    assert len(response.transitions) == 1
    assert len(response.events) == 1


def test_get_dashboard_job_timeline_raises_not_found() -> None:
    fake_service = _FakeDashboardService()

    with pytest.raises(HTTPException) as error:
        get_dashboard_job_timeline(
            job_id='missing_job',
            limit=9,
            offset=0,
            dashboard_service=fake_service,
        )

    assert error.value.status_code == 404


def test_get_dashboard_service_returns_runtime_service() -> None:
    service = get_dashboard_service()

    assert service.__class__.__name__ == 'DashboardService'
