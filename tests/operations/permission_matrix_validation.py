from __future__ import annotations

from pathlib import Path
import sys

REQUIRED_COMPONENT_ENTRY_COUNT = 15


def _get_repo_root() -> Path:

    '''
    Create repository root path from permission-matrix validation script location.

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
    Compute process exit code for permission-matrix validation.

    Returns:
    int: Zero when validation passes, otherwise one.
    '''

    repo_root = _get_repo_root()
    _configure_backend_import_path(repo_root)
    from agent1.core.control_loader import validate_control_bundle

    control_bundle = validate_control_bundle()
    permission_matrix = control_bundle.policies.permission_matrix
    if len(permission_matrix.entries) != REQUIRED_COMPONENT_ENTRY_COUNT:
        print('Permission matrix validation failed:')
        print(
            '- invalid entry count: '
            f'expected {REQUIRED_COMPONENT_ENTRY_COUNT}, got {len(permission_matrix.entries)}',
        )
        return 1

    print('Permission matrix validation passed.')
    print(f'- entries: {len(permission_matrix.entries)}')
    print(
        '- persistence roles: '
        'migrator, runtime, readonly_analytics',
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
