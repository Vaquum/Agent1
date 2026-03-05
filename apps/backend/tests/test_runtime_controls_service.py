from __future__ import annotations

from pathlib import Path

import pytest

from agent1.core.services.runtime_controls_service import RuntimeControlsService


def test_runtime_controls_service_uses_defaults_when_state_file_missing(tmp_path: Path) -> None:
    service = RuntimeControlsService(
        default_active_repositories=['Vaquum/Agent1'],
        state_path=tmp_path / 'runtime-controls-state.json',
    )

    assert service.get_active_repositories() == ['Vaquum/Agent1']


def test_runtime_controls_service_persists_normalized_repositories(tmp_path: Path) -> None:
    state_path = tmp_path / 'runtime-controls-state.json'
    service = RuntimeControlsService(
        default_active_repositories=['Vaquum/Agent1'],
        state_path=state_path,
    )

    updated_active_repositories = service.replace_active_repositories(
        ['Vaquum/Agent1', ' Vaquum/Confab ', 'Vaquum/Agent1'],
    )

    assert updated_active_repositories == ['Vaquum/Agent1', 'Vaquum/Confab']
    reloaded_service = RuntimeControlsService(
        default_active_repositories=['Vaquum/Agent1'],
        state_path=state_path,
    )
    assert reloaded_service.get_active_repositories() == ['Vaquum/Agent1', 'Vaquum/Confab']


def test_runtime_controls_service_rejects_invalid_repository_values(tmp_path: Path) -> None:
    service = RuntimeControlsService(
        default_active_repositories=['Vaquum/Agent1'],
        state_path=tmp_path / 'runtime-controls-state.json',
    )

    with pytest.raises(ValueError, match='Repository scope values must use <owner>/<repo> format'):
        service.replace_active_repositories(['invalid-repository-name'])
