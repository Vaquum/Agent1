from __future__ import annotations

import json
from collections.abc import Mapping
from urllib.request import Request

import pytest

import agent1.adapters.github.client as github_client_module
from agent1.adapters.github.client import GitHubPolicyError
from agent1.adapters.github.client import UrlLibGitHubApiClient
from agent1.config.settings import Settings
from agent1.core.contracts import EnvironmentName
from agent1.core.control_loader import ControlValidationError
from agent1.core.control_schemas import PoliciesControl


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def __enter__(self) -> '_FakeResponse':
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        _ = exc_type
        _ = exc
        _ = traceback

    def read(self) -> bytes:
        return json.dumps(self._payload).encode('utf-8')


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


def _create_policies(
    capability_overrides: Mapping[str, bool] | None = None,
    enforce_read_write_credential_split: bool = True,
    fail_closed_policy_resolution: bool = True,
) -> PoliciesControl:
    capability_payload: dict[str, bool] = {
        'read_notifications': True,
        'read_pr_timeline': True,
        'read_pr_check_runs': True,
        'read_issue': True,
        'read_pull_request': True,
        'write_issue_comment': True,
        'write_pr_review_reply': True,
    }
    for capability_key, capability_value in (capability_overrides or {}).items():
        capability_payload[capability_key] = capability_value

    return PoliciesControl.model_validate(
        {
            'version': '0.1.0',
            'repo_scope': ['Vaquum/Agent1'],
            'agent_actor': 'runtime-agent-user',
            'ignored_actors': [],
            'ignored_actor_suffixes': ['[bot]'],
            'deny_git_commands': ['git push --force'],
            'allowed_git_mutation_commands': ['git add', 'git commit', 'git push'],
            'branch_mutation_patterns_by_environment': {
                'dev': ['sandbox/*'],
                'prod': ['release/*'],
                'ci': ['sandbox/*', 'ci/*'],
            },
            'permission_matrix': _create_permission_matrix_payload(),
            'protected_mutation_approval': _create_protected_mutation_approval_payload(),
            'enforce_read_write_credential_split': enforce_read_write_credential_split,
            'default_deny_github_capabilities': True,
            'fail_closed_policy_resolution': fail_closed_policy_resolution,
            'mutating_credential_owner_by_environment': {
                'dev': 'runtime-agent-user',
                'prod': 'runtime-agent-user',
                'ci': 'runtime-agent-user',
            },
            'github_capabilities': capability_payload,
            'rules': [],
        }
    )


def _create_settings(
    github_token: str = '',
) -> Settings:
    return Settings(
        github_api_url='https://api.github.com',
        github_user='runtime-agent-user',
        github_token=github_token,
    )


def test_github_client_denies_mutation_when_capability_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    policies = _create_policies(capability_overrides={'write_issue_comment': False})
    settings = _create_settings(github_token='shared-token')

    def _unexpected_urlopen(request: Request, timeout: int = 0) -> _FakeResponse:
        _ = request
        _ = timeout
        raise AssertionError('urlopen must not be called when capability is denied')

    monkeypatch.setattr(github_client_module, 'urlopen', _unexpected_urlopen)
    client = UrlLibGitHubApiClient(
        settings=settings,
        policies=policies,
        environment=EnvironmentName.DEV,
    )

    with pytest.raises(GitHubPolicyError):
        client.post_issue_comment(
            repository='Vaquum/Agent1',
            issue_number=1,
            body='blocked comment',
        )


def test_github_client_requires_github_token(monkeypatch: pytest.MonkeyPatch) -> None:
    policies = _create_policies()
    settings = _create_settings()

    def _unexpected_urlopen(request: Request, timeout: int = 0) -> _FakeResponse:
        _ = request
        _ = timeout
        raise AssertionError('urlopen must not be called when token split fails')

    monkeypatch.setattr(github_client_module, 'urlopen', _unexpected_urlopen)
    client = UrlLibGitHubApiClient(
        settings=settings,
        policies=policies,
        environment=EnvironmentName.DEV,
    )

    with pytest.raises(GitHubPolicyError, match='Missing GITHUB_TOKEN'):
        client.fetch_notifications()


def test_github_client_rejects_mutation_when_owner_preflight_mismatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policies = _create_policies()
    settings = _create_settings(github_token='shared-token')
    requested_urls: list[str] = []

    def _urlopen(request: Request, timeout: int = 0) -> _FakeResponse:
        _ = timeout
        requested_urls.append(request.full_url)
        if request.full_url.endswith('/user'):
            return _FakeResponse({'login': 'mikkokotila'})

        return _FakeResponse({})

    monkeypatch.setattr(github_client_module, 'urlopen', _urlopen)
    client = UrlLibGitHubApiClient(
        settings=settings,
        policies=policies,
        environment=EnvironmentName.DEV,
    )

    with pytest.raises(GitHubPolicyError):
        client.post_issue_comment(
            repository='Vaquum/Agent1',
            issue_number=2,
            body='owner mismatch',
        )

    assert requested_urls == ['https://api.github.com/user']


def test_github_client_uses_shared_token_for_read_and_write_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policies = _create_policies()
    settings = _create_settings(github_token='shared-token')
    request_headers: list[tuple[str, str]] = []

    def _urlopen(request: Request, timeout: int = 0) -> _FakeResponse:
        _ = timeout
        authorization = request.get_header('Authorization') or ''
        request_headers.append((request.full_url, authorization))
        if request.full_url.endswith('/notifications?all=true&participating=false&per_page=100&page=1'):
            return _FakeResponse([])
        if request.full_url.endswith('/user'):
            return _FakeResponse({'login': 'runtime-agent-user'})
        if request.full_url.endswith('/repos/Vaquum/Agent1/issues/3/comments'):
            return _FakeResponse({'id': 123})

        return _FakeResponse({})

    monkeypatch.setattr(github_client_module, 'urlopen', _urlopen)
    client = UrlLibGitHubApiClient(
        settings=settings,
        policies=policies,
        environment=EnvironmentName.DEV,
    )

    client.fetch_notifications()
    client.post_issue_comment(
        repository='Vaquum/Agent1',
        issue_number=3,
        body='token routing',
    )

    assert request_headers[0][1] == 'Bearer shared-token'
    assert request_headers[1][0].endswith('/user')
    assert request_headers[1][1] == 'Bearer shared-token'
    assert request_headers[2][0].endswith('/repos/Vaquum/Agent1/issues/3/comments')
    assert request_headers[2][1] == 'Bearer shared-token'


def test_github_client_submits_pull_request_review_with_shared_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policies = _create_policies()
    settings = _create_settings(github_token='shared-token')
    request_headers: list[tuple[str, str]] = []

    def _urlopen(request: Request, timeout: int = 0) -> _FakeResponse:
        _ = timeout
        authorization = request.get_header('Authorization') or ''
        request_headers.append((request.full_url, authorization))
        if request.full_url.endswith('/user'):
            return _FakeResponse({'login': 'runtime-agent-user'})
        if request.full_url.endswith('/repos/Vaquum/Agent1/pulls/4/reviews'):
            return _FakeResponse({'id': 222, 'state': 'CHANGES_REQUESTED'})

        return _FakeResponse({})

    monkeypatch.setattr(github_client_module, 'urlopen', _urlopen)
    client = UrlLibGitHubApiClient(
        settings=settings,
        policies=policies,
        environment=EnvironmentName.DEV,
    )

    payload = client.submit_pull_request_review(
        repository='Vaquum/Agent1',
        pull_number=4,
        body='requesting changes',
        event='REQUEST_CHANGES',
    )

    assert payload.get('id') == 222
    assert request_headers[0][0].endswith('/user')
    assert request_headers[0][1] == 'Bearer shared-token'
    assert request_headers[1][0].endswith('/repos/Vaquum/Agent1/pulls/4/reviews')
    assert request_headers[1][1] == 'Bearer shared-token'


def test_github_client_fails_closed_when_policy_resolution_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _create_settings(github_token='shared-token')

    def _raise_control_error() -> object:
        raise ControlValidationError('policy load failed')

    monkeypatch.setattr(github_client_module, 'validate_control_bundle', _raise_control_error)

    with pytest.raises(GitHubPolicyError):
        UrlLibGitHubApiClient(settings=settings)
