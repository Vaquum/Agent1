from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class EnvironmentName(str, Enum):
    DEV = 'dev'
    PROD = 'prod'
    CI = 'ci'


class RuntimeMode(str, Enum):
    ACTIVE = 'active'
    SHADOW = 'shadow'
    DRY_RUN = 'dry_run'


class EventSource(str, Enum):
    GITHUB = 'github'
    AGENT = 'agent'
    CODEX = 'codex'
    POLICY = 'policy'
    WATCHER = 'watcher'


class EventType(str, Enum):
    STATE_TRANSITION = 'state_transition'
    API_CALL = 'api_call'
    COMMENT_POST = 'comment_post'
    EXECUTION_RESULT = 'execution_result'


class EventStatus(str, Enum):
    OK = 'ok'
    RETRY = 'retry'
    BLOCKED = 'blocked'
    ERROR = 'error'


class JobKind(str, Enum):
    ISSUE = 'issue'
    PR_AUTHOR = 'pr_author'
    PR_REVIEWER = 'pr_reviewer'
    REVIEW = 'review'
    CI = 'ci'


class JobState(str, Enum):
    AWAITING_CONTEXT = 'awaiting_context'
    READY_TO_EXECUTE = 'ready_to_execute'
    EXECUTING = 'executing'
    AWAITING_HUMAN_FEEDBACK = 'awaiting_human_feedback'
    AWAITING_CI = 'awaiting_ci'
    COMPLETED = 'completed'
    BLOCKED = 'blocked'


class ExecutionStatus(str, Enum):
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    BLOCKED = 'blocked'


class CommentTargetType(str, Enum):
    ISSUE = 'issue'
    PR = 'pr'
    PR_REVIEW_THREAD = 'pr_review_thread'


class AgentEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')

    timestamp: datetime
    environment: EnvironmentName
    trace_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    entity_key: str = Field(min_length=1)
    source: EventSource
    event_type: EventType
    status: EventStatus
    details: dict[str, Any] = Field(default_factory=dict)


class JobRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    job_id: str = Field(min_length=1)
    entity_key: str = Field(min_length=1)
    kind: JobKind
    state: JobState
    idempotency_key: str = Field(min_length=1)
    lease_epoch: int = Field(ge=0)
    environment: EnvironmentName
    mode: RuntimeMode


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')

    allowed: bool
    decision_rule: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    status: ExecutionStatus
    summary: str = Field(min_length=1)
    command: str | None = None
    exit_code: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CommentTarget(BaseModel):
    model_config = ConfigDict(extra='forbid')

    target_type: CommentTargetType
    issue_number: int | None = Field(default=None, gt=0)
    pr_number: int | None = Field(default=None, gt=0)
    thread_id: str | None = None
    review_comment_id: int | None = Field(default=None, gt=0)
    path: str | None = None
    line: int | None = Field(default=None, gt=0)
    side: str | None = None


__all__ = [
    'AgentEvent',
    'CommentTarget',
    'CommentTargetType',
    'EnvironmentName',
    'EventSource',
    'EventStatus',
    'EventType',
    'ExecutionResult',
    'ExecutionStatus',
    'JobKind',
    'JobRecord',
    'JobState',
    'PolicyDecision',
    'RuntimeMode',
]
