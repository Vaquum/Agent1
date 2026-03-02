from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Callable

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class CodexStreamEventType(str, Enum):
    STARTED = 'started'
    STDOUT = 'stdout'
    STDERR = 'stderr'
    COMPLETED = 'completed'
    FAILED = 'failed'
    TIMEOUT = 'timeout'
    CANCELLED = 'cancelled'


class CodexTaskInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    task_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    arguments: list[str] = Field(default_factory=list)
    working_directory: str | None = None
    timeout_seconds: int | None = Field(default=None, gt=0)
    environment: dict[str, str] = Field(default_factory=dict)


class CodexStreamEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')

    task_id: str = Field(min_length=1)
    event_type: CodexStreamEventType
    timestamp: datetime
    message: str


StreamEventHandler = Callable[[CodexStreamEvent], None]


__all__ = [
    'CodexStreamEvent',
    'CodexStreamEventType',
    'CodexTaskInput',
    'StreamEventHandler',
]
