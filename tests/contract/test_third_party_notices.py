"""THIRD_PARTY_NOTICES.md names every package in the locked runtime dependencies, those the direct
ones bring in as well as the direct ones.

Traces to release 0.1.0's other checks in the default suite, and to AGENTS.md: each dependency is
recorded in THIRD_PARTY_NOTICES.md, together with every package it brings in (LIC-11 and the
release checklist, LIC-19, in docs/licensing-policy.md). The locked set comes from `uv export
--frozen --no-dev --no-emit-project`, which reads `uv.lock` and nothing else, so the test needs no
network. Names compare as PEP 503 normalizes them, so the file may write `PyYAML` or
`typing_extensions` as their publishers do.
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

_WORD = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")
"""A word that could be a package name."""


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


def test_the_notices_name_every_locked_runtime_package() -> None:
    named = {normalized(word) for word in _WORD.findall(NOTICES.read_text(encoding="utf-8"))}

    assert sorted(locked_runtime_packages() - named) == []
