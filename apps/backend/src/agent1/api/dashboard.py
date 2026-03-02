from __future__ import annotations

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Query

from agent1.api.dashboard_contracts import DashboardOverviewResponse
from agent1.core.services.dashboard_service import DashboardService

router = APIRouter()


def get_dashboard_service() -> DashboardService:

    '''
    Create dashboard service dependency instance for API route handlers.

    Returns:
    DashboardService: Dashboard service instance.
    '''

    return DashboardService()


@router.get('/dashboard/overview', response_model=DashboardOverviewResponse)
def get_dashboard_overview(
    limit: int = Query(default=20, ge=1, le=200),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
) -> DashboardOverviewResponse:

    '''
    Create dashboard overview response payload for operations UI consumption.

    Args:
    limit (int): Maximum rows returned for each dashboard section.
    dashboard_service (DashboardService): Dashboard service dependency.

    Returns:
    DashboardOverviewResponse: Dashboard overview payload.
    '''

    return dashboard_service.get_overview(limit)


__all__ = ['router', 'get_dashboard_overview', 'get_dashboard_service']
