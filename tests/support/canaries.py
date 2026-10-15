"""The canaries (release 0.1.0, test pairing): distinct values that mustn't appear where a test
looks for them, and the scans that look.

- **The credentials and the token** the fake server issues belong in no output at all. `leaks`
  scans every file in the directories it's given, such as the output, configuration, and log
  directories, and stdout and stderr, for them.
- **The canary fixtures' values,** from `screen-configs/canaries.yaml`,
  `responses/canaries.json`, `review-configs/canaries.yaml`, and
  `experiment-configs/canaries.yaml`, belong in some outputs, such as
  `configuration.yaml`, `settings.csv`, the report, and the plan display. `logged` scans only log
  files for them, and stderr where a criterion says so.
- **A revision's reason and Portfolio123's message,** which a test gives as `--revision-reason`
  and in a 400's body, belong in some records, such as the revision's `experiment.json` and the
  attempt record, and never in a log file, which `logged` scans for them too (release 0.3.0,
  test pairing, canaries).

R01-T09 created the credential and token values; R01-T15 added the fixtures' values and the
scans, R02-T09 the review configuration's, R03-T13 the experiment configuration's, and R03-T11
the revision's reason and Portfolio123's message. Release 0.4.0's R04-T06 listed
`experiment-configs/ranking/canaries.xml`'s, which it wrote: R04-T13 adds them to the scans,
with its other canaries (release 0.4.0, test pairing, canaries). Each value is ASCII without
characters JSON escapes, so a scan of the bytes finds it however a file encodes it.
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

EXPERIMENT: Final = (
    "canary-experiment-1f2e3d4c",
    "canary-experiment-title-2c9f4e81",
    "canary-experiment-purpose-7b3d0a56",
    "canary-prior-research-e4a19c37",
    "canary-experiment-universe-9d4c2b17",
    "canary-experiment-rule-6e0f3a98",
    "canary-experiment-with-b72d5c41",
    "canary-experiment-formula-0c8e1f64",
    "canary-experiment-benchmark-4a7b9d20",
    "canary-key-5a66f676",
    "canary-variant-description-one-58c2f0b4",
    "canary-key-0d3b7e19",
    "canary-variant-description-two-a1e7d963",
    "canary-key-c84f2a65",
    "canary-variant-description-three-3f6b8e02",
)
"""Every canary in `experiment-configs/canaries.yaml`: the `experiment_id`, a canary-like slug;
the title, the purpose, and the prior-research description; the universe, the baseline's rule,
the formula a variant puts in its place, the ranking formula, and the benchmark; and each
variant's key, also a canary-like slug, and its description."""

RANKING_DEFINITION: Final = (
    "canary-node-one-86f2100d",
    "canary-node-two-d7ace873",
    "canary-node-three-83b2c3ff",
    "canary-node-four-5f2f6c75",
    "canary-node-five-817d6442",
    "canary-node-six-991acb71",
    "canary-node-seven-d426dda9",
    "canary-node-eight-bf8abb5d",
    "canary-node-nine-f9db236d",
    "canary-definition-formula-one-98286c85",
    "canary-definition-formula-two-3d5ce32f",
    "canary-definition-formula-three-f4e3a28e",
    "canary-definition-formula-four-bf57d868",
    "canary-definition-formula-five-1434d680",
    "canary-definition-formula-six-67e7e38c",
    "canary-description-one-1a6a175b",
    "canary-description-two-99cd4488",
    "canary-description-three-e4a0b8a2",
    "canary-description-four-11bc6d97",
    "canary-description-five-e54db84b",
    "canary-description-six-03e5a08a",
    "38.2917",
    "52.7381",
    "47.2619",
    "30.8541",
    "51.9046",
    "48.0954",
    "30.8542",
    "53.6172",
    "46.3828",
)
"""Every canary in `experiment-configs/ranking/canaries.xml`: each node's name, in the
definition's order; each `StockFormula`'s formula and `Description`; and each node's weight,
with distinctive digits. A definition is the user's strategy definition, which logs never hold
(release 0.4.0, R04-AC11)."""

REVISION_REASON: Final = "canary-revision-reason-5f024a69"
"""A revision's reason, given with `--revision-reason`: the user's text, which logs never hold
(docs/contracts.md, the experiment manifest)."""

PROVIDER_MESSAGE: Final = "canary-provider-message-6b7f758e"
"""Portfolio123's message in the body of a 400, which the attempt record's error message gives,
and a loggable message never does."""

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
    """Where a canary fixture's value, a revision's reason, Portfolio123's message, or one of
    `more`, appears in a log file under `roots`, and in `stderr` when it's given. Each finding
    names the file or stream and the canary."""
    canaries = (
        *CONFIGURATION,
        *RESPONSE,
        *REVIEW,
        *EXPERIMENT,
        REVISION_REASON,
        PROVIDER_MESSAGE,
        *more,
    )
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
