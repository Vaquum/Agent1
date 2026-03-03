import json
from pathlib import Path

import pytest

from agent1.core.control_loader import CONTROL_FILE_NAME
from agent1.core.control_loader import ControlValidationError
from agent1.core.control_loader import load_control_bundle


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')


def _create_valid_controls(root: Path) -> None:
    _write_json(
        root / 'prompts' / CONTROL_FILE_NAME,
        {
            'version': '0.1.0',
            'templates': {
                'issue_assignment': {
                    'system_prompt': 'You are Agent1.',
                    'task_prompt': 'Handle the assigned issue.',
                }
            },
        },
    )
    _write_json(
        root / 'policies' / CONTROL_FILE_NAME,
        {
            'version': '0.1.0',
            'repo_scope': ['Vaquum/Agent1'],
            'agent_actor': 'zero-bang',
            'ignored_actors': [],
            'ignored_actor_suffixes': ['[bot]'],
            'deny_git_commands': ['git push --force'],
            'enforce_read_write_credential_split': True,
            'default_deny_github_capabilities': True,
            'fail_closed_policy_resolution': True,
            'mutating_credential_owner_by_environment': {
                'dev': 'zero-bang',
                'prod': 'zero-bang',
                'ci': 'zero-bang',
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
        },
    )
    _write_json(
        root / 'styles' / CONTROL_FILE_NAME,
        {
            'version': '0.1.0',
            'coding_style': 'clean',
            'communication_style': 'concise',
        },
    )
    _write_json(
        root / 'commenting' / CONTROL_FILE_NAME,
        {
            'version': '0.1.0',
            'require_review_thread_reply': True,
            'allow_top_level_pr_fallback': False,
            'issue_comment_mode': 'top_level_only',
        },
    )
    _write_json(
        root / 'jobs' / CONTROL_FILE_NAME,
        {
            'version': '0.1.0',
            'rules': [
                {
                    'job_kind': 'issue',
                    'terminal_states': ['completed', 'blocked'],
                }
            ],
        },
    )
    _write_json(
        root / 'runtime' / CONTROL_FILE_NAME,
        {
            'version': '0.1.0',
            'mode': 'active',
            'active_repositories': ['Vaquum/Agent1'],
            'require_sandbox_scope_for_dev_active': True,
            'sandbox_label': 'agent1-sandbox',
            'sandbox_branch_prefix': 'sandbox/',
            'poll_interval_seconds': 30,
            'watch_interval_seconds': 30,
            'max_retry_attempts': 5,
        },
    )


def test_load_control_bundle_parses_valid_controls(tmp_path: Path) -> None:
    _create_valid_controls(tmp_path)
    bundle = load_control_bundle(tmp_path)

    assert bundle.runtime.poll_interval_seconds == 30
    assert bundle.runtime.active_repositories == ['Vaquum/Agent1']
    assert bundle.runtime.require_sandbox_scope_for_dev_active is True
    assert bundle.commenting.require_review_thread_reply is True
    assert bundle.policies.agent_actor == 'zero-bang'
    assert bundle.policies.ignored_actor_suffixes == ['[bot]']


def test_load_control_bundle_fails_when_control_file_missing(tmp_path: Path) -> None:
    _create_valid_controls(tmp_path)
    (tmp_path / 'runtime' / CONTROL_FILE_NAME).unlink()

    with pytest.raises(ControlValidationError):
        load_control_bundle(tmp_path)
