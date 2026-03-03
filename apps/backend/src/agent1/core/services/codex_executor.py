from __future__ import annotations

from agent1.adapters.codex.client import CodexCliAdapter
from agent1.adapters.codex.client import SubprocessCodexCliAdapter
from agent1.adapters.codex.contracts import CodexTaskInput
from agent1.adapters.codex.contracts import StreamEventHandler
from agent1.config.settings import Settings
from agent1.config.settings import get_settings
from agent1.core.contracts import ExecutionResult
from agent1.core.contracts import ExecutionStatus
from agent1.core.control_loader import validate_control_bundle
from agent1.core.control_schemas import PoliciesControl
from agent1.core.services.telemetry_runtime import get_tracer

GIT_MUTATION_VERBS = {
    'add',
    'checkout',
    'cherry-pick',
    'commit',
    'merge',
    'mv',
    'pull',
    'push',
    'rebase',
    'reset',
    'restore',
    'revert',
    'rm',
    'switch',
}


def _extract_explicit_git_commands(arguments: list[str], prompt: str) -> list[str]:

    '''
    Create explicit git command list from codex arguments and prompt line payload.

    Args:
    arguments (list[str]): Codex task argument list.
    prompt (str): Codex task prompt payload.

    Returns:
    list[str]: Explicit git command lines discovered in task input.
    '''

    commands: list[str] = []
    for argument in arguments:
        normalized_argument = argument.strip()
        if normalized_argument.startswith('git '):
            commands.append(normalized_argument)

    for prompt_line in prompt.splitlines():
        normalized_prompt_line = prompt_line.strip()
        if normalized_prompt_line.startswith('git '):
            commands.append(normalized_prompt_line)

    return commands


def _is_git_mutation_command(command: str) -> bool:

    '''
    Compute git mutation classification from command verb.

    Args:
    command (str): Explicit git command line.

    Returns:
    bool: True when command is classified as git mutation.
    '''

    command_tokens = command.split()
    if len(command_tokens) < 2:
        return False

    if command_tokens[0] != 'git':
        return False

    return command_tokens[1] in GIT_MUTATION_VERBS


def _matches_command_prefix(command: str, prefixes: list[str]) -> bool:

    '''
    Compute prefix match result for one command against configured command prefixes.

    Args:
    command (str): Explicit command line.
    prefixes (list[str]): Configured command prefixes.

    Returns:
    bool: True when command matches one configured prefix.
    '''

    for prefix in prefixes:
        normalized_prefix = prefix.strip()
        if normalized_prefix == '':
            continue
        if command.startswith(normalized_prefix):
            return True

    return False


class CodexExecutor:
    def __init__(
        self,
        codex_adapter: CodexCliAdapter | None = None,
        settings: Settings | None = None,
        policies: PoliciesControl | None = None,
    ) -> None:
        runtime_settings = settings or get_settings()
        self._default_timeout_seconds = runtime_settings.codex_cli_timeout_seconds
        self._codex_adapter = codex_adapter or SubprocessCodexCliAdapter(settings=runtime_settings)
        self._policies = policies or validate_control_bundle().policies

    def _resolve_blocked_git_command(self, arguments: list[str], prompt: str) -> str | None:

        '''
        Create blocked git command result from policy denylist and allowlist checks.

        Args:
        arguments (list[str]): Codex task argument list.
        prompt (str): Codex task prompt payload.

        Returns:
        str | None: Blocked git command line, or None when all commands are allowed.
        '''

        explicit_git_commands = _extract_explicit_git_commands(arguments=arguments, prompt=prompt)
        for command in explicit_git_commands:
            if _matches_command_prefix(command, self._policies.deny_git_commands):
                return command

            if _is_git_mutation_command(command):
                if len(self._policies.allowed_git_mutation_commands) == 0:
                    return command
                if _matches_command_prefix(command, self._policies.allowed_git_mutation_commands) is False:
                    return command

        return None

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

        resolved_arguments = arguments or []
        blocked_git_command = self._resolve_blocked_git_command(
            arguments=resolved_arguments,
            prompt=prompt,
        )
        if blocked_git_command is not None:
            return ExecutionResult(
                status=ExecutionStatus.BLOCKED,
                summary='Codex task blocked by git mutation command policy allowlist.',
                command=blocked_git_command,
                exit_code=None,
                metadata={'blocked_git_command': blocked_git_command},
            )

        task_input = CodexTaskInput(
            task_id=task_id,
            prompt=prompt,
            arguments=resolved_arguments,
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
