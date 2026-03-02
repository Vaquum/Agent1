from __future__ import annotations

import json
import logging
from datetime import datetime
from datetime import timezone

from _pytest.logging import LogCaptureFixture

from agent1.core.contracts import AgentEvent
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EventSource
from agent1.core.contracts import EventStatus
from agent1.core.contracts import EventType
from agent1.core.services.structured_event_logger import log_agent_event
from agent1.core.services.structured_event_logger import redact_payload
from agent1.core.services.trace_context import reset_trace_id
from agent1.core.services.trace_context import set_trace_id


def _create_event() -> AgentEvent:
    return AgentEvent(
        timestamp=datetime.now(timezone.utc),
        environment=EnvironmentName.DEV,
        trace_id='trc_event_logger',
        job_id='job_logger_1',
        entity_key='Vaquum/Agent1#99',
        source=EventSource.AGENT,
        event_type=EventType.STATE_TRANSITION,
        status=EventStatus.OK,
        details={
            'github_token': 'secret-value',
            'nested': {'authorization': 'Bearer abc', 'safe': 'value'},
        },
    )


def test_redact_payload_masks_secret_like_keys() -> None:
    payload = {
        'token': 'abc',
        'nested': {'password': 'def', 'safe': 'ok'},
        'items': [{'api_key': 'ghi'}, {'label': 'value'}],
    }

    redacted = redact_payload(payload)

    assert redacted['token'] == '[REDACTED]'
    assert redacted['nested']['password'] == '[REDACTED]'
    assert redacted['nested']['safe'] == 'ok'
    assert redacted['items'][0]['api_key'] == '[REDACTED]'
    assert redacted['items'][1]['label'] == 'value'


def test_log_agent_event_emits_structured_json_payload(caplog: LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger='agent1.events')
    token = set_trace_id('trc_active_context')
    try:
        log_agent_event(_create_event())
    finally:
        reset_trace_id(token)

    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].message)
    assert payload['trace_id'] == 'trc_event_logger'
    assert payload['active_trace_id'] == 'trc_active_context'
    assert payload['details']['github_token'] == '[REDACTED]'
    assert payload['details']['nested']['authorization'] == '[REDACTED]'
