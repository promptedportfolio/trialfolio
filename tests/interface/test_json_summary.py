"""With `--json`, every command writes exactly one JSON summary to stdout, followed by a newline,
whether it succeeds or fails; without it, stdout holds only the result, and warnings and errors go
to stderr.

Traces to R01-AC18, over the scenarios of R01-AC01 (no approval), R01-AC05 (provider failures and
missing credentials), and R01-AC15 (an output directory that isn't empty), and for `report`,
`demo`, `license`, and `init` (R01-AC33); to R02-AC13, for `review`, over the scenarios of
R02-AC01 (a review that completes), R02-AC06 (an input that isn't a complete run, or doesn't
exist), R02-AC10 (an output directory that isn't empty), R02-AC11 (a configuration that isn't
valid), R02-AC14 (a schema version without a reader), and R02-AC19 (a storage failure and an
interrupt after the claim): a failure before the claim has no `review_id` and a `null`
`output_dir`, and one after it has both; and to docs/contracts.md, JSON summary: `ids` and
`outputs` leave out a key that has no value, `counts` is `{}` for `init`, `report`, and `license`,
and `outcome`, `exit_code`, and
`error` agree; and to R01-T14's rules that a blank `--out`, or one that isn't valid UTF-8 text,
which `output_dir` can't hold, is a usage error, and that an error message escapes a path it
names, so the summary can hold it. Each summary is checked against the `JsonSummaryV1_2` model and
the keys of the generated schema, `schemas/json-summary-1.2.0.schema.json`, and holds no `cases`,
which only an experiment's does. Through the CLI's entry function in the test process, with the
real client, `requests`, and `urllib3` over the fake server.

The summary's version moved from 1.0.0 to 1.1.0 with release 0.2.0, for every command, as its open
question on the summary's version settled (owner's sign-off, 2026-10-05; D-25): the committed 1.0.0
schema can't hold a review's summary, and keys are added only in a minor version. It moved to 1.2.0
with release 0.3.0, for every command, as that release's open question settled (owner's sign-off,
2026-10-08; D-33): the committed 1.1.0 schema can't hold an experiment's. Each earlier key keeps its
meaning, so these checks are otherwise 0.1.0's and 0.2.0's. R03-T06 moved them.
"""

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.interface.conftest import (
    Cli,
    FaultyStores,
    Outcome,
    config,
    occupied,
    plan_hash_for,
    serve_success,
)
from tests.support.fake_portfolio123 import Reply
from tests.support.run_builder import REVIEW_CONFIGS, SYNTHETIC_RUN
from trialfolio.contracts.summary import JsonSummaryV1_2
from trialfolio.errors import EXIT_CODES

SCHEMA = Path(__file__).resolve().parents[2] / "schemas" / "json-summary-1.2.0.schema.json"

RUN_COUNTS = {"attempts", "provider_requests", "metrics_unavailable", "warnings", "cost"}
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


def approved(cli: Cli, out: Path, *extra: str) -> Outcome:
    path = config("formula.yaml")
    return cli("run", path, "--out", out, "--approve", plan_hash_for(path), "--json", *extra)


# run


def test_a_run_that_succeeds(cli: Cli) -> None:
    cli.ready()
    serve_success(cli.server)
    out = cli.tmp / "out"

    summary = summary_of(approved(cli, out), "run")

    assert summary["outcome"] == "completed"
    assert summary["error"] is None
    assert summary["output_dir"] == str(out)
    ids = summary["ids"]
    assert isinstance(ids, dict)
    assert set(ids) == {"plan_hash", "case_id", "attempt_id"}  # pyright: ignore[reportUnknownArgumentType]
    assert ids["plan_hash"] == plan_hash_for(config("formula.yaml"))
    assert summary["outputs"] == {
        "manifest": "manifest.json",
        "report": "report.html",
        "metrics": "normalized/metrics.csv",
        "settings": "normalized/settings.csv",
    }
    assert summary["counts"] == {
        "attempts": 1,
        "provider_requests": 1,
        "metrics_unavailable": 0,
        "warnings": 0,
        "cost": 5,
    }


def test_a_run_without_approval_gives_the_plan_hash_and_creates_nothing(cli: Cli) -> None:
    cli.ready()
    out = cli.tmp / "out"

    outcome = cli("run", config("formula.yaml"), "--out", out, "--json")
    summary = summary_of(outcome, "run")

    assert outcome.exit_code == 2
    assert summary["error"]["code"] == "plan.approval_required"  # pyright: ignore[reportIndexIssue]
    ids = summary["ids"]
    assert isinstance(ids, dict)
    assert set(ids) == {"plan_hash", "case_id"}  # pyright: ignore[reportUnknownArgumentType]
    assert ids["plan_hash"] == plan_hash_for(config("formula.yaml"))
    assert str(ids["case_id"]).startswith("case-")
    assert summary["output_dir"] is None
    assert summary["counts"]["attempts"] == 0  # pyright: ignore[reportIndexIssue]
    assert summary["counts"]["provider_requests"] == 0  # pyright: ignore[reportIndexIssue]
    assert f"Plan hash: {ids['plan_hash']}" in outcome.stderr
    assert not out.exists()
    assert cli.server.requests() == []


def test_an_invalid_configuration(cli: Cli) -> None:
    cli.ready()
    out = cli.tmp / "out"

    outcome = cli("run", config("invalid/misspelled-key.yaml"), "--out", out, "--json")
    summary = summary_of(outcome, "run")

    assert outcome.exit_code == 3
    assert summary["error"]["code"] == "config.invalid"  # pyright: ignore[reportIndexIssue]
    assert summary["ids"] == {}
    assert summary["output_dir"] is None
    assert not out.exists()


def test_an_output_directory_that_isnt_empty(cli: Cli) -> None:
    cli.ready()
    out = cli.tmp / "out"
    out.mkdir()
    (out / "other.txt").write_text("someone else's\n", encoding="utf-8")

    outcome = approved(cli, out)
    summary = summary_of(outcome, "run")

    assert outcome.exit_code == 4
    assert summary["error"]["code"] == "output.not_empty"  # pyright: ignore[reportIndexIssue]
    assert summary["output_dir"] is None
    assert summary["outputs"] == {}
    assert [p.name for p in out.iterdir()] == ["other.txt"]


def test_missing_credentials(cli: Cli) -> None:
    cli.accept_license()
    out = cli.tmp / "out"

    outcome = approved(cli, out)
    summary = summary_of(outcome, "run")

    assert outcome.exit_code == 5
    assert summary["error"]["code"] == "provider.auth_failed"  # pyright: ignore[reportIndexIssue]
    ids = summary["ids"]
    assert isinstance(ids, dict)
    assert set(ids) == {"plan_hash", "case_id"}  # pyright: ignore[reportUnknownArgumentType]
    assert summary["output_dir"] is None
    assert not out.exists()
    assert cli.server.requests() == []


def test_a_failed_authentication_names_its_attempt(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", Reply(401, b"Unauthorized"))
    out = cli.tmp / "out"

    outcome = approved(cli, out)
    summary = summary_of(outcome, "run")

    assert outcome.exit_code == 5
    assert summary["error"]["code"] == "provider.auth_failed"  # pyright: ignore[reportIndexIssue]
    ids = summary["ids"]
    assert isinstance(ids, dict)
    assert set(ids) == {"plan_hash", "case_id", "attempt_id"}  # pyright: ignore[reportUnknownArgumentType]
    assert summary["output_dir"] == str(out)
    outputs = summary["outputs"]
    assert isinstance(outputs, dict)
    assert "metrics" not in outputs
    assert "settings" not in outputs
    assert summary["counts"]["attempts"] == 1  # pyright: ignore[reportIndexIssue]
    assert summary["counts"]["provider_requests"] == 0  # pyright: ignore[reportIndexIssue]
    assert summary["counts"]["cost"] is None  # pyright: ignore[reportIndexIssue]


def test_a_rejected_request_is_possibly_charged(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", Reply(200, b"token"))
    cli.server.reply("/screen/backtest", Reply(400, b"Unsupported value"))

    outcome = approved(cli, cli.tmp / "out")
    summary = summary_of(outcome, "run")

    assert outcome.exit_code == 5
    assert summary["error"]["code"] == "provider.unsupported_capability"  # pyright: ignore[reportIndexIssue]
    assert summary["counts"]["provider_requests"] == 1  # pyright: ignore[reportIndexIssue]


def test_a_warning_is_counted_and_goes_to_stderr(cli: Cli, monkeypatch: pytest.MonkeyPatch) -> None:
    cli.ready()
    monkeypatch.setenv("SSLKEYLOGFILE", str(cli.tmp / "keys.log"))

    outcome = cli("run", config("formula.yaml"), "--out", cli.tmp / "out", "--json")
    summary = summary_of(outcome, "run")

    assert summary["counts"]["warnings"] == 1  # pyright: ignore[reportIndexIssue]
    assert "Warning: SSLKEYLOGFILE" in outcome.stderr
    assert "SSLKEYLOGFILE" not in outcome.stdout


# demo, report, and license


def test_demo(cli: Cli) -> None:
    cli.accept_license()
    out = cli.tmp / "demo"

    summary = summary_of(cli("demo", "--out", out, "--json"), "demo")

    assert summary["outcome"] == "completed"
    assert summary["output_dir"] == str(out)
    ids = summary["ids"]
    assert isinstance(ids, dict)
    assert set(ids) == {"plan_hash", "case_id", "attempt_id"}  # pyright: ignore[reportUnknownArgumentType]
    assert set(summary["outputs"]) == {"manifest", "report", "metrics", "settings"}  # pyright: ignore[reportArgumentType]
    assert summary["counts"]["cost"] is None  # pyright: ignore[reportIndexIssue]
    assert cli.server.requests() == []


def test_report(cli: Cli) -> None:
    cli.accept_license()
    run = cli.tmp / "demo"
    assert cli("demo", "--out", run).exit_code == 0
    out = cli.tmp / "reports" / "demo"

    summary = summary_of(cli("report", run, "--out", out, "--json"), "report")

    assert summary["outcome"] == "completed"
    assert summary["ids"] == {}
    assert summary["output_dir"] == str(out)
    assert summary["outputs"] == {"report": "report.html"}
    assert summary["counts"] == {}


def test_report_of_something_that_isnt_a_run(cli: Cli) -> None:
    cli.accept_license()
    out = cli.tmp / "report"

    outcome = cli("report", cli.tmp / "missing", "--out", out, "--json")
    summary = summary_of(outcome, "report")

    assert outcome.exit_code == 3
    assert summary["error"]["code"] == "input.not_found"  # pyright: ignore[reportIndexIssue]
    assert summary["output_dir"] is None
    assert summary["counts"] == {}
    assert not out.exists()


def test_report_of_an_empty_directory_isnt_a_run(cli: Cli) -> None:
    cli.accept_license()
    (cli.tmp / "empty").mkdir()

    outcome = cli("report", cli.tmp / "empty", "--out", cli.tmp / "report", "--json")
    summary = summary_of(outcome, "report")

    assert outcome.exit_code == 3
    assert summary["error"]["code"] == "input.not_a_run"  # pyright: ignore[reportIndexIssue]


def test_init(cli: Cli) -> None:
    workspace = cli.tmp / "workspace"

    outcome = cli("init", workspace, "--json")
    summary = summary_of(outcome, "init")

    assert summary["outcome"] == "completed"
    assert summary["ids"] == {}
    assert summary["output_dir"] == str(workspace)
    assert summary["outputs"] == {"configuration": "screen.yaml"}
    assert summary["counts"] == {}


def test_init_into_a_directory_that_isnt_empty(cli: Cli) -> None:
    (cli.tmp / "notes.txt").write_bytes(b"mine")

    outcome = cli("init", cli.tmp, "--json")
    summary = summary_of(outcome, "init")

    assert summary["error"]["code"] == "output.not_empty"  # pyright: ignore[reportIndexIssue]
    assert summary["output_dir"] is None
    assert summary["outputs"] == {}


@pytest.mark.parametrize("accept", [False, True], ids=["status", "accept"])
def test_license(cli: Cli, accept: bool) -> None:
    outcome = cli("license", *(["--accept"] if accept else []), "--json")
    summary = summary_of(outcome, "license")

    assert summary["outcome"] == "completed"
    assert summary["ids"] == {}
    assert summary["output_dir"] is None
    assert summary["outputs"] == {}
    assert summary["counts"] == {}
    assert "License" not in outcome.stdout


# review


def review(cli: Cli, path: Path, out: Path, **options: object) -> dict[str, object]:
    """The summary of `trialfolio review` of the configuration at `path` into `out`."""
    cli.accept_license()
    outcome = cli(
        "review",
        path,
        "--out",
        out,
        "--json",
        **options,  # pyright: ignore[reportArgumentType]
    )
    return summary_of(outcome, "review")


def two_copies(cli: Cli, break_second: Callable[[Path], None] = lambda run: None) -> Path:
    """A review configuration of two copies of the committed run, the second broken by
    `break_second`."""
    directory = cli.tmp / "review-config"
    for label in ("first", "second"):
        shutil.copytree(SYNTHETIC_RUN, directory / "runs" / label)
    break_second(directory / "runs" / "second")
    path = directory / "review.yaml"
    path.write_text(
        "kind: review\nschema_version: 1.0.0\ntitle: Two copies\nbaseline: first\nresults:\n"
        "  - label: first\n    run: runs/first\n  - label: second\n    run: runs/second\n",
        encoding="utf-8",
    )
    return path


def newer_manifest(run: Path) -> None:
    manifest = json.loads((run / "manifest.json").read_bytes())
    manifest["schema_version"] = "1.1.0"
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_a_review_that_completes(cli: Cli, built: Callable[[str], Path]) -> None:
    out = cli.tmp / "review"

    summary = review(cli, built("example.yaml"), out)

    assert summary["outcome"] == "completed"
    assert summary["output_dir"] == str(out)
    manifest = json.loads((out / "manifest.json").read_bytes())
    assert summary["ids"] == {"review_id": manifest["review_id"]}
    assert summary["outputs"] == {
        "manifest": "manifest.json",
        "report": "report.html",
        "differences": "normalized/differences.csv",
    }
    assert summary["counts"] == {
        "results": 2,
        "settings_flagged": 0,
        "metrics_unavailable": 0,
        "warnings": 0,
    }
    assert cli.server.requests() == []


BEFORE_THE_CLAIM: dict[str, tuple[Callable[[Cli], Path], str, int]] = {
    "an input that isn't a run": (
        lambda cli: two_copies(cli, lambda run: (run / "manifest.json").unlink()),
        "input.not_a_run",
        2,
    ),
    "an input that doesn't exist": (
        lambda cli: two_copies(cli, shutil.rmtree),
        "input.not_found",
        2,
    ),
    "a schema version without a reader": (
        lambda cli: two_copies(cli, newer_manifest),
        "artifact.unknown_schema_version",
        2,
    ),
    "a configuration that isn't valid": (
        lambda cli: REVIEW_CONFIGS / "invalid" / "misspelled-key.yaml",
        "config.invalid",
        0,
    ),
}
"""Each failure before the claim: the configuration, the error code, and the results counted,
which a configuration that isn't valid names none of."""


@pytest.mark.parametrize(
    ("configure", "code", "results"), BEFORE_THE_CLAIM.values(), ids=BEFORE_THE_CLAIM.keys()
)
def test_a_review_that_fails_before_the_claim(
    cli: Cli, configure: Callable[[Cli], Path], code: str, results: int
) -> None:
    out = cli.tmp / "review"

    summary = review(cli, configure(cli), out)

    assert summary["error"]["code"] == code  # pyright: ignore[reportIndexIssue]
    assert summary["ids"] == {}
    assert summary["output_dir"] is None
    assert summary["counts"] == {
        "results": results,
        "settings_flagged": 0,
        "metrics_unavailable": 0,
        "warnings": 0,
    }
    assert not out.exists()


def test_a_review_into_an_output_directory_that_isnt_empty(
    cli: Cli, built: Callable[[str], Path]
) -> None:
    out = occupied(cli, "results.txt")

    summary = review(cli, built("example.yaml"), out)

    assert summary["error"]["code"] == "output.not_empty"  # pyright: ignore[reportIndexIssue]
    assert summary["ids"] == {}
    assert summary["output_dir"] is None


AFTER_THE_CLAIM: dict[str, tuple[Callable[[FaultyStores], None], str]] = {
    "a storage failure": (lambda faults: faults.fail_os("report.html"), "storage.write_failed"),
    "an interrupt": (
        lambda faults: faults.fail_before("report.html", KeyboardInterrupt()),
        "command.interrupted",
    ),
}
"""Each failure after the claim, at the report: how it fails, and the error code."""


@pytest.mark.parametrize(("fail", "code"), AFTER_THE_CLAIM.values(), ids=AFTER_THE_CLAIM.keys())
def test_a_review_that_fails_after_the_claim(
    cli: Cli,
    built: Callable[[str], Path],
    faults: FaultyStores,
    fail: Callable[[FaultyStores], None],
    code: str,
) -> None:
    fail(faults)
    out = cli.tmp / "review"

    summary = review(cli, built("example.yaml"), out, store_factory=faults)

    assert summary["error"]["code"] == code  # pyright: ignore[reportIndexIssue]
    assert summary["output_dir"] == str(out)
    ids = summary["ids"]
    assert isinstance(ids, dict)
    assert set(ids) == {"review_id"}  # pyright: ignore[reportUnknownArgumentType]
    assert summary["outputs"] == {"differences": "normalized/differences.csv"}
    assert not (out / "manifest.json").exists()


# Without --json


def test_without_json_stdout_holds_only_the_result(cli: Cli) -> None:
    cli.ready()
    serve_success(cli.server)
    out = cli.tmp / "out"
    path = config("formula.yaml")

    outcome = cli("run", path, "--out", out, "--approve", plan_hash_for(path))

    assert outcome.exit_code == 0, outcome.stderr
    lines = outcome.stdout.splitlines()
    assert lines[0] == f"Run completed: {out}"
    assert f"Report: {out / 'report.html'}" in lines
    assert not outcome.stdout.lstrip().startswith("{")
    assert "Plan hash:" in outcome.stderr
    assert "Error" not in outcome.stdout


def test_without_json_a_failure_writes_nothing_to_stdout(cli: Cli) -> None:
    cli.ready()

    outcome = cli("run", config("formula.yaml"), "--out", cli.tmp / "out")

    assert outcome.exit_code == 2
    assert outcome.stdout == ""
    assert "Error (plan.approval_required)" in outcome.stderr


def test_without_json_report_and_demo_write_their_result(cli: Cli) -> None:
    cli.accept_license()
    run = cli.tmp / "demo"
    out = cli.tmp / "report"

    demo = cli("demo", "--out", run)
    report = cli("report", run, "--out", out)

    assert demo.exit_code == 0
    assert demo.stdout.startswith(f"Synthetic example run written to {run}.")
    assert report.exit_code == 0
    assert report.stdout == f"Report written: {out / 'report.html'}\n"


@pytest.mark.parametrize("out", [" ", ""], ids=["whitespace", "empty"])
@pytest.mark.parametrize("command", ["run", "report", "demo", "review"])
def test_a_blank_output_directory_is_a_usage_error(
    cli: Cli, monkeypatch: pytest.MonkeyPatch, command: str, out: str
) -> None:
    # A blank path names no directory of its own, and the summary's `output_dir` can't hold it,
    # so the parser rejects it before anything runs.
    cli.ready()
    monkeypatch.chdir(cli.tmp)
    before = sorted(p.name for p in cli.tmp.iterdir())
    inputs = {
        "run": [str(config("formula.yaml"))],
        "report": [str(cli.tmp)],
        "demo": [],
        "review": [str(REVIEW_CONFIGS / "example.yaml")],
    }

    outcome = cli(command, *inputs[command], "--out", out, "--json")

    assert outcome.exit_code == 2
    assert outcome.stdout == ""
    assert "argument --out: it's blank, and must name the output directory" in outcome.stderr
    assert sorted(p.name for p in cli.tmp.iterdir()) == before


NOT_UTF8 = chr(0xDCFF)
"""How Python reads the byte 0xff in a name that isn't UTF-8 (PEP 383): a lone surrogate, which
JSON text can't hold."""

ESCAPED = "\\udcff"
"""How an error message shows it."""


@pytest.mark.parametrize("command", ["run", "report", "demo", "review"])
def test_an_output_directory_that_isnt_utf8_text_is_a_usage_error(
    cli: Cli, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    cli.ready()
    monkeypatch.chdir(cli.tmp)
    before = sorted(p.name for p in cli.tmp.iterdir())
    inputs = {
        "run": [str(config("formula.yaml"))],
        "report": [str(cli.tmp)],
        "demo": [],
        "review": [str(REVIEW_CONFIGS / "example.yaml")],
    }

    outcome = cli(command, *inputs[command], "--out", f"out-{NOT_UTF8}", "--json")

    assert outcome.exit_code == 2
    assert outcome.stdout == ""
    assert "argument --out: it isn't valid UTF-8 text" in outcome.stderr
    assert sorted(p.name for p in cli.tmp.iterdir()) == before


def test_a_configuration_path_that_isnt_utf8_text_is_escaped_in_the_error(cli: Cli) -> None:
    cli.accept_license()

    outcome = cli("run", cli.tmp / f"missing-{NOT_UTF8}.yaml", "--out", cli.tmp / "out", "--json")
    summary = summary_of(outcome, "run")

    assert outcome.exit_code == 3
    error = summary["error"]
    assert isinstance(error, dict)
    assert error["code"] == "input.not_found"
    assert f"missing-{ESCAPED}.yaml" in error["message"]  # pyright: ignore[reportOperatorIssue]
    assert not (cli.tmp / "out").exists()


def test_a_run_directory_path_that_isnt_utf8_text_is_escaped_in_the_error(cli: Cli) -> None:
    cli.accept_license()

    outcome = cli("report", cli.tmp / f"run-{NOT_UTF8}", "--out", cli.tmp / "report", "--json")
    summary = summary_of(outcome, "report")

    assert outcome.exit_code == 3
    error = summary["error"]
    assert isinstance(error, dict)
    assert error["code"] == "input.not_found"
    assert f"run-{ESCAPED}" in error["message"]  # pyright: ignore[reportOperatorIssue]
    assert not (cli.tmp / "report").exists()
