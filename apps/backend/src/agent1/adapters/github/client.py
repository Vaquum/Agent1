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
from agent1.core.contracts import EnvironmentName
from agent1.core.control_loader import ControlValidationError
from agent1.core.control_loader import validate_control_bundle
from agent1.core.control_schemas import PoliciesControl

READ_NOTIFICATIONS_CAPABILITY = 'read_notifications'
READ_PR_TIMELINE_CAPABILITY = 'read_pr_timeline'
READ_PR_CHECK_RUNS_CAPABILITY = 'read_pr_check_runs'
READ_ISSUE_CAPABILITY = 'read_issue'
READ_PULL_REQUEST_CAPABILITY = 'read_pull_request'
WRITE_ISSUE_COMMENT_CAPABILITY = 'write_issue_comment'
WRITE_PR_REVIEW_REPLY_CAPABILITY = 'write_pr_review_reply'


class GitHubPolicyError(PermissionError):
    pass


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

    def fetch_pull_request_review_comments(
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

    def fetch_pull_request_files(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict[str, object]]:
        ...

    def submit_pull_request_review(
        self,
        repository: str,
        pull_number: int,
        body: str,
        event: str = 'COMMENT',
        comments: list[dict[str, object]] | None = None,
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
    def __init__(
        self,
        settings: Settings | None = None,
        policies: PoliciesControl | None = None,
        environment: EnvironmentName = EnvironmentName.DEV,
    ) -> None:
        self._settings = settings or get_settings()
        self._environment = environment
        self._owner_cache: dict[str, str] = {}
        if policies is not None:
            self._policies = policies
        else:
            try:
                control_bundle = validate_control_bundle()
                self._policies = control_bundle.policies
            except ControlValidationError as error:
                message = 'Failed to resolve GitHub policy control.'
                raise GitHubPolicyError(message) from error

    def _resolve_token(self, for_mutation: bool) -> str:
        _ = for_mutation
        token = self._settings.github_token.strip()

        if token == '':
            message = 'Missing GITHUB_TOKEN for API client.'
            raise GitHubPolicyError(message)

        return token

    def _create_headers(self, for_mutation: bool) -> dict[str, str]:
        token = self._resolve_token(for_mutation)
        github_user = self._settings.github_user.strip()
        if github_user == '':
            message = 'Missing GITHUB_USER for API client.'
            raise GitHubPolicyError(message)

        return {
            'Accept': 'application/vnd.github+json',
            'Authorization': f"Bearer {token}",
            'X-GitHub-Api-Version': '2022-11-28',
            'User-Agent': github_user,
        }

    def _require_capability(self, capability: str) -> None:
        capabilities = self._policies.github_capabilities.model_dump()
        capability_allowed = capabilities.get(capability)
        if capability_allowed is True:
            return

        if self._policies.default_deny_github_capabilities:
            message = f'GitHub capability denied by default-deny policy: {capability}'
            raise GitHubPolicyError(message)

        message = f'GitHub capability not explicitly allowed: {capability}'
        raise GitHubPolicyError(message)

    def _expected_mutating_owner(self) -> str:
        expected_owner = self._settings.github_user.strip()
        if expected_owner == '':
            message = 'Missing GITHUB_USER for mutating credential owner preflight.'
            raise GitHubPolicyError(message)

        return expected_owner

    def _resolve_token_owner(self, token: str) -> str:
        cached_owner = self._owner_cache.get(token)
        if cached_owner is not None:
            return cached_owner

        headers = {
            'Accept': 'application/vnd.github+json',
            'Authorization': f"Bearer {token}",
            'X-GitHub-Api-Version': '2022-11-28',
            'User-Agent': self._settings.github_user.strip(),
        }
        request = Request(
            url=f'{self._settings.github_api_url}/user',
            headers=headers,
            method='GET',
        )
        with urlopen(request, timeout=self._settings.github_http_timeout_seconds) as response:
            body = response.read().decode('utf-8')

        payload = json.loads(body)
        if not isinstance(payload, dict):
            message = 'GitHub owner preflight response must be an object payload.'
            raise GitHubPolicyError(message)

        owner = self._get_string(payload, 'login').strip()
        if owner == '':
            message = 'GitHub owner preflight could not resolve token owner.'
            raise GitHubPolicyError(message)

        self._owner_cache[token] = owner
        return owner

    def _validate_mutating_credential_owner(self) -> None:
        if self._policies.fail_closed_policy_resolution is False:
            return

        expected_owner = self._expected_mutating_owner().strip()

        token = self._resolve_token(for_mutation=True)
        actual_owner = self._resolve_token_owner(token)
        if actual_owner != expected_owner:
            message = (
                'Mutating credential owner preflight mismatch: '
                f'expected={expected_owner} actual={actual_owner}'
            )
            raise GitHubPolicyError(message)

    def _request_json(
        self,
        url: str,
        method: str = 'GET',
        payload: dict[str, object] | None = None,
        for_mutation: bool = False,
    ) -> object:
        if for_mutation:
            self._validate_mutating_credential_owner()

        headers = self._create_headers(for_mutation=for_mutation)
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

        self._require_capability(READ_NOTIFICATIONS_CAPABILITY)

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

        self._require_capability(READ_PR_TIMELINE_CAPABILITY)

        url = (
            f"{self._settings.github_api_url}/repos/{repository}/issues/{pull_number}/timeline"
            '?per_page=100'
        )
        payload = self._request_json(url)
        if not isinstance(payload, list):
            message = 'GitHub timeline response must be a list payload.'
            raise ValueError(message)

        return [item for item in payload if isinstance(item, dict)]

    def fetch_pull_request_review_comments(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict[str, object]]:

        '''
        Create pull request review-comment payload list for thread-update ingestion.

        Args:
        repository (str): Repository full name in owner/repo format.
        pull_number (int): Pull request number.

        Returns:
        list[dict[str, object]]: Pull request review-comment payload list.
        '''

        self._require_capability(READ_PR_TIMELINE_CAPABILITY)
        url = (
            f"{self._settings.github_api_url}/repos/{repository}/pulls/{pull_number}/comments"
            '?per_page=100'
        )
        payload = self._request_json(url)
        if not isinstance(payload, list):
            message = 'GitHub pull review comments response must be a list payload.'
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

        self._require_capability(READ_PR_CHECK_RUNS_CAPABILITY)

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

        self._require_capability(READ_ISSUE_CAPABILITY)

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

        self._require_capability(READ_PULL_REQUEST_CAPABILITY)

        url = f"{self._settings.github_api_url}/repos/{repository}/pulls/{pull_number}"
        payload = self._request_json(url)
        if not isinstance(payload, dict):
            return {}

        return payload

    def fetch_pull_request_files(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict[str, object]]:

        '''
        Create pull request file payload list from GitHub pull request files endpoint.

        Args:
        repository (str): Repository full name in owner/repo format.
        pull_number (int): Pull request number.

        Returns:
        list[dict[str, object]]: Pull request file payload list.
        '''

        self._require_capability(READ_PULL_REQUEST_CAPABILITY)

        file_payloads: list[dict[str, object]] = []
        page = 1
        per_page = 100
        while page <= 10:
            query = urlencode({'per_page': str(per_page), 'page': str(page)})
            url = (
                f"{self._settings.github_api_url}/repos/{repository}/pulls/{pull_number}/files"
                f'?{query}'
            )
            payload = self._request_json(url)
            if not isinstance(payload, list):
                break

            page_items = [item for item in payload if isinstance(item, dict)]
            if len(page_items) == 0:
                break
            file_payloads.extend(page_items)
            if len(page_items) < per_page:
                break
            page += 1

        return file_payloads

    def submit_pull_request_review(
        self,
        repository: str,
        pull_number: int,
        body: str,
        event: str = 'COMMENT',
        comments: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:

        '''
        Create pull request review submission using GitHub reviews API endpoint.

        Args:
        repository (str): Repository full name in owner/repo format.
        pull_number (int): Pull request number.
        body (str): Markdown review body payload.
        event (str): Review event type (`COMMENT`, `APPROVE`, `REQUEST_CHANGES`).
        comments (list[dict[str, object]] | None): Optional inline review comments payload.

        Returns:
        dict[str, object]: Pull request review response payload.
        '''

        self._require_capability(WRITE_PR_REVIEW_REPLY_CAPABILITY)

        url = f"{self._settings.github_api_url}/repos/{repository}/pulls/{pull_number}/reviews"
        request_payload: dict[str, object] = {
            'body': body,
            'event': event,
        }
        if comments is not None:
            request_payload['comments'] = comments

        payload = self._request_json(
            url=url,
            method='POST',
            payload=request_payload,
            for_mutation=True,
        )
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

        self._require_capability(WRITE_ISSUE_COMMENT_CAPABILITY)

        url = f"{self._settings.github_api_url}/repos/{repository}/issues/{issue_number}/comments"
        payload = self._request_json(
            url=url,
            method='POST',
            payload={'body': body},
            for_mutation=True,
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

        self._require_capability(WRITE_PR_REVIEW_REPLY_CAPABILITY)

        url = (
            f"{self._settings.github_api_url}/repos/{repository}/pulls/"
            f"{pull_number}/comments/{review_comment_id}/replies"
        )
        payload = self._request_json(
            url=url,
            method='POST',
            payload={'body': body},
            for_mutation=True,
        )
        if not isinstance(payload, dict):
            return {}

        return payload


__all__ = ['GitHubApiClient', 'GitHubPolicyError', 'UrlLibGitHubApiClient']
