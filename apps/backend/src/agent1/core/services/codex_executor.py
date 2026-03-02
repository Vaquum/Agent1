from __future__ import annotations

from agent1.adapters.codex.client import CodexCliAdapter
from agent1.adapters.codex.client import SubprocessCodexCliAdapter
from agent1.adapters.codex.contracts import CodexTaskInput
from agent1.adapters.codex.contracts import StreamEventHandler
from agent1.config.settings import Settings
from agent1.config.settings import get_settings
from agent1.core.contracts import ExecutionResult
from agent1.core.services.telemetry_runtime import get_tracer


class CodexExecutor:
    def __init__(
        self,
        codex_adapter: CodexCliAdapter | None = None,
        settings: Settings | None = None,
    ) -> None:
        runtime_settings = settings or get_settings()
        self._default_timeout_seconds = runtime_settings.codex_cli_timeout_seconds
        self._codex_adapter = codex_adapter or SubprocessCodexCliAdapter(settings=runtime_settings)

    def execute_task(
        self,
        task_id: str,
        prompt: str,
        arguments: list[str] | None = None,
        working_directory: str | None = None,
        timeout_seconds: int | None = None,
        environment: dict[str, str] | None = None,
        event_handler: StreamEventHandler | None = None,
    ) -> ExecutionResult:

        '''
        Create Codex execution result for a normalized runtime task input.

        Args:
        task_id (str): Deterministic task identifier.
        prompt (str): Prompt payload for Codex execution.
        arguments (list[str] | None): Optional Codex CLI arguments.
        working_directory (str | None): Optional working directory for command execution.
        timeout_seconds (int | None): Optional timeout override in seconds.
        environment (dict[str, str] | None): Optional environment variable overrides.
        event_handler (StreamEventHandler | None): Optional stream event callback.

        Returns:
        ExecutionResult: Parsed execution result contract.
        '''

        task_input = CodexTaskInput(
            task_id=task_id,
            prompt=prompt,
            arguments=arguments or [],
            working_directory=working_directory,
            timeout_seconds=timeout_seconds or self._default_timeout_seconds,
            environment=environment or {},
        )
        with get_tracer().start_as_current_span('codex.executor.execute_task') as span:
            span.set_attribute('agent1.codex.task_id', task_id)
            span.set_attribute('agent1.codex.arguments_count', len(task_input.arguments))
            execution_result = self._codex_adapter.execute(task_input=task_input, event_handler=event_handler)
            span.set_attribute('agent1.codex.execution_status', execution_result.status.value)
            return execution_result

    def cancel_task(self, task_id: str) -> bool:

        '''
        Create runtime cancellation request for an active Codex task.

        Args:
        task_id (str): Deterministic task identifier.

        Returns:
        bool: True when cancel signal is accepted, otherwise False.
        '''

        return self._codex_adapter.cancel(task_id)


__all__ = ['CodexExecutor']
