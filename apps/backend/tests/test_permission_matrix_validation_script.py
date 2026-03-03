from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def test_permission_matrix_validation_script_passes() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / 'tests' / 'operations' / 'permission_matrix_validation.py'
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert 'Permission matrix validation passed.' in result.stdout
