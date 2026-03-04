from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

ACTIVE_REPOSITORIES_KEY = 'active_repositories'


def _normalize_active_repositories(active_repositories: list[str]) -> list[str]:

    '''
    Create normalized runtime active-repository scope list.

    Args:
    active_repositories (list[str]): Raw active repository scope list.

    Returns:
    list[str]: Normalized active repository scope list.

    Raises:
    ValueError: Raised when repository scope values are invalid or empty.
    '''

    normalized_active_repositories: list[str] = []
    seen_repositories: set[str] = set()
    for repository in active_repositories:
        normalized_repository = repository.strip()
        if normalized_repository == '':
            continue
        repository_segments = normalized_repository.split('/')
        if len(repository_segments) != 2 or any(
            segment.strip() == '' for segment in repository_segments
        ):
            message = (
                'Repository scope values must use <owner>/<repo> format. '
                f'Invalid value: {repository}'
            )
            raise ValueError(message)
        if normalized_repository in seen_repositories:
            continue
        seen_repositories.add(normalized_repository)
        normalized_active_repositories.append(normalized_repository)
    if len(normalized_active_repositories) == 0:
        raise ValueError(
            'Active repository allow list must include at least one repository.',
        )

    return normalized_active_repositories


class RuntimeControlsService:
    def __init__(
        self,
        default_active_repositories: list[str],
        state_path: Path,
    ) -> None:
        self._state_path = state_path
        self._lock = Lock()
        self._default_active_repositories = _normalize_active_repositories(
            default_active_repositories,
        )
        self._active_repositories = self._load_active_repositories_state()

    def _load_active_repositories_state(self) -> list[str]:
        if not self._state_path.exists():
            return list(self._default_active_repositories)

        try:
            with self._state_path.open('r', encoding='utf-8') as file_handle:
                payload: Any = json.load(file_handle)
        except (OSError, json.JSONDecodeError):
            return list(self._default_active_repositories)

        if not isinstance(payload, dict):
            return list(self._default_active_repositories)
        active_repositories_payload = payload.get(ACTIVE_REPOSITORIES_KEY)
        if not isinstance(active_repositories_payload, list):
            return list(self._default_active_repositories)
        if any(not isinstance(repository, str) for repository in active_repositories_payload):
            return list(self._default_active_repositories)

        try:
            return _normalize_active_repositories(active_repositories_payload)
        except ValueError:
            return list(self._default_active_repositories)

    def _write_active_repositories_state(self, active_repositories: list[str]) -> None:
        payload = {
            ACTIVE_REPOSITORIES_KEY: active_repositories,
        }
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        with self._state_path.open('w', encoding='utf-8') as file_handle:
            json.dump(payload, file_handle, indent=2, sort_keys=True)
            file_handle.write('\n')

    def get_active_repositories(self) -> list[str]:

        '''
        Create current runtime active-repository scope list for API responses.

        Returns:
        list[str]: Active repository allow-list values.
        '''

        with self._lock:
            return list(self._active_repositories)

    def replace_active_repositories(self, active_repositories: list[str]) -> list[str]:

        '''
        Create persisted runtime active-repository scope update.

        Args:
        active_repositories (list[str]): New active repository allow-list values.

        Returns:
        list[str]: Persisted active repository allow-list values.
        '''

        normalized_active_repositories = _normalize_active_repositories(active_repositories)
        with self._lock:
            self._write_active_repositories_state(normalized_active_repositories)
            self._active_repositories = normalized_active_repositories
            return list(self._active_repositories)


__all__ = ['RuntimeControlsService']
