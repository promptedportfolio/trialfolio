"""THIRD_PARTY_NOTICES.md's statement of the locked runtime set names every package in the locked
runtime dependencies, those the direct ones bring in as well as the direct ones.

Traces to release 0.1.0's other checks in the default suite, and to AGENTS.md: each dependency is
recorded in THIRD_PARTY_NOTICES.md, together with every package it brings in (LIC-11 and the
release checklist, LIC-19, in docs/licensing-policy.md). The locked set comes from `uv export
--frozen --no-dev --no-emit-project`, which reads `uv.lock` and nothing else, so the test needs no
network. Names compare as PEP 503 normalizes them, so the file may write `PyYAML` or
`typing_extensions` as their publishers do.

Only the file's "The locked runtime set" paragraph counts. The file also names packages that aren't
in that set: the development tools, which are never distributed, and the packages the p123api
pandas extra would add. A runtime dependency named only there is still missing from the record.
Versions aren't compared: the release checklist requires them to match at a release.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NOTICES = ROOT / "THIRD_PARTY_NOTICES.md"

_REQUIREMENT = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)==")
"""A pinned requirement's name, at the start of an exported line."""

_RUNTIME_SET = re.compile(r"^\*\*The locked runtime set\*\*.*$", re.MULTILINE)
"""The file's statement of the locked runtime set: one paragraph, on one line."""

_PACKAGE = re.compile(r"(?<![\w.-])([A-Za-z][A-Za-z0-9._-]*) \d+(?:\.[0-9A-Za-z]+)+")
"""A package's name, followed by its version, as the runtime set lists them: `PyYAML 6.0.3`."""


def normalized(name: str) -> str:
    """`name` as PEP 503 normalizes it."""
    return re.sub(r"[-_.]+", "-", name).lower()


def locked_runtime_packages() -> set[str]:
    """The normalized names of the locked runtime dependencies."""
    uv = os.environ.get("UV") or shutil.which("uv")
    if not uv:
        pytest.fail("uv not found; this test needs it (AGENTS.md, development commands)")
    result = subprocess.run(
        [uv, "export", "--frozen", "--no-dev", "--no-emit-project"]
        + ["--no-hashes", "--no-header", "--no-annotate"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    names = {
        normalized(match.group(1))
        for line in result.stdout.splitlines()
        if (match := _REQUIREMENT.match(line.strip()))
    }
    # The export's form changed if the direct dependencies aren't in it.
    assert {"p123api", "pydantic", "pyyaml", "requests", "rfc8785", "urllib3"} <= names
    return names


def recorded_runtime_packages() -> set[str]:
    """The normalized names in THIRD_PARTY_NOTICES.md's "The locked runtime set" paragraph."""
    paragraphs = _RUNTIME_SET.findall(NOTICES.read_text(encoding="utf-8"))
    assert len(paragraphs) == 1, "THIRD_PARTY_NOTICES.md has no single locked runtime set"
    return {normalized(name) for name in _PACKAGE.findall(paragraphs[0])}


def test_the_notices_name_every_locked_runtime_package() -> None:
    assert sorted(locked_runtime_packages() - recorded_runtime_packages()) == []
