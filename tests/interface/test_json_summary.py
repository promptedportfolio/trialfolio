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
and `outcome`, `exit_code`, and `error` agree; to R03-AC16, for `run` with an experiment's
configuration, over the scenarios of R03-AC01 (no approval), R03-AC05 (a case that fails, each
provider failure that leaves the run partial or stops it, and missing credentials), R03-AC07 (a
revision without its reason and its hash, an approved one, a reason with no revision, and another
experiment), R03-AC09 (the lock another holder holds, in this process or in a resume waiting at
its approval prompt in another, and a new experiment's claim), R03-AC14 (a case awaiting a repeat,
a confirmed repeat, its used confirmation, and a key alone for a complete case, a repeat whose
authentication fails or that's interrupted during its send, and each repeat that fails before
anything is sent), R03-AC17 (records that aren't complete), and R03-AC19 (a storage failure and
an interrupt, in a new experiment and in a resume, before and after the session record, and a
manifest whose write fails once it's published), and an invalid configuration: its `ids` name
the plan the core builds, its `cases` are that plan's, in order, with the outcomes and the
repeats' attempts the records give, its `counts` agree with the records and the session's
manifest, and its `output_dir` is given from a new experiment's claim, or a resume's session
record, and is `null` before; and to R01-T14's rules that a blank `--out`, or one that isn't
valid UTF-8 text, which `output_dir` can't hold, is a usage error, and that an error message
escapes a path it names, so the summary can hold it. Each summary is checked against the
`JsonSummaryV1_2` model and the keys of the generated schema,
`schemas/json-summary-1.2.0.schema.json`, and holds no `cases`, but an experiment's. Through the
CLI's entry function in the test process, with the real client, `requests`, and `urllib3` over
the fake server; the terminal is a real pseudo-terminal, in the test process or, for the resume
that holds the lock, in another process under the test launcher, and the socket faults interrupt
a repeat during its send, as Ctrl-C does.

The summary's version moved from 1.0.0 to 1.1.0 with release 0.2.0, for every command, as its open
question on the summary's version settled (owner's sign-off, 2026-10-05; D-25): the committed 1.0.0
schema can't hold a review's summary, and keys are added only in a minor version. It moved to 1.2.0
with release 0.3.0, for every command, as that release's open question settled (owner's sign-off,
2026-10-08; D-33): the committed 1.1.0 schema can't hold an experiment's. Each earlier key keeps its
meaning, so these checks are otherwise 0.1.0's and 0.2.0's. R03-T06 moved them, R03-T13 added
an experiment's, and R03-T11 the rest of R03-AC16's scenarios, and the check of the cases against
the records.
"""

import csv
import io
import json
import shutil
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple, cast

import pytest

from tests.support.cli import Cli, occupied, plan_hash_for
from tests.support.directories import snapshot
from tests.support.environment import Outcome
from tests.support.experiment_builder import (
    AUTHENTICATED,
    REFUSED,
    REJECTED,
    UNAVAILABLE,
    ExperimentBuilder,
    experiment_config,
    plan_hash,
    returns,
)
from tests.support.fake_portfolio123 import Reply, serve_success
from tests.support.paths import REVIEW_CONFIGS, screen_config
from tests.support.run_builder import SYNTHETIC_RUN
from tests.support.socket_faults import SocketFaults
from tests.support.storage_faults import FaultyStores
from tests.support.terminal import PseudoTerminal
from trialfolio.cli import API_KEY_VARIABLE
from trialfolio.configuration import read_experiment_configuration
from trialfolio.contracts.attempt import AttemptRecordV1_1, AuthenticationRecord, StartRecordV1_1
from trialfolio.contracts.experiment_manifest import ExperimentManifest
from trialfolio.contracts.experiment_plan import PlanV1_1
from trialfolio.contracts.summary import JsonSummaryV1_2
from trialfolio.errors import EXIT_CODES, ErrorCode, TrialFolioError
from trialfolio.experiment_records import read_experiment
from trialfolio.planning import build_experiment_plan, installed_versions, plan_revision
from trialfolio.storage import ArtifactStore, LocalArtifactStore, StoredFile

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


def approved(cli: Cli, out: Path, *extra: str) -> Outcome:
    path = screen_config("formula.yaml")
    return cli.run_approved(path, out, "--json", *extra)


# run


def test_a_run_that_succeeds(cli: Cli) -> None:
    cli.ready()
    serve_success(cli.server)
    out = cli.tmp / "out"

    outcome = approved(cli, out)
    summary = summary_of(outcome, "run")

    assert summary["outcome"] == "completed"
    assert summary["error"] is None
    assert summary["output_dir"] == str(out)
    ids = outcome.ids
    assert set(ids) == {"plan_hash", "case_id", "attempt_id"}
    assert ids["plan_hash"] == plan_hash_for(screen_config("formula.yaml"))
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

    outcome = cli("run", screen_config("formula.yaml"), "--out", out, "--json")
    summary = summary_of(outcome, "run")

    assert outcome.exit_code == 2
    assert outcome.error_code == "plan.approval_required"
    ids = outcome.ids
    assert set(ids) == {"plan_hash", "case_id"}
    assert ids["plan_hash"] == plan_hash_for(screen_config("formula.yaml"))
    assert str(ids["case_id"]).startswith("case-")
    assert summary["output_dir"] is None
    assert outcome.counts["attempts"] == 0
    assert outcome.counts["provider_requests"] == 0
    assert f"Plan hash: {ids['plan_hash']}" in outcome.stderr
    assert not out.exists()
    assert cli.server.requests() == []


def test_an_invalid_configuration(cli: Cli) -> None:
    cli.ready()
    out = cli.tmp / "out"

    outcome = cli("run", screen_config("invalid/misspelled-key.yaml"), "--out", out, "--json")
    summary = summary_of(outcome, "run")

    assert outcome.exit_code == 3
    assert outcome.error_code == "config.invalid"
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
    assert outcome.error_code == "output.not_empty"
    assert summary["output_dir"] is None
    assert summary["outputs"] == {}
    assert [p.name for p in out.iterdir()] == ["other.txt"]


def test_missing_credentials(cli: Cli) -> None:
    cli.accept_license()
    out = cli.tmp / "out"

    outcome = approved(cli, out)
    summary = summary_of(outcome, "run")

    assert outcome.exit_code == 5
    assert outcome.error_code == "provider.auth_failed"
    ids = outcome.ids
    assert set(ids) == {"plan_hash", "case_id"}
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
    assert outcome.error_code == "provider.auth_failed"
    ids = outcome.ids
    assert set(ids) == {"plan_hash", "case_id", "attempt_id"}
    assert summary["output_dir"] == str(out)
    outputs = outcome.outputs
    assert "metrics" not in outputs
    assert "settings" not in outputs
    assert outcome.counts["attempts"] == 1
    assert outcome.counts["provider_requests"] == 0
    assert outcome.counts["cost"] is None


def test_a_rejected_request_is_possibly_charged(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", Reply(200, b"token"))
    cli.server.reply("/screen/backtest", Reply(400, b"Unsupported value"))

    outcome = approved(cli, cli.tmp / "out")
    summary_of(outcome, "run")

    assert outcome.exit_code == 5
    assert outcome.error_code == "provider.unsupported_capability"
    assert outcome.counts["provider_requests"] == 1


def test_a_warning_is_counted_and_goes_to_stderr(cli: Cli, monkeypatch: pytest.MonkeyPatch) -> None:
    cli.ready()
    monkeypatch.setenv("SSLKEYLOGFILE", str(cli.tmp / "keys.log"))

    outcome = cli("run", screen_config("formula.yaml"), "--out", cli.tmp / "out", "--json")
    summary_of(outcome, "run")

    assert outcome.counts["warnings"] == 1
    assert "Warning: SSLKEYLOGFILE" in outcome.stderr
    assert "SSLKEYLOGFILE" not in outcome.stdout


# demo, report, and license


def test_demo(cli: Cli) -> None:
    cli.accept_license()
    out = cli.tmp / "demo"

    outcome = cli("demo", "--out", out, "--json")
    summary = summary_of(outcome, "demo")

    assert summary["outcome"] == "completed"
    assert summary["output_dir"] == str(out)
    ids = outcome.ids
    assert set(ids) == {"plan_hash", "case_id", "attempt_id"}
    assert set(outcome.outputs) == {"manifest", "report", "metrics", "settings"}
    assert outcome.counts["cost"] is None
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
    assert outcome.error_code == "input.not_found"
    assert summary["output_dir"] is None
    assert summary["counts"] == {}
    assert not out.exists()


def test_report_of_an_empty_directory_isnt_a_run(cli: Cli) -> None:
    cli.accept_license()
    (cli.tmp / "empty").mkdir()

    outcome = cli("report", cli.tmp / "empty", "--out", cli.tmp / "report", "--json")
    summary_of(outcome, "report")

    assert outcome.exit_code == 3
    assert outcome.error_code == "input.not_a_run"


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

    assert outcome.error_code == "output.not_empty"
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


def review(
    cli: Cli,
    path: Path,
    out: Path,
    store_factory: Callable[[str], ArtifactStore] = LocalArtifactStore,
) -> Outcome:
    """`trialfolio review` of the configuration at `path` into `out`, whose summary is checked
    as `summary_of` checks one."""
    cli.accept_license()
    outcome = cli("review", path, "--out", out, "--json", store_factory=store_factory)
    summary_of(outcome, "review")
    return outcome


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
    # Not 1.1.0, which a review reads in a run manifest, from release 0.4.0's R04-T11.
    manifest["schema_version"] = "9.9.9"
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_a_review_that_completes(cli: Cli, built: Callable[[str], Path]) -> None:
    out = cli.tmp / "review"

    outcome = review(cli, built("example.yaml"), out)
    summary = outcome.summary

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

    outcome = review(cli, configure(cli), out)
    summary = outcome.summary

    assert outcome.error_code == code
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

    outcome = review(cli, built("example.yaml"), out)
    summary = outcome.summary

    assert outcome.error_code == "output.not_empty"
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

    outcome = review(cli, built("example.yaml"), out, store_factory=faults)
    summary = outcome.summary

    assert outcome.error_code == code
    assert summary["output_dir"] == str(out)
    ids = outcome.ids
    assert set(ids) == {"review_id"}
    assert summary["outputs"] == {"differences": "normalized/differences.csv"}
    assert not (out / "manifest.json").exists()


# Without --json


def test_without_json_stdout_holds_only_the_result(cli: Cli) -> None:
    cli.ready()
    serve_success(cli.server)
    out = cli.tmp / "out"
    path = screen_config("formula.yaml")

    outcome = cli.run_approved(path, out)

    assert outcome.exit_code == 0, outcome.stderr
    lines = outcome.stdout.splitlines()
    assert lines[0] == f"Run completed: {out}"
    assert f"Report: {out / 'report.html'}" in lines
    assert not outcome.stdout.lstrip().startswith("{")
    assert "Plan hash:" in outcome.stderr
    assert "Error" not in outcome.stdout


def test_without_json_a_failure_writes_nothing_to_stdout(cli: Cli) -> None:
    cli.ready()

    outcome = cli("run", screen_config("formula.yaml"), "--out", cli.tmp / "out")

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
        "run": [str(screen_config("formula.yaml"))],
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
        "run": [str(screen_config("formula.yaml"))],
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
    summary_of(outcome, "run")

    assert outcome.exit_code == 3
    error = outcome.error
    assert error["code"] == "input.not_found"
    assert f"missing-{ESCAPED}.yaml" in error["message"]
    assert not (cli.tmp / "out").exists()


def test_a_run_directory_path_that_isnt_utf8_text_is_escaped_in_the_error(cli: Cli) -> None:
    cli.accept_license()

    outcome = cli("report", cli.tmp / f"run-{NOT_UTF8}", "--out", cli.tmp / "report", "--json")
    summary_of(outcome, "report")

    assert outcome.exit_code == 3
    error = outcome.error
    assert error["code"] == "input.not_found"
    assert f"run-{ESCAPED}" in error["message"]
    assert not (cli.tmp / "report").exists()


# An experiment (R03-AC16)

EXAMPLE = experiment_config("example.yaml")

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Windows has no pseudo-terminals")


def experiment_summary_of(outcome: Outcome) -> dict[str, object]:
    """The one JSON summary of `run` with an experiment's configuration, checked as `summary_of`
    checks one, with an experiment's keys. Once the session's manifest is written, its `ids` and
    `counts` are the manifest's, and `metrics_unavailable` is the `unavailable` rows of the
    planned cases' tables."""
    summary = outcome.summary
    JsonSummaryV1_2.model_validate_json(outcome.stdout)
    schema: dict[str, object] = json.loads(SCHEMA.read_bytes())
    required = cast("list[str]", schema["required"])
    properties = cast("dict[str, object]", schema["properties"])
    assert set(summary) - {"cases"} == set(required)
    assert set(summary) <= set(properties)
    assert (summary["schema_version"], summary["command"]) == ("1.2.0", "run")
    assert summary["exit_code"] == outcome.exit_code
    error = cast("dict[str, str] | None", summary["error"])
    if error is None:
        assert (summary["outcome"], outcome.exit_code) == ("completed", 0)
    else:
        assert outcome.exit_code == EXIT_CODES[error["code"]]  # pyright: ignore[reportArgumentType]
        assert f"Error ({error['code']})" in outcome.stderr
    ids = cast("dict[str, object]", summary["ids"])
    assert set(ids) <= {"experiment_id", "plan_hash", "session"}
    assert ("plan_hash" in ids) == ("cases" in summary)
    outputs = cast("dict[str, str]", summary["outputs"])
    assert set(outputs) <= {"manifest", "report"}
    output_dir = summary["output_dir"]
    if output_dir is None:
        assert outputs == {}
        assert "session" not in ids
    for path in outputs.values():
        assert (Path(cast("str", output_dir)) / path).is_file()
    counts = cast("dict[str, int | None]", summary["counts"])
    assert counts == {} or set(counts) == EXPERIMENT_COUNTS
    if "manifest" in outputs:
        out = Path(cast("str", output_dir))
        manifest = ExperimentManifest.model_validate_json((out / outputs["manifest"]).read_bytes())
        assert ids == {
            "experiment_id": manifest.experiment_id,
            "plan_hash": manifest.plan_hash,
            "session": manifest.session,
        }
        assert outputs == {
            "manifest": f"sessions/{manifest.session}/manifest.json",
            "report": f"sessions/{manifest.session}/report.html",
        }
        assert without_warnings(counts) == recorded_counts(manifest, out, summary)
    return summary


def without_warnings(counts: dict[str, int | None]) -> dict[str, int | None]:
    """A summary's counts, but `warnings`, which are this command's."""
    return {name: value for name, value in counts.items() if name != "warnings"}


def recorded_counts(
    manifest: ExperimentManifest, out: Path, summary: dict[str, object]
) -> dict[str, int | None]:
    """The counts, but `warnings`, that `manifest` records, with `metrics_unavailable` the
    `unavailable` rows of the summary's cases' `metrics.csv` files."""
    recorded = manifest.counts
    attempts = recorded.attempts
    return {
        "cases_planned": recorded.cases.planned,
        "cases_succeeded": recorded.cases.succeeded,
        "cases_failed": recorded.cases.failed,
        "cases_skipped": recorded.cases.skipped,
        "cases_unknown": recorded.cases.unknown,
        "cases_not_yet_run": recorded.cases.not_yet_run,
        "cases_retired": recorded.retired_cases,
        "attempts": attempts.succeeded + attempts.failed + attempts.unknown + attempts.running,
        "repeats": attempts.repeats,
        "provider_requests": recorded.provider_requests,
        "authentication_calls": recorded.authentication_calls,
        "cost": recorded.cost,
        "metrics_unavailable": unavailable_rows(out, summary),
    }


def unavailable_rows(out: Path, summary: dict[str, object]) -> int:
    """The `unavailable` rows of the summary's cases' `metrics.csv` files."""
    rows = 0
    for case in cast("list[dict[str, str]]", summary["cases"]):
        metrics = out / "cases" / case["case_id"] / "normalized" / "metrics.csv"
        if metrics.is_file():
            reader = csv.DictReader(io.StringIO(metrics.read_text(encoding="utf-8")))
            rows += sum(row["availability"] == "unavailable" for row in reader)
    return rows


def case_outcomes(summary: dict[str, object]) -> list[tuple[str, str]]:
    return [
        (case["case_key"], case["outcome"])
        for case in cast("list[dict[str, str]]", summary["cases"])
    ]


def built_plan(config: Path, out: Path) -> PlanV1_1:
    """The plan `trialfolio run` builds from `config` into `out`, with the installed versions,
    as the core builds it: a new experiment's, until `out` holds the first plan's
    `experiment.json`, and then the current plan, or its revision."""
    configuration = read_experiment_configuration(config.read_bytes(), str(config))
    versions = installed_versions()
    if not (out / "plans/1/experiment.json").is_file():
        return build_experiment_plan(configuration, versions)
    saved = read_experiment(LocalArtifactStore(out))
    revision = plan_revision(configuration, versions, saved.plan)
    return saved.plan if revision is None else revision.plan


class Attempt(NamedTuple):
    """An attempt as its records give it, ordered by session and then sequence."""

    session: int
    sequence: int
    outcome: str
    possibly_charged: bool
    attempt_id: str
    repeat_of: str | None


def recorded_attempts(out: Path, case_id: str) -> list[Attempt]:
    """The case's attempts, by session and then sequence: each attempt record's; an attempt with
    a start record and no attempt record is running, so `unknown` and possibly charged; and one
    with only an authentication record sent nothing, so it's `failed`."""
    attempts: list[Attempt] = []
    for attempt in sorted(out.glob(f"cases/{case_id}/attempts/*")):
        if (attempt / "attempt.json").is_file():
            record = AttemptRecordV1_1.model_validate_json((attempt / "attempt.json").read_bytes())
            outcome, charged = record.outcome, record.possibly_charged
        elif (attempt / "started.json").is_file():
            record = StartRecordV1_1.model_validate_json((attempt / "started.json").read_bytes())
            outcome, charged = "unknown", True
        else:
            record = AuthenticationRecord.model_validate_json(
                (attempt / "authenticating.json").read_bytes()
            )
            outcome, charged = "failed", False
        repeat_of = None if record.repeat_of is None else str(record.repeat_of)
        attempts.append(
            Attempt(record.session, record.sequence, outcome, charged, attempt.name, repeat_of)
        )
    return sorted(attempts)


def recorded_cases(plan: PlanV1_1, out: Path) -> list[dict[str, str | None]]:
    """Each case of `plan`, in its order, with its outcome as the experiment manifest counts it
    from the records in `out`, and the attempt that confirms its repeat (docs/contracts.md, the
    experiment manifest, and repeating a case): `succeeded` once an attempt succeeded; otherwise
    the outcome of its latest possibly charged attempt, whose `attempt_id` confirms the repeat;
    `failed` when it has attempts and none is possibly charged, since it's due; and `not_yet_run`
    without one. No response these tests send fails validation."""
    cases: list[dict[str, str | None]] = []
    for case in plan.cases:
        attempts = recorded_attempts(out, case.case_id)
        charged = [attempt for attempt in attempts if attempt.possibly_charged]
        outcome, repeat = "not_yet_run", None
        if any(attempt.outcome == "succeeded" for attempt in attempts):
            outcome = "succeeded"
        elif charged:
            outcome, repeat = charged[-1].outcome, charged[-1].attempt_id
        elif attempts:
            outcome = "failed"
        cases.append(
            {
                "case_key": case.case_key,
                "case_id": case.case_id,
                "outcome": outcome,
                "repeat_attempt_id": repeat,
            }
        )
    return cases


def assert_recorded(summary: dict[str, object], config: Path, out: Path) -> None:
    """The summary's `ids` name the experiment and the plan the run built, from `config` into
    `out`; its `cases` are that plan's, in order, with the outcomes and the repeats' attempts the
    records give; and its counts, when it gives them, tally those outcomes, and every attempt of
    the experiment, and its repeats, in the records."""
    plan = built_plan(config, out)
    ids = cast("dict[str, object]", summary["ids"])
    assert (ids["experiment_id"], ids["plan_hash"]) == (plan.experiment_id, plan.plan_hash)
    cases = recorded_cases(plan, out)
    assert summary["cases"] == cases
    counts = cast("dict[str, int | None]", summary["counts"])
    if counts == {}:
        return
    outcomes = [case["outcome"] for case in cases]
    assert {name: counts[name] for name in CASE_COUNTS} == {
        "cases_planned": len(outcomes),
        "cases_succeeded": outcomes.count("succeeded"),
        "cases_failed": outcomes.count("failed"),
        "cases_skipped": 0,
        "cases_unknown": outcomes.count("unknown"),
        "cases_not_yet_run": outcomes.count("not_yet_run"),
    }
    attempts = [
        attempt for case in out.glob("cases/*") for attempt in recorded_attempts(out, case.name)
    ]
    repeats = [attempt for attempt in attempts if attempt.repeat_of is not None]
    assert (counts["attempts"], counts["repeats"]) == (len(attempts), len(repeats))


CASE_COUNTS = (
    "cases_planned",
    "cases_succeeded",
    "cases_failed",
    "cases_skipped",
    "cases_unknown",
    "cases_not_yet_run",
)


def test_an_experiment_that_completes(cli: Cli, experiments: ExperimentBuilder[Outcome]) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = experiments.run(
        EXAMPLE, out, sends=[returns("missing-metrics.json"), *[returns()] * 4]
    )
    summary = experiment_summary_of(outcome)

    assert summary["outcome"] == "completed"
    assert summary["output_dir"] == str(out)
    assert all(outcome == "succeeded" for _, outcome in case_outcomes(summary))
    assert_recorded(summary, EXAMPLE, out)
    counts = outcome.counts
    assert (counts["cases_succeeded"], counts["attempts"], counts["provider_requests"]) == (5, 5, 5)
    assert counts["authentication_calls"] == 1
    assert (counts["metrics_unavailable"] or 0) > 0


def test_an_experiment_with_a_failed_case_ends_partial_and_gives_its_repeat(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    summary = experiment_summary_of(
        experiments.run(EXAMPLE, out, sends=[returns(), returns(), REJECTED, returns(), returns()])
    )

    assert summary["outcome"] == "partial"
    cases = cast("list[dict[str, str | None]]", summary["cases"])
    (failed,) = [case for case in cases if case["outcome"] != "succeeded"]
    assert (failed["case_key"], failed["outcome"]) == ("holdings-50", "failed")
    (attempt,) = (out / "cases" / cast("str", failed["case_id"]) / "attempts").iterdir()
    record = AttemptRecordV1_1.model_validate_json((attempt / "attempt.json").read_bytes())
    assert record.possibly_charged
    assert failed["repeat_attempt_id"] == str(record.attempt_id)
    assert all(case["repeat_attempt_id"] is None for case in cases if case is not failed)
    assert_recorded(summary, EXAMPLE, out)


def test_an_experiment_without_approval_or_credentials(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    unapproved = cli("run", EXAMPLE, "--out", out, "--json")
    monkeypatch.delenv(API_KEY_VARIABLE)
    approved = cli("run", EXAMPLE, "--out", out, "--approve", plan_hash(EXAMPLE, out), "--json")

    for ran, code in (
        (unapproved, "plan.approval_required"),
        (approved, "provider.auth_failed"),
    ):
        summary = experiment_summary_of(ran)
        assert ran.error_code == code
        assert set(ran.ids) == {"experiment_id", "plan_hash"}
        assert summary["output_dir"] is None
        assert all(outcome == "not_yet_run" for _, outcome in case_outcomes(summary))
        # Every case of the plan the core builds, in its order, with its case_id.
        assert_recorded(summary, EXAMPLE, out)
        counts = ran.counts
        assert (counts["cases_planned"], counts["cases_not_yet_run"], counts["attempts"]) == (
            5,
            5,
            0,
        )
    assert not out.exists()


def test_an_invalid_experiment_configuration_gives_a_runs_counts(cli: Cli) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = cli("run", experiment_config("invalid/misspelled-key.yaml"), "--out", out, "--json")
    summary = summary_of(outcome, "run")

    assert outcome.error_code == "config.invalid"
    assert summary["ids"] == {}


def test_a_resume_that_stops_before_its_session_gives_the_records_counts_and_repeats(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    # R03-T13's review: before its session, a resume's cases and counts come from the records,
    # which no other summary check compared with them.
    cli.ready()
    out = cli.tmp / "experiment"
    first = experiment_summary_of(
        experiments.run(
            EXAMPLE,
            out,
            sends=[returns("missing-metrics.json"), returns(), UNAVAILABLE, returns(), returns()],
        )
    )
    unknown = cast("list[dict[str, str]]", first["cases"])[2]
    assert (unknown["case_key"], unknown["outcome"]) == ("holdings-50", "unknown")
    option = f"holdings-50:{unknown['repeat_attempt_id']}"
    # The repeat's request gets a 503 too: it's unknown, and awaits a repeat of its own.
    repeated = experiment_summary_of(
        experiments.run(EXAMPLE, out, "--repeat", option, sends=[UNAVAILABLE])
    )
    repeat = cast("list[dict[str, str]]", repeated["cases"])[2]["repeat_attempt_id"]
    assert repeat != unknown["repeat_attempt_id"]

    outcome = experiments.run(EXAMPLE, out, approve=False)
    summary = experiment_summary_of(outcome)

    assert outcome.error_code == "plan.approval_required"
    assert summary["output_dir"] is None
    counts = outcome.counts
    recorded = ExperimentManifest.model_validate_json(
        (out / "sessions/2/manifest.json").read_bytes()
    )
    assert without_warnings(counts) == recorded_counts(recorded, out, summary)
    assert (counts["repeats"], counts["provider_requests"], counts["authentication_calls"]) == (
        1,
        6,
        2,
    )
    assert (counts["cost"] or 0) > 0
    assert (counts["metrics_unavailable"] or 0) > 0
    # The outcomes the records give, and the repeat's attempt confirms the next repeat.
    assert summary["cases"] == repeated["cases"]
    cases = cast("list[dict[str, str | None]]", summary["cases"])
    assert [case["repeat_attempt_id"] for case in cases] == [None, None, repeat, None, None]


REVISION_REASON = "Tries 40 holdings instead of 50."


@pytest.mark.parametrize(
    "given",
    [
        pytest.param("neither", id="no-reason-or-approve"),
        pytest.param("reason", id="reason-alone"),
        pytest.param("approve", id="approve-alone"),
        pytest.param("current-hash", id="reason-and-the-current-plans-hash"),
    ],
)
def test_an_experiment_whose_revision_isnt_approved_gives_the_revisions_cases(
    cli: Cli, experiments: ExperimentBuilder[Outcome], given: str
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    assert experiments.run(EXAMPLE, out, sends=[returns()] * 5).exit_code == 0
    changed = experiment_config("revisions/holdings-40.yaml")
    options = {
        "neither": [],
        "reason": ["--revision-reason", REVISION_REASON],
        "approve": ["--approve", plan_hash(changed, out)],
        "current-hash": [
            "--revision-reason",
            REVISION_REASON,
            "--approve",
            plan_hash(EXAMPLE, out),
        ],
    }[given]
    before = snapshot(out)

    outcome = experiments.run(changed, out, *options, approve=False)
    summary = experiment_summary_of(outcome)

    assert outcome.error_code == "plan.changed"
    assert outcome.ids["plan_hash"] == plan_hash(changed, out)
    assert summary["output_dir"] is None
    assert snapshot(out) == before
    # The revision's cases: its kept cases with their outcomes, and its new one not yet run.
    assert_recorded(summary, changed, out)
    assert ("holdings-50", "not_yet_run") in case_outcomes(summary)
    counts = outcome.counts
    assert (counts["cases_retired"], counts["cases_succeeded"], counts["attempts"]) == (1, 4, 5)


@pytest.mark.parametrize("name", ["other-experiment-id.yaml", "other-universe.yaml"])
def test_another_experiment_in_the_output_directory_has_no_counts(
    cli: Cli, experiments: ExperimentBuilder[Outcome], name: str
) -> None:
    # R03-T13's review: the summary gave the configuration's experiment_id with the counts of
    # the experiment in the directory, which isn't the configuration's.
    cli.ready()
    out = cli.tmp / "experiment"
    assert experiments.run(EXAMPLE, out, sends=[returns()] * 5).exit_code == 0
    other = experiment_config(f"revisions/{name}")

    outcome = experiments.run(other, out, approve=False)
    summary = experiment_summary_of(outcome)

    assert outcome.error_code == "output.not_empty"
    assert "cases" not in summary
    assert (summary["counts"], summary["output_dir"]) == ({}, None)


@pytest.mark.parametrize("hold", ["lock", "break"])
def test_an_experiment_whose_records_cant_be_read_has_no_counts(
    cli: Cli, experiments: ExperimentBuilder[Outcome], hold: str
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    assert experiments.run(EXAMPLE, out, sends=[returns()] * 5).exit_code == 0
    holder = LocalArtifactStore(out)
    if hold == "lock":
        holder.lock("experiment.lock")
    else:
        (out / "sessions/1/report.html").unlink()
    try:
        outcome = experiments.run(EXAMPLE, out, approve=False)
        summary = experiment_summary_of(outcome)
    finally:
        holder.close()

    code = "experiment.locked" if hold == "lock" else "input.not_a_run"
    assert outcome.error_code == code
    assert summary["ids"] == {"experiment_id": "earnyield-sensitivity"}
    assert "cases" not in summary
    assert (summary["counts"], summary["output_dir"]) == ({}, None)


@pytest.mark.parametrize(
    ("fail", "code"),
    [
        pytest.param(
            lambda faults: faults.fail_os("attempt.json"), "storage.write_failed", id="storage"
        ),
        pytest.param(
            lambda faults: faults.fail_before("attempt.json", KeyboardInterrupt()),
            "command.interrupted",
            id="interrupt",
        ),
    ],
)
def test_an_experiment_that_stops_without_its_manifest(
    cli: Cli,
    experiments: ExperimentBuilder[Outcome],
    faults: FaultyStores,
    fail: Callable[[FaultyStores], None],
    code: str,
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # At the first case's attempt record, once its request was sent: it reads as running.
    fail(faults)

    outcome = experiments.run(EXAMPLE, out, sends=[returns()] * 5, store_factory=faults)
    summary = experiment_summary_of(outcome)

    assert outcome.error_code == code
    assert summary["output_dir"] == str(out)
    assert outcome.ids["session"] == 1
    assert summary["outputs"] == {}
    counts = outcome.counts
    on_disk = len(list(out.glob("cases/*/attempts/*/started.json")))
    assert (counts["attempts"], counts["provider_requests"]) == (on_disk, on_disk)


@pytest.mark.parametrize(
    ("fail", "code"),
    [
        pytest.param(
            lambda faults: faults.fail_os("settings.csv"), "storage.write_failed", id="storage"
        ),
        pytest.param(
            lambda faults: faults.fail_after("metrics.csv", KeyboardInterrupt()),
            "command.interrupted",
            id="interrupt",
        ),
    ],
)
def test_a_metrics_table_written_without_its_settings_table_is_counted(
    cli: Cli,
    experiments: ExperimentBuilder[Outcome],
    faults: FaultyStores,
    fail: Callable[[FaultyStores], None],
    code: str,
) -> None:
    # R03-T13's review: the summary counted only a case's pair of tables, so a failure between
    # them left the saved metrics.csv's unavailable rows out.
    cli.ready()
    out = cli.tmp / "experiment"
    fail(faults)

    outcome = experiments.run(
        EXAMPLE,
        out,
        sends=[returns("missing-metrics.json"), *[returns()] * 4],
        store_factory=faults,
    )
    summary = experiment_summary_of(outcome)

    assert outcome.error_code == code
    assert list(out.glob("cases/*/normalized/settings.csv")) == []
    counts = outcome.counts
    assert counts["metrics_unavailable"] == unavailable_rows(out, summary) > 0


def sync_failure() -> TrialFolioError:
    """A storage failure after the store published the file, as when the directory's sync
    fails."""
    return TrialFolioError("storage.write_failed", "Couldn't sync the directory.")


def test_an_attempt_record_published_before_its_write_failed_is_read_as_written(
    cli: Cli, experiments: ExperimentBuilder[Outcome], faults: FaultyStores
) -> None:
    # R03-T13's review: the summary read the first case's attempt as running, so unknown,
    # awaiting a repeat, and without its cost, though its published record says it succeeded,
    # and the repeat the summary gave then failed with plan.approval_required.
    cli.ready()
    out = cli.tmp / "experiment"
    faults.fail_after("attempt.json", sync_failure())

    outcome = experiments.run(EXAMPLE, out, sends=[returns()] * 5, store_factory=faults)
    summary = experiment_summary_of(outcome)

    assert outcome.error_code == "storage.write_failed"
    (path,) = out.glob("cases/*/attempts/*/attempt.json")
    record = AttemptRecordV1_1.model_validate_json(path.read_bytes())
    assert record.outcome == "succeeded"
    first = cast("list[dict[str, str | None]]", summary["cases"])[0]
    assert (first["case_id"], first["outcome"], first["repeat_attempt_id"]) == (
        record.case_id,
        "succeeded",
        None,
    )
    counts = outcome.counts
    assert (counts["cases_succeeded"], counts["cases_unknown"], counts["cost"]) == (
        1,
        0,
        record.provider_metadata.cost,
    )
    # A resume reads the records the same way.
    resumed = experiments.run(EXAMPLE, out, approve=False)
    assert experiment_summary_of(resumed)["cases"] == summary["cases"]
    assert without_warnings(resumed.counts) == without_warnings(counts)


def test_an_attempt_record_a_resume_published_before_its_write_failed_is_counted(
    cli: Cli,
    experiments: ExperimentBuilder[Outcome],
    faults: FaultyStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # R03-T13's review: the first run leaves the first case's attempt running, with its response
    # saved. The resume's step 8 publishes its attempt record, and then the write fails. The
    # summary left the record's cost out, though the records hold it.
    cli.ready()
    out = cli.tmp / "experiment"
    faults.fail_os("attempt.json")
    first = experiments.run(EXAMPLE, out, sends=[returns()] * 5, store_factory=faults)
    assert first.exit_code == 4
    resume = FaultyStores(monkeypatch)
    resume.fail_after("attempt.json", sync_failure())

    outcome = experiments.run(EXAMPLE, out, store_factory=resume)
    summary = experiment_summary_of(outcome)

    assert outcome.error_code == "storage.write_failed"
    assert [path for path in resume.published if path.endswith("/attempt.json")] != []
    counts = outcome.counts
    assert counts["cost"] is not None
    records = experiments.run(EXAMPLE, out, approve=False)
    assert summary["cases"] == experiment_summary_of(records)["cases"]
    assert without_warnings(counts) == without_warnings(records.counts)


class RefusingLock(LocalArtifactStore):
    """The output directory's store, whose experiment lock is refused with `code`: as another
    process's, at a new experiment's claim, or by the file system, at a resume's lock. An
    injected storage failure."""

    def __init__(self, root: str, code: ErrorCode) -> None:
        super().__init__(root)
        self._code: ErrorCode = code

    def claim(self, path: str, data: bytes, *, lock: bool = False) -> StoredFile:
        if lock:
            raise TrialFolioError(self._code, "The experiment lock was refused.")
        return super().claim(path, data, lock=lock)

    def lock(self, path: str) -> None:
        raise TrialFolioError(self._code, "The experiment lock was refused.")


def test_a_new_experiment_whose_claim_finds_the_lock_held_gives_its_cases_without_counts(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    # The owner's decision of 2026-10-09: cases with {} counts, only after experiment.locked.
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = experiments.run(
        EXAMPLE, out, store_factory=lambda root: RefusingLock(root, "experiment.locked")
    )
    summary = experiment_summary_of(outcome)

    assert outcome.error_code == "experiment.locked"
    assert all(outcome == "not_yet_run" for _, outcome in case_outcomes(summary))
    assert (summary["counts"], summary["output_dir"]) == ({}, None)
    assert cli.server.requests() == []


def test_a_resume_whose_lock_the_file_system_refuses_has_no_counts(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    assert experiments.run(EXAMPLE, out, sends=[returns()] * 5).exit_code == 0
    received = len(cli.server.received)

    outcome = experiments.run(
        EXAMPLE,
        out,
        approve=False,
        store_factory=lambda root: RefusingLock(root, "storage.write_failed"),
    )
    summary = experiment_summary_of(outcome)

    assert outcome.error_code == "storage.write_failed"
    assert summary["ids"] == {"experiment_id": "earnyield-sensitivity"}
    assert (summary["counts"], summary["output_dir"]) == ({}, None)
    assert len(cli.server.received) == received


def test_a_new_experiment_whose_claim_fails_gives_no_output_directory_and_its_counts(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    # Only experiment.locked gives {}: a new experiment's counts are known once its configuration
    # is valid, each case not yet run.
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = experiments.run(
        EXAMPLE, out, store_factory=lambda root: RefusingLock(root, "storage.write_failed")
    )
    summary = experiment_summary_of(outcome)

    assert outcome.error_code == "storage.write_failed"
    assert summary["output_dir"] is None
    assert_recorded(summary, EXAMPLE, out)
    counts = outcome.counts
    assert (counts["attempts"], counts["provider_requests"], counts["cost"]) == (0, 0, None)
    assert cli.server.requests() == []


# A provider failure: a partial run, and a stop (R03-AC05)

FAILURES: dict[str, tuple[list[Reply], list[Reply], list[str]]] = {
    "a-404": (
        [returns(), returns(), Reply(404, b"Not found"), returns(), returns()],
        [AUTHENTICATED],
        ["succeeded", "succeeded", "failed", "succeeded", "succeeded"],
    ),
    "a-403": (
        [returns(), Reply(403, b"Forbidden"), returns(), returns(), returns()],
        [AUTHENTICATED, AUTHENTICATED],
        ["succeeded", "failed", "succeeded", "succeeded", "succeeded"],
    ),
    "a-402": (
        [returns(), Reply(402, b"Quota exceeded")],
        [AUTHENTICATED],
        ["succeeded", "failed", "not_yet_run", "not_yet_run", "not_yet_run"],
    ),
    "an-authentication-401": ([], [REFUSED], ["failed", *["not_yet_run"] * 4]),
    "an-authentication-503": ([], [Reply(503, b"")], ["failed", *["not_yet_run"] * 4]),
}
"""Each failure of R03-AC05 but the 400 and the 503 above: the replies to the cases' requests and
to Trial Folio's authentication calls, and each case's outcome. After a 402, or an
authentication call's 401 or 503, no later case starts (D-32)."""


@pytest.mark.parametrize(("sends", "authenticates", "outcomes"), FAILURES.values(), ids=FAILURES)
def test_an_experiment_that_a_provider_failure_leaves_partial_or_stops(
    cli: Cli,
    experiments: ExperimentBuilder[Outcome],
    sends: list[Reply],
    authenticates: list[Reply],
    outcomes: list[str],
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = experiments.run(EXAMPLE, out, sends=sends, authenticates=authenticates)
    summary = experiment_summary_of(outcome)

    assert (summary["outcome"], summary["exit_code"]) == ("partial", 6)
    assert outcome.error_code == "execution.partial"
    assert summary["output_dir"] == str(out)
    assert outcome.ids["session"] == 1
    assert [outcome for _, outcome in case_outcomes(summary)] == outcomes
    assert_recorded(summary, EXAMPLE, out)


# A revision (R03-AC07)


def test_an_approved_revision_gives_its_plan_hash_and_its_cases(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    assert experiments.run(EXAMPLE, out, sends=[returns()] * 5).exit_code == 0
    changed = experiment_config("revisions/holdings-40.yaml")
    revised = plan_hash(changed, out)

    outcome = experiments.run(changed, out, "--revision-reason", REVISION_REASON, sends=[returns()])
    summary = experiment_summary_of(outcome)

    assert summary["outcome"] == "completed"
    ids = outcome.ids
    assert (ids["plan_hash"], ids["session"]) == (revised, 2)
    assert_recorded(summary, changed, out)
    counts = outcome.counts
    assert (counts["cases_retired"], counts["attempts"]) == (1, 6)


# A resume refused before its session (R03-AC07 and R03-AC14)


def attempt_of(out: Path, summary: dict[str, object], key: str) -> str:
    """The `attempt_id` of the case's only attempt."""
    (case_id,) = (
        case["case_id"]
        for case in cast("list[dict[str, str]]", summary["cases"])
        if case["case_key"] == key
    )
    (attempt,) = (out / "cases" / case_id / "attempts").iterdir()
    return attempt.name


REFUSALS: dict[str, tuple[str, Callable[[Path, dict[str, object]], list[str]]]] = {
    "a-reason-with-no-revision": (
        "unknown",
        lambda out, first: ["--revision-reason", "Nothing changed."],
    ),
    "a-key-alone-without-a-terminal": ("unknown", lambda out, first: ["--repeat", "holdings-50"]),
    "no-such-attempt": ("unknown", lambda out, first: ["--repeat", f"holdings-50:{uuid.uuid4()}"]),
    "another-cases-attempt": (
        "unknown",
        lambda out, first: ["--repeat", f"holdings-50:{attempt_of(out, first, 'baseline')}"],
    ),
    "a-succeeded-attempt": (
        "unknown",
        lambda out, first: ["--repeat", f"baseline:{attempt_of(out, first, 'baseline')}"],
    ),
    "no-case-of-the-plan": ("unknown", lambda out, first: ["--repeat", "nothing-of-the-plan"]),
    "a-due-cases-key": ("refused", lambda out, first: ["--repeat", "liquidity-100m"]),
    "an-attempt-not-possibly-charged": (
        "refused",
        lambda out, first: ["--repeat", f"baseline:{attempt_of(out, first, 'baseline')}"],
    ),
}
"""Each refusal before the session: the experiment it follows, `unknown`, whose `holdings-50`
got a 503, or `refused`, whose authentication call got a 401, so every case is due; and the
options, from its directory and its summary."""


def first_run(
    cli: Cli, experiments: ExperimentBuilder[Outcome], kind: str
) -> tuple[Path, dict[str, object]]:
    """Writes `example.yaml`'s experiment as `kind` says, and returns its directory and its
    summary."""
    cli.ready()
    out = cli.tmp / "experiment"
    if kind == "unknown":
        sends = [returns(), returns(), UNAVAILABLE, returns(), returns()]
        outcome = experiments.run(EXAMPLE, out, sends=sends)
    else:
        outcome = experiments.run(EXAMPLE, out, authenticates=[REFUSED])
    assert outcome.exit_code == 6, outcome.stderr
    return out, experiment_summary_of(outcome)


def assert_refused_before_the_session(
    outcome: Outcome, out: Path, before: dict[str, bytes | None]
) -> None:
    """`plan.approval_required`, with the current plan's hash and cases, and the records' counts,
    which are the first session's manifest's; nothing written."""
    summary = experiment_summary_of(outcome)
    assert outcome.error_code == "plan.approval_required"
    assert summary["output_dir"] is None
    assert set(outcome.ids) == {"experiment_id", "plan_hash"}
    assert_recorded(summary, EXAMPLE, out)
    recorded = ExperimentManifest.model_validate_json(
        (out / "sessions/1/manifest.json").read_bytes()
    )
    assert without_warnings(outcome.counts) == recorded_counts(recorded, out, summary)
    assert snapshot(out) == before


@pytest.mark.parametrize(("kind", "options"), REFUSALS.values(), ids=REFUSALS)
def test_a_resume_refused_before_its_session_gives_the_records_cases_and_counts(
    cli: Cli,
    experiments: ExperimentBuilder[Outcome],
    kind: str,
    options: Callable[[Path, dict[str, object]], list[str]],
) -> None:
    out, first = first_run(cli, experiments, kind)
    before = snapshot(out)
    received = len(cli.server.received)

    outcome = experiments.run(EXAMPLE, out, *options(out, first))

    assert_refused_before_the_session(outcome, out, before)
    assert len(cli.server.received) == received


@posix_only
def test_another_answer_at_the_repeat_prompt_gives_the_records_cases_and_counts(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    out, _ = first_run(cli, experiments, "unknown")
    before = snapshot(out)

    with PseudoTerminal() as terminal:
        terminal.press("approve\nno\n")
        ran = cli(
            "run",
            EXAMPLE,
            "--out",
            out,
            "--repeat",
            "holdings-50",
            "--json",
            stdin=terminal.stdin,
            stderr=terminal.stderr,
        )
    outcome = Outcome(ran.exit_code, ran.stdout, terminal.shown())

    assert_refused_before_the_session(outcome, out, before)


def test_a_repeat_with_a_new_experiment_or_a_screen_gives_its_summary(cli: Cli) -> None:
    cli.ready()
    new = cli.tmp / "experiment"
    screen = cli.tmp / "run"

    experiment_run = cli(
        "run",
        EXAMPLE,
        "--out",
        new,
        "--approve",
        plan_hash(EXAMPLE, new),
        "--repeat",
        "holdings-50",
        "--json",
    )
    screen_run = cli(
        "run", screen_config("formula.yaml"), "--out", screen, "--repeat", "holdings-50", "--json"
    )
    experiment = experiment_summary_of(experiment_run)
    run = summary_of(screen_run, "run")

    for ran, summary in ((experiment_run, experiment), (screen_run, run)):
        assert ran.error_code == "plan.approval_required"
        assert summary["output_dir"] is None
    assert_recorded(experiment, EXAMPLE, new)
    assert experiment_run.counts["attempts"] == 0
    assert set(screen_run.ids) == {"plan_hash", "case_id"}
    assert not new.exists()
    assert not screen.exists()


# A repeat that runs (R03-AC14)


def test_a_confirmed_repeat_and_then_its_used_confirmation_give_the_records_cases(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    out, first = first_run(cli, experiments, "unknown")
    option = f"holdings-50:{attempt_of(out, first, 'holdings-50')}"

    repeated = experiments.run(EXAMPLE, out, "--repeat", option, sends=[returns()])
    received = len(cli.server.received)
    again = experiments.run(EXAMPLE, out, "--repeat", option)
    # A key alone for a complete case resumes the rest.
    alone = experiments.run(EXAMPLE, out, "--repeat", "baseline")

    assert len(cli.server.received) == received
    for ran, session in ((repeated, 2), (again, 3), (alone, 4)):
        summary = experiment_summary_of(ran)
        assert summary["outcome"] == "completed"
        assert ran.ids["session"] == session
        assert_recorded(summary, EXAMPLE, out)
        assert ran.counts["repeats"] == 1


def test_a_repeat_whose_authentication_fails_keeps_its_confirmation_in_the_summary(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    out, first = first_run(cli, experiments, "unknown")
    attempt = attempt_of(out, first, "holdings-50")

    outcome = experiments.run(
        EXAMPLE, out, "--repeat", f"holdings-50:{attempt}", authenticates=[REFUSED]
    )
    summary = experiment_summary_of(outcome)

    assert (summary["outcome"], summary["exit_code"]) == ("partial", 6)
    assert outcome.ids["session"] == 2
    assert_recorded(summary, EXAMPLE, out)
    # The repeat sent nothing, so the same attempt still confirms it.
    holdings = cast("list[dict[str, str | None]]", summary["cases"])[2]
    assert (holdings["outcome"], holdings["repeat_attempt_id"]) == ("unknown", attempt)


def test_a_repeat_interrupted_during_its_send_gives_its_own_attempt_to_confirm(
    cli: Cli, experiments: ExperimentBuilder[Outcome], monkeypatch: pytest.MonkeyPatch
) -> None:
    out, first = first_run(cli, experiments, "unknown")
    attempt = attempt_of(out, first, "holdings-50")
    cli.server.reply("/auth", AUTHENTICATED)
    with monkeypatch.context() as patch:
        SocketFaults(patch).interrupt_send(b"POST /screen/backtest")
        interrupted = cli(
            "run",
            EXAMPLE,
            "--out",
            out,
            "--repeat",
            f"holdings-50:{attempt}",
            "--approve",
            plan_hash(EXAMPLE, out),
            "--json",
        )

    summary = experiment_summary_of(interrupted)

    assert interrupted.error_code == "command.interrupted"
    # From the resume's session record.
    assert summary["output_dir"] == str(out)
    assert interrupted.ids["session"] == 2
    assert summary["outputs"] == {}
    assert_recorded(summary, EXAMPLE, out)
    holdings = cast("list[dict[str, str | None]]", summary["cases"])[2]
    assert holdings["outcome"] == "unknown"
    assert holdings["repeat_attempt_id"] not in (None, attempt)


# The lock another process holds (R03-AC09)


@posix_only
def test_a_resume_while_another_process_holds_the_lock_has_no_cases_or_counts(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    assert experiments.run(EXAMPLE, out, sends=[returns()] * 5).exit_code == 0
    received = len(cli.server.received)

    # A resume waits at its approval prompt, in another process, holding the lock.
    with cli.on_terminal("run", EXAMPLE, "--out", out, "--json") as holder:
        holder.wait_for("Type approve")
        outcome = experiments.run(EXAMPLE, out)
        summary = experiment_summary_of(outcome)
        holder.press("no\n")
        holder.wait()

    assert outcome.error_code == "experiment.locked"
    assert summary["ids"] == {"experiment_id": "earnyield-sensitivity"}
    assert "cases" not in summary
    assert (summary["counts"], summary["output_dir"]) == ({}, None)
    assert len(cli.server.received) == received


# A storage failure and an interrupt, before and after the session record (R03-AC19)

STOPS: dict[str, tuple[str, str, bool]] = {
    "a-new-experiments-session-record": ("new", "/sessions/1/session.json", False),
    "a-new-experiments-plan": ("new", "/plans/1/plan.json", True),
    "a-new-experiments-manifest": ("new", "/sessions/1/manifest.json", True),
    "a-resumes-session-record": ("resume", "/sessions/2/session.json", False),
    "a-resumes-attempt-record": ("resume", "attempt.json", True),
}
"""Where each session stops: in a new experiment, or a resume of one whose authentication call
got a 401, so every case is due; the file whose write fails; and whether the session record was
written by then."""

FAULTS: dict[str, tuple[Callable[[FaultyStores, str], None], str]] = {
    "storage": (lambda faults, name: faults.fail_os(name), "storage.write_failed"),
    "interrupt": (
        lambda faults, name: faults.fail_before(name, KeyboardInterrupt()),
        "command.interrupted",
    ),
}


@pytest.mark.parametrize(("fail", "code"), FAULTS.values(), ids=FAULTS)
@pytest.mark.parametrize(("kind", "name", "session"), STOPS.values(), ids=STOPS)
def test_an_experiment_that_stops_gives_its_output_directory_once_it_writes_there(
    cli: Cli,
    experiments: ExperimentBuilder[Outcome],
    faults: FaultyStores,
    fail: Callable[[FaultyStores, str], None],
    code: str,
    kind: str,
    name: str,
    session: bool,
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    if kind == "resume":
        assert experiments.run(EXAMPLE, out, authenticates=[REFUSED]).exit_code == 6
    fail(faults, name)

    outcome = experiments.run(EXAMPLE, out, sends=[returns()] * 5, store_factory=faults)
    summary = experiment_summary_of(outcome)

    assert outcome.error_code == code
    outputs = outcome.outputs
    assert "manifest" not in outputs
    ids = outcome.ids
    # A new experiment's, from its claim; a resume's, from its session record.
    if kind == "new" or session:
        assert summary["output_dir"] == str(out)
    else:
        assert summary["output_dir"] is None
    assert ("session" in ids) == session
    if session:
        assert ids["session"] == (1 if kind == "new" else 2)
    assert_recorded(summary, EXAMPLE, out)


PUBLISHED_FAULTS: dict[str, tuple[Callable[[], BaseException], str]] = {
    "storage": (sync_failure, "storage.write_failed"),
    "interrupt": (KeyboardInterrupt, "command.interrupted"),
}


@pytest.mark.parametrize(("failure", "code"), PUBLISHED_FAULTS.values(), ids=PUBLISHED_FAULTS)
@pytest.mark.parametrize("kind", ["new", "resume"])
def test_a_session_record_published_before_its_write_failed_reserves_its_session(
    cli: Cli,
    experiments: ExperimentBuilder[Outcome],
    faults: FaultyStores,
    failure: Callable[[], BaseException],
    code: str,
    kind: str,
) -> None:
    # A corrected defect: the summary gave no session, and for a resume no output directory,
    # though the store had published the session record, as every later run reads it.
    cli.ready()
    out = cli.tmp / "experiment"
    if kind == "resume":
        assert experiments.run(EXAMPLE, out, authenticates=[REFUSED]).exit_code == 6
    session = 1 if kind == "new" else 2
    faults.fail_after(f"/sessions/{session}/session.json", failure())

    outcome = experiments.run(EXAMPLE, out, sends=[returns()] * 5, store_factory=faults)
    summary = experiment_summary_of(outcome)

    assert outcome.error_code == code
    assert (out / f"sessions/{session}/session.json").is_file()
    assert outcome.ids["session"] == session
    assert summary["output_dir"] == str(out)
    assert "manifest" not in outcome.outputs
    assert_recorded(summary, EXAMPLE, out)


def test_a_manifest_whose_write_fails_once_published_isnt_among_the_outputs(
    cli: Cli, experiments: ExperimentBuilder[Outcome], faults: FaultyStores
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    faults.fail_after("/sessions/1/manifest.json", sync_failure())

    outcome = experiments.run(EXAMPLE, out, sends=[returns()] * 5, store_factory=faults)
    summary = experiment_summary_of(outcome)

    assert outcome.error_code == "storage.write_failed"
    assert summary["output_dir"] == str(out)
    assert outcome.ids["session"] == 1
    # The store discarded the manifest it had published, and the report stays.
    assert summary["outputs"] == {"report": "sessions/1/report.html"}
    assert not (out / "sessions/1/manifest.json").exists()
    assert_recorded(summary, EXAMPLE, out)
