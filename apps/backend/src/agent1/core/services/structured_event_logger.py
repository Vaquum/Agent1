from __future__ import annotations

import json
import logging
from typing import Any

from agent1.core.contracts import AgentEvent
from agent1.core.services.telemetry_runtime import get_otel_trace_id
from agent1.core.services.trace_context import get_trace_id

LOGGER_NAME = 'agent1.events'
REDACTED_VALUE = '[REDACTED]'
_SECRET_KEY_MARKERS = ('token', 'secret', 'password', 'authorization', 'api_key', 'dsn')


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _SECRET_KEY_MARKERS)


def redact_payload(payload: Any) -> Any:

    '''
    Create redacted payload copy with secret-like keys replaced.

    Args:
    payload (Any): Payload value to redact recursively.

    Returns:
    Any: Redacted payload value.
    '''

    if isinstance(payload, dict):
        return {
            key: REDACTED_VALUE if _is_secret_key(key) else redact_payload(value)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact_payload(item) for item in payload]
    if isinstance(payload, tuple):
        return tuple(redact_payload(item) for item in payload)
    return payload


def _create_logger() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    return logger


def log_agent_event(event: AgentEvent) -> None:

    '''
    Create structured JSON log line from typed AgentEvent contract.

    Args:
    event (AgentEvent): Event payload to emit as structured runtime log.
    '''

    active_trace_id = get_trace_id()
    otel_trace_id = get_otel_trace_id()
    payload = {
        'timestamp': event.timestamp.isoformat(),
        'environment': event.environment.value,
        'trace_id': event.trace_id,
        'active_trace_id': active_trace_id,
        'otel_trace_id': otel_trace_id,
        'job_id': event.job_id,
        'entity_key': event.entity_key,
        'source': event.source.value,
        'event_type': event.event_type.value,
        'status': event.status.value,
        'details': redact_payload(event.details),
    }
    _create_logger().info(
        json.dumps(
            payload,
            separators=(',', ':'),
            sort_keys=True,
        )
    )


__all__ = ['log_agent_event', 'redact_payload']
