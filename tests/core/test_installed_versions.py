"""Trial Folio plans only in an environment a release has verified (docs/contracts.md, plan
contents).

Traces to R01-AC05: an unverified `p123api`, `requests`, or `urllib3`, and an importable
`simplejson`, each fail with `environment.unsupported`, which comes before the plan is shown
because a plan needs the versions. These tests change what the test process reads, at the
installed package versions' boundary: a directory first on `sys.path` holds a `.dist-info` that
reports another version, or a `simplejson` package. `tests/interface/test_environment.py`
(R01-T16) runs the command itself in a subprocess with the same directory on its `PYTHONPATH`.
"""

from pathlib import Path

import pytest
import requests

from trialfolio.errors import TrialFolioError
from trialfolio.planning import VERIFIED_VERSIONS, installed_versions


def fake_distribution(directory: Path, name: str, version: str) -> None:
    info = directory / f"{name}-{version}.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")


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
    (tmp_path / "simplejson").mkdir()
    (tmp_path / "simplejson" / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(tmp_path)

    message = unsupported()

    assert "simplejson is importable" in message
    assert "Uninstall simplejson" in message
