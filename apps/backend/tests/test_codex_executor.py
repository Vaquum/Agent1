from __future__ import annotations

from agent1.adapters.codex.contracts import CodexTaskInput
from agent1.adapters.codex.contracts import StreamEventHandler
from agent1.config.settings import Settings
from agent1.core.contracts import ExecutionResult
from agent1.core.contracts import ExecutionStatus
from agent1.core.services.codex_executor import CodexExecutor


class _FakeCodexAdapter:
    def __init__(self) -> None:
        self.last_task_input: CodexTaskInput | None = None
        self.cancelled_task_id: str | None = None

    def execute(
        self,
        task_input: CodexTaskInput,
        event_handler: StreamEventHandler | None = None,
    ) -> ExecutionResult:
        self.last_task_input = task_input
        return ExecutionResult(
            status=ExecutionStatus.SUCCEEDED,
            summary='ok',
            command='fake',
            exit_code=0,
            metadata={},
        )

    def cancel(self, task_id: str) -> bool:
        self.cancelled_task_id = task_id
        return True


def test_codex_executor_builds_task_input_with_default_timeout() -> None:
    fake_adapter = _FakeCodexAdapter()
    settings = Settings(codex_cli_timeout_seconds=12)
    executor = CodexExecutor(codex_adapter=fake_adapter, settings=settings)

    result = executor.execute_task(task_id='task_1', prompt='run', arguments=['exec'])

    assert result.status == ExecutionStatus.SUCCEEDED
    assert fake_adapter.last_task_input is not None
    assert fake_adapter.last_task_input.timeout_seconds == 12
    assert fake_adapter.last_task_input.arguments == ['exec']


def test_codex_executor_cancel_task_delegates_to_adapter() -> None:
    fake_adapter = _FakeCodexAdapter()
    executor = CodexExecutor(codex_adapter=fake_adapter, settings=Settings(codex_cli_timeout_seconds=12))

    cancelled = executor.cancel_task('task_2')

    assert cancelled is True
    assert fake_adapter.cancelled_task_id == 'task_2'
