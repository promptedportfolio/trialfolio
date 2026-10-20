"""The JSON summary, which `--json` writes to stdout, on success and on failure (docs/contracts.md,
the JSON summary): built from the command's own fields and its outcome's, which `Invocation`
gathers.
"""

from typing import Final

from trialfolio.cli.arguments import CommandName
from trialfolio.contracts.common import ErrorDetail
from trialfolio.contracts.summary import (
    ExperimentCounts,
    JsonSummaryV1_2,
    NoCounts,
    ReviewCounts,
    RunCounts,
    SummaryCase,
    SummaryIdsV1_2,
)
from trialfolio.errors import TrialFolioError

SUMMARY_SCHEMA_VERSION: Final = "1.2.0"

type Counts = RunCounts | ReviewCounts | ExperimentCounts | NoCounts
"""The summary's `counts`, which each kind of command gives in its own form."""


def json_summary(
    command: CommandName,
    version: str,
    error: TrialFolioError | None,
    exit_code: int,
    *,
    ids: SummaryIdsV1_2,
    output_dir: str | None,
    outputs: dict[str, str],
    cases: tuple[SummaryCase, ...] | None,
    counts: Counts,
) -> JsonSummaryV1_2:
    """The JSON summary of `command`, which ended with `error`, or None, and `exit_code`. `cases`
    is given only for an experiment, once its plan is built."""
    outcome = (
        "completed"
        if error is None
        else "partial"
        if error.code == "execution.partial"
        else "failed"
    )
    return JsonSummaryV1_2.model_validate(
        {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "command": command,
            "trialfolio_version": version,
            "outcome": outcome,
            "exit_code": exit_code,
            "ids": ids,
            "output_dir": output_dir,
            "outputs": outputs,
            **({} if cases is None else {"cases": cases}),
            "counts": counts,
            "statistical_validation": "not_assessed",
            "trading_readiness": "not_assessed",
            "error": None if error is None else ErrorDetail(code=error.code, message=error.message),
        }
    )
