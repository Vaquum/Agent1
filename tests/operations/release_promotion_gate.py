from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

TRUE_VALUES: tuple[str, ...] = ('1', 'true', 'yes', 'on')
FALSE_VALUES: tuple[str, ...] = ('0', 'false', 'no', 'off')


def _get_repo_root() -> Path:

    '''
    Create repository root path from release-promotion gate script location.

    Returns:
    Path: Repository root path.
    '''

    return Path(__file__).resolve().parents[2]


def _configure_backend_import_path(repo_root: Path) -> None:

    '''
    Create backend source import path configuration for release gate runtime imports.

    Args:
    repo_root (Path): Repository root path.
    '''

    backend_src_path = repo_root / 'apps' / 'backend' / 'src'
    backend_src_path_value = str(backend_src_path)
    if backend_src_path_value not in sys.path:
        sys.path.insert(0, backend_src_path_value)


def _read_boolean_env(name: str, default_value: bool) -> bool:

    '''
    Create boolean environment value from normalized truthy and falsy string values.

    Args:
    name (str): Environment variable name.
    default_value (bool): Default value when variable is unset.

    Returns:
    bool: Parsed boolean environment value.
    '''

    raw_value = os.getenv(name)
    if raw_value is None:
        return default_value

    normalized_value = raw_value.strip().lower()
    if normalized_value in TRUE_VALUES:
        return True
    if normalized_value in FALSE_VALUES:
        return False

    message = f'Invalid boolean environment value for {name}: {raw_value}'
    raise ValueError(message)


def _build_release_promotion_evidence(
    operational_readiness_passed: bool,
) -> dict[str, bool]:

    '''
    Create release-promotion evidence payload for configured policy precondition evaluation.

    Args:
    operational_readiness_passed (bool): Operational-readiness gate result.

    Returns:
    dict[str, bool]: Boolean evidence map by precondition identifier.
    '''

    return {
        'operational_readiness_gate_passed': operational_readiness_passed,
        'runbook_set_current': operational_readiness_passed,
        'alert_routing_matrix_valid': operational_readiness_passed,
        'service_level_policy_current': operational_readiness_passed,
        'stop_the_line_clear': _read_boolean_env('STOP_THE_LINE_CLEAR', True),
        'rollout_stage_gate_passed': _read_boolean_env('ROLLOUT_STAGE_GATE_PASSED', True),
    }


def main() -> int:

    '''
    Compute process exit code for release-promotion gate evaluation.

    Returns:
    int: Zero when release-promotion preconditions pass, otherwise one.
    '''

    repo_root = _get_repo_root()
    _configure_backend_import_path(repo_root)
    from agent1.core.control_loader import validate_control_bundle
    from agent1.core.services.release_promotion_gate_service import ReleasePromotionGateService

    operational_readiness_result = subprocess.run(
        [sys.executable, str(repo_root / 'tests' / 'operations' / 'run.py')],
        cwd=repo_root,
        check=False,
    )
    operational_readiness_passed = operational_readiness_result.returncode == 0
    evidence = _build_release_promotion_evidence(
        operational_readiness_passed=operational_readiness_passed,
    )
    control_bundle = validate_control_bundle()
    gate_service = ReleasePromotionGateService(
        release_promotion_policy=control_bundle.runtime.release_promotion_policy,
    )
    decision = gate_service.evaluate(evidence=evidence)
    if decision.passed:
        print('Release promotion gate passed.')
        return 0

    print('Release promotion gate failed:')
    for precondition_id in decision.failed_preconditions:
        print(f'- failed precondition: {precondition_id}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
