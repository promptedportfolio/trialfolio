"""Trial Folio plans only in an environment a release has verified (docs/contracts.md, plan
contents).

Traces to R01-AC05: an unverified `p123api`, `requests`, or `urllib3`, and an importable
`simplejson`, each fail with `environment.unsupported`, which comes before the plan is shown
because a plan needs the versions. These tests change what the test process reads, at the
installed package versions' boundary: a directory first on `sys.path` holds a `.dist-info` that
reports another version, or a `simplejson` package, from `tests/support/package_versions.py`.
`tests/interface/test_environment.py` runs the command itself in a subprocess with the same
directory on its `PYTHONPATH`.

A missing `p123api`, `requests`, or `urllib3` fails the same way, as the release's plan details
from R01-T10 say, and so does one that's installed but can't be imported, which R01-T14 extended
to `p123api`. That's checked in a new process, which imports the planner with the package
unimportable, and, when it isn't installed, without its package metadata.
"""

import subprocess
import sys
from pathlib import Path

import pytest
import requests

from tests.support.package_versions import fake_distribution, fake_simplejson
from trialfolio.errors import TrialFolioError
from trialfolio.planning import VERIFIED_VERSIONS, installed_versions

REPO_ROOT = Path(__file__).resolve().parents[2]


def unsupported() -> str:
    with pytest.raises(TrialFolioError) as raised:
        installed_versions()
    assert raised.value.code == "environment.unsupported"
    assert "p123api 3.1.0, requests 2.34.2, and urllib3 2.8.0" in raised.value.message
    return raised.value.message


def test_the_installed_versions_are_the_verified_ones() -> None:
    versions = installed_versions()

    assert versions.trialfolio == "0.1.0"
    for name, verified in VERIFIED_VERSIONS.items():
        assert getattr(versions, name) in verified


@pytest.mark.parametrize(
    ("name", "version"), [("p123api", "3.2.0"), ("requests", "2.35.0"), ("urllib3", "2.7.0")]
)
def test_an_unverified_version_is_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, version: str
) -> None:
    fake_distribution(tmp_path, name, version)
    monkeypatch.syspath_prepend(tmp_path)

    message = unsupported()

    assert f"The installed {name} is {version}." in message
    assert "Reinstall Trial Folio" in message


def test_an_imported_module_of_another_version_is_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A stale .dist-info: the metadata says the verified version, but other code is imported.
    monkeypatch.setattr(requests, "__version__", "2.33.0")

    message = unsupported()

    assert "The imported requests reports another version than its package metadata" in message


def test_an_importable_simplejson_is_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_simplejson(tmp_path)
    monkeypatch.syspath_prepend(tmp_path)

    message = unsupported()

    assert "simplejson is importable" in message
    assert "Uninstall simplejson" in message


MISSING_PACKAGE = """
import importlib.metadata
import sys

name, state = sys.argv[1:]
sys.modules[name] = None  # importing it fails, as when its files are gone
if state == "not installed":
    read_version = importlib.metadata.version

    def version(distribution):
        if distribution == name:
            raise importlib.metadata.PackageNotFoundError(distribution)
        return read_version(distribution)

    importlib.metadata.version = version

from trialfolio.errors import TrialFolioError
from trialfolio.planning import installed_versions

try:
    installed_versions()
except TrialFolioError as error:
    print(error.code)
    print(error.message)
"""
"""Imports the planner without the package named first, and prints the error planning gives."""


@pytest.mark.parametrize("state", ["not installed", "unimportable"])
@pytest.mark.parametrize("name", ["p123api", "requests", "urllib3"])
def test_a_missing_provider_package_is_unsupported(name: str, state: str) -> None:
    # A new process, because the planner itself must import without the package.
    result = subprocess.run(
        [sys.executable, "-c", MISSING_PACKAGE, name, state],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    )

    code, message = result.stdout.split("\n", 1)
    assert code == "environment.unsupported"
    assert "p123api 3.1.0, requests 2.34.2, and urllib3 2.8.0" in message
    if state == "not installed":
        assert f"{name} isn't installed." in message
    else:
        assert f"{name} is installed, but it can't be imported" in message
    assert "Reinstall Trial Folio" in message
