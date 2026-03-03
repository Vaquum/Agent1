from __future__ import annotations

from datetime import datetime
from datetime import timezone
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

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


def _create_release_promotion_audit_run_id() -> str:
    return f"aud_release_promotion_gate_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"


def _resolve_audit_environment() -> str:
    return os.getenv('AGENT1_AUDIT_ENVIRONMENT', 'ci').strip().lower()


def _append_release_promotion_audit_run(
    repo_root: Path,
    started_at: datetime,
    completed_at: datetime,
    operational_readiness_return_code: int,
    evidence: dict[str, bool],
    required_preconditions: list[str],
    failed_preconditions: list[str],
    passed: bool,
) -> None:

    '''
    Create persisted audit-run snapshot for one release-promotion gate execution.

    Args:
    repo_root (Path): Repository root path.
    started_at (datetime): Gate evaluation start timestamp.
    completed_at (datetime): Gate evaluation completion timestamp.
    operational_readiness_return_code (int): Operational-readiness subprocess return code.
    evidence (dict[str, bool]): Release-promotion evidence payload.
    required_preconditions (list[str]): Required precondition identifiers from policy.
    failed_preconditions (list[str]): Failed precondition identifiers from evaluation.
    passed (bool): Gate pass/fail decision value.
    '''

    _configure_backend_import_path(repo_root)
    from agent1.core.contracts import AuditRunRecord
    from agent1.core.contracts import AuditRunStatus
    from agent1.core.contracts import EnvironmentName
    from agent1.core.services.persistence_service import PersistenceService

    status = AuditRunStatus.SUCCEEDED if passed else AuditRunStatus.FAILED
    audit_environment = EnvironmentName(_resolve_audit_environment())
    persistence_service = PersistenceService()
    persistence_service.append_audit_run(
        AuditRunRecord(
            audit_run_id=_create_release_promotion_audit_run_id(),
            environment=audit_environment,
            audit_type='release_promotion_gate',
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            snapshot={
                'decision_passed': passed,
                'operational_readiness_return_code': operational_readiness_return_code,
                'required_preconditions': required_preconditions,
                'failed_preconditions': failed_preconditions,
                'evidence': evidence,
            },
        )
    )


def main() -> int:

    '''
    Compute process exit code for release-promotion gate evaluation.

    Returns:
    int: Zero when release-promotion preconditions pass, otherwise one.
    '''

    started_at = datetime.now(timezone.utc)
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
    completed_at = datetime.now(timezone.utc)
    _append_release_promotion_audit_run(
        repo_root=repo_root,
        started_at=started_at,
        completed_at=completed_at,
        operational_readiness_return_code=operational_readiness_result.returncode,
        evidence=evidence,
        required_preconditions=decision.required_preconditions,
        failed_preconditions=decision.failed_preconditions,
        passed=decision.passed,
    )
    if decision.passed:
        print('Release promotion gate passed.')
        return 0

    print('Release promotion gate failed:')
    for precondition_id in decision.failed_preconditions:
        print(f'- failed precondition: {precondition_id}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
