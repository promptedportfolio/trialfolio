"""`uv`, which the packaging tests build and install the wheel with: the command, and a run of it
that fails the test, with uv's output, unless uv exits 0.

TS-T04 moved them here from the packaging tests' conftest, which keeps its fixture.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


def uv() -> str:
    """The `uv` command: the one `uv run` names in `UV`, or the first on `PATH`."""
    found = os.environ.get("UV") or shutil.which("uv")
    if not found:
        pytest.fail("uv not found; the packaging tests need it (AGENTS.md, development commands)")
    return found


def run_uv(*argv: str | Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Runs `uv` with `argv` in `cwd`, with stdin closed. It fails the test, with uv's output,
    unless uv exits 0."""
    result = subprocess.run(
        [uv(), *(str(arg) for arg in argv)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    assert result.returncode == 0, f"uv {' '.join(map(str, argv))}:\n{result.stdout}{result.stderr}"
    return result
