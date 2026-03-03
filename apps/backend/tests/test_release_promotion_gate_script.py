from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import create_engine

from agent1.core.contracts import AuditRunStatus
from agent1.db.base import Base
from agent1.db.models import AuditRunModel

def _initialize_database(database_url: str) -> None:
    engine = create_engine(database_url, future=True)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()


def _run_release_promotion_gate(
    stop_the_line_clear: bool,
    rollout_stage_gate_passed: bool,
    database_url: str,
) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / 'tests' / 'operations' / 'release_promotion_gate.py'
    env = os.environ.copy()
    env['STOP_THE_LINE_CLEAR'] = 'true' if stop_the_line_clear else 'false'
    env['ROLLOUT_STAGE_GATE_PASSED'] = 'true' if rollout_stage_gate_passed else 'false'
    env['AGENT1_AUDIT_ENVIRONMENT'] = 'ci'
    env['DATABASE_URL'] = database_url
    return subprocess.run(
        [sys.executable, str(script_path)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_release_promotion_gate_script_passes_when_required_evidence_flags_are_true(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / 'release_promotion_gate_pass.db'
    database_url = f"sqlite+pysqlite:///{database_path}"
    _initialize_database(database_url)
    result = _run_release_promotion_gate(
        stop_the_line_clear=True,
        rollout_stage_gate_passed=True,
        database_url=database_url,
    )
    verification_engine = create_engine(database_url, future=True)
    try:
        with verification_engine.connect() as connection:
            rows = connection.execute(
                AuditRunModel.__table__.select().order_by(AuditRunModel.started_at.desc())
            ).all()
    finally:
        verification_engine.dispose()

    assert result.returncode == 0
    assert 'Release promotion gate passed.' in result.stdout
    assert len(rows) == 1
    assert rows[0].audit_type == 'release_promotion_gate'
    assert rows[0].status == AuditRunStatus.SUCCEEDED.value
    assert rows[0].snapshot.get('decision_passed') is True


def test_release_promotion_gate_script_fails_when_stop_the_line_clear_is_false(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / 'release_promotion_gate_fail.db'
    database_url = f"sqlite+pysqlite:///{database_path}"
    _initialize_database(database_url)
    result = _run_release_promotion_gate(
        stop_the_line_clear=False,
        rollout_stage_gate_passed=True,
        database_url=database_url,
    )
    verification_engine = create_engine(database_url, future=True)
    try:
        with verification_engine.connect() as connection:
            rows = connection.execute(
                AuditRunModel.__table__.select().order_by(AuditRunModel.started_at.desc())
            ).all()
    finally:
        verification_engine.dispose()

    assert result.returncode == 1
    assert 'Release promotion gate failed:' in result.stdout
    assert 'stop_the_line_clear' in result.stdout
    assert len(rows) == 1
    assert rows[0].status == AuditRunStatus.FAILED.value
    assert 'stop_the_line_clear' in rows[0].snapshot.get('failed_preconditions', [])
