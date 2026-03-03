from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def _get_repo_root() -> Path:

    '''
    Create repository root path from PR smoke runner module location.

    Returns:
    Path: Absolute Agent1 repository root path.
    '''

    return Path(__file__).resolve().parents[2]


def _load_catalog_payload(catalog_path: Path) -> dict[str, object]:

    '''
    Create decoded JSON payload from one catalog path.

    Args:
    catalog_path (Path): Catalog file path.

    Returns:
    dict[str, object]: Decoded catalog payload.
    '''

    with catalog_path.open('r', encoding='utf-8') as file_handle:
        payload = json.load(file_handle)

    if not isinstance(payload, dict):
        message = f'Invalid catalog payload at {catalog_path}.'
        raise ValueError(message)

    return payload


def _load_backend_smoke_node_ids() -> list[str]:

    '''
    Create ordered backend pytest node list for PR smoke scenarios.

    Returns:
    list[str]: Backend pytest node identifiers for PR smoke execution.
    '''

    repo_root = _get_repo_root()
    catalog_payload = _load_catalog_payload(repo_root / 'tests' / 'scenarios' / 'catalog.json')
    pr_smoke_payload = _load_catalog_payload(repo_root / 'tests' / 'scenarios' / 'pr-smoke-catalog.json')

    catalog_entries = catalog_payload.get('scenarios')
    if not isinstance(catalog_entries, list):
        raise ValueError('Scenario catalog does not contain scenarios list.')

    scenario_node_id_by_id: dict[str, str] = {}
    for entry in catalog_entries:
        if not isinstance(entry, dict):
            continue
        scenario_id = entry.get('id')
        node_id = entry.get('node_id')
        if isinstance(scenario_id, str) and isinstance(node_id, str):
            scenario_node_id_by_id[scenario_id] = node_id

    backend_scenario_ids = pr_smoke_payload.get('backend_scenario_ids')
    if not isinstance(backend_scenario_ids, list):
        raise ValueError('PR smoke catalog does not contain backend_scenario_ids list.')

    missing_scenario_ids: list[str] = []
    node_ids: list[str] = []
    for scenario_id in backend_scenario_ids:
        if not isinstance(scenario_id, str):
            continue
        node_id = scenario_node_id_by_id.get(scenario_id)
        if node_id is None:
            missing_scenario_ids.append(scenario_id)
            continue
        node_ids.append(node_id)

    if len(missing_scenario_ids) != 0:
        message = (
            'PR smoke catalog references missing backend scenario IDs: '
            + ', '.join(missing_scenario_ids)
        )
        raise ValueError(message)

    if len(node_ids) == 0:
        raise ValueError('No backend PR smoke scenarios resolved for execution.')

    return node_ids


def _get_junit_report_path() -> Path:

    '''
    Create backend PR smoke junit report output path from optional environment override.

    Returns:
    Path: Absolute junit report output path.
    '''

    repo_root = _get_repo_root()
    report_path_env = os.getenv('AGENT1_PR_SMOKE_JUNIT_PATH', '').strip()
    if report_path_env == '':
        return repo_root / 'tests' / 'scenarios' / 'artifacts' / 'pr-smoke-backend-junit.xml'

    return Path(report_path_env)


def _run_backend_pr_smoke(node_ids: list[str], junit_report_path: Path) -> int:

    '''
    Compute backend PR smoke pytest return code for provided node list and junit path.

    Args:
    node_ids (list[str]): Backend pytest node identifiers.
    junit_report_path (Path): Junit report output path.

    Returns:
    int: Pytest process return code.
    '''

    junit_report_path.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-m', 'pytest', '-q', f'--junitxml={junit_report_path}', *node_ids]
    completed = subprocess.run(
        command,
        cwd=_get_repo_root() / 'apps' / 'backend',
        check=False,
    )
    return completed.returncode


def main() -> int:

    '''
    Compute process exit code for backend PR smoke scenario execution.

    Returns:
    int: Runner process exit code.
    '''

    node_ids = _load_backend_smoke_node_ids()
    junit_report_path = _get_junit_report_path()
    return _run_backend_pr_smoke(
        node_ids=node_ids,
        junit_report_path=junit_report_path,
    )


if __name__ == '__main__':
    raise SystemExit(main())
