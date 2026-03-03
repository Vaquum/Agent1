from __future__ import annotations

import fnmatch
import shlex

from agent1.adapters.codex.client import CodexCliAdapter
from agent1.adapters.codex.client import SubprocessCodexCliAdapter
from agent1.adapters.codex.contracts import CodexTaskInput
from agent1.adapters.codex.contracts import StreamEventHandler
from agent1.config.settings import Settings
from agent1.config.settings import get_settings
from agent1.core.contracts import EnvironmentName
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


def _tokenize_command(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _normalize_branch_name(branch_name: str) -> str:
    normalized_branch_name = branch_name.strip()
    if normalized_branch_name.startswith('refs/heads/'):
        return normalized_branch_name.removeprefix('refs/heads/')

    return normalized_branch_name


def _extract_checkout_or_switch_created_branch(tokens: list[str]) -> str | None:
    for token_index, token in enumerate(tokens):
        if token in {'-b', '-B', '-c', '-C'} and token_index + 1 < len(tokens):
            return _normalize_branch_name(tokens[token_index + 1])

    return None


def _extract_push_branch(tokens: list[str]) -> str | None:
    if len(tokens) < 3:
        return None

    candidate_tokens: list[str] = []
    for token in tokens[2:]:
        if token.startswith('-'):
            continue
        if token in {'origin', 'upstream'}:
            continue
        candidate_tokens.append(token)

    if len(candidate_tokens) == 0:
        return None

    first_candidate = candidate_tokens[0]
    if ':' in first_candidate:
        destination_ref = first_candidate.split(':')[-1]
        if destination_ref == '':
            return None
        return _normalize_branch_name(destination_ref)

    if first_candidate in {'HEAD', '@'}:
        return None

    return _normalize_branch_name(first_candidate)


def _extract_branch_target_for_policy(command: str) -> str | None:
    tokens = _tokenize_command(command)
    if len(tokens) < 2:
        return None
    if tokens[0] != 'git':
        return None

    command_verb = tokens[1]
    if command_verb in {'checkout', 'switch'}:
        return _extract_checkout_or_switch_created_branch(tokens)
    if command_verb == 'push':
        return _extract_push_branch(tokens)

    return None


class CodexExecutor:
    def __init__(
        self,
        codex_adapter: CodexCliAdapter | None = None,
        settings: Settings | None = None,
        policies: PoliciesControl | None = None,
        runtime_environment: EnvironmentName = EnvironmentName.DEV,
    ) -> None:
        runtime_settings = settings or get_settings()
        self._default_timeout_seconds = runtime_settings.codex_cli_timeout_seconds
        self._codex_adapter = codex_adapter or SubprocessCodexCliAdapter(settings=runtime_settings)
        self._policies = policies or validate_control_bundle().policies
        self._runtime_environment = runtime_environment

    def _list_allowed_branch_patterns(self) -> list[str]:
        patterns_by_environment = self._policies.branch_mutation_patterns_by_environment
        if self._runtime_environment == EnvironmentName.PROD:
            return patterns_by_environment.prod
        if self._runtime_environment == EnvironmentName.CI:
            return patterns_by_environment.ci

        return patterns_by_environment.dev

    def _is_branch_allowed(self, branch_name: str) -> bool:
        for pattern in self._list_allowed_branch_patterns():
            normalized_pattern = pattern.strip()
            if normalized_pattern == '':
                continue
            if fnmatch.fnmatchcase(branch_name, normalized_pattern):
                return True

        return False

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

                branch_target = _extract_branch_target_for_policy(command)
                if branch_target is not None and self._is_branch_allowed(branch_target) is False:
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
                summary='Codex task blocked by git mutation or branch namespace policy.',
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
