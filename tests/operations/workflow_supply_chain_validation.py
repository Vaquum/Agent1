from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

CI_TOKEN_PERMISSIONS_POLICY_RELATIVE_PATH = 'docs/Developer/ci-token-permissions-policy.json'
PINNED_ACTION_REF_PATTERN = re.compile(r'^[a-f0-9]{40}$')
USES_LINE_PATTERN = re.compile(r'^\s*uses:\s*([^\s#]+)\s*$')
JOB_LINE_PATTERN = re.compile(r'^  ([A-Za-z0-9_-]+):\s*$')
TOP_LEVEL_KEY_PATTERN = re.compile(r'^[A-Za-z0-9_-]+:\s*$')
JOB_PERMISSIONS_LINE_PATTERN = re.compile(r'^    permissions:\s*$')
PERMISSION_ENTRY_LINE_PATTERN = re.compile(r'^      ([A-Za-z-]+):\s*([A-Za-z_]+)\s*$')


def _get_repo_root() -> Path:

    '''
    Create repository root path from workflow supply-chain validation script location.

    Returns:
    Path: Repository root path.
    '''

    return Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> object:

    '''
    Create JSON payload loaded from file path.

    Args:
    path (Path): JSON file path.

    Returns:
    object: Decoded JSON payload.
    '''

    with path.open('r', encoding='utf-8') as file_handle:
        return json.load(file_handle)


def _load_permissions_policy(repo_root: Path) -> dict[str, dict[str, dict[str, str]]]:

    '''
    Create workflow job-permissions policy map from machine-readable policy artifact.

    Args:
    repo_root (Path): Repository root path.

    Returns:
    dict[str, dict[str, dict[str, str]]]: Workflow to job-permissions policy map.
    '''

    policy_path = repo_root / CI_TOKEN_PERMISSIONS_POLICY_RELATIVE_PATH
    payload = _read_json(policy_path)
    if not isinstance(payload, dict):
        message = (
            'Workflow supply-chain policy payload must be an object: '
            f'{CI_TOKEN_PERMISSIONS_POLICY_RELATIVE_PATH}'
        )
        raise ValueError(message)

    workflow_job_permissions = payload.get('workflow_job_permissions')
    if not isinstance(workflow_job_permissions, dict):
        message = (
            'Workflow supply-chain policy missing workflow_job_permissions map: '
            f'{CI_TOKEN_PERMISSIONS_POLICY_RELATIVE_PATH}'
        )
        raise ValueError(message)

    normalized_map: dict[str, dict[str, dict[str, str]]] = {}
    for workflow_path, workflow_payload in workflow_job_permissions.items():
        if not isinstance(workflow_path, str) or workflow_path.strip() == '':
            message = 'Workflow supply-chain policy contains empty workflow path key.'
            raise ValueError(message)
        if not isinstance(workflow_payload, dict):
            message = f'Workflow permissions payload must be object: {workflow_path}'
            raise ValueError(message)

        normalized_workflow_payload: dict[str, dict[str, str]] = {}
        for job_name, permissions_payload in workflow_payload.items():
            if not isinstance(job_name, str) or job_name.strip() == '':
                message = f'Workflow permissions payload contains empty job name: {workflow_path}'
                raise ValueError(message)
            if not isinstance(permissions_payload, dict):
                message = (
                    'Workflow job permissions payload must be object: '
                    f'{workflow_path}::{job_name}'
                )
                raise ValueError(message)

            normalized_permissions: dict[str, str] = {}
            for permission_name, permission_value in permissions_payload.items():
                if not isinstance(permission_name, str) or permission_name.strip() == '':
                    message = (
                        'Workflow job permissions payload contains empty permission key: '
                        f'{workflow_path}::{job_name}'
                    )
                    raise ValueError(message)
                if not isinstance(permission_value, str) or permission_value.strip() == '':
                    message = (
                        'Workflow job permissions payload contains empty permission value: '
                        f'{workflow_path}::{job_name}::{permission_name}'
                    )
                    raise ValueError(message)

                normalized_permissions[permission_name.strip()] = permission_value.strip()

            normalized_workflow_payload[job_name.strip()] = normalized_permissions

        normalized_map[workflow_path.strip()] = normalized_workflow_payload

    return normalized_map


def _extract_unpinned_action_findings(lines: list[str], workflow_relative_path: str) -> list[str]:

    '''
    Create unpinned-action validation findings from workflow text lines.

    Args:
    lines (list[str]): Workflow file lines.
    workflow_relative_path (str): Relative workflow path for finding messages.

    Returns:
    list[str]: Human-readable unpinned-action findings.
    '''

    findings: list[str] = []
    for line_number, line in enumerate(lines, start=1):
        uses_match = USES_LINE_PATTERN.match(line)
        if uses_match is None:
            continue

        uses_value = uses_match.group(1)
        if uses_value.startswith('./') or uses_value.startswith('docker://'):
            continue

        if '@' not in uses_value:
            findings.append(
                'Workflow action reference is missing version/ref '
                f'({workflow_relative_path}:{line_number}): {uses_value}'
            )
            continue

        action_name, action_ref = uses_value.split('@', maxsplit=1)
        if '/' not in action_name:
            continue

        if PINNED_ACTION_REF_PATTERN.fullmatch(action_ref) is None:
            findings.append(
                'Workflow action reference must be pinned to immutable SHA '
                f'({workflow_relative_path}:{line_number}): {uses_value}'
            )

    return findings


def _extract_job_blocks(lines: list[str]) -> list[tuple[str, int, int]]:

    '''
    Create list of workflow job blocks with start and end line indexes.

    Args:
    lines (list[str]): Workflow file lines.

    Returns:
    list[tuple[str, int, int]]: Sequence of `(job_name, start_index, end_index)` tuples.
    '''

    in_jobs_section = False
    job_start_entries: list[tuple[str, int]] = []
    for line_index, line in enumerate(lines):
        if line == 'jobs:':
            in_jobs_section = True
            continue

        if not in_jobs_section:
            continue

        if TOP_LEVEL_KEY_PATTERN.match(line) is not None:
            break

        job_match = JOB_LINE_PATTERN.match(line)
        if job_match is None:
            continue

        job_start_entries.append((job_match.group(1), line_index))

    job_blocks: list[tuple[str, int, int]] = []
    for entry_index, (job_name, start_index) in enumerate(job_start_entries):
        if entry_index == len(job_start_entries) - 1:
            end_index = len(lines)
        else:
            end_index = job_start_entries[entry_index + 1][1]

        job_blocks.append((job_name, start_index, end_index))

    return job_blocks


def _extract_job_permissions_from_block(
    block_lines: list[str],
) -> tuple[dict[str, str] | None, list[str]]:

    '''
    Create job permission payload extracted from one workflow job block.

    Args:
    block_lines (list[str]): Workflow lines scoped to one job block.

    Returns:
    tuple[dict[str, str] | None, list[str]]: Parsed permission map and finding messages.
    '''

    findings: list[str] = []
    for line_index, line in enumerate(block_lines):
        if JOB_PERMISSIONS_LINE_PATTERN.match(line) is None:
            continue

        permission_map: dict[str, str] = {}
        cursor = line_index + 1
        while cursor < len(block_lines):
            permission_line = block_lines[cursor]
            permission_match = PERMISSION_ENTRY_LINE_PATTERN.match(permission_line)
            if permission_match is not None:
                permission_map[permission_match.group(1)] = permission_match.group(2)
                cursor += 1
                continue

            if permission_line.strip() == '' or permission_line.strip().startswith('#'):
                cursor += 1
                continue

            break

        if len(permission_map) == 0:
            findings.append('Job permissions block is present but empty.')

        return permission_map, findings

    findings.append('Job permissions block is missing.')
    return None, findings


def _extract_job_permissions_findings(
    lines: list[str],
    workflow_relative_path: str,
    expected_job_permissions: dict[str, dict[str, str]],
) -> list[str]:

    '''
    Create job-permission drift findings for one workflow file.

    Args:
    lines (list[str]): Workflow file lines.
    workflow_relative_path (str): Relative workflow path.
    expected_job_permissions (dict[str, dict[str, str]]): Expected job-permission map.

    Returns:
    list[str]: Human-readable job-permission findings.
    '''

    findings: list[str] = []
    parsed_job_permissions: dict[str, dict[str, str]] = {}
    for job_name, start_index, end_index in _extract_job_blocks(lines):
        block_lines = lines[start_index:end_index]
        permission_map, parse_findings = _extract_job_permissions_from_block(block_lines)
        if len(parse_findings) != 0:
            for parse_finding in parse_findings:
                findings.append(f'{workflow_relative_path}::{job_name}: {parse_finding}')
            continue

        if permission_map is None:
            findings.append(
                f'{workflow_relative_path}::{job_name}: Job permissions block parsing returned no payload.'
            )
            continue

        parsed_job_permissions[job_name] = permission_map

    expected_job_names = set(expected_job_permissions.keys())
    parsed_job_names = set(parsed_job_permissions.keys())
    missing_jobs = sorted(expected_job_names - parsed_job_names)
    extra_jobs = sorted(parsed_job_names - expected_job_names)
    for missing_job in missing_jobs:
        findings.append(
            'Workflow permissions policy contains job that is missing in parsed workflow permissions: '
            f'{workflow_relative_path}::{missing_job}'
        )
    for extra_job in extra_jobs:
        findings.append(
            'Parsed workflow permissions contain job missing from policy: '
            f'{workflow_relative_path}::{extra_job}'
        )

    for job_name in sorted(expected_job_names & parsed_job_names):
        expected_permissions = expected_job_permissions[job_name]
        parsed_permissions = parsed_job_permissions[job_name]
        if parsed_permissions != expected_permissions:
            findings.append(
                'Workflow job permissions drift detected '
                f'{workflow_relative_path}::{job_name}: '
                f'expected {expected_permissions}, got {parsed_permissions}'
            )

    return findings


def _validate_workflow_supply_chain_controls(repo_root: Path) -> list[str]:

    '''
    Create workflow supply-chain validation findings for action pinning and token permissions.

    Args:
    repo_root (Path): Repository root path.

    Returns:
    list[str]: Human-readable validation finding messages.
    '''

    findings: list[str] = []
    expected_permissions_by_workflow = _load_permissions_policy(repo_root)
    for workflow_relative_path, expected_job_permissions in expected_permissions_by_workflow.items():
        workflow_path = repo_root / workflow_relative_path
        if not workflow_path.exists():
            findings.append(f'Missing workflow file declared in permissions policy: {workflow_relative_path}.')
            continue

        workflow_lines = workflow_path.read_text(encoding='utf-8').splitlines()
        findings.extend(
            _extract_unpinned_action_findings(workflow_lines, workflow_relative_path)
        )
        findings.extend(
            _extract_job_permissions_findings(
                lines=workflow_lines,
                workflow_relative_path=workflow_relative_path,
                expected_job_permissions=expected_job_permissions,
            )
        )

    return findings


def main() -> int:

    '''
    Compute process exit code for workflow supply-chain validation.

    Returns:
    int: Zero when validation passes, otherwise one.
    '''

    repo_root = _get_repo_root()
    try:
        findings = _validate_workflow_supply_chain_controls(repo_root)
    except ValueError as error:
        print('Workflow supply-chain validation failed:')
        print(f'- {error}')
        return 1

    if len(findings) != 0:
        print('Workflow supply-chain validation failed:')
        for finding in findings:
            print(f'- {finding}')
        return 1

    print('Workflow supply-chain validation passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
