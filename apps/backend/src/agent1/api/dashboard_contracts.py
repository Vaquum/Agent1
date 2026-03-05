from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from agent1.core.contracts import ActionAttemptStatus
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EventSource
from agent1.core.contracts import EventStatus
from agent1.core.contracts import EventType
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobState
from agent1.core.contracts import OutboxActionType
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


class DashboardActionAttemptSummary(BaseModel):
    model_config = ConfigDict(extra='forbid')

    attempt_id: str = Field(min_length=1)
    outbox_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    action_type: OutboxActionType
    status: ActionAttemptStatus
    error_message: str | None = None
    attempt_started_at: datetime
    attempt_completed_at: datetime | None = None


class DashboardAnomalySummary(BaseModel):
    model_config = ConfigDict(extra='forbid')

    timestamp: datetime
    trace_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    entity_key: str = Field(min_length=1)
    alert_name: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    runbook: str = Field(min_length=1)
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


class DashboardActiveRepositoriesResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    active_repositories: list[str] = Field(min_length=1)


class DashboardActiveRepositoriesUpdateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    active_repositories: list[str] = Field(min_length=1)


class DashboardOverviewResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    filters: DashboardOverviewFilters
    jobs_page: DashboardPageSummary
    transitions_page: DashboardPageSummary
    events_page: DashboardPageSummary
    anomalies_page: DashboardPageSummary
    jobs: list[DashboardJobSummary]
    transitions: list[DashboardTransitionSummary]
    events: list[DashboardEventSummary]
    anomalies: list[DashboardAnomalySummary]


class DashboardJobTimelineResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    job: DashboardJobSummary
    transitions_page: DashboardPageSummary
    events_page: DashboardPageSummary
    action_attempts_page: DashboardPageSummary
    transitions: list[DashboardTransitionSummary]
    events: list[DashboardEventSummary]
    action_attempts: list[DashboardActionAttemptSummary]


class StopTheLineAcknowledgeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    trace_id: str = Field(min_length=1)
    alert_id: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    acknowledgement_note: str = Field(min_length=1)


class StopTheLineAcknowledgeResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    trace_id: str = Field(min_length=1)
    alert_id: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    acknowledged_at: datetime


__all__ = [
    'DashboardActiveRepositoriesResponse',
    'DashboardActiveRepositoriesUpdateRequest',
    'DashboardActionAttemptSummary',
    'DashboardAnomalySummary',
    'DashboardEventSummary',
    'DashboardJobTimelineResponse',
    'DashboardJobSummary',
    'DashboardOverviewFilters',
    'DashboardOverviewResponse',
    'DashboardPageSummary',
    'DashboardTransitionSummary',
    'StopTheLineAcknowledgeRequest',
    'StopTheLineAcknowledgeResponse',
]
