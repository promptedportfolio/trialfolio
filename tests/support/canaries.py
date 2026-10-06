"""The canaries (release 0.1.0, test pairing): distinct values that mustn't appear where a test
looks for them, and the scans that look.

- **The credentials and the token** the fake server issues belong in no output at all. `leaks`
  scans every file in the directories it's given, such as the output, configuration, and log
  directories, and stdout and stderr, for them.
- **The canary fixtures' values,** from `screen-configs/canaries.yaml`,
  `responses/canaries.json`, and `review-configs/canaries.yaml`, belong in some outputs, such as
  `configuration.yaml`, `settings.csv`, the report, and the plan display. `logged` scans only log
  files for them, and stderr where a criterion says so.

R01-T09 created the credential and token values; R01-T15 added the fixtures' values and the
scans, and R02-T09 the review configuration's. Each value is ASCII without characters JSON
escapes, so a scan of the bytes finds it however a file encodes it.
"""

from collections.abc import Iterable
from pathlib import Path
from typing import Final

API_ID: Final = "canary-api-id-5b1e9c"
API_KEY: Final = "canary-api-key-0f7d2a6e"
TOKEN: Final = "canary-token-93c4be71"
"""The bearer token the fake server issues for a successful authentication."""

SECRETS: Final = (API_ID, API_KEY, TOKEN)
"""The values that belong in no output."""

CONFIGURATION: Final = (
    "canary-title-5e1d0b7c",
    "canary-purpose-9a42f6e1",
    "canary-universe-3c8b2d40",
    "canary-rule-one-71f0a9d3",
    "canary-rule-two-0b6e4c52",
    "canary-formula-d29a1e87",
    "canary-benchmark-46c3f0b9",
)
"""Every value `screen-configs/canaries.yaml` gives a canary: the title, the purpose, the
universe, each of the two rules, the ranking formula, and the benchmark."""

RESPONSE: Final = (
    "canary-response-key-6a1f3c9e",
    "canary-response-chart-2b7e5d10",
    "87654.3219",
    "76543.2108",
)
"""Every canary in `responses/canaries.json`: a string in the extra key `canaryExtra`, a string
in `chart`, a number as `stats.port.total_return`, and a number as the newest period's `Ret%`."""

REVIEW: Final = (
    "canary-review-title-07df75ea",
    "canary-review-purpose-f861bb17",
    "canary-description-one-c7ef6dc9",
    "canary-description-two-17f855b8",
    "canary-description-three-db79e5ab",
    "canary-reason-one-afcbcf87",
    "canary-reason-two-33b9b50a",
    "canary-reason-three-9ab8d5c5",
    "canary-label-5a66f676",
    "canary-label-bec3da08",
    "canary-label-0aa24019",
    "canary-run-da943a28",
    "canary-run-bdcb5a6c",
    "canary-run-993a190a",
)
"""Every canary in `review-configs/canaries.yaml`: the title, the purpose, each result's
description, each reason, each label, and each `run` path's directory name, where the run
builder writes the result's run."""

LOG_FILE: Final = "trialfolio.log"
"""A log file's name, and with a number after it, a rotated one's."""


def leaks(roots: Iterable[Path], *, stdout: str, stderr: str) -> list[str]:
    """Where a credential or token canary appears: in a file under one of `roots`, hidden files
    included, or in stdout or stderr. Each finding names the file or stream and the canary."""
    found = [
        f"{path}: {canary}"
        for path in _files(roots)
        for canary in SECRETS
        if canary.encode() in path.read_bytes()
    ]
    for name, text in (("stdout", stdout), ("stderr", stderr)):
        found += [f"{name}: {canary}" for canary in SECRETS if canary in text]
    return found


def log_files(roots: Iterable[Path]) -> list[Path]:
    """Every log file under `roots`, rotated ones included, sorted."""
    return [path for path in _files(roots) if path.name.startswith(LOG_FILE)]


def logged(
    roots: Iterable[Path], *, stderr: str | None = None, more: Iterable[str] = ()
) -> list[str]:
    """Where a canary fixture's value, or one of `more`, appears in a log file under `roots`,
    and in `stderr` when it's given. Each finding names the file or stream and the canary."""
    canaries = (*CONFIGURATION, *RESPONSE, *REVIEW, *more)
    found = [
        f"{path}: {canary}"
        for path in log_files(roots)
        for canary in canaries
        if canary.encode() in path.read_bytes()
    ]
    if stderr is not None:
        found += [f"stderr: {canary}" for canary in canaries if canary in stderr]
    return found


def _files(roots: Iterable[Path]) -> list[Path]:
    return sorted({path for root in roots for path in root.rglob("*") if path.is_file()})
