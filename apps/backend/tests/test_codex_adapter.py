from __future__ import annotations

import sys
import threading
import time

from agent1.adapters.codex.client import SubprocessCodexCliAdapter
from agent1.adapters.codex.contracts import CodexStreamEvent
from agent1.adapters.codex.contracts import CodexStreamEventType
from agent1.adapters.codex.contracts import CodexTaskInput
from agent1.core.contracts import ExecutionResult
from agent1.core.contracts import ExecutionStatus


def test_codex_adapter_execute_success_streams_stdout() -> None:
    script = 'import sys; payload = sys.stdin.read().strip(); print(f"ack:{payload}")'
    adapter = SubprocessCodexCliAdapter(base_command=[sys.executable, '-c', script], default_timeout_seconds=5)
    events: list[CodexStreamEvent] = []
    task_input = CodexTaskInput(task_id='task_success', prompt='hello')

    result = adapter.execute(task_input=task_input, event_handler=events.append)

    event_types = [event.event_type for event in events]
    assert result.status == ExecutionStatus.SUCCEEDED
    assert event_types[0] == CodexStreamEventType.STARTED
    assert CodexStreamEventType.STDOUT in event_types
    assert CodexStreamEventType.COMPLETED in event_types
    assert 'ack:hello' in result.metadata['stdout']


def test_codex_adapter_execute_failure_streams_stderr() -> None:
    script = 'import sys; sys.stderr.write("boom\\n"); raise SystemExit(3)'
    adapter = SubprocessCodexCliAdapter(base_command=[sys.executable, '-c', script], default_timeout_seconds=5)
    events: list[CodexStreamEvent] = []
    task_input = CodexTaskInput(task_id='task_failure', prompt='ignored')

    result = adapter.execute(task_input=task_input, event_handler=events.append)

    event_types = [event.event_type for event in events]
    assert result.status == ExecutionStatus.FAILED
    assert result.exit_code == 3
    assert CodexStreamEventType.STDERR in event_types
    assert CodexStreamEventType.FAILED in event_types
    assert 'boom' in result.metadata['stderr']


def test_codex_adapter_execute_timeout_returns_failure() -> None:
    script = 'import time; time.sleep(2)'
    adapter = SubprocessCodexCliAdapter(base_command=[sys.executable, '-c', script], default_timeout_seconds=1)
    events: list[CodexStreamEvent] = []
    task_input = CodexTaskInput(task_id='task_timeout', prompt='ignored', timeout_seconds=1)

    result = adapter.execute(task_input=task_input, event_handler=events.append)

    event_types = [event.event_type for event in events]
    assert result.status == ExecutionStatus.FAILED
    assert result.metadata['timed_out'] is True
    assert CodexStreamEventType.TIMEOUT in event_types


def test_codex_adapter_cancel_stops_active_task() -> None:
    script = 'import time; time.sleep(5)'
    adapter = SubprocessCodexCliAdapter(base_command=[sys.executable, '-c', script], default_timeout_seconds=10)
    events: list[CodexStreamEvent] = []
    task_input = CodexTaskInput(task_id='task_cancel', prompt='ignored')
    result_holder: dict[str, ExecutionResult] = {}

    def _run_execute() -> None:
        result_holder['result'] = adapter.execute(task_input=task_input, event_handler=events.append)

    worker = threading.Thread(target=_run_execute)
    worker.start()

    cancelled = False
    for _ in range(20):
        cancelled = adapter.cancel(task_input.task_id)
        if cancelled:
            break
        time.sleep(0.05)

    worker.join(timeout=10)
    event_types = [event.event_type for event in events]
    assert cancelled is True
    assert worker.is_alive() is False
    assert result_holder['result'].status == ExecutionStatus.BLOCKED
    assert result_holder['result'].metadata['cancelled'] is True
    assert CodexStreamEventType.CANCELLED in event_types
