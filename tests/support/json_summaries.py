"""The checks every JSON summary gets: `summary_of` reads the one summary on stdout, and checks it
against the `JsonSummaryV1_2` model, the keys of the generated schema,
`schemas/json-summary-1.2.0.schema.json`, and the rules that tie its fields together, with each
command's counts (docs/contracts.md, JSON summary). `EXPERIMENT_COUNTS` are the counts of an
experiment's summary.

TS-T07 moved them here from tests/interface/test_json_summary.py, when it separated the experiment's
summaries into tests/interface/test_experiment_summary.py, which checks a screen run's summary with
them too (docs/test-refactoring.md, modules to separate).
"""

import json
from pathlib import Path

from tests.support.environment import Outcome
from trialfolio.contracts.summary import JsonSummaryV1_2
from trialfolio.errors import EXIT_CODES

SCHEMA = Path(__file__).resolve().parents[2] / "schemas" / "json-summary-1.2.0.schema.json"

RUN_COUNTS = {"attempts", "provider_requests", "metrics_unavailable", "warnings", "cost"}
EXPERIMENT_COUNTS = {
    "cases_planned",
    "cases_succeeded",
    "cases_failed",
    "cases_skipped",
    "cases_unknown",
    "cases_not_yet_run",
    "cases_retired",
    "attempts",
    "repeats",
    "provider_requests",
    "authentication_calls",
    "cost",
    "metrics_unavailable",
    "warnings",
}
REVIEW_COUNTS = {"results", "settings_flagged", "metrics_unavailable", "warnings"}


def summary_of(outcome: Outcome, command: str) -> dict[str, object]:
    """The one JSON summary on stdout, checked against the model, the schema's keys, and the
    rules that tie its fields together."""
    summary = outcome.summary
    # From its JSON text: in strict mode, only JSON input reads an ID's text as a UUID.
    JsonSummaryV1_2.model_validate_json(outcome.stdout)
    schema: dict[str, object] = json.loads(SCHEMA.read_bytes())
    required = schema["required"]
    properties = schema["properties"]
    assert isinstance(required, list)
    assert isinstance(properties, dict)
    assert set(summary) == set(required)  # pyright: ignore[reportUnknownArgumentType]
    assert set(summary) <= set(properties)  # pyright: ignore[reportUnknownArgumentType]
    assert summary["schema_version"] == "1.2.0"
    assert "cases" not in summary
    assert summary["command"] == command
    assert summary["exit_code"] == outcome.exit_code
    assert summary["statistical_validation"] == "not_assessed"
    assert summary["trading_readiness"] == "not_assessed"
    error = summary["error"]
    if error is None:
        assert (summary["outcome"], outcome.exit_code) == ("completed", 0)
    else:
        assert isinstance(error, dict)
        assert set(error) == {"code", "message"}  # pyright: ignore[reportUnknownArgumentType]
        assert summary["outcome"] == "failed"
        assert outcome.exit_code == EXIT_CODES[error["code"]]  # pyright: ignore[reportArgumentType]
        assert f"Error ({error['code']})" in outcome.stderr
    for group in ("ids", "outputs"):
        values = summary[group]
        assert isinstance(values, dict)
        assert None not in values.values()  # pyright: ignore[reportUnknownMemberType]
    output_dir = summary["output_dir"]
    outputs = summary["outputs"]
    assert isinstance(outputs, dict)
    if output_dir is None:
        assert outputs == {}
    else:
        assert isinstance(output_dir, str)
        for path in outputs.values():  # pyright: ignore[reportUnknownVariableType]
            assert isinstance(path, str)
            assert (Path(output_dir) / path).is_file()
    counts = summary["counts"]
    assert isinstance(counts, dict)
    if command in ("run", "demo"):
        assert set(counts) == RUN_COUNTS  # pyright: ignore[reportUnknownArgumentType]
    elif command == "review":
        assert set(counts) == REVIEW_COUNTS  # pyright: ignore[reportUnknownArgumentType]
    else:
        assert counts == {}
    return summary
