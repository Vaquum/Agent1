from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def _get_repo_root() -> Path:

    '''
    Create repository root path from live runner module location.

    Returns:
    Path: Absolute Agent1 repository root path.
    '''

    return Path(__file__).resolve().parents[2]


def main() -> int:

    '''
    Compute live smoke process exit code.

    Returns:
    int: Runner process exit code.
    '''

    repo_root = _get_repo_root()
    command = [
        sys.executable,
        '-m',
        'pytest',
        '-q',
        'tests/live/test_github_sandbox_smoke.py',
    ]
    completed = subprocess.run(
        command,
        cwd=repo_root,
        check=False,
    )
    return completed.returncode


if __name__ == '__main__':
    raise SystemExit(main())
