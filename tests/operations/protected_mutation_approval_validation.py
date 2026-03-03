from __future__ import annotations

from pathlib import Path
import sys


def _get_repo_root() -> Path:

    '''
    Create repository root path from protected-mutation validation script location.

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
    Compute process exit code for protected-mutation approval validation.

    Returns:
    int: Zero when validation passes, otherwise one.
    '''

    repo_root = _get_repo_root()
    _configure_backend_import_path(repo_root)
    from agent1.core.control_loader import validate_control_bundle

    control_bundle = validate_control_bundle()
    protected_mutation_approval = control_bundle.policies.protected_mutation_approval
    print('Protected mutation approval validation passed.')
    print(f'- active approval id: {protected_mutation_approval.active_snapshot.approval_id}')
    print(f'- audit trail events: {len(protected_mutation_approval.audit_trail)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
