"""The wheel the packaging tests check, built once for the session from the working tree, in a
temporary directory, so nothing lands in the tree (release 0.1.0, verification: `uv run pytest -m
packaging` runs on a wheel built from the working tree).

`uv build --offline` needs the build backend in uv's cache. `pyproject.toml` pins it exactly, and
`uv sync` has already cached it, so the build downloads nothing.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
"""The repository's root, where `pyproject.toml` is."""


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


@pytest.fixture(scope="session")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The wheel built from the working tree, offline."""
    out = tmp_path_factory.mktemp("wheel")
    run_uv("build", "--wheel", "--offline", "--out-dir", out, cwd=ROOT)
    (built,) = out.glob("*.whl")
    return built
