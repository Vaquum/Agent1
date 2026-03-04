from __future__ import annotations

import sys

from agent1.adapters.codex.client import SubprocessCodexCliAdapter
from agent1.adapters.codex.contracts import CodexTaskInput
from agent1.adapters.codex.contracts import StreamEventHandler
from agent1.config.settings import Settings
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import ExecutionResult
from agent1.core.contracts import ExecutionStatus
from agent1.core.control_schemas import PoliciesControl
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


def _create_permission_matrix_payload() -> dict[str, object]:
    entries: list[dict[str, object]] = []
    for component in ['api', 'worker', 'watcher', 'dashboard', 'ci']:
        for environment in ['dev', 'prod', 'ci']:
            entries.append(
                {
                    'component': component,
                    'environment': environment,
                    'permissions': [f'{component}_read', f'{component}_write'],
                }
            )

    return {
        'entries': entries,
        'persistence_roles': {
            'migrator': ['schema_read', 'schema_write'],
            'runtime': ['data_read', 'data_write'],
            'readonly_analytics': ['data_read'],
        },
    }


def _create_protected_mutation_approval_payload() -> dict[str, object]:
    return {
        'version': '0.1.0',
        'active_snapshot': {
            'approval_id': 'approval_ci_001',
            'change_ticket': 'ci-baseline',
            'approved_by': ['ci-operator'],
            'approved_at': '2026-03-01T00:00:00Z',
            'reason': 'Baseline protected mutation approval payload for policy fixtures.',
            'protected_files': [
                {'path': 'policies/default.json', 'sha256': 'a' * 64},
                {'path': 'policies/permission-matrix.json', 'sha256': 'b' * 64},
                {'path': 'runtime/default.json', 'sha256': 'c' * 64},
            ],
        },
        'audit_trail': [
            {
                'event_id': 'approval_ci_001_event_approved',
                'approval_id': 'approval_ci_001',
                'decision': 'approved',
                'recorded_at': '2026-03-01T00:00:00Z',
                'recorded_by': 'ci-operator',
                'note': 'Fixture baseline approval.',
            }
        ],
    }


def _create_policies(allowed_git_mutation_commands: list[str]) -> PoliciesControl:
    return PoliciesControl.model_validate(
        {
            'version': '0.1.0',
            'repo_scope': ['Vaquum/Agent1'],
            'agent_actor': 'runtime-agent-user',
            'ignored_actors': [],
            'ignored_actor_suffixes': ['[bot]'],
            'deny_git_commands': ['git push --force'],
            'allowed_git_mutation_commands': allowed_git_mutation_commands,
            'branch_mutation_patterns_by_environment': {
                'dev': ['sandbox/*'],
                'prod': ['release/*'],
                'ci': ['sandbox/*', 'ci/*'],
            },
            'permission_matrix': _create_permission_matrix_payload(),
            'protected_mutation_approval': _create_protected_mutation_approval_payload(),
            'enforce_read_write_credential_split': True,
            'default_deny_github_capabilities': True,
            'fail_closed_policy_resolution': True,
            'mutating_credential_owner_by_environment': {
                'dev': 'runtime-agent-user',
                'prod': 'runtime-agent-user',
                'ci': 'runtime-agent-user',
            },
            'github_capabilities': {
                'read_notifications': True,
                'read_pr_timeline': True,
                'read_pr_check_runs': True,
                'read_issue': True,
                'read_pull_request': True,
                'write_issue_comment': True,
                'write_pr_review_reply': True,
            },
            'rules': [],
        }
    )


def test_codex_executor_builds_task_input_with_default_timeout() -> None:
    fake_adapter = _FakeCodexAdapter()
    settings = Settings(codex_cli_timeout_seconds=12)
    executor = CodexExecutor(
        codex_adapter=fake_adapter,
        settings=settings,
        policies=_create_policies(['git add', 'git commit']),
    )

    result = executor.execute_task(task_id='task_1', prompt='run', arguments=['exec'])

    assert result.status == ExecutionStatus.SUCCEEDED
    assert fake_adapter.last_task_input is not None
    assert fake_adapter.last_task_input.timeout_seconds == 12
    assert fake_adapter.last_task_input.arguments == ['exec']


def test_codex_executor_cancel_task_delegates_to_adapter() -> None:
    fake_adapter = _FakeCodexAdapter()
    executor = CodexExecutor(
        codex_adapter=fake_adapter,
        settings=Settings(codex_cli_timeout_seconds=12),
        policies=_create_policies(['git add', 'git commit']),
    )

    cancelled = executor.cancel_task('task_2')

    assert cancelled is True
    assert fake_adapter.cancelled_task_id == 'task_2'


def test_codex_executor_blocks_disallowed_git_mutation_command() -> None:
    fake_adapter = _FakeCodexAdapter()
    executor = CodexExecutor(
        codex_adapter=fake_adapter,
        settings=Settings(codex_cli_timeout_seconds=12),
        policies=_create_policies(['git add', 'git commit']),
    )

    result = executor.execute_task(
        task_id='task_blocked',
        prompt='git reset --hard',
    )

    assert result.status == ExecutionStatus.BLOCKED
    assert fake_adapter.last_task_input is None
    assert result.metadata['blocked_git_command'] == 'git reset --hard'


def test_codex_executor_blocks_explicit_denylist_git_command() -> None:
    fake_adapter = _FakeCodexAdapter()
    executor = CodexExecutor(
        codex_adapter=fake_adapter,
        settings=Settings(codex_cli_timeout_seconds=12),
        policies=_create_policies(['git add', 'git commit', 'git push']),
    )

    result = executor.execute_task(
        task_id='task_denylist_blocked',
        prompt='git push --force origin HEAD',
    )

    assert result.status == ExecutionStatus.BLOCKED
    assert fake_adapter.last_task_input is None
    assert result.metadata['blocked_git_command'] == 'git push --force origin HEAD'


def test_codex_executor_allows_push_to_allowed_dev_branch_namespace() -> None:
    fake_adapter = _FakeCodexAdapter()
    executor = CodexExecutor(
        codex_adapter=fake_adapter,
        settings=Settings(codex_cli_timeout_seconds=12),
        policies=_create_policies(['git push']),
        runtime_environment=EnvironmentName.DEV,
    )

    result = executor.execute_task(
        task_id='task_branch_allowed',
        prompt='git push origin sandbox/feature-branch',
    )

    assert result.status == ExecutionStatus.SUCCEEDED
    assert fake_adapter.last_task_input is not None


def test_codex_executor_blocks_push_to_disallowed_dev_branch_namespace() -> None:
    fake_adapter = _FakeCodexAdapter()
    executor = CodexExecutor(
        codex_adapter=fake_adapter,
        settings=Settings(codex_cli_timeout_seconds=12),
        policies=_create_policies(['git push']),
        runtime_environment=EnvironmentName.DEV,
    )

    result = executor.execute_task(
        task_id='task_branch_blocked',
        prompt='git push origin release/feature-branch',
    )

    assert result.status == ExecutionStatus.BLOCKED
    assert fake_adapter.last_task_input is None
    assert result.metadata['blocked_git_command'] == 'git push origin release/feature-branch'


def test_codex_executor_allows_checkout_branch_creation_for_allowed_namespace() -> None:
    fake_adapter = _FakeCodexAdapter()
    executor = CodexExecutor(
        codex_adapter=fake_adapter,
        settings=Settings(codex_cli_timeout_seconds=12),
        policies=_create_policies(['git checkout']),
        runtime_environment=EnvironmentName.DEV,
    )

    result = executor.execute_task(
        task_id='task_checkout_allowed',
        prompt='git checkout -b sandbox/feature-branch',
    )

    assert result.status == ExecutionStatus.SUCCEEDED
    assert fake_adapter.last_task_input is not None


def test_codex_executor_blocks_checkout_branch_creation_for_disallowed_namespace() -> None:
    fake_adapter = _FakeCodexAdapter()
    executor = CodexExecutor(
        codex_adapter=fake_adapter,
        settings=Settings(codex_cli_timeout_seconds=12),
        policies=_create_policies(['git checkout']),
        runtime_environment=EnvironmentName.DEV,
    )

    result = executor.execute_task(
        task_id='task_checkout_blocked',
        prompt='git checkout -b release/feature-branch',
    )

    assert result.status == ExecutionStatus.BLOCKED
    assert fake_adapter.last_task_input is None
    assert result.metadata['blocked_git_command'] == 'git checkout -b release/feature-branch'


def test_codex_executor_namespace_policy_integration_allows_push() -> None:
    adapter = SubprocessCodexCliAdapter(
        base_command=[sys.executable, '-c', 'print("adapter-ran")'],
        default_timeout_seconds=5,
    )
    executor = CodexExecutor(
        codex_adapter=adapter,
        settings=Settings(codex_cli_timeout_seconds=5),
        policies=_create_policies(['git push']),
        runtime_environment=EnvironmentName.DEV,
    )

    result = executor.execute_task(
        task_id='task_namespace_integration_allowed',
        prompt='git push origin sandbox/feature-branch',
    )

    assert result.status == ExecutionStatus.SUCCEEDED
    assert 'adapter-ran' in result.metadata.get('stdout', '')


def test_codex_executor_namespace_policy_integration_blocks_push() -> None:
    adapter = SubprocessCodexCliAdapter(
        base_command=[sys.executable, '-c', 'print("adapter-ran")'],
        default_timeout_seconds=5,
    )
    executor = CodexExecutor(
        codex_adapter=adapter,
        settings=Settings(codex_cli_timeout_seconds=5),
        policies=_create_policies(['git push']),
        runtime_environment=EnvironmentName.DEV,
    )

    result = executor.execute_task(
        task_id='task_namespace_integration_blocked',
        prompt='git push origin release/feature-branch',
    )

    assert result.status == ExecutionStatus.BLOCKED
    assert result.metadata['blocked_git_command'] == 'git push origin release/feature-branch'
