from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def test_protected_mutation_approval_validation_script_passes() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / 'tests' / 'operations' / 'protected_mutation_approval_validation.py'
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert 'Protected mutation approval validation passed.' in result.stdout
