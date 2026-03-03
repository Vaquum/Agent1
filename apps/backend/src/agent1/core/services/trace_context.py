from __future__ import annotations

from contextvars import ContextVar
from contextvars import Token
from uuid import uuid4

TRACE_HEADER_NAME = 'x-trace-id'
_TRACE_CONTEXT: ContextVar[str | None] = ContextVar('agent1_trace_id', default=None)


def create_trace_id() -> str:

    '''
    Create deterministic-format runtime trace identifier for correlation.

    Returns:
    str: Generated trace identifier value.
    '''

    return f'trc_{uuid4().hex}'


def get_trace_id() -> str | None:

    '''
    Create current trace identifier lookup from runtime context.

    Returns:
    str | None: Current trace identifier when present, otherwise None.
    '''

    return _TRACE_CONTEXT.get()


def set_trace_id(trace_id: str) -> Token[str | None]:

    '''
    Create trace context assignment token for scoped request handling.

    Args:
    trace_id (str): Trace identifier to set in runtime context.

    Returns:
    Token[str | None]: Context token for restoring previous trace state.
    '''

    return _TRACE_CONTEXT.set(trace_id)


def reset_trace_id(token: Token[str | None]) -> None:

    '''
    Create trace context reset using a prior assignment token.

    Args:
    token (Token[str | None]): Prior trace context token.
    '''

    _TRACE_CONTEXT.reset(token)


def get_or_create_trace_id(trace_id: str | None) -> str:

    '''
    Create non-empty trace identifier using provided or generated value.

    Args:
    trace_id (str | None): Optional incoming trace identifier.

    Returns:
    str: Existing or generated trace identifier.
    '''

    if trace_id is None or trace_id.strip() == '':
        return create_trace_id()

    return trace_id.strip()


__all__ = [
    'TRACE_HEADER_NAME',
    'create_trace_id',
    'get_or_create_trace_id',
    'get_trace_id',
    'reset_trace_id',
    'set_trace_id',
]
