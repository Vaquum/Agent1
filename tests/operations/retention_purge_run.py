from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

from sqlalchemy.exc import SQLAlchemyError

def _get_repo_root() -> Path:

    '''
    Create repository root path from retention-purge runner script location.

    Returns:
    Path: Repository root path.
    '''

    return Path(__file__).resolve().parents[2]


def _configure_backend_import_path(repo_root: Path) -> None:

    '''
    Create backend source import path configuration for retention-purge imports.

    Args:
    repo_root (Path): Repository root path.
    '''

    backend_src_path = repo_root / 'apps' / 'backend' / 'src'
    backend_src_path_value = str(backend_src_path)
    if backend_src_path_value not in sys.path:
        sys.path.insert(0, backend_src_path_value)


def _parse_args() -> argparse.Namespace:

    '''
    Create parsed CLI arguments for retention-purge runner execution.

    Returns:
    argparse.Namespace: Parsed CLI argument namespace.
    '''

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--environment',
        required=True,
        choices=('dev', 'prod', 'ci'),
        help='Retention-purge target environment.',
    )
    parser.add_argument(
        '--mode',
        required=True,
        choices=('dry_run', 'execute'),
        help='Retention-purge mode.',
    )
    parser.add_argument(
        '--reference-timestamp',
        required=False,
        help='Optional ISO8601 UTC reference timestamp for deterministic retention cutoffs.',
    )
    parser.add_argument(
        '--allow-prod-execute',
        action='store_true',
        help='Explicit acknowledgement required for production execute mode.',
    )
    return parser.parse_args()


def _parse_reference_timestamp(reference_timestamp: str | None) -> datetime | None:
    if reference_timestamp is None:
        return None

    normalized_timestamp = reference_timestamp.replace('Z', '+00:00')
    return datetime.fromisoformat(normalized_timestamp)


def main() -> int:

    '''
    Compute process exit code for retention-purge run execution.

    Returns:
    int: Zero when execution succeeds, otherwise one.
    '''

    repo_root = _get_repo_root()
    _configure_backend_import_path(repo_root)

    from agent1.core.contracts import EnvironmentName
    from agent1.core.control_loader import validate_control_bundle
    from agent1.core.services.retention_purge_service import RetentionPurgeMode
    from agent1.core.services.retention_purge_service import RetentionPurgeService
    from agent1.core.services.retention_purge_service import render_retention_purge_report
    from agent1.db.base import Base
    from agent1.db.session import create_session_factory

    args = _parse_args()
    try:
        reference_timestamp = _parse_reference_timestamp(args.reference_timestamp)
        control_bundle = validate_control_bundle()
        environment = EnvironmentName(args.environment)
        mode = RetentionPurgeMode(args.mode)
        session_factory = create_session_factory()
        with session_factory() as session:
            Base.metadata.create_all(bind=session.get_bind())
        service = RetentionPurgeService(
            retention_policy=control_bundle.runtime.retention_policy,
            session_factory=session_factory,
        )
        report = service.run(
            environment=environment,
            mode=mode,
            reference_timestamp=reference_timestamp,
            allow_prod_execute=args.allow_prod_execute,
        )
    except ValueError as error:
        print('Retention purge run failed:')
        print(f'- {error}')
        return 1
    except SQLAlchemyError as error:
        print('Retention purge run failed:')
        print(f'- database schema validation error: {error}')
        print('- remediation: run `alembic upgrade head` before retention purge execution.')
        return 1

    print('Retention purge run completed.')
    print(render_retention_purge_report(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
