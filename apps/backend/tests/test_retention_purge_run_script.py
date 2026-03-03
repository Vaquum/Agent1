from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.contracts import AgentEvent
from agent1.core.contracts import AuditRunStatus
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EventSource
from agent1.core.contracts import EventStatus
from agent1.core.contracts import EventType
from agent1.db.base import Base
from agent1.db.models import AuditRunModel
from agent1.db.models import EventJournalModel
from agent1.db.models import GitHubEventModel
from agent1.db.repositories.event_repository import EventRepository


def _initialize_database(database_url: str) -> None:
    engine = create_engine(database_url, future=True)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()


def _seed_boundary_rows(database_url: str, reference_timestamp: datetime) -> None:
    engine = create_engine(database_url, future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    cutoff_timestamp = reference_timestamp - timedelta(days=14)
    older_timestamp = cutoff_timestamp - timedelta(seconds=1)
    boundary_timestamp = cutoff_timestamp
    newer_timestamp = cutoff_timestamp + timedelta(seconds=1)
    try:
        with session_factory() as session:
            event_repository = EventRepository(session)
            event_repository.append_event(
                AgentEvent(
                    timestamp=older_timestamp,
                    environment=EnvironmentName.DEV,
                    trace_id='retention_purge_old_log',
                    job_id='retention_purge_old_log',
                    entity_key='Vaquum/Agent1#8101',
                    source=EventSource.AGENT,
                    event_type=EventType.STATE_TRANSITION,
                    status=EventStatus.OK,
                    details={'sample': 'old'},
                )
            )
            event_repository.append_event(
                AgentEvent(
                    timestamp=boundary_timestamp,
                    environment=EnvironmentName.DEV,
                    trace_id='retention_purge_boundary_log',
                    job_id='retention_purge_boundary_log',
                    entity_key='Vaquum/Agent1#8102',
                    source=EventSource.AGENT,
                    event_type=EventType.STATE_TRANSITION,
                    status=EventStatus.OK,
                    details={'sample': 'boundary'},
                )
            )
            event_repository.append_event(
                AgentEvent(
                    timestamp=newer_timestamp,
                    environment=EnvironmentName.DEV,
                    trace_id='retention_purge_new_log',
                    job_id='retention_purge_new_log',
                    entity_key='Vaquum/Agent1#8103',
                    source=EventSource.AGENT,
                    event_type=EventType.STATE_TRANSITION,
                    status=EventStatus.OK,
                    details={'sample': 'new'},
                )
            )
            session.add(
                GitHubEventModel(
                    source_event_id='retention_trace_old',
                    source_timestamp_or_seq='retention-trace-old',
                    source_timestamp=older_timestamp,
                    received_at=older_timestamp,
                    environment=EnvironmentName.DEV,
                    repository='Vaquum/Agent1',
                    entity_number=8101,
                    entity_key='Vaquum/Agent1#8101',
                    actor='mikkokotila',
                    ingress_event_type='issue_mention',
                    ordering_decision='accepted',
                    is_stale=False,
                    stale_reason=None,
                    details={'sample': 'old'},
                )
            )
            session.add(
                GitHubEventModel(
                    source_event_id='retention_trace_boundary',
                    source_timestamp_or_seq='retention-trace-boundary',
                    source_timestamp=boundary_timestamp,
                    received_at=boundary_timestamp,
                    environment=EnvironmentName.DEV,
                    repository='Vaquum/Agent1',
                    entity_number=8102,
                    entity_key='Vaquum/Agent1#8102',
                    actor='mikkokotila',
                    ingress_event_type='issue_mention',
                    ordering_decision='accepted',
                    is_stale=False,
                    stale_reason=None,
                    details={'sample': 'boundary'},
                )
            )
            session.add(
                GitHubEventModel(
                    source_event_id='retention_trace_new',
                    source_timestamp_or_seq='retention-trace-new',
                    source_timestamp=newer_timestamp,
                    received_at=newer_timestamp,
                    environment=EnvironmentName.DEV,
                    repository='Vaquum/Agent1',
                    entity_number=8103,
                    entity_key='Vaquum/Agent1#8103',
                    actor='mikkokotila',
                    ingress_event_type='issue_mention',
                    ordering_decision='accepted',
                    is_stale=False,
                    stale_reason=None,
                    details={'sample': 'new'},
                )
            )
            session.add(
                AuditRunModel(
                    audit_run_id='retention_audit_old',
                    environment=EnvironmentName.DEV,
                    audit_type='retention',
                    status=AuditRunStatus.SUCCEEDED,
                    started_at=older_timestamp,
                    completed_at=older_timestamp + timedelta(minutes=1),
                    snapshot={'sample': 'old'},
                )
            )
            session.add(
                AuditRunModel(
                    audit_run_id='retention_audit_boundary',
                    environment=EnvironmentName.DEV,
                    audit_type='retention',
                    status=AuditRunStatus.SUCCEEDED,
                    started_at=boundary_timestamp,
                    completed_at=boundary_timestamp + timedelta(minutes=1),
                    snapshot={'sample': 'boundary'},
                )
            )
            session.add(
                AuditRunModel(
                    audit_run_id='retention_audit_new',
                    environment=EnvironmentName.DEV,
                    audit_type='retention',
                    status=AuditRunStatus.SUCCEEDED,
                    started_at=newer_timestamp,
                    completed_at=newer_timestamp + timedelta(minutes=1),
                    snapshot={'sample': 'new'},
                )
            )
            session.commit()
    finally:
        engine.dispose()


def _parse_report_payload(stdout: str) -> dict[str, object]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip() != '']
    report_line = lines[-1]
    payload = json.loads(report_line)
    assert isinstance(payload, dict)
    return payload


def _run_retention_purge_script(
    database_url: str,
    environment: str,
    mode: str,
    reference_timestamp: str,
    allow_prod_execute: bool = False,
) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / 'tests' / 'operations' / 'retention_purge_run.py'
    env = os.environ.copy()
    env['DATABASE_URL'] = database_url
    command = [
        sys.executable,
        str(script_path),
        '--environment',
        environment,
        '--mode',
        mode,
        '--reference-timestamp',
        reference_timestamp,
    ]
    if allow_prod_execute:
        command.append('--allow-prod-execute')

    return subprocess.run(
        command,
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _count_rows_by_model(session: Session) -> tuple[int, int, int]:
    log_count = (
        session.query(EventJournalModel)
        .filter(EventJournalModel.environment == EnvironmentName.DEV)
        .count()
    )
    trace_count = (
        session.query(GitHubEventModel)
        .filter(GitHubEventModel.environment == EnvironmentName.DEV)
        .count()
    )
    artifact_count = (
        session.query(AuditRunModel)
        .filter(AuditRunModel.environment == EnvironmentName.DEV)
        .count()
    )
    return log_count, trace_count, artifact_count


def test_retention_purge_run_script_dry_run_preserves_boundary_rows(tmp_path: Path) -> None:
    database_path = tmp_path / 'retention_purge_dry_run.db'
    database_url = f"sqlite+pysqlite:///{database_path}"
    reference_timestamp = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
    _initialize_database(database_url)
    _seed_boundary_rows(database_url, reference_timestamp)

    result = _run_retention_purge_script(
        database_url=database_url,
        environment='dev',
        mode='dry_run',
        reference_timestamp='2026-03-10T12:00:00Z',
    )
    payload = _parse_report_payload(result.stdout)

    engine = create_engine(database_url, future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        with session_factory() as session:
            row_counts = _count_rows_by_model(session)
    finally:
        engine.dispose()

    assert result.returncode == 0
    assert payload['mode'] == 'dry_run'
    assert payload['total_candidates'] == 3
    assert payload['total_purged'] == 0
    assert row_counts == (3, 3, 3)


def test_retention_purge_run_script_execute_purges_older_than_cutoff_only(tmp_path: Path) -> None:
    database_path = tmp_path / 'retention_purge_execute.db'
    database_url = f"sqlite+pysqlite:///{database_path}"
    reference_timestamp = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
    cutoff_timestamp = reference_timestamp - timedelta(days=14)
    _initialize_database(database_url)
    _seed_boundary_rows(database_url, reference_timestamp)

    result = _run_retention_purge_script(
        database_url=database_url,
        environment='dev',
        mode='execute',
        reference_timestamp='2026-03-10T12:00:00Z',
    )
    payload = _parse_report_payload(result.stdout)

    engine = create_engine(database_url, future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        with session_factory() as session:
            row_counts = _count_rows_by_model(session)
            boundary_event_count = (
                session.query(EventJournalModel)
                .filter(EventJournalModel.environment == EnvironmentName.DEV)
                .filter(EventJournalModel.timestamp == cutoff_timestamp)
                .count()
            )
            event_repository = EventRepository(session)
            chain_findings = event_repository.verify_event_chain(environment=EnvironmentName.DEV)
    finally:
        engine.dispose()

    assert result.returncode == 0
    assert payload['mode'] == 'execute'
    assert payload['total_candidates'] == 3
    assert payload['total_purged'] == 3
    assert row_counts == (2, 2, 2)
    assert boundary_event_count == 1
    assert chain_findings == []


def test_retention_purge_run_script_requires_explicit_prod_execute_ack(tmp_path: Path) -> None:
    database_path = tmp_path / 'retention_purge_prod_guard.db'
    database_url = f"sqlite+pysqlite:///{database_path}"
    _initialize_database(database_url)

    result = _run_retention_purge_script(
        database_url=database_url,
        environment='prod',
        mode='execute',
        reference_timestamp='2026-03-10T12:00:00Z',
    )

    assert result.returncode == 1
    assert 'Retention purge run failed:' in result.stdout
    assert 'allow_prod_execute=True' in result.stdout
