from __future__ import annotations

from agent1.core.services.trace_context import create_trace_id
from agent1.core.services.trace_context import get_or_create_trace_id
from agent1.core.services.trace_context import get_trace_id
from agent1.core.services.trace_context import reset_trace_id
from agent1.core.services.trace_context import set_trace_id


def test_create_trace_id_uses_expected_prefix() -> None:
    trace_id = create_trace_id()

    assert trace_id.startswith('trc_')
    assert len(trace_id) > 4


def test_get_or_create_trace_id_prefers_non_empty_input() -> None:
    resolved = get_or_create_trace_id('trc_input')

    assert resolved == 'trc_input'


def test_set_and_reset_trace_id_context() -> None:
    token = set_trace_id('trc_context')

    assert get_trace_id() == 'trc_context'

    reset_trace_id(token)
    assert get_trace_id() is None
