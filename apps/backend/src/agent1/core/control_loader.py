from __future__ import annotations

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
    policies = _parse_model(root_path / 'policies' / CONTROL_FILE_NAME, PoliciesControl)
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
    'ControlValidationError',
    'get_controls_root',
    'get_project_root',
    'load_control_bundle',
    'validate_control_bundle',
]
