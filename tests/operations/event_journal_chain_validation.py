from __future__ import annotations

import argparse
from pathlib import Path
import sys


def _get_repo_root() -> Path:

    '''
    Create repository root path from event-journal chain validation script location.

    Returns:
    Path: Repository root path.
    '''

    return Path(__file__).resolve().parents[2]


def _configure_backend_import_path(repo_root: Path) -> None:

    '''
    Create backend source import path configuration for chain validation imports.

    Args:
    repo_root (Path): Repository root path.
    '''

    backend_src_path = repo_root / 'apps' / 'backend' / 'src'
    backend_src_path_value = str(backend_src_path)
    if backend_src_path_value not in sys.path:
        sys.path.insert(0, backend_src_path_value)


def _parse_args() -> argparse.Namespace:

    '''
    Create parsed CLI arguments for event-journal chain validation execution.

    Returns:
    argparse.Namespace: Parsed CLI argument namespace.
    '''

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--environment',
        required=False,
        choices=('dev', 'prod', 'ci'),
        help='Optional environment scope for chain validation.',
    )
    parser.add_argument(
        '--backfill-missing',
        action='store_true',
        help='Rebuild chain values before verification.',
    )
    return parser.parse_args()


def main() -> int:

    '''
    Compute process exit code for event-journal chain validation.

    Returns:
    int: Zero when validation passes, otherwise one.
    '''

    repo_root = _get_repo_root()
    _configure_backend_import_path(repo_root)

    from agent1.core.contracts import EnvironmentName
    from agent1.db.base import Base
    from agent1.db.repositories.event_repository import EventRepository
    from agent1.db.session import create_session_factory

    args = _parse_args()
    environment = EnvironmentName(args.environment) if args.environment is not None else None
    session_factory = create_session_factory()
    rebuilt_count = 0
    with session_factory() as session:
        Base.metadata.create_all(bind=session.get_bind())
        repository = EventRepository(session)
        if args.backfill_missing:
            rebuilt_count = repository.rebuild_event_chain(environment=environment)
            session.commit()
        findings = repository.verify_event_chain(environment=environment)

    if len(findings) != 0:
        print('Event journal chain validation failed:')
        for finding in findings:
            print(f'- {finding}')
        return 1

    print('Event journal chain validation passed.')
    if environment is not None:
        print(f'- environment: {environment.value}')
    if args.backfill_missing:
        print(f'- rebuilt rows: {rebuilt_count}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
