"""`trialfolio run` plans only in an environment a release has verified: an unverified `p123api`,
`requests`, or `urllib3`, and an importable `simplejson`, each fail with `environment.unsupported`
and exit 3, before the plan is shown, and create no output.

Traces to R01-AC05's environment part, and to docs/contracts.md, plan contents (verified
versions). The installed command runs in a subprocess, with the package versions double's
directory on its `PYTHONPATH` right after the network guard's: a `.dist-info` that reports
another version, or a fake `simplejson`. It fails before any request, so the test launcher isn't
needed. `tests/core/test_installed_versions.py` checks the same in the test process.
"""

import json
from pathlib import Path
from typing import cast

import pytest

from tests.interface.conftest import Cli, config
from tests.support.package_versions import fake_distribution, fake_simplejson, run_installed


def fails_before_the_plan(cli: Cli, directory: Path) -> str:
    """Runs `trialfolio run --json` with `directory` on the command's `PYTHONPATH`, checks that it
    failed with `environment.unsupported` and exit 3, showed no plan, and created no output, and
    returns its message."""
    out = cli.tmp / "out"

    result = run_installed(
        directory, "run", config("formula.yaml"), "--out", out, "--json", cwd=cli.tmp
    )

    assert result.returncode == 3, result.stderr
    summary = cast("dict[str, object]", json.loads(result.stdout))
    error = cast("dict[str, str]", summary["error"])
    assert error["code"] == "environment.unsupported"
    assert "Plan hash" not in result.stderr
    assert "Earnings yield with a liquidity floor" not in result.stderr
    assert summary["output_dir"] is None
    assert not out.exists()
    assert not list(cli.home.rglob("*.log"))
    return error["message"]


@pytest.mark.parametrize(
    ("name", "version"), [("p123api", "3.2.0"), ("requests", "2.35.0"), ("urllib3", "2.7.0")]
)
def test_an_unverified_version_fails_before_the_plan(cli: Cli, name: str, version: str) -> None:
    cli.accept_license()
    directory = cli.tmp / "packages"
    directory.mkdir()
    fake_distribution(directory, name, version)

    message = fails_before_the_plan(cli, directory)

    assert f"The installed {name} is {version}." in message


def test_an_importable_simplejson_fails_before_the_plan(cli: Cli) -> None:
    cli.accept_license()
    directory = cli.tmp / "packages"
    directory.mkdir()
    fake_simplejson(directory)

    message = fails_before_the_plan(cli, directory)

    assert "simplejson is importable" in message
