"""The built wheel carries the license and the notices, and declares the custom license, never MIT
or an OSI license.

Traces to R01-AC19 (the wheel contains LICENSE, CONTACT.md, THIRD_PARTY_NOTICES.md, and the
disclaimers, and its metadata declares `LicenseRef-NSPRL-1.0`, with no MIT or OSI classifier),
and to LIC-01 and LIC-11 (docs/licensing-policy.md): the license identity, and the license and
notices in every copy. It also carries `trialfolio init`'s starter files (R01-AC33), `.gitignore`
included, under its packaged name, `gitignore`.
"""

import zipfile
from email.message import Message
from email.parser import BytesParser
from pathlib import Path

import pytest

from tests.packaging.conftest import ROOT

pytestmark = pytest.mark.packaging

LICENSE_FILES = ("LICENSE", "CONTACT.md", "THIRD_PARTY_NOTICES.md", "docs/disclaimers.md")
"""The files every copy carries, by their paths in the repository."""


def dist_info(archive: zipfile.ZipFile) -> str:
    """The wheel's `.dist-info` directory, with a trailing `/`."""
    (directory,) = {name.split("/", 1)[0] for name in archive.namelist() if ".dist-info/" in name}
    return directory + "/"


def metadata(wheel: Path) -> Message:
    """The wheel's core metadata."""
    with zipfile.ZipFile(wheel) as archive:
        return BytesParser().parsebytes(archive.read(dist_info(archive) + "METADATA"))


def test_the_wheel_carries_the_license_and_the_notices_unchanged(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        licenses = dist_info(archive) + "licenses/"
        for path in LICENSE_FILES:
            assert archive.read(licenses + path) == (ROOT / path).read_bytes(), path

    assert sorted(metadata(wheel).get_all("License-File", [])) == sorted(LICENSE_FILES)


def test_the_metadata_declares_the_custom_license_and_no_open_source_one(wheel: Path) -> None:
    core = metadata(wheel)

    assert core["License-Expression"] == "LicenseRef-NSPRL-1.0"
    assert core["License"] is None
    classifiers: list[str] = core.get_all("Classifier", [])
    assert not [c for c in classifiers if c.startswith("License ::")]
    assert not [c for c in classifiers if "MIT" in c or "OSI Approved" in c]


def test_the_wheel_carries_the_starter_files_unchanged(wheel: Path) -> None:
    starters = ROOT / "src" / "trialfolio" / "init_data"
    with zipfile.ZipFile(wheel) as archive:
        packaged = {
            name.removeprefix("trialfolio/init_data/"): archive.read(name)
            for name in archive.namelist()
            if name.startswith("trialfolio/init_data/")
        }

    # By name, not from the folder's listing: the build leaves out what Git ignores, such as a
    # `.DS_Store` that macOS's Finder adds.
    names = ("screen.yaml", "README.md", "gitignore")
    assert packaged == {name: (starters / name).read_bytes() for name in names}
