from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobState


class IngressEntityType(str, Enum):
    ISSUE = 'issue'
    PR = 'pr'


class IngressEventType(str, Enum):
    ISSUE_MENTION = 'issue_mention'
    ISSUE_UPDATED = 'issue_updated'
    PR_MENTION = 'pr_mention'
    ISSUE_ASSIGNMENT = 'issue_assignment'
    PR_REVIEW_REQUESTED = 'pr_review_requested'
    PR_REVIEW_COMMENT = 'pr_review_comment'
    PR_CI_FAILED = 'pr_ci_failed'
    PR_UPDATED = 'pr_updated'


class GitHubIngressEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')

    event_id: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    entity_number: int = Field(gt=0)
    entity_type: IngressEntityType
    actor: str = Field(min_length=1)
    event_type: IngressEventType
    timestamp: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class NormalizedIngressEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')

    event_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    environment: EnvironmentName
    repository: str = Field(min_length=1)
    entity_number: int = Field(gt=0)
    entity_key: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    job_kind: JobKind
    initial_state: JobState
    should_claim_lease: bool
    transition_to: JobState | None = None
    transition_reason: str | None = None
    idempotency_key: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    'GitHubIngressEvent',
    'IngressEntityType',
    'IngressEventType',
    'NormalizedIngressEvent',
]
