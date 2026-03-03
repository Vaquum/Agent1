from datetime import datetime
from datetime import timezone

import pytest
from pydantic import ValidationError

from agent1.core.contracts import AgentEvent
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EventSource
from agent1.core.contracts import EventStatus
from agent1.core.contracts import EventType
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import RuntimeMode


def test_agent_event_parses_valid_payload() -> None:
    event = AgentEvent(
        timestamp=datetime.now(timezone.utc),
        environment=EnvironmentName.DEV,
        trace_id='trc_123',
        job_id='job_123',
        entity_key='Vaquum/Agent1#1',
        source=EventSource.GITHUB,
        event_type=EventType.STATE_TRANSITION,
        status=EventStatus.OK,
        details={'message': 'ok'},
    )

    assert event.environment == EnvironmentName.DEV
    assert event.source == EventSource.GITHUB


def test_job_record_rejects_negative_lease_epoch() -> None:
    with pytest.raises(ValidationError):
        JobRecord(
            job_id='job_456',
            entity_key='Vaquum/Agent1#2',
            kind=JobKind.ISSUE,
            state=JobState.AWAITING_CONTEXT,
            idempotency_key='idem_456',
            lease_epoch=-1,
            environment=EnvironmentName.DEV,
            mode=RuntimeMode.ACTIVE,
        )
