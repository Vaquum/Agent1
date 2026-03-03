from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_event_journal_chain_validation_script_passes(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / 'tests' / 'operations' / 'event_journal_chain_validation.py'
    database_url = f'sqlite+pysqlite:///{tmp_path / "event_chain_validation.db"}'
    environment = os.environ.copy()
    environment['DATABASE_URL'] = database_url
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert 'Event journal chain validation passed.' in result.stdout
