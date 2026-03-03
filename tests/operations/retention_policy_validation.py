from __future__ import annotations

from pathlib import Path
import sys

REQUIRED_ARTIFACT_TYPES: tuple[str, ...] = (
    'logs',
    'traces',
    'test_artifacts',
)
REQUIRED_ENVIRONMENTS: tuple[str, ...] = (
    'dev',
    'prod',
    'ci',
)


def _get_repo_root() -> Path:

    '''
    Create repository root path from retention-policy validation script location.

    Returns:
    Path: Repository root path.
    '''

    return Path(__file__).resolve().parents[2]


def _configure_backend_import_path(repo_root: Path) -> None:

    '''
    Create backend source import path configuration for control validation imports.

    Args:
    repo_root (Path): Repository root path.
    '''

    backend_src_path = repo_root / 'apps' / 'backend' / 'src'
    backend_src_path_value = str(backend_src_path)
    if backend_src_path_value not in sys.path:
        sys.path.insert(0, backend_src_path_value)


def main() -> int:

    '''
    Compute process exit code for retention-policy drift validation.

    Returns:
    int: Zero when validation passes, otherwise one.
    '''

    repo_root = _get_repo_root()
    _configure_backend_import_path(repo_root)
    from agent1.core.control_loader import validate_control_bundle

    control_bundle = validate_control_bundle()
    retention_entries = control_bundle.runtime.retention_policy.entries
    retention_days_by_scope = {
        (entry.artifact_type, entry.environment.value): entry.retention_days
        for entry in retention_entries
    }

    findings: list[str] = []
    required_scope_pairs = {
        (artifact_type, environment)
        for artifact_type in REQUIRED_ARTIFACT_TYPES
        for environment in REQUIRED_ENVIRONMENTS
    }
    present_scope_pairs = set(retention_days_by_scope.keys())
    missing_scope_pairs = sorted(required_scope_pairs - present_scope_pairs)
    if len(missing_scope_pairs) != 0:
        findings.append(
            'missing scope entries: '
            + ', '.join(f'{artifact}:{environment}' for artifact, environment in missing_scope_pairs)
        )

    for artifact_type in REQUIRED_ARTIFACT_TYPES:
        prod_retention = retention_days_by_scope.get((artifact_type, 'prod'))
        dev_retention = retention_days_by_scope.get((artifact_type, 'dev'))
        ci_retention = retention_days_by_scope.get((artifact_type, 'ci'))
        if prod_retention is None or dev_retention is None or ci_retention is None:
            continue

        if prod_retention < dev_retention:
            findings.append(
                f'prod retention below dev for {artifact_type}: '
                f'prod={prod_retention}, dev={dev_retention}'
            )
        if prod_retention < ci_retention:
            findings.append(
                f'prod retention below ci for {artifact_type}: '
                f'prod={prod_retention}, ci={ci_retention}'
            )

    if len(findings) != 0:
        print('Retention policy validation failed:')
        for finding in findings:
            print(f'- {finding}')
        return 1

    print('Retention policy validation passed.')
    for artifact_type in REQUIRED_ARTIFACT_TYPES:
        dev_days = retention_days_by_scope[(artifact_type, 'dev')]
        prod_days = retention_days_by_scope[(artifact_type, 'prod')]
        ci_days = retention_days_by_scope[(artifact_type, 'ci')]
        print(f'- {artifact_type}: dev={dev_days}, prod={prod_days}, ci={ci_days}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
