"""The built wheel installs in a new virtual environment, offline, and its `trialfolio demo` runs
there under the network guard, and writes a run labeled synthetic.

Traces to R01-AC16 (clean install: the wheel installs, and `trialfolio demo --out <dir>` runs
offline with `TRIALFOLIO_ACCEPT_LICENSE` set and exits 0, labeled synthetic), in the form release
0.1.0's test pairing gives. The locked runtime dependencies are exported with their hashes as
`pylock.toml`, installed from uv's cache, which `uv sync` filled, and the wheel then without
dependencies, so the versions come from `uv.lock` and nothing is downloaded. The project's own
environment isn't touched, and everything is written under a temporary directory.

The demo runs with the network guard first on its `PYTHONPATH`, as every subprocess the suite
starts does, so it fails if it reaches any host but localhost.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.packaging.conftest import ROOT, run_uv
from tests.support.html_report import parse
from trialfolio.acknowledgment import ACCEPT_VALUE, ACCEPT_VARIABLE
from trialfolio.contracts.manifest import RunManifest
from trialfolio.userdirs import CONFIG_DIRECTORY_VARIABLE, LOG_DIRECTORY_VARIABLE

pytestmark = pytest.mark.packaging


def scripts(environment: Path) -> Path:
    """A virtual environment's directory of commands."""
    return environment / ("Scripts" if sys.platform == "win32" else "bin")


def command(environment: Path, name: str) -> Path:
    return scripts(environment) / (f"{name}.exe" if sys.platform == "win32" else name)


def clean_install(wheel: Path, tmp: Path) -> Path:
    """A new virtual environment, on the suite's interpreter, holding the locked runtime
    dependencies and then the wheel, all installed offline."""
    lock = tmp / "pylock.toml"
    run_uv(
        "export", "--frozen", "--no-dev", "--no-emit-project", "--format", "pylock.toml",
        "-o", lock, cwd=ROOT,
    )  # fmt: skip
    environment = tmp / "venv"
    run_uv("venv", "--python", sys.executable, environment, cwd=tmp)
    run_uv("pip", "install", "--python", environment, "--offline", "-r", lock, cwd=tmp)
    run_uv("pip", "install", "--python", environment, "--offline", "--no-deps", wheel, cwd=tmp)
    run_uv("pip", "check", "--python", environment, cwd=tmp)
    return environment


def demo_environment(tmp: Path) -> dict[str, str]:
    """The test's environment, with the license acknowledged for the process, and the per-user
    configuration and log directories under `tmp`, without any other variable Trial Folio
    reads."""
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("TRIALFOLIO_") and name != "SSLKEYLOGFILE"
    }
    environment[ACCEPT_VARIABLE] = ACCEPT_VALUE
    environment[CONFIG_DIRECTORY_VARIABLE] = str(tmp / "config")
    environment[LOG_DIRECTORY_VARIABLE] = str(tmp / "logs")
    return environment


def run(argv: list[str | Path], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(arg) for arg in argv],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=env,
    )


def test_the_wheel_installs_cleanly_and_its_demo_runs_offline(wheel: Path, tmp_path: Path) -> None:
    environment = clean_install(wheel, tmp_path)
    env = demo_environment(tmp_path)
    out = tmp_path / "demo"

    # The command is the clean environment's, and it imports Trial Folio from there.
    imported = run(
        [command(environment, "python"), "-c", "import trialfolio; print(trialfolio.__file__)"],
        tmp_path,
        env,
    )
    assert imported.returncode == 0, imported.stderr
    assert Path(imported.stdout.strip()).resolve().is_relative_to(environment.resolve())

    result = run([command(environment, "trialfolio"), "demo", "--out", out], tmp_path, env)

    assert result.returncode == 0, result.stderr
    manifest = RunManifest.model_validate_json((out / "manifest.json").read_bytes())
    assert manifest.synthetic is True
    assert manifest.approval == "not_required"
    assert manifest.outcome == "completed"
    document = parse((out / "report.html").read_text(encoding="utf-8"))
    assert document.dd("Results")[0].startswith("Synthetic:")
    (banner,) = (e for e in document.root.iter() if e.attrs.get("class") == "synthetic")
    assert banner.text.startswith("Synthetic example.")
    # The variable acknowledges for the process without a record, and the run logs only under
    # its output directory.
    assert not (tmp_path / "config").exists()
    assert not (tmp_path / "logs").exists()
    assert (out / "logs" / "trialfolio.log").is_file()
