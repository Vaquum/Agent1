from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    node_id: str


def _get_repo_root() -> Path:

    '''
    Create repository root path from scenario runner module location.

    Returns:
    Path: Absolute Agent1 repository root path.
    '''

    return Path(__file__).resolve().parents[2]


def _load_catalog() -> list[Scenario]:

    '''
    Create scenario list from deterministic catalog payload.

    Returns:
    list[Scenario]: Parsed scenario definitions.
    '''

    catalog_path = Path(__file__).resolve().with_name('catalog.json')
    with catalog_path.open('r', encoding='utf-8') as file_handle:
        payload = json.load(file_handle)

    raw_scenarios = payload.get('scenarios', [])
    return [
        Scenario(
            scenario_id=str(raw_scenario['id']),
            node_id=str(raw_scenario['node_id']),
        )
        for raw_scenario in raw_scenarios
    ]


def _select_scenarios(scenarios: list[Scenario]) -> list[Scenario]:

    '''
    Create selected scenario list using optional environment filter.

    Args:
    scenarios (list[Scenario]): Full scenario catalog.

    Returns:
    list[Scenario]: Filtered scenarios for execution.
    '''

    requested_scenario_ids = os.getenv('AGENT1_SCENARIO_IDS', '').strip()
    if requested_scenario_ids == '':
        return scenarios

    requested_id_set = {
        scenario_id.strip()
        for scenario_id in requested_scenario_ids.split(',')
        if scenario_id.strip() != ''
    }
    return [scenario for scenario in scenarios if scenario.scenario_id in requested_id_set]


def _validate_scenarios(scenarios: list[Scenario]) -> None:

    '''
    Create validation pass for scenario identifier and node uniqueness.

    Args:
    scenarios (list[Scenario]): Scenario selection for execution.
    '''

    scenario_ids = [scenario.scenario_id for scenario in scenarios]
    node_ids = [scenario.node_id for scenario in scenarios]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ValueError('Scenario catalog contains duplicate scenario IDs.')
    if len(node_ids) != len(set(node_ids)):
        raise ValueError('Scenario catalog contains duplicate pytest node IDs.')


def _run_pytest_for_scenarios(scenarios: list[Scenario]) -> int:

    '''
    Compute pytest execution return code for selected scenario node IDs.

    Args:
    scenarios (list[Scenario]): Scenario selection for execution.

    Returns:
    int: Pytest process return code.
    '''

    if len(scenarios) == 0:
        raise ValueError('No scenarios selected for execution.')

    node_ids = [scenario.node_id for scenario in scenarios]
    backend_root = _get_repo_root() / 'apps/backend'
    command = [sys.executable, '-m', 'pytest', '-q', *node_ids]
    completed = subprocess.run(
        command,
        cwd=backend_root,
        check=False,
    )
    return completed.returncode


def main() -> int:

    '''
    Compute scenario harness process exit code from selected scenario execution.

    Returns:
    int: Runner process exit code.
    '''

    scenarios = _load_catalog()
    selected_scenarios = _select_scenarios(scenarios)
    _validate_scenarios(selected_scenarios)
    return _run_pytest_for_scenarios(selected_scenarios)


if __name__ == '__main__':
    raise SystemExit(main())
