from __future__ import annotations

from datetime import datetime
from datetime import timezone

from fastapi import FastAPI

from agent1.api.dashboard import get_dashboard_overview
from agent1.api.dashboard import get_dashboard_service
from agent1.api.dashboard import router
from agent1.api.dashboard_contracts import DashboardEventSummary
from agent1.api.dashboard_contracts import DashboardJobSummary
from agent1.api.dashboard_contracts import DashboardOverviewResponse
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

    def get_overview(self, limit: int) -> DashboardOverviewResponse:
        self.received_limit = limit
        now = datetime.now(timezone.utc)
        return DashboardOverviewResponse(
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


def test_dashboard_router_exposes_overview_path() -> None:
    application = FastAPI()
    application.include_router(router)
    route_paths = {route.path for route in application.routes}

    assert '/dashboard/overview' in route_paths


def test_get_dashboard_overview_uses_dashboard_service() -> None:
    fake_service = _FakeDashboardService()

    response = get_dashboard_overview(limit=7, dashboard_service=fake_service)

    assert fake_service.received_limit == 7
    assert len(response.jobs) == 1
    assert len(response.transitions) == 1
    assert len(response.events) == 1
    assert response.jobs[0].job_id == 'job_dashboard_api_1'


def test_get_dashboard_service_returns_runtime_service() -> None:
    service = get_dashboard_service()

    assert service.__class__.__name__ == 'DashboardService'
