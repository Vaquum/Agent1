from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from typing import TypeVar

from pydantic import BaseModel
from pydantic import ValidationError

from agent1.core.control_schemas import CommentingControl
from agent1.core.control_schemas import ControlBundle
from agent1.core.control_schemas import JobsControl
from agent1.core.control_schemas import PoliciesControl
from agent1.core.control_schemas import PromptsControl
from agent1.core.control_schemas import RuntimeControl
from agent1.core.control_schemas import StylesControl

CONTROL_FILE_NAME = 'default.json'
POLICY_PERMISSION_MATRIX_FILE_NAME = 'permission-matrix.json'
POLICY_PROTECTED_APPROVAL_FILE_NAME = 'protected-approval.json'
PROTECTED_MUTATION_CONTROL_RELATIVE_PATHS: tuple[str, ...] = (
    'policies/default.json',
    'policies/permission-matrix.json',
    'runtime/default.json',
)
ModelType = TypeVar('ModelType', bound=BaseModel)


class ControlValidationError(ValueError):
    pass


def get_project_root() -> Path:

    '''
    Create absolute project root path from backend module location.

    Returns:
    Path: Absolute root path for Agent1 repository.
    '''

    return Path(__file__).resolve().parents[5]


def get_controls_root() -> Path:

    '''
    Create controls root path for control bundle loading.

    Returns:
    Path: Absolute controls directory path.
    '''

    return get_project_root() / 'controls'


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        message = f'Control file not found: {path}'
        raise ControlValidationError(message)

    try:
        with path.open('r', encoding='utf-8') as file_handle:
            payload = json.load(file_handle)
    except json.JSONDecodeError as error:
        message = f'Invalid JSON in control file: {path}'
        raise ControlValidationError(message) from error

    if not isinstance(payload, dict):
        message = f'Control payload must be a JSON object: {path}'
        raise ControlValidationError(message)

    return payload


def _parse_model(path: Path, model_type: type[ModelType]) -> ModelType:
    payload = _read_json_file(path)

    try:
        return model_type.model_validate(payload)
    except ValidationError as error:
        message = f'Control validation failed for {path}: {error}'
        raise ControlValidationError(message) from error


def _parse_model_payload(
    payload: dict[str, Any],
    model_type: type[ModelType],
    source_path: Path,
) -> ModelType:
    try:
        return model_type.model_validate(payload)
    except ValidationError as error:
        message = f'Control validation failed for {source_path}: {error}'
        raise ControlValidationError(message) from error


def _compute_sha256_hex(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_protected_mutation_approval(controls_root: Path, policies: PoliciesControl) -> None:

    '''
    Create fail-closed validation for protected policy and guardrail mutations.

    Args:
    controls_root (Path): Root controls path used for control loading.
    policies (PoliciesControl): Parsed policy controls payload.

    Raises:
    ControlValidationError: Raised when active protected mutation snapshot is invalid.
    '''

    expected_paths = set(PROTECTED_MUTATION_CONTROL_RELATIVE_PATHS)
    active_protected_files = {
        protected_file.path: protected_file.sha256
        for protected_file in policies.protected_mutation_approval.active_snapshot.protected_files
    }
    active_paths = set(active_protected_files.keys())
    if active_paths != expected_paths:
        missing_paths = sorted(expected_paths - active_paths)
        extra_paths = sorted(active_paths - expected_paths)
        finding_segments: list[str] = []
        if len(missing_paths) != 0:
            finding_segments.append(f'missing={", ".join(missing_paths)}')
        if len(extra_paths) != 0:
            finding_segments.append(f'extra={", ".join(extra_paths)}')
        message = (
            'Protected-mutation approval active snapshot does not match required '
            'policy and guardrail path set'
        )
        if len(finding_segments) != 0:
            message = f'{message}: {"; ".join(finding_segments)}'
        raise ControlValidationError(message)

    for relative_path in sorted(expected_paths):
        absolute_path = controls_root / relative_path
        if not absolute_path.exists():
            message = (
                'Protected-mutation approval references missing control file: '
                f'{absolute_path}'
            )
            raise ControlValidationError(message)

        expected_sha256 = active_protected_files[relative_path]
        current_sha256 = _compute_sha256_hex(absolute_path)
        if current_sha256 != expected_sha256:
            message = (
                'Protected-mutation approval hash mismatch for control file '
                f'{relative_path}: expected {expected_sha256}, got {current_sha256}'
            )
            raise ControlValidationError(message)


def load_control_bundle(controls_root: Path | None = None) -> ControlBundle:

    '''
    Create validated control bundle from controls directory files.

    Args:
    controls_root (Path | None): Optional controls root override.

    Returns:
    ControlBundle: Fully validated control bundle.
    '''

    root_path = controls_root or get_controls_root()

    prompts = _parse_model(root_path / 'prompts' / CONTROL_FILE_NAME, PromptsControl)
    policies_path = root_path / 'policies' / CONTROL_FILE_NAME
    policy_permission_matrix_path = root_path / 'policies' / POLICY_PERMISSION_MATRIX_FILE_NAME
    policy_protected_approval_path = root_path / 'policies' / POLICY_PROTECTED_APPROVAL_FILE_NAME
    policies_payload = _read_json_file(policies_path)
    policies_payload['permission_matrix'] = _read_json_file(policy_permission_matrix_path)
    policies_payload['protected_mutation_approval'] = _read_json_file(
        policy_protected_approval_path
    )
    policies = _parse_model_payload(
        payload=policies_payload,
        model_type=PoliciesControl,
        source_path=policies_path,
    )
    _validate_protected_mutation_approval(controls_root=root_path, policies=policies)
    styles = _parse_model(root_path / 'styles' / CONTROL_FILE_NAME, StylesControl)
    commenting = _parse_model(
        root_path / 'commenting' / CONTROL_FILE_NAME,
        CommentingControl,
    )
    jobs = _parse_model(root_path / 'jobs' / CONTROL_FILE_NAME, JobsControl)
    runtime = _parse_model(root_path / 'runtime' / CONTROL_FILE_NAME, RuntimeControl)

    return ControlBundle(
        prompts=prompts,
        policies=policies,
        styles=styles,
        commenting=commenting,
        jobs=jobs,
        runtime=runtime,
    )


def validate_control_bundle(controls_root: Path | None = None) -> ControlBundle:

    '''
    Create and validate control bundle for fail-fast startup checks.

    Args:
    controls_root (Path | None): Optional controls root override.

    Returns:
    ControlBundle: Validated control bundle.
    '''

    return load_control_bundle(controls_root=controls_root)


__all__ = [
    'CONTROL_FILE_NAME',
    'POLICY_PERMISSION_MATRIX_FILE_NAME',
    'POLICY_PROTECTED_APPROVAL_FILE_NAME',
    'PROTECTED_MUTATION_CONTROL_RELATIVE_PATHS',
    'ControlValidationError',
    'get_controls_root',
    'get_project_root',
    'load_control_bundle',
    'validate_control_bundle',
]
