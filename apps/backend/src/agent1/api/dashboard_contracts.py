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


class DashboardOverviewResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    jobs: list[DashboardJobSummary]
    transitions: list[DashboardTransitionSummary]
    events: list[DashboardEventSummary]


__all__ = [
    'DashboardEventSummary',
    'DashboardJobSummary',
    'DashboardOverviewResponse',
    'DashboardTransitionSummary',
]
