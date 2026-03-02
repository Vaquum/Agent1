from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EventSource
from agent1.core.contracts import EventStatus
from agent1.core.contracts import EventType
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobState
from agent1.core.contracts import RuntimeMode


class DashboardJobSummary(BaseModel):
    model_config = ConfigDict(extra='forbid')

    job_id: str = Field(min_length=1)
    entity_key: str = Field(min_length=1)
    kind: JobKind
    state: JobState
    lease_epoch: int = Field(ge=0)
    environment: EnvironmentName
    mode: RuntimeMode
    updated_at: datetime


class DashboardTransitionSummary(BaseModel):
    model_config = ConfigDict(extra='forbid')

    job_id: str = Field(min_length=1)
    from_state: JobState
    to_state: JobState
    reason: str = Field(min_length=1)
    transition_at: datetime


class DashboardEventSummary(BaseModel):
    model_config = ConfigDict(extra='forbid')

    timestamp: datetime
    trace_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    entity_key: str = Field(min_length=1)
    source: EventSource
    event_type: EventType
    status: EventStatus
    details: dict[str, Any] = Field(default_factory=dict)


class DashboardPageSummary(BaseModel):
    model_config = ConfigDict(extra='forbid')

    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    total: int = Field(ge=0)


class DashboardOverviewFilters(BaseModel):
    model_config = ConfigDict(extra='forbid')

    entity_key: str | None = None
    job_id: str | None = None
    trace_id: str | None = None
    status: EventStatus | None = None


class DashboardOverviewResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    filters: DashboardOverviewFilters
    jobs_page: DashboardPageSummary
    transitions_page: DashboardPageSummary
    events_page: DashboardPageSummary
    jobs: list[DashboardJobSummary]
    transitions: list[DashboardTransitionSummary]
    events: list[DashboardEventSummary]


class DashboardJobTimelineResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    job: DashboardJobSummary
    transitions_page: DashboardPageSummary
    events_page: DashboardPageSummary
    transitions: list[DashboardTransitionSummary]
    events: list[DashboardEventSummary]


__all__ = [
    'DashboardEventSummary',
    'DashboardJobTimelineResponse',
    'DashboardJobSummary',
    'DashboardOverviewFilters',
    'DashboardOverviewResponse',
    'DashboardPageSummary',
    'DashboardTransitionSummary',
]
