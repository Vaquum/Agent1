from __future__ import annotations

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Path
from fastapi import Query

from agent1.api.dashboard_contracts import DashboardJobTimelineResponse
from agent1.api.dashboard_contracts import DashboardOverviewResponse
from agent1.api.dashboard_contracts import StopTheLineAcknowledgeRequest
from agent1.api.dashboard_contracts import StopTheLineAcknowledgeResponse
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EventStatus
from agent1.core.services.alert_signal_service import AlertSignalService
from agent1.core.services.dashboard_service import DashboardService

router = APIRouter()


def get_dashboard_service() -> DashboardService:

    '''
    Create dashboard service dependency instance for API route handlers.

    Returns:
    DashboardService: Dashboard service instance.
    '''

    return DashboardService()


def get_alert_signal_service() -> AlertSignalService:

    '''
    Create alert-signal service dependency instance for dashboard alert routes.

    Returns:
    AlertSignalService: Alert-signal service instance.
    '''

    return AlertSignalService()


@router.get('/dashboard/overview', response_model=DashboardOverviewResponse)
def get_dashboard_overview(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    entity_key: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    trace_id: str | None = Query(default=None),
    status: EventStatus | None = Query(default=None),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
) -> DashboardOverviewResponse:

    '''
    Create dashboard overview response payload for operations UI consumption.

    Args:
    limit (int): Maximum rows returned for each dashboard section.
    offset (int): Pagination offset for each dashboard section.
    entity_key (str | None): Optional entity key filter.
    job_id (str | None): Optional job identifier filter.
    trace_id (str | None): Optional trace identifier filter.
    status (EventStatus | None): Optional event status filter.
    dashboard_service (DashboardService): Dashboard service dependency.

    Returns:
    DashboardOverviewResponse: Dashboard overview payload.
    '''

    return dashboard_service.get_overview(
        limit=limit,
        offset=offset,
        entity_key=entity_key,
        job_id=job_id,
        trace_id=trace_id,
        status=status,
    )


@router.get('/dashboard/jobs/{job_id}/timeline', response_model=DashboardJobTimelineResponse)
def get_dashboard_job_timeline(
    job_id: str = Path(min_length=1),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
) -> DashboardJobTimelineResponse:

    '''
    Create single-job timeline response payload for dashboard drill-down views.

    Args:
    job_id (str): Durable job identifier for timeline lookup.
    limit (int): Maximum rows returned for each timeline section.
    offset (int): Pagination offset for each timeline section.
    dashboard_service (DashboardService): Dashboard service dependency.

    Returns:
    DashboardJobTimelineResponse: Dashboard timeline payload for one job.
    '''

    timeline = dashboard_service.get_job_timeline(
        job_id=job_id,
        limit=limit,
        offset=offset,
    )
    if timeline is None:
        raise HTTPException(status_code=404, detail='Job timeline not found.')

    return timeline


@router.post(
    '/dashboard/alerts/stop-the-line/acknowledge',
    response_model=StopTheLineAcknowledgeResponse,
)
def acknowledge_stop_the_line_alert(
    request: StopTheLineAcknowledgeRequest,
    alert_signal_service: AlertSignalService = Depends(get_alert_signal_service),
) -> StopTheLineAcknowledgeResponse:

    '''
    Create stop-the-line alert acknowledgement record from operator acknowledgement payload.

    Args:
    request (StopTheLineAcknowledgeRequest): Operator acknowledgement request payload.
    alert_signal_service (AlertSignalService): Alert-signal service dependency.

    Returns:
    StopTheLineAcknowledgeResponse: Persisted acknowledgement response payload.
    '''

    acknowledged_at = alert_signal_service.acknowledge_stop_the_line_alert(
        environment=EnvironmentName.DEV,
        trace_id=request.trace_id,
        alert_id=request.alert_id,
        operator_id=request.operator_id,
        acknowledgement_note=request.acknowledgement_note,
    )
    return StopTheLineAcknowledgeResponse(
        trace_id=request.trace_id,
        alert_id=request.alert_id,
        operator_id=request.operator_id,
        acknowledged_at=acknowledged_at,
    )


__all__ = [
    'router',
    'get_dashboard_job_timeline',
    'get_dashboard_overview',
    'acknowledge_stop_the_line_alert',
    'get_alert_signal_service',
    'get_dashboard_service',
]
