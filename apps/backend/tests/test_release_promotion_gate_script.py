from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def _run_release_promotion_gate(
    stop_the_line_clear: bool,
    rollout_stage_gate_passed: bool,
) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / 'tests' / 'operations' / 'release_promotion_gate.py'
    env = os.environ.copy()
    env['STOP_THE_LINE_CLEAR'] = 'true' if stop_the_line_clear else 'false'
    env['ROLLOUT_STAGE_GATE_PASSED'] = 'true' if rollout_stage_gate_passed else 'false'
    return subprocess.run(
        [sys.executable, str(script_path)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_release_promotion_gate_script_passes_when_required_evidence_flags_are_true() -> None:
    result = _run_release_promotion_gate(
        stop_the_line_clear=True,
        rollout_stage_gate_passed=True,
    )

    assert result.returncode == 0
    assert 'Release promotion gate passed.' in result.stdout


def test_release_promotion_gate_script_fails_when_stop_the_line_clear_is_false() -> None:
    result = _run_release_promotion_gate(
        stop_the_line_clear=False,
        rollout_stage_gate_passed=True,
    )

    assert result.returncode == 1
    assert 'Release promotion gate failed:' in result.stdout
    assert 'stop_the_line_clear' in result.stdout
