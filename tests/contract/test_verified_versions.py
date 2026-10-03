"""The package pins `p123api`, `requests`, and `urllib3` exactly, to versions a release has
verified (docs/contracts.md, plan contents; ADR 0006).

Traces to R01-AC05 in release 0.1.0's test pairing: a clean install gets the versions Trial
Folio plans with, so `environment.unsupported` happens only in an environment changed by hand.
"""

import tomllib
from pathlib import Path

from trialfolio.planning import VERIFIED_VERSIONS

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_the_package_pins_each_provider_package_to_a_verified_version() -> None:
    dependencies: list[str] = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"][
        "dependencies"
    ]

    for name, verified in VERIFIED_VERSIONS.items():
        (pin,) = (entry for entry in dependencies if entry.startswith(name))
        assert pin.removeprefix(name).startswith("==")
        assert pin.removeprefix(f"{name}==") in verified
