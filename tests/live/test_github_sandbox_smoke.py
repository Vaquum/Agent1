from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request
from urllib.request import urlopen

import pytest

GITHUB_API_URL = 'https://api.github.com'
DEFAULT_REPOSITORY = 'Vaquum/Agent1'


def _is_truthy(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {'1', 'true', 'yes', 'on'}


def _request_json(
    endpoint: str,
    token: str,
) -> Any:

    '''
    Create GitHub API JSON payload from authenticated endpoint request.

    Args:
    endpoint (str): GitHub API endpoint path.
    token (str): GitHub token for authenticated request.

    Returns:
    Any: Parsed JSON response payload.
    '''

    request = Request(
        url=f'{GITHUB_API_URL}{endpoint}',
        headers={
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
            'User-Agent': 'agent1-live-smoke',
        },
        method='GET',
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = response.read().decode('utf-8')
    except HTTPError as error:
        message = f'GitHub API request failed: {endpoint} status={error.code}'
        raise AssertionError(message) from error

    return json.loads(payload)


@pytest.fixture(scope='session')
def live_github_token() -> str:

    '''
    Create validated live smoke token or skip based on runtime requirement mode.

    Returns:
    str: Token value for live GitHub smoke requests.
    '''

    token = os.getenv('AGENT1_LIVE_GITHUB_TOKEN', '').strip()
    required = _is_truthy(os.getenv('AGENT1_LIVE_REQUIRED', 'false'))
    if token == '':
        if required:
            pytest.fail('AGENT1_LIVE_GITHUB_TOKEN is required for live smoke execution.')
        pytest.skip('AGENT1_LIVE_GITHUB_TOKEN is not set.')

    return token


@pytest.fixture(scope='session')
def live_repository() -> str:

    '''
    Create live repository value for sandbox smoke checks.

    Returns:
    str: Target repository full name.
    '''

    return os.getenv('AGENT1_LIVE_REPOSITORY', DEFAULT_REPOSITORY).strip()


def test_live_smoke_auth_identity_is_available(live_github_token: str) -> None:
    payload = _request_json('/user', token=live_github_token)
    assert isinstance(payload, dict)
    assert isinstance(payload.get('login', ''), str)
    assert str(payload.get('login', '')).strip() != ''


def test_live_smoke_sandbox_repository_metadata_is_available(
    live_github_token: str,
    live_repository: str,
) -> None:
    payload = _request_json(f'/repos/{live_repository}', token=live_github_token)
    assert isinstance(payload, dict)
    assert payload.get('full_name') == live_repository
    default_branch = payload.get('default_branch', '')
    assert isinstance(default_branch, str)
    assert default_branch.strip() != ''


def test_live_smoke_sandbox_pulls_endpoint_is_available(
    live_github_token: str,
    live_repository: str,
) -> None:
    payload = _request_json(f'/repos/{live_repository}/pulls?state=open&per_page=1', token=live_github_token)
    assert isinstance(payload, list)
