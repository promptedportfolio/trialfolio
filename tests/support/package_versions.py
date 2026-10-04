"""Package versions: the double for the installed environment (release 0.1.0, test pairing).

A directory holds a fake `simplejson` package, or a `.dist-info` that reports another version of
`p123api`, `requests`, or `urllib3`. Trial Folio reads versions from package metadata, so the fake
`.dist-info` changes what it reads; for `requests` and `urllib3`, it then also differs from the
imported module's `__version__`. The fake `simplejson` defines `JSONDecodeError` as a `ValueError`
subclass, because `requests.compat` imports it, so `requests` still imports, and Trial Folio's own
check is what fails.

`run_installed` runs the installed command in a subprocess whose `PYTHONPATH` holds the directory
right after the network guard's, which the guard puts first. In the test process, a test puts the
directory first on `sys.path` instead.
"""

import os
import subprocess
import sys
import sysconfig
from collections.abc import Mapping
from pathlib import Path


def fake_distribution(directory: Path, name: str, version: str) -> None:
    """A `.dist-info` in `directory` that reports `version` of the package `name`."""
    info = directory / f"{name}-{version}.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")


def fake_simplejson(directory: Path) -> None:
    """A `simplejson` package in `directory`, which `requests` can import."""
    package = directory / "simplejson"
    package.mkdir()
    (package / "__init__.py").write_text(
        '"""A fake simplejson for Trial Folio\'s tests."""\n\n'
        "from json import dumps, loads\n\n"
        '__all__ = ["JSONDecodeError", "dumps", "loads"]\n\n\n'
        "class JSONDecodeError(ValueError):\n"
        "    pass\n"
    )


def installed_command() -> Path:
    """The installed `trialfolio` command, in the environment the tests run in."""
    name = "trialfolio.exe" if sys.platform == "win32" else "trialfolio"
    return Path(sysconfig.get_path("scripts")) / name


def run_installed(
    directory: Path,
    *argv: str | Path,
    cwd: Path,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Runs the installed command with `argv`, with `directory` first on its `PYTHONPATH` after
    the network guard's, in `cwd`, with `env`, or the test's environment, and stdin closed."""
    environment = dict(os.environ if env is None else env)
    inherited = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(directory), *(inherited.split(os.pathsep) if inherited else [])]
    )
    return subprocess.run(
        [str(installed_command()), *(str(arg) for arg in argv)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=environment,
    )
