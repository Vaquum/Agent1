from __future__ import annotations

import json
from datetime import datetime
from collections.abc import Mapping
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen

from agent1.config.settings import Settings
from agent1.config.settings import get_settings


class GitHubApiClient(Protocol):
    def fetch_notifications(
        self,
        since: datetime | None = None,
        page: int = 1,
        per_page: int = 100,
    ) -> list[dict[str, object]]:
        ...

    def fetch_pull_request_timeline(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict[str, object]]:
        ...

    def fetch_pull_request_check_runs(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict[str, object]]:
        ...

    def fetch_issue(
        self,
        repository: str,
        issue_number: int,
    ) -> dict[str, object]:
        ...

    def fetch_pull_request(
        self,
        repository: str,
        pull_number: int,
    ) -> dict[str, object]:
        ...

    def post_issue_comment(
        self,
        repository: str,
        issue_number: int,
        body: str,
    ) -> dict[str, object]:
        ...

    def post_pull_review_comment_reply(
        self,
        repository: str,
        pull_number: int,
        review_comment_id: int,
        body: str,
    ) -> dict[str, object]:
        ...


class UrlLibGitHubApiClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def _create_headers(self) -> dict[str, str]:
        token = self._settings.github_token
        if token == '':
            message = 'Missing GitHub token for API client.'
            raise ValueError(message)

        return {
            'Accept': 'application/vnd.github+json',
            'Authorization': f"Bearer {token}",
            'X-GitHub-Api-Version': '2022-11-28',
            'User-Agent': self._settings.github_user,
        }

    def _request_json(
        self,
        url: str,
        method: str = 'GET',
        payload: dict[str, object] | None = None,
    ) -> object:
        headers = self._create_headers()
        request_payload = None
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            request_payload = json.dumps(payload).encode('utf-8')

        request = Request(url=url, headers=headers, method=method, data=request_payload)

        with urlopen(request, timeout=self._settings.github_http_timeout_seconds) as response:
            body = response.read().decode('utf-8')

        return json.loads(body)

    def _get_string(self, payload: Mapping[str, object], key: str) -> str:
        value = payload.get(key)
        if isinstance(value, str):
            return value

        return ''

    def _get_dict(self, payload: Mapping[str, object], key: str) -> dict[str, object]:
        value = payload.get(key)
        if isinstance(value, Mapping):
            return dict(value)

        return {}

    def fetch_notifications(
        self,
        since: datetime | None = None,
        page: int = 1,
        per_page: int = 100,
    ) -> list[dict[str, object]]:

        '''
        Create GitHub notifications payload list from notifications API endpoint.

        Returns:
        list[dict[str, object]]: Raw notification payload list.
        '''

        query_payload: dict[str, str] = {
            'all': 'true',
            'participating': 'false',
            'per_page': str(per_page),
            'page': str(page),
        }
        if since is not None:
            query_payload['since'] = since.isoformat().replace('+00:00', 'Z')

        query = urlencode(query_payload)
        url = f"{self._settings.github_api_url}/notifications?{query}"
        payload = self._request_json(url)
        if not isinstance(payload, list):
            message = 'GitHub notifications response must be a list payload.'
            raise ValueError(message)

        return [item for item in payload if isinstance(item, dict)]

    def fetch_pull_request_timeline(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict[str, object]]:

        '''
        Create pull request timeline payload list from GitHub timeline endpoint.

        Args:
        repository (str): Repository full name in owner/repo format.
        pull_number (int): Pull request number.

        Returns:
        list[dict[str, object]]: Pull request timeline payload list.
        '''

        url = (
            f"{self._settings.github_api_url}/repos/{repository}/issues/{pull_number}/timeline"
            '?per_page=100'
        )
        payload = self._request_json(url)
        if not isinstance(payload, list):
            message = 'GitHub timeline response must be a list payload.'
            raise ValueError(message)

        return [item for item in payload if isinstance(item, dict)]

    def fetch_pull_request_check_runs(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict[str, object]]:

        '''
        Create pull request check-run payload list for pull request head commit.

        Args:
        repository (str): Repository full name in owner/repo format.
        pull_number (int): Pull request number.

        Returns:
        list[dict[str, object]]: Check-run payload list.
        '''

        pull_payload = self.fetch_pull_request(repository=repository, pull_number=pull_number)
        if len(pull_payload) == 0:
            return []

        head = self._get_dict(pull_payload, 'head')
        sha = self._get_string(head, 'sha')
        if sha == '':
            return []

        checks_url = f"{self._settings.github_api_url}/repos/{repository}/commits/{sha}/check-runs"
        checks_payload = self._request_json(checks_url)
        if not isinstance(checks_payload, dict):
            return []

        check_runs = checks_payload.get('check_runs')
        if not isinstance(check_runs, list):
            return []

        return [item for item in check_runs if isinstance(item, dict)]

    def fetch_issue(
        self,
        repository: str,
        issue_number: int,
    ) -> dict[str, object]:

        '''
        Create issue payload map from GitHub issues API endpoint.

        Args:
        repository (str): Repository full name in owner/repo format.
        issue_number (int): Issue number.

        Returns:
        dict[str, object]: Issue payload map.
        '''

        url = f"{self._settings.github_api_url}/repos/{repository}/issues/{issue_number}"
        payload = self._request_json(url)
        if not isinstance(payload, dict):
            return {}

        return payload

    def fetch_pull_request(
        self,
        repository: str,
        pull_number: int,
    ) -> dict[str, object]:

        '''
        Create pull request payload map from GitHub pull request API endpoint.

        Args:
        repository (str): Repository full name in owner/repo format.
        pull_number (int): Pull request number.

        Returns:
        dict[str, object]: Pull request payload map.
        '''

        url = f"{self._settings.github_api_url}/repos/{repository}/pulls/{pull_number}"
        payload = self._request_json(url)
        if not isinstance(payload, dict):
            return {}

        return payload

    def post_issue_comment(
        self,
        repository: str,
        issue_number: int,
        body: str,
    ) -> dict[str, object]:

        '''
        Create issue or pull request top-level comment using GitHub issue comments endpoint.

        Args:
        repository (str): Repository full name in owner/repo format.
        issue_number (int): Issue or pull request number.
        body (str): Markdown comment body payload.

        Returns:
        dict[str, object]: Comment response payload.
        '''

        url = f"{self._settings.github_api_url}/repos/{repository}/issues/{issue_number}/comments"
        payload = self._request_json(
            url=url,
            method='POST',
            payload={'body': body},
        )
        if not isinstance(payload, dict):
            return {}

        return payload

    def post_pull_review_comment_reply(
        self,
        repository: str,
        pull_number: int,
        review_comment_id: int,
        body: str,
    ) -> dict[str, object]:

        '''
        Create pull request review-thread reply comment using review comments API endpoint.

        Args:
        repository (str): Repository full name in owner/repo format.
        pull_number (int): Pull request number.
        review_comment_id (int): Pull review comment identifier to reply to.
        body (str): Markdown reply body payload.

        Returns:
        dict[str, object]: Reply comment response payload.
        '''

        url = (
            f"{self._settings.github_api_url}/repos/{repository}/pulls/"
            f"{pull_number}/comments/{review_comment_id}/replies"
        )
        payload = self._request_json(
            url=url,
            method='POST',
            payload={'body': body},
        )
        if not isinstance(payload, dict):
            return {}

        return payload


__all__ = ['GitHubApiClient', 'UrlLibGitHubApiClient']
