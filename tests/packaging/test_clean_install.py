"""The built wheel installs in a new virtual environment, offline, and its `trialfolio demo` runs
there under the network guard, and writes a run labeled synthetic. Its `trialfolio init` writes
the starter files from the installed package (R01-AC33), and its `trialfolio review` compares two
runs its `trialfolio demo` wrote.

Traces to R01-AC16 (clean install: the wheel installs, and `trialfolio demo --out <dir>` runs
offline with `TRIALFOLIO_ACCEPT_LICENSE` set and exits 0, labeled synthetic), in the form release
0.1.0's test pairing gives, and to the packaging part of R02-AC05 (the installed `trialfolio
review` of two runs the installed `trialfolio demo` wrote exits 0 under the network guard). The
locked runtime dependencies are exported with their hashes as `pylock.toml`, installed from uv's
cache, which `uv sync` filled, and the wheel then without dependencies, so the versions come from
`uv.lock` and nothing is downloaded. The environment is installed once for the module. The
project's own environment isn't touched, and everything is written under a temporary directory.

Each command runs with the network guard first on its `PYTHONPATH`, as every subprocess the suite
starts does, so it fails if it reaches any host but localhost.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.packaging.conftest import ROOT, run_uv
from tests.support.html_report import parse
from trialfolio.acknowledgment import ACCEPT_VALUE, ACCEPT_VARIABLE
from trialfolio.contracts.manifest import RunManifest
from trialfolio.contracts.review_manifest import ReviewManifest
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


@pytest.fixture(scope="module")
def environment(wheel: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The clean environment, installed once for the module."""
    return clean_install(wheel, tmp_path_factory.mktemp("install"))


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


def test_the_wheel_installs_cleanly_and_its_demo_runs_offline(
    environment: Path, tmp_path: Path
) -> None:
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

    workspace = tmp_path / "workspace"
    initialized = run([command(environment, "trialfolio"), "init", workspace], tmp_path, env)

    assert initialized.returncode == 0, initialized.stderr
    assert sorted(path.name for path in workspace.iterdir()) == [
        ".gitignore",
        "README.md",
        "screen.yaml",
    ]


REVIEW = """\
kind: review
schema_version: 1.0.0
title: Two demo runs
baseline: first
results:
  - label: first
    run: runs/first
  - label: second
    run: runs/second
"""


def test_the_installed_review_compares_two_demo_runs_offline(
    environment: Path, tmp_path: Path
) -> None:
    env = demo_environment(tmp_path)
    trialfolio = command(environment, "trialfolio")
    for label in ("first", "second"):
        demo = run([trialfolio, "demo", "--out", tmp_path / "runs" / label], tmp_path, env)
        assert demo.returncode == 0, demo.stderr
    configuration = tmp_path / "review.yaml"
    configuration.write_text(REVIEW, encoding="utf-8")
    out = tmp_path / "review"

    result = run([trialfolio, "review", configuration, "--out", out, "--json"], tmp_path, env)

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["command"] == "review"
    assert summary["outcome"] == "completed"
    manifest = ReviewManifest.model_validate_json((out / "manifest.json").read_bytes())
    assert manifest.synthetic is True
    assert [(r.label, r.synthetic) for r in manifest.results] == [("first", True), ("second", True)]
    assert summary["ids"] == {"review_id": str(manifest.review_id)}
    # The demo saves the same invented response each time, so the two results share it.
    assert manifest.results[0].response == manifest.results[1].response
    assert summary["counts"]["warnings"] == 1
    document = parse((out / "report.html").read_text(encoding="utf-8"))
    (banner,) = (e for e in document.root.iter() if e.attrs.get("class") == "synthetic")
    assert banner.text.startswith("Synthetic results.")
    assert (out / "logs" / "trialfolio.log").is_file()
    assert not (tmp_path / "config").exists()
    assert not (tmp_path / "logs").exists()
