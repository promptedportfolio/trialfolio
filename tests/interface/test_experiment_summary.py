"""With `--json`, `run` with an experiment's configuration writes exactly one JSON summary to
stdout, followed by a newline, whether it succeeds or fails, with the experiment's `cases`.

Traces to R03-AC16, for `run` with an experiment's configuration, over the scenarios of R03-AC01 (no
approval), R03-AC05 (a case that fails, each provider failure that leaves the run partial or stops
it, and missing credentials), R03-AC07 (a revision without its reason and its hash, an approved one,
a reason with no revision, and another experiment), R03-AC09 (the lock another holder holds, in this
process or in a resume waiting at its approval prompt in another, and a new experiment's claim),
R03-AC14 (a case awaiting a repeat, a confirmed repeat, its used confirmation, and a key alone for a
complete case, a repeat whose authentication fails or that's interrupted during its send, and each
repeat that fails before anything is sent), R03-AC17 (records that aren't complete), and R03-AC19 (a
storage failure and an interrupt, in a new experiment and in a resume, before and after the session
record, and a manifest whose write fails once it's published), and an invalid configuration: its
`ids` name the plan the core builds, its `cases` are that plan's, in order, with the outcomes and
the repeats' attempts the records give, its `counts` agree with the records and the session's
manifest, and its `output_dir` is given from a new experiment's claim, or a resume's session record,
and is `null` before. Each summary is checked against the `JsonSummaryV1_2` model and the keys of
the generated schema, `schemas/json-summary-1.2.0.schema.json`, with an experiment's keys, as
tests/interface/test_json_summary.py checks every command's; and the screen run's summary one test
compares with an experiment's is checked as that module checks it, with
tests/support/json_summaries.py's `summary_of`. Through the CLI's entry function in the test
process, with the real client, `requests`, and `urllib3` over the fake server; the
terminal is a real pseudo-terminal, in the test process or, for the resume that holds the lock, in
another process under the test launcher, and the socket faults interrupt a repeat during its send,
as Ctrl-C does.

R03-T13 wrote the first of these checks, of an experiment's summary, and R03-T11 the rest of
R03-AC16's scenarios, and the check of the cases against the records. TS-T07 separated them from
tests/interface/test_json_summary.py, with their own helpers (docs/test-refactoring.md, modules to
separate).
"""

import csv
import io
import json
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple, cast

import pytest

from tests.support.cli import Cli
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
from tests.support.fake_portfolio123 import Reply
from tests.support.json_summaries import EXPERIMENT_COUNTS, SCHEMA, summary_of
from tests.support.paths import screen_config
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
from trialfolio.storage import LocalArtifactStore, StoredFile

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
