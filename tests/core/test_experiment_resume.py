"""A resume, in the core: it reads and checks the experiment's records under the lock, records
the attempts a stopped run left without their attempt records, each with a message that says
where it stopped, writes the tables a stopped run didn't, sends only the cases that are due and
those a confirmed repeat names, revises the plan when it's given a revision with its reason, and
counts every attempt of the experiment.

Traces to docs/contracts.md, running an experiment (a resumed experiment, checking the records, the
cases that are due, and the executor), uncertain completion, experiment attempts, an experiment's
normalized tables, experiment plans and revisions (approving a revision, what a revision keeps, and
the budget across runs), repeating a case, the experiment manifest, and the experiment report's
evidence; and, at the core, to R03-AC02 (case identities are stable across restarts), R03-AC04 (an
interruption after case n resumes at case n + 1, with no repeated provider call), R03-AC06 (a
restart skips complete cases and flags an attempt with uncertain completion, which isn't repeated),
R03-AC07 (an approved revision gives the changed case a new identity and keeps the old one),
R03-AC08 (the counts add up), R03-AC14 (execution given a repeat checks it, and never asks),
R03-AC17 (records that are incomplete or changed fail with `input.not_a_run`, and send and write
nothing), and R03-AC18 (a resume writes the tables a stopped run didn't). The real client,
`requests`, and `urllib3` run over the fake server; storage faults wrap the real store; the clock is
fixed.

Each experiment is built during the test, through the core, and stopped where the test needs it:
by a cancellation, by storage faults, or by an interrupt, as a stopped process leaves it. One, for
the demo's client given an experiment that isn't synthetic, is `trialfolio run`'s, written by the
experiment builder through the CLI's entry function (R03-AC17's pairing). The records check's
breaks are made with the editors of `tests/support/broken_runs.py`, which TS-T05 moved there from
this module: each edit updates the latest manifest's entry, and, for a plan's file, the
`artifact_id` each `experiment.json` records, so only the check under test can tell.
"""

import json
import logging
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import pytest

from tests.support.broken_runs import (
    copy_attempt,
    edit_attempt,
    edit_record,
    rewrite_record,
    unlist_record,
)
from tests.support.cli import Cli
from tests.support.clock import FixedClock
from tests.support.directories import snapshot
from tests.support.experiment_builder import ExperimentBuilder
from tests.support.experiment_lab import RELEASE_0_3_0, Lab
from tests.support.fake_portfolio123 import (
    AUTH,
    AUTHENTICATED,
    BACKTEST,
    CREDENTIALS,
    FakePortfolio123,
    Reply,
    response,
)
from tests.support.paths import EXPERIMENT_CONFIGS, RESPONSES
from tests.support.plans import case_ids, experiment_plan
from tests.support.storage_faults import StorageFaults
from trialfolio.canonical import sha256_hex
from trialfolio.contracts.attempt import AttemptRecordV1_1
from trialfolio.contracts.experiment_manifest import ExperimentManifest
from trialfolio.contracts.experiment_plan import PlanV1_1
from trialfolio.contracts.experiment_record import ExperimentRecord
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_execution import ExperimentExecution, SessionStarted
from trialfolio.experiment_records import open_experiment
from trialfolio.experiment_repeats import Repeat
from trialfolio.normalization import case_metrics_rows
from trialfolio.planning import plan_hash
from trialfolio.provider import P123ScreenBacktestClient
from trialfolio.storage import LocalArtifactStore
from trialfolio.tables import metrics_csv, read_metrics_csv, read_settings_csv, settings_csv

type Json = dict[str, Any]


@pytest.fixture
def lab(tmp_path: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch) -> Lab:
    return Lab(tmp_path, server, monkeypatch, reader=RELEASE_0_3_0, catch=True)


EXAMPLE = experiment_plan(EXPERIMENT_CONFIGS / "example.yaml")
DEFAULT_ONLY = experiment_plan(EXPERIMENT_CONFIGS / "default-only.yaml")


# Resuming


@pytest.mark.parametrize("n", [1, 4])
def test_a_resume_sends_only_the_cases_after_the_last_complete_one(lab: Lab, n: int) -> None:
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply("/screen/backtest", *(response("complete.json") for _ in range(5)))
    first = lab.new(cancel_after=n)
    assert first.refused("execution.partial")
    sent = [json.loads(r.body) for r in lab.server.received if r.path == "/screen/backtest"]

    resumed = lab.resume()

    assert resumed.error is None
    assert resumed.received == (AUTH, *(BACKTEST for _ in range(5 - n)))
    bodies = [json.loads(r.body) for r in lab.server.received if r.path == "/screen/backtest"]
    assert bodies[n:] == [
        case.requests[0].params.model_dump(mode="json") for case in EXAMPLE.cases[n:]
    ]
    assert bodies[:n] == sent[:n]
    started = resumed.events[0]
    assert started == SessionStarted(session=2, cases=tuple(case_ids(EXAMPLE)[n:]))
    assert resumed.outcomes == ["succeeded"] * 5
    manifest = lab.manifest(2, ExperimentManifest)
    assert (manifest.session, manifest.plan, manifest.outcome) == (2, 1, "completed")
    counts = manifest.counts
    assert counts.cases.succeeded == 5 and counts.attempts.succeeded == 5
    assert (counts.provider_requests, counts.authentication_calls) == (5, 2)
    # Each case keeps its case_id, in every record (R03-AC02), and the session's attempts are
    # numbered from 1 again.
    records = [
        record
        for case_id in case_ids(EXAMPLE)
        for record in lab.attempts(case_id, AttemptRecordV1_1)
    ]
    assert [record.case_id for record in records] == case_ids(EXAMPLE)
    assert [(r.session, r.sequence) for r in records] == [
        *((1, s) for s in range(1, n + 1)),
        *((2, s) for s in range(1, 6 - n)),
    ]
    assert records[n].authenticated_by == records[n].attempt_id
    assert all(r.authenticated_by == records[n].attempt_id for r in records[n:])


def test_a_resume_lists_every_file_of_the_experiment_and_keeps_the_earlier_entries(
    lab: Lab,
) -> None:
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply("/screen/backtest", *(response("complete.json") for _ in range(5)))
    lab.new(cancel_after=2)

    # A time no entry rebuilt from the records would give, so a kept entry can't pass for one.
    def acquired_earlier(manifest: Json) -> None:
        for artifact in manifest["artifacts"]:
            if artifact["source"] is not None:
                artifact["source"]["acquired_at"] = "2026-10-01T00:00:00Z"

    edit_record(lab.out, "sessions/1/manifest.json", acquired_earlier)
    earlier = {
        artifact.path: artifact for artifact in lab.manifest(1, ExperimentManifest).artifacts
    }

    resumed = lab.resume()

    assert resumed.error is None
    manifest = lab.manifest(2, ExperimentManifest)
    listed = {artifact.path: artifact for artifact in manifest.artifacts}
    on_disk = {
        path.relative_to(lab.out).as_posix() for path in lab.out.rglob("*") if path.is_file()
    }
    assert on_disk - set(listed) == {
        "experiment.lock",
        "sessions/1/manifest.json",
        "sessions/2/manifest.json",
        "sessions/1/session.json",
        "sessions/1/report.html",
    }
    # Each file the first session's manifest lists, apart from its own session's, is listed
    # again as it was, its source record included.
    kept = {path: entry for path, entry in earlier.items() if not path.startswith("sessions/")}
    assert {path: listed[path] for path in kept} == kept
    assert {entry.role for entry in kept.values() if entry.source is not None} == {
        "configuration",
        "provider_request",
        "provider_response",
    }
    assert {a.path for a in manifest.artifacts if a.role in ("session_record", "report")} == {
        "sessions/2/session.json",
        "sessions/2/report.html",
    }


def test_resuming_a_complete_experiment_sends_nothing_and_writes_a_session(lab: Lab) -> None:
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"), response("complete.json"))
    assert lab.new("default-only.yaml").error is None

    resumed = lab.resume("default-only.yaml")

    assert resumed.error is None and resumed.received == ()
    assert resumed.events[0] == SessionStarted(session=2, cases=())
    assert lab.manifest(2, ExperimentManifest).counts == lab.manifest(1, ExperimentManifest).counts
    # The saved responses hold per-period series, though this session saved none.
    assert lab.manifest(2, ExperimentManifest).capabilities.return_series == "source_only"


def test_a_session_number_is_never_reused(lab: Lab) -> None:
    # A process killed while writing the next session's record leaves its directory, with only
    # the store's hidden temporary file. The resume skips that name, and takes the number after.
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"), response("complete.json"))
    assert lab.new("default-only.yaml").error is None
    (lab.out / "sessions/2").mkdir()
    (lab.out / "sessions/2/.session.json.0123456789abcdef.tmp").write_bytes(b"{")

    resumed = lab.resume("default-only.yaml")

    assert resumed.error is None
    assert resumed.events[0] == SessionStarted(session=3, cases=())
    assert lab.manifest(3, ExperimentManifest).session == 3


def test_the_same_configuration_written_differently_resumes_its_plan(lab: Lab) -> None:
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply("/screen/backtest", *(response("complete.json") for _ in range(5)))
    lab.new(cancel_after=1)

    resumed = lab.resume("written-differently.yaml")

    assert resumed.error is None and len(resumed.received) == 5
    assert not (lab.out / "plans/2").exists()
    # Each case's tables take their original values from the configuration of the plan its
    # attempt ran under, never from the file given to the run that resumed it.
    slippage = EXAMPLE.cases[4]
    rows = read_settings_csv(
        (lab.out / f"cases/{slippage.case_id}/normalized/settings.csv").read_bytes(), "settings"
    )
    (baseline_rows,) = (
        read_settings_csv(
            (lab.out / f"cases/{EXAMPLE.cases[1].case_id}/normalized/settings.csv").read_bytes(),
            "settings",
        ),
    )
    assert {row.setting: row.original_value for row in rows}["slippage_percent"] == "0.5"
    assert {r.setting: r.original_value for r in baseline_rows}["slippage_percent"] == "0.25"


# What a stopped run left


def test_a_running_attempt_with_a_saved_response_is_recorded_as_succeeded(lab: Lab) -> None:
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"), response("complete.json"))
    baseline, default = case_ids(DEFAULT_ONLY)

    first = lab.new("default-only.yaml", arm=lambda store: store.fail_os("attempt.json"))
    assert first.refused("storage.write_failed")
    (directory,) = lab.attempt_directories(baseline)
    assert sorted(p.name for p in directory.iterdir()) == [
        "authenticating.json",
        "request.json",
        "response.json",
        "started.json",
    ]
    assert lab.read().cases(DEFAULT_ONLY)[0].state == "complete"

    resumed = lab.resume("default-only.yaml")

    assert resumed.error is None
    # Not sent again: one authentication, for the other case.
    assert resumed.received == (AUTH, BACKTEST)
    (record,) = lab.attempts(baseline, AttemptRecordV1_1)
    assert (record.outcome, record.possibly_charged, record.error) == ("succeeded", True, None)
    assert (record.session, record.sequence) == (1, 1)
    assert [(e.request, e.result, e.status, e.note) for e in record.exchanges] == [
        (AUTH, "response", 200, None),
        (BACKTEST, "response", 200, "completed_from_saved_response"),
    ]
    # Portfolio123's cost and quota, from the saved response, as the attempt would have recorded
    # them.
    assert (record.provider_metadata.cost, record.provider_metadata.quota_remaining) == (5, 4321)
    assert record.response is not None and record.response.path.endswith("/response.json")
    assert record.request is not None and record.request.path.endswith("/request.json")
    # The tables a stopped run didn't write, from its saved response.
    metrics = read_metrics_csv(
        (lab.out / f"cases/{baseline}/normalized/metrics.csv").read_bytes(), "metrics"
    )
    assert {row.source_artifact for row in metrics} == {record.response.artifact_id}
    assert all(row.label == baseline for row in metrics)
    manifest = lab.manifest(2, ExperimentManifest)
    assert manifest.counts.cases.succeeded == 2
    assert (manifest.counts.provider_requests, manifest.counts.authentication_calls) == (2, 2)
    # The manifest lists the attempt record the resume wrote, and counts its cost.
    written = f"cases/{baseline}/attempts/{record.attempt_id}/attempt.json"
    assert written in {artifact.path for artifact in manifest.artifacts}
    assert manifest.counts.cost == 10
    assert default in {a.path.split("/")[1] for a in manifest.artifacts if a.role == "metrics"}


def test_a_running_attempt_without_a_saved_response_is_unknown_and_not_sent_again(
    lab: Lab,
) -> None:
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply("/screen/backtest", Reply(503), response("complete.json"))
    baseline, _ = case_ids(DEFAULT_ONLY)
    first = lab.new("default-only.yaml", arm=lambda store: store.fail_os("attempt.json"))
    assert first.refused("storage.write_failed")
    assert first.received == (AUTH, BACKTEST)
    saved = lab.read()
    (case, _) = saved.cases(DEFAULT_ONLY)
    assert case.state == "awaiting_repeat"
    latest = case.latest_charged
    assert latest is not None and latest.outcome == "unknown"
    # It reads as the resume will record it: one possible send, after one authentication call.
    assert latest.error_code == "command.interrupted"
    assert (saved.provider_requests, saved.authentication_calls) == (1, 1)

    resumed = lab.resume("default-only.yaml")

    error = resumed.refused("execution.partial")
    assert resumed.received == (AUTH, BACKTEST)
    assert [json.loads(r.body) for r in lab.server.received[-1:]] == [
        DEFAULT_ONLY.cases[1].requests[0].params.model_dump(mode="json")
    ]
    (record,) = lab.attempts(baseline, AttemptRecordV1_1)
    assert (record.outcome, record.possibly_charged) == ("unknown", True)
    assert record.error is not None and record.error.code == "command.interrupted"
    assert "may have been charged" in record.error.message
    assert [(e.request, e.status) for e in record.exchanges] == [(AUTH, 200)]
    # It references the request.json written before its start record, and no response.
    assert record.request is not None and record.request.path.endswith("/request.json")
    assert record.response is None
    assert record.attempt_id == latest.attempt_id
    assert resumed.outcomes == ["unknown", "succeeded"]
    assert "`baseline`, unknown (command.interrupted)" in error.message
    assert "a confirmed repeat sends it" in error.message
    counts = lab.manifest(2, ExperimentManifest).counts
    assert (counts.cases.unknown, counts.cases.succeeded) == (1, 1)
    assert (counts.provider_requests, counts.authentication_calls) == (2, 2)
    # The next resume doesn't send it either.
    again = lab.resume("default-only.yaml")
    assert again.refused("execution.partial") and again.received == ()


def test_an_attempt_with_only_its_authentication_record_is_failed_and_its_case_is_sent(
    lab: Lab,
) -> None:
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"), response("complete.json"))
    baseline, _ = case_ids(DEFAULT_ONLY)

    def arm(store: StorageFaults) -> None:
        store.fail_before("started.json", KeyboardInterrupt())
        store.fail_os("attempt.json")

    first = lab.new("default-only.yaml", arm=arm)
    assert first.refused("command.interrupted")
    (directory,) = lab.attempt_directories(baseline)
    assert sorted(p.name for p in directory.iterdir()) == ["authenticating.json", "request.json"]
    saved = lab.read()
    assert saved.cases(DEFAULT_ONLY)[0].state == "due"
    assert (saved.provider_requests, saved.authentication_calls) == (0, 1)

    resumed = lab.resume("default-only.yaml")

    assert resumed.error is None
    assert resumed.received == (AUTH, BACKTEST, BACKTEST)
    old, new = lab.attempts(baseline, AttemptRecordV1_1)
    assert (old.outcome, old.possibly_charged, old.request, old.authenticated_by) == (
        "failed",
        False,
        None,
        None,
    )
    assert old.error is not None and old.error.code == "command.interrupted"
    assert [(e.request, e.result, e.status) for e in old.exchanges] == [(AUTH, "interrupted", None)]
    assert new.outcome == "succeeded" and new.repeat_of is None
    counts = lab.manifest(2, ExperimentManifest).counts
    assert (counts.provider_requests, counts.authentication_calls) == (2, 2)
    assert counts.attempts.failed == 1 and counts.attempts.succeeded == 2
    # The request.json the stopped attempt wrote is listed, though no record references it.
    assert f"{old.case_id}/attempts/{old.attempt_id}/request.json" in "".join(
        a.path for a in lab.manifest(2, ExperimentManifest).artifacts
    )


STOPPED: Final = {
    "while it authenticated": (
        "started.json",
        (
            "The run that started the attempt stopped while it authenticated, before its request was"
            " sent. The screen backtest request wasn't sent."
        ),
    ),
    "after its start record": (
        "response.json",
        (
            "The run that started the attempt stopped after its start record was written, before a"
            " response was saved. The screen backtest request may have been charged, and its outcome"
            " is unknown: no response was saved. Trial Folio never retries it automatically: check"
            " the account's API credits on Portfolio123's website before running the command again."
        ),
    ),
}
"""Where the first case's attempt stopped, without its attempt record: the file whose write fails
with a full disk, before an unexpected failure at the attempt record, and the message of the
attempt record the resume writes for it, in step 8, as written by hand."""


@pytest.mark.parametrize("where", STOPPED)
def test_the_attempt_record_a_resume_writes_says_where_its_run_stopped(
    lab: Lab, where: str
) -> None:
    """Each message of an attempt record that step 8 writes under a plan 1.1.0, whose attempt
    sends one request (docs/test-refactoring.md, the missing tests' item 5)."""
    stopped_at, message = STOPPED[where]
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply(
        "/screen/backtest",
        response("complete.json"),
        response("complete.json"),
        response("complete.json"),
    )
    baseline, _ = case_ids(DEFAULT_ONLY)

    def arm(store: StorageFaults) -> None:
        store.fail_os(stopped_at)
        store.fail_before("attempt.json", RuntimeError())

    lab.new("default-only.yaml", arm=arm)
    assert not (lab.attempt_directories(baseline)[0] / "attempt.json").exists()

    lab.resume("default-only.yaml")

    stopped = lab.attempts(baseline, AttemptRecordV1_1)[0]
    assert stopped.session == 1
    assert stopped.error is not None
    assert stopped.error.message == message


def test_an_attempt_directory_without_its_records_is_no_attempt(lab: Lab) -> None:
    # A process killed after an attempt that sends with the session's token wrote its
    # request.json, and before its start record, leaves a directory without any of the attempt's
    # records. There's no record of the attempt: its case is due, and nothing lists the file.
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"), response("complete.json"))
    _, default = case_ids(DEFAULT_ONLY)
    lab.new("default-only.yaml", cancel_after=1)
    left = lab.out / "cases" / default / "attempts" / str(uuid.uuid4())
    left.mkdir(parents=True)
    params = DEFAULT_ONLY.cases[1].requests[0].params.model_dump(mode="json")
    (left / "request.json").write_text(json.dumps(params, indent=2))
    assert lab.read().cases(DEFAULT_ONLY)[1].state == "due"

    resumed = lab.resume("default-only.yaml")

    assert resumed.error is None and resumed.received == (AUTH, BACKTEST)
    assert (left / "request.json").exists()
    assert not any(
        left.name in artifact.path for artifact in lab.manifest(2, ExperimentManifest).artifacts
    )


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError(),
        TrialFolioError(
            "storage.write_failed",
            "Couldn't write response.json durably: Input/output error. Check the output"
            " directory's free space and permissions.",
        ),
    ],
    ids=["unexpected", "storage-failure"],
)
def test_return_series_reads_a_response_published_before_its_write_failed(
    lab: Lab, failure: Exception
) -> None:
    # The response is listed, though its attempt record doesn't reference it, so its attempt is
    # unknown. return_series reads it all the same: in the manifest of its own session, which an
    # unexpected failure lets go on, and in a resume's. The other case's request gets a 503,
    # which saves no response. A defect found by PR #68's review: both declared absent.
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"), Reply(503))
    baseline, _ = case_ids(DEFAULT_ONLY)
    first = lab.new(
        "default-only.yaml", arm=lambda store: store.fail_after("response.json", failure)
    )
    if isinstance(failure, TrialFolioError):
        assert first.refused("storage.write_failed")
        assert not (lab.out / "sessions/1/manifest.json").exists()
    else:
        assert first.refused("execution.partial")
        assert lab.manifest(1, ExperimentManifest).capabilities.return_series == "source_only"

    resumed = lab.resume("default-only.yaml")

    assert resumed.refused("execution.partial")
    (record,) = lab.attempts(baseline, AttemptRecordV1_1)
    assert (record.outcome, record.response) == ("unknown", None)
    assert resumed.outcomes == ["unknown", "unknown"]
    manifest = lab.manifest(2, ExperimentManifest)
    (directory,) = lab.attempt_directories(baseline)
    published = (directory / "response.json").relative_to(lab.out).as_posix()
    assert {a.path: a.role for a in manifest.artifacts}[published] == "provider_response"
    assert manifest.capabilities.return_series == "source_only"


def test_a_metrics_table_without_its_settings_table_is_completed(
    lab: Lab, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The same experiment, uninterrupted, for the tables a resume must write.
    # Its response's coverage differs from the settings' dates, so settings.csv flags it.
    mismatch = Reply(200, (RESPONSES / "coverage-mismatch.json").read_bytes())
    whole = Lab(
        tmp_path / "whole", FakePortfolio123(), monkeypatch, reader=RELEASE_0_3_0, catch=True
    )
    whole.server.reply("/auth", AUTHENTICATED)
    whole.server.reply("/screen/backtest", response("complete.json"), mismatch)
    try:
        assert whole.new("default-only.yaml").error is None
    finally:
        whole.server.close()
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"), mismatch)
    _, default = case_ids(DEFAULT_ONLY)
    first = lab.new(
        "default-only.yaml",
        arm=lambda store: store.fail_os(f"/cases/{default}/normalized/settings.csv"),
    )
    assert first.refused("storage.write_failed")
    metrics = (lab.out / f"cases/{default}/normalized/metrics.csv").read_bytes()

    resumed = lab.resume("default-only.yaml")

    assert resumed.error is None and resumed.received == ()
    assert resumed.published[:2] == (
        "sessions/2/session.json",
        f"cases/{default}/normalized/settings.csv",
    )
    assert (lab.out / f"cases/{default}/normalized/metrics.csv").read_bytes() == metrics
    # Exactly the tables the uninterrupted experiment wrote.
    for name in ("metrics.csv", "settings.csv"):
        path = f"cases/{default}/normalized/{name}"
        assert (lab.out / path).read_bytes() == (whole.out / path).read_bytes()
    assert (
        b"coverage_mismatch" in (lab.out / f"cases/{default}/normalized/settings.csv").read_bytes()
    )
    rows = read_settings_csv(
        (lab.out / f"cases/{default}/normalized/settings.csv").read_bytes(), "settings"
    )
    (configuration,) = (
        a.artifact_id
        for a in lab.manifest(2, ExperimentManifest).artifacts
        if a.path == "plans/1/configuration.yaml"
    )
    assert {row.source_artifact for row in rows} == {configuration}
    assert {row.label for row in rows} == {default}
    # The evidence the session's report shows holds the rows the resume wrote, flag and all.
    assert resumed.execution is not None and resumed.execution.evidence is not None
    (view,) = (v for v in resumed.execution.evidence.cases if v.case.case_id == default)
    assert view.settings == rows
    # The manifest names the installed parser for the case's response, whose table no manifest
    # had listed.
    (listed,) = (
        a
        for a in lab.manifest(2, ExperimentManifest).artifacts
        if a.role == "provider_response" and default in a.path
    )
    assert listed.source is not None and listed.source.parser_version == 1
    assert [parser.parser_version for parser in lab.manifest(2, ExperimentManifest).parsers] == [1]


def test_the_tables_a_resume_writes_come_from_the_response_its_check_read(lab: Lab) -> None:
    # The resume writes a stopped run's tables from the response's bytes as its records check
    # read them, never by reading the file again: a response changed after the check doesn't
    # reach the tables.
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"), response("complete.json"))
    baseline, _ = case_ids(DEFAULT_ONLY)
    stopped = lab.new(
        "default-only.yaml",
        arm=lambda store: store.fail_os(f"/cases/{baseline}/normalized/metrics.csv"),
    )
    assert stopped.refused("storage.write_failed")
    content = (EXPERIMENT_CONFIGS / "default-only.yaml").read_bytes()
    with (
        LocalArtifactStore(lab.out) as store,
        P123ScreenBacktestClient(CREDENTIALS, endpoint=lab.server.endpoint) as client,
    ):
        saved = open_experiment(store)
        (published,) = (lab.out / "cases" / baseline / "attempts").rglob("response.json")
        published.unlink()
        published.write_bytes((RESPONSES / "changed-metrics.json").read_bytes())
        execution = ExperimentExecution(
            saved.plan,
            saved.plan.plan_hash,
            "option",
            store,
            client,
            command=None,
            clock=FixedClock(),
            experiment=saved,
        )
        assert execution.run(content) is None
    metrics = (lab.out / f"cases/{baseline}/normalized/metrics.csv").read_bytes()
    (record,) = lab.attempts(baseline, AttemptRecordV1_1)
    assert record.response is not None
    expected = case_metrics_rows(
        response("complete.json").body, DEFAULT_ONLY.cases[0], record.response
    )
    assert metrics == metrics_csv(expected)


def test_a_saved_response_that_fails_validation_leaves_its_case_failed_without_tables(
    lab: Lab,
) -> None:
    # A running attempt with a saved response is recorded as succeeded, but its response doesn't
    # have the layout's structure, so the case has no tables, and isn't sent again.
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply(
        "/screen/backtest", Reply(200, (RESPONSES / "invalid-structure.json").read_bytes())
    )
    lab.server.reply("/screen/backtest", response("complete.json"))
    baseline, _ = case_ids(DEFAULT_ONLY)
    lab.new("default-only.yaml", arm=lambda store: store.fail_os("attempt.json"))

    resumed = lab.resume("default-only.yaml")

    error = resumed.refused("execution.partial")
    assert "`baseline`, failed (provider.response_invalid)" in error.message
    assert resumed.received == (AUTH, BACKTEST)
    (record,) = lab.attempts(baseline, AttemptRecordV1_1)
    assert record.outcome == "succeeded"
    assert not (lab.out / "cases" / baseline / "normalized").exists()
    assert resumed.outcomes == ["failed", "succeeded"]
    assert lab.manifest(2, ExperimentManifest).counts.cases.failed == 1


def test_a_case_whose_saved_response_fails_validation_is_failed_before_step_8(lab: Lab) -> None:
    # The records check found the case's saved response invalid, so the execution gives its
    # outcome as failed from the start, as the records do, even when the resume ends before step
    # 8 reaches the case: here, when its session record can't be written.
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply(
        "/screen/backtest", Reply(200, (RESPONSES / "invalid-structure.json").read_bytes())
    )
    lab.new("default-only.yaml", arm=lambda store: store.fail_os("attempt.json"))
    assert [case.outcome for case in lab.read().cases(DEFAULT_ONLY)] == ["failed", "not_yet_run"]

    stopped = lab.resume("default-only.yaml", arm=lambda store: store.fail_os("session.json"))

    assert stopped.refused("storage.write_failed")
    assert stopped.received == () and stopped.published == ()
    assert stopped.outcomes == ["failed", "not_yet_run"]


@pytest.mark.parametrize("change", ["no-request", "two-responses"])
def test_a_running_attempt_needs_its_request_and_one_saved_response(lab: Lab, change: str) -> None:
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"))
    baseline, _ = case_ids(DEFAULT_ONLY)
    lab.new("default-only.yaml", arm=lambda store: store.fail_os("attempt.json"))
    (directory,) = lab.attempt_directories(baseline)
    if change == "no-request":
        (directory / "request.json").unlink()
    else:
        (directory / "response.raw").write_bytes((directory / "response.json").read_bytes())

    ran = lab.resume("default-only.yaml")

    problem = "not the request.json" if change == "no-request" else "holds two saved responses"
    assert problem in ran.refused("input.not_a_run").message
    assert ran.published == ()


@pytest.mark.parametrize("left", ["none", "metrics", "both"])
def test_the_manifest_names_the_parser_that_wrote_each_table(lab: Lab, left: str) -> None:
    # As a later version, whose parser is 2, would have left the records: the latest manifest
    # names parser 2 for both responses, and lists the baseline's tables, which parser 2 read
    # differently from the installed one, but not the other case's, as when parser 2 found its
    # response invalid. A resume with the installed parser may then have written the other
    # case's metrics.csv, or both its tables, before it stopped without its manifest. This resume
    # keeps the baseline's, and writes the others' that are missing with the installed parser,
    # which its manifest then names for that response, and in `parsers`, whatever the latest
    # manifest named for the response; the baseline's keeps parser 2.
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"), response("complete.json"))
    assert lab.new("default-only.yaml").error is None
    baseline, default = case_ids(DEFAULT_ONLY)
    listed = f"cases/{baseline}/normalized/metrics.csv"
    normalized = lab.out / "cases" / default / "normalized"
    tables = {name: (normalized / name).read_bytes() for name in ("metrics.csv", "settings.csv")}

    def written_by_parser_2(manifest: Json) -> None:
        artifacts: list[Json] = []
        for artifact in manifest["artifacts"]:
            if artifact["role"] == "provider_response":
                artifact["source"]["parser_version"] = 2
            if artifact["role"] in ("metrics", "settings") and default in artifact["path"]:
                continue
            artifacts.append(artifact)
        manifest["artifacts"] = artifacts
        manifest["parsers"][0]["parser_version"] = 2

    edit_record(lab.out, "sessions/1/manifest.json", written_by_parser_2)
    if left == "none":
        shutil.rmtree(normalized)
    elif left == "metrics":
        (normalized / "settings.csv").unlink()
    rows = read_metrics_csv((lab.out / listed).read_bytes(), "metrics")
    other = [
        row.model_copy(update={"value": _another_digit(row.value)})
        if (row.subject, row.metric_id) == ("strategy", "sharpe_ratio")
        else row
        for row in rows
    ]
    rewrite_record(lab.out, listed, metrics_csv(other))
    parser_2 = (lab.out / listed).read_bytes()

    resumed = lab.resume("default-only.yaml")

    assert resumed.error is None and resumed.received == ()
    assert (lab.out / listed).read_bytes() == parser_2
    assert {name: (normalized / name).read_bytes() for name in tables} == tables
    manifest = lab.manifest(2, ExperimentManifest)
    parsers = {
        artifact.path.split("/")[1]: artifact.source.parser_version
        for artifact in manifest.artifacts
        if artifact.role == "provider_response" and artifact.source is not None
    }
    assert parsers == {baseline: 2, default: 1}
    assert [parser.parser_version for parser in manifest.parsers] == [1, 2]


def _another_digit(value: str | None) -> str:
    """`value` with its last digit changed, so it keeps its decimals."""
    assert value is not None
    return value[:-1] + ("1" if value[-1] != "1" else "2")


def test_a_metrics_table_the_installed_parser_doesnt_write_fails_the_check(lab: Lab) -> None:
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"), response("complete.json"))
    _, default = case_ids(DEFAULT_ONLY)
    lab.new(
        "default-only.yaml",
        arm=lambda store: store.fail_os(f"/cases/{default}/normalized/settings.csv"),
    )
    # As after an upgrade whose parser reads the response differently: the table is valid, but
    # another parser wrote it, with another value.
    path = lab.out / f"cases/{default}/normalized/metrics.csv"
    rows = read_metrics_csv(path.read_bytes(), "metrics")
    changed = [
        row.model_copy(update={"value": _another_digit(row.value)})
        if row.metric_id == "sharpe_ratio" and row.subject == "strategy"
        else row
        for row in rows
    ]
    assert changed != list(rows)
    path.write_bytes(metrics_csv(changed))

    resumed = lab.resume("default-only.yaml")

    error = resumed.refused("input.not_a_run")
    assert "isn't what this version's parser writes" in error.message
    # The version that wrote the session, the installed one: 0.4.0, whose specification R04-T04
    # completed (D-26).
    assert "0.4.0" in error.message
    assert resumed.received == () and not (lab.out / "sessions/2").exists()


# Revisions


def test_a_revision_writes_its_plan_sends_its_new_case_and_retires_the_old_one(
    lab: Lab,
) -> None:
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply("/screen/backtest", *(response("complete.json") for _ in range(6)))
    assert lab.new().error is None
    revised = experiment_plan(EXPERIMENT_CONFIGS / "revisions/holdings-40.yaml")
    old = EXAMPLE.cases[2].case_id

    resumed = lab.resume("revisions/holdings-40.yaml", reason="Holdings of 40, not 50.")

    assert resumed.error is None
    assert resumed.received == (AUTH, BACKTEST)
    # The revision's cases are those of the same configuration as a first plan.
    new_case = revised.cases[2]
    assert new_case.case_key == "holdings-50" and new_case.case_id != old
    assert [json.loads(lab.server.received[-1].body)] == [
        new_case.requests[0].params.model_dump(mode="json")
    ]
    record = ExperimentRecord.model_validate_json(
        (lab.out / "plans/2/experiment.json").read_bytes()
    )
    assert record.plans[-1].reason == "Holdings of 40, not 50."
    assert [case.case_id for case in record.retired_cases] == [old]
    assert (
        record.plans[:-1]
        == ExperimentRecord.model_validate_json(
            (lab.out / "plans/1/experiment.json").read_bytes()
        ).plans
    )
    manifest = lab.manifest(2, ExperimentManifest)
    assert (manifest.plan, manifest.counts.retired_cases) == (2, 1)
    assert manifest.counts.attempts.succeeded == 6
    assert manifest.counts.cases.planned == 5 and manifest.counts.cases.succeeded == 5
    # The retired case and its attempt stay, and are listed.
    assert any(a.path.startswith(f"cases/{old}/attempts/") for a in manifest.artifacts)


def test_a_revision_whose_experiment_json_wasnt_written_isnt_a_plan(lab: Lab) -> None:
    # The run that revised the plan stopped while writing plans/2/experiment.json, so plans/2/
    # isn't a plan, and nothing was sent under it. The same revision, approved again, takes the
    # next number, plans/3/, and plans/2/ is left as it is, and listed nowhere.
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply("/screen/backtest", *(response("complete.json") for _ in range(6)))
    assert lab.new().error is None
    reason = "Holdings of 40, not 50."

    stopped = lab.resume(
        "revisions/holdings-40.yaml",
        reason=reason,
        arm=lambda store: store.fail_os("/plans/2/experiment.json"),
    )
    assert stopped.refused("storage.write_failed")
    assert stopped.received == ()
    assert sorted(p.name for p in (lab.out / "plans/2").iterdir()) == [
        "configuration.yaml",
        "plan.json",
    ]
    assert lab.read().current.number == 1

    resumed = lab.resume("revisions/holdings-40.yaml", reason=reason)

    assert resumed.error is None and resumed.received == (AUTH, BACKTEST)
    record = ExperimentRecord.model_validate_json(
        (lab.out / "plans/3/experiment.json").read_bytes()
    )
    assert [entry.plan for entry in record.plans] == [1, 3]
    assert not (lab.out / "plans/2/experiment.json").exists()
    manifest = lab.manifest(3, ExperimentManifest)
    assert manifest.plan == 3
    assert not any(a.path.startswith("plans/2/") for a in manifest.artifacts)


def test_removing_a_variant_and_bringing_it_back_keeps_its_case_and_attempt(lab: Lab) -> None:
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", *(response("complete.json") for _ in range(5)))
    assert lab.new().error is None

    removed = lab.resume("revisions/variant-removed.yaml", reason="No slippage variant.")
    back = lab.resume("example.yaml", reason="The slippage variant again.")

    assert removed.error is None and back.error is None
    assert removed.received == () and back.received == ()
    assert lab.manifest(2, ExperimentManifest).counts.retired_cases == 1
    assert lab.manifest(3, ExperimentManifest).counts.retired_cases == 0
    assert lab.manifest(3, ExperimentManifest).counts.cases.succeeded == 5
    assert len(lab.attempts(EXAMPLE.cases[4].case_id, AttemptRecordV1_1)) == 1


def test_a_revision_needs_its_hash_and_a_reason(lab: Lab) -> None:
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", *(response("complete.json") for _ in range(5)))
    assert lab.new().error is None
    before = sorted(path for path in lab.out.rglob("*"))

    without_reason = lab.resume("revisions/holdings-40.yaml")
    current_hash = lab.resume(
        "revisions/holdings-40.yaml", approve=EXAMPLE.plan_hash, reason="A reason."
    )

    for ran in (without_reason, current_hash):
        error = ran.refused("plan.changed")
        assert "Nothing was sent" in error.message
        assert ran.received == () and ran.published == ()
    assert sorted(path for path in lab.out.rglob("*")) == before


def test_a_reason_with_no_revision_fails_unless_its_the_current_plans_own(lab: Lab) -> None:
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply("/screen/backtest", *(response("complete.json") for _ in range(6)))
    assert lab.new().error is None
    assert lab.resume("revisions/holdings-40.yaml", reason="Holdings of 40.").error is None

    other = lab.resume("revisions/holdings-40.yaml", reason="Another reason.")
    same = lab.resume("revisions/holdings-40.yaml", reason="Holdings of 40.")

    assert other.refused("plan.approval_required").message.startswith(
        "A reason for a revision was given, but there's no revision."
    )
    assert other.published == ()
    assert same.error is None and same.received == ()
    assert not (lab.out / "plans/3").exists()
    assert lab.manifest(3, ExperimentManifest).plan == 2


def test_a_new_experiment_takes_no_reason_and_no_repeat(tmp_path: Path) -> None:
    plan = EXAMPLE
    client = SyntheticScreenBacktestClient(response_bytes())
    with LocalArtifactStore(tmp_path / "new") as store:
        with pytest.raises(TrialFolioError) as reason:
            ExperimentExecution(
                plan, plan.plan_hash, "not_required", store, client, command=None, reason="Why."
            )
        with pytest.raises(TrialFolioError) as repeat:
            ExperimentExecution(
                plan,
                plan.plan_hash,
                "not_required",
                store,
                client,
                command=None,
                repeats=[Repeat(case_ids(plan)[0], uuid.uuid4())],
            )
    assert reason.value.code == repeat.value.code == "plan.approval_required"
    assert not (tmp_path / "new").exists()


# Repeats


def _unknown_baseline(lab: Lab) -> uuid.UUID:
    """Runs `default-only.yaml` with a 503 to the baseline's request, which leaves it `unknown`,
    awaiting a repeat, and returns its attempt's ID."""
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", Reply(503), response("complete.json"))
    assert lab.new("default-only.yaml").refused("execution.partial")
    (record,) = lab.attempts(DEFAULT_ONLY.cases[0].case_id, AttemptRecordV1_1)
    assert record.outcome == "unknown"
    return record.attempt_id


def test_a_repeat_the_budget_cant_cover_waits_for_a_revision_that_raises_it(
    lab: Lab, tmp_path: Path
) -> None:
    attempt_id = _unknown_baseline(lab)
    baseline = DEFAULT_ONLY.cases[0].case_id
    repeat = Repeat(baseline, attempt_id)

    # The budget, 2 requests, is spent: the repeat isn't started, and its confirmation stays
    # unused (the budget).
    spent = lab.resume("default-only.yaml", repeats=[repeat])

    error = spent.refused("execution.partial")
    assert spent.received == ()
    assert "budget couldn't cover the next case" in error.message
    assert spent.execution is not None and spent.execution.repeats_used == ()
    # A revision that raises the budget lets the same confirmation repeat it.
    raised = tmp_path / "default-only-budget-3.yaml"
    raised.write_bytes(
        (EXPERIMENT_CONFIGS / "default-only.yaml")
        .read_bytes()
        .replace(b"provider_requests: 2", b"provider_requests: 3")
    )
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"))
    revised = lab.resume(raised, reason="A third request, for the repeat.", repeats=[repeat])
    assert revised.error is None and revised.received == (AUTH, BACKTEST)
    assert lab.attempts(baseline, AttemptRecordV1_1)[-1].repeat_of == attempt_id
    counts = lab.manifest(3, ExperimentManifest).counts
    assert (counts.provider_requests, counts.budget.provider_requests, counts.attempts.repeats) == (
        3,
        3,
        1,
    )


def test_a_repeat_names_the_unknown_attempt_and_isnt_made_twice(lab: Lab) -> None:
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", Reply(503), response("complete.json"))
    assert lab.new("example.yaml", cancel_after=2).refused("execution.partial")
    baseline = EXAMPLE.cases[0].case_id
    (unknown,) = lab.attempts(baseline, AttemptRecordV1_1)
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply("/screen/backtest", Reply(503), *(response("complete.json") for _ in range(4)))
    repeat = Repeat(baseline, unknown.attempt_id)

    first = lab.resume(repeats=[repeat])

    assert first.refused("execution.partial")
    assert first.received == (AUTH, BACKTEST, BACKTEST, BACKTEST, BACKTEST)
    _, again = lab.attempts(baseline, AttemptRecordV1_1)
    assert (again.repeat_of, again.outcome) == (unknown.attempt_id, "unknown")
    assert lab.manifest(2, ExperimentManifest).counts.attempts.repeats == 1
    # The repeat is now the case's latest possibly charged attempt, which a new confirmation names.
    latest = lab.read().cases(EXAMPLE)[0].latest_charged
    assert latest is not None and latest.attempt_id == again.attempt_id
    # The same command again: the repeat may have reached Portfolio123, so its confirmation is
    # used, and the case isn't repeated a second time.
    second = lab.resume(repeats=[repeat])
    assert second.refused("execution.partial") and second.received == ()
    assert second.execution is not None and second.execution.repeats_used == (repeat,)
    # A new confirmation names the repeat's own attempt, once a revision makes room for it: the
    # budget's 6 requests are spent.
    third = lab.resume(
        "revisions/budget-raised.yaml",
        reason="Room for another repeat.",
        repeats=[Repeat(baseline, again.attempt_id)],
    )
    assert third.error is None and third.received == (AUTH, BACKTEST)
    assert lab.attempts(baseline, AttemptRecordV1_1)[-1].repeat_of == again.attempt_id
    assert lab.manifest(4, ExperimentManifest).counts.attempts.repeats == 2


def test_a_repeat_whose_authentication_fails_leaves_its_confirmation_unused(lab: Lab) -> None:
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", Reply(503), response("complete.json"))
    lab.new("example.yaml", cancel_after=2)
    baseline = EXAMPLE.cases[0].case_id
    (unknown,) = lab.attempts(baseline, AttemptRecordV1_1)
    repeat = Repeat(baseline, unknown.attempt_id)
    lab.server.reply("/auth", Reply(401))

    failed = lab.resume(repeats=[repeat])

    assert failed.refused("execution.partial")
    assert failed.received == (AUTH,)
    _, attempt = lab.attempts(baseline, AttemptRecordV1_1)
    assert (attempt.repeat_of, attempt.possibly_charged) == (unknown.attempt_id, False)
    # Still unknown, by its latest possibly charged attempt.
    assert failed.outcomes[0] == "unknown"
    # A repeat names an attempt whose request may have been charged, never one that sent nothing.
    uncharged = lab.resume(repeats=[Repeat(baseline, attempt.attempt_id)])
    error = uncharged.refused("plan.approval_required")
    assert "isn't an attempt of the case whose request may have been charged" in error.message
    assert uncharged.received == () and uncharged.published == ()
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", *(response("complete.json") for _ in range(4)))
    again = lab.resume(repeats=[repeat])
    assert again.error is None and again.received == (AUTH, BACKTEST, BACKTEST, BACKTEST, BACKTEST)
    assert lab.attempts(baseline, AttemptRecordV1_1)[-1].repeat_of == unknown.attempt_id


def test_d32s_stop_in_a_resume_needs_a_later_case_the_session_sends(
    lab: Lab, caplog: pytest.LogCaptureFixture
) -> None:
    # Only the second case awaits a repeat, and the cases after it are complete, so its repeat is
    # the session's only send. Its authentication fails, but no case the session sends or repeats
    # remains, so D-32's stop doesn't apply, though later cases of the plan do remain.
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply(
        "/screen/backtest",
        response("complete.json"),
        Reply(503),
        response("complete.json"),
        response("complete.json"),
        response("complete.json"),
    )
    assert lab.new().refused("execution.partial")
    liquidity = EXAMPLE.cases[1].case_id
    (unknown,) = lab.attempts(liquidity, AttemptRecordV1_1)
    lab.server.reply("/auth", Reply(401))

    with caplog.at_level(logging.WARNING, logger="trialfolio"):
        failed = lab.resume(repeats=[Repeat(liquidity, unknown.attempt_id)])

    error = failed.refused("execution.partial")
    assert failed.received == (AUTH,)
    assert failed.outcomes == ["succeeded", "unknown", "succeeded", "succeeded", "succeeded"]
    assert "no later case started" not in error.message
    assert "authentication call failed" not in error.message
    assert not [r for r in caplog.records if getattr(r, "event", None) == "experiment.stopped"]


def test_the_repeats_are_checked_before_the_approval(lab: Lab) -> None:
    # Steps 5 and 6: a revision without its reason, and with a repeat that names a due case,
    # fails for the repeat, which is checked first.
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", Reply(503), response("complete.json"))
    lab.new("example.yaml", cancel_after=2)
    baseline, due = EXAMPLE.cases[0].case_id, EXAMPLE.cases[3].case_id
    (unknown,) = lab.attempts(baseline, AttemptRecordV1_1)
    revised = experiment_plan(EXPERIMENT_CONFIGS / "revisions/holdings-40.yaml")
    assert due in case_ids(revised)

    ran = lab.resume("revisions/holdings-40.yaml", repeats=[Repeat(due, unknown.attempt_id)])

    error = ran.refused("plan.approval_required")
    assert "isn't awaiting a repeat" in error.message
    assert ran.received == () and ran.published == ()


@pytest.mark.parametrize("which", ["no-case", "due", "other-attempt", "succeeded", "twice"])
def test_a_repeat_that_cant_apply_fails_before_anything_is_written(lab: Lab, which: str) -> None:
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", Reply(503), response("complete.json"))
    lab.new("example.yaml", cancel_after=2)
    baseline, liquidity, holdings = case_ids(EXAMPLE)[:3]
    (unknown,) = lab.attempts(baseline, AttemptRecordV1_1)
    (succeeded,) = lab.attempts(liquidity, AttemptRecordV1_1)
    repeats = {
        "no-case": [Repeat("case-0000000000000000", unknown.attempt_id)],
        "due": [Repeat(holdings, unknown.attempt_id)],
        "other-attempt": [Repeat(baseline, succeeded.attempt_id)],
        "succeeded": [Repeat(liquidity, succeeded.attempt_id)],
        "twice": [Repeat(baseline, unknown.attempt_id)] * 2,
    }[which]
    before = sorted(path for path in lab.out.rglob("*"))

    if which == "twice":
        with pytest.raises(ValueError, match="once"):
            lab.resume(repeats=repeats)
    else:
        ran = lab.resume(repeats=repeats)
        error = ran.refused("plan.approval_required")
        assert ran.received == () and ran.published == ()
        assert "Nothing was sent" in error.message
        problem = {
            "no-case": "which the plan doesn't include",
            "due": "isn't awaiting a repeat",
            "other-attempt": "isn't an attempt of the case whose request may have been charged",
            "succeeded": "isn't an attempt of the case whose request may have been charged",
        }[which]
        assert problem in error.message
        assert "liquidity" not in error.log_message and "holdings" not in error.log_message
    assert sorted(path for path in lab.out.rglob("*")) == before


# Synthetic experiments, and the lock


def test_a_synthetic_experiment_resumes_only_with_the_demos_client(lab: Lab) -> None:
    assert lab.new("default-only.yaml", synthetic=True, cancel_after=1).error is not None

    real = lab.resume("default-only.yaml")
    synthetic = lab.resume("default-only.yaml", synthetic=True)

    assert "synthetic experiment" in real.refused("output.not_empty").message
    assert real.published == ()
    assert synthetic.error is None and synthetic.received == ()
    manifest = lab.manifest(2, ExperimentManifest)
    assert (manifest.synthetic, manifest.approval, manifest.counts.cases.succeeded) == (
        True,
        "not_required",
        2,
    )


def test_the_demos_client_cant_resume_an_experiment_that_isnt_synthetic(lab: Lab) -> None:
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"))
    lab.new("default-only.yaml", cancel_after=1)

    ran = lab.resume("default-only.yaml", synthetic=True)

    assert "attempts are real" in ran.refused("output.not_empty").message
    assert ran.published == () and not (lab.out / "sessions/2").exists()


def test_the_demos_client_cant_resume_an_experiment_the_builder_wrote(
    lab: Lab, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The experiment is trialfolio run's, as the experiment builder writes it, with its command
    # record and its logs; another interface then gives the core the demo's client for it.
    cli = Cli(monkeypatch, tmp_path, lab.server)
    cli.ready()
    built = ExperimentBuilder(lab.server, cli).run(
        EXPERIMENT_CONFIGS / "default-only.yaml",
        lab.out,
        sends=[response("complete.json"), response("complete.json")],
    )
    assert built.exit_code == 0, built.stderr
    assert lab.manifest(1, ExperimentManifest).command is not None and (lab.out / "logs").is_dir()
    before = snapshot(lab.out)

    ran = lab.resume("default-only.yaml", synthetic=True)

    assert "attempts are real" in ran.refused("output.not_empty").message
    assert ran.received == () and ran.published == ()
    assert snapshot(lab.out) == before


def test_opening_an_experiment_takes_its_lock(lab: Lab, tmp_path: Path) -> None:
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"), response("complete.json"))
    lab.new("default-only.yaml")

    with LocalArtifactStore(lab.out) as holder:
        open_experiment(holder)
        with LocalArtifactStore(lab.out) as other, pytest.raises(TrialFolioError) as caught:
            open_experiment(other)
    assert caught.value.code == "experiment.locked"
    (tmp_path / "other").mkdir()
    (tmp_path / "other/notes.txt").write_text("not an experiment")
    with LocalArtifactStore(tmp_path / "other") as store, pytest.raises(TrialFolioError) as not_one:
        open_experiment(store)
    assert not_one.value.code == "output.not_empty"


# The records check (R03-AC17)


def _attempt_of(out: Path, case: int) -> str:
    """The directory of the one attempt of `EXAMPLE`'s case at that place."""
    (directory,) = sorted((out / "cases" / EXAMPLE.cases[case].case_id / "attempts").iterdir())
    return directory.relative_to(out).as_posix()


def _completed(lab: Lab) -> None:
    """A complete experiment of `example.yaml`: its first two cases in session 1, the rest in
    session 2, and a revision that renames a key, and sends nothing, in session 3."""
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply("/screen/backtest", *(response("complete.json") for _ in range(5)))
    lab.new(cancel_after=2)
    assert lab.resume().error is None
    assert lab.resume("revisions/key-renamed.yaml", reason="A clearer key.").error is None


def _stray(out: Path, path: str) -> None:
    """Adds a file the layout doesn't have, or that no manifest lists."""
    (out / path).parent.mkdir(parents=True, exist_ok=True)
    (out / path).write_bytes(b"stray\n")


def _revision_changed(out: Path, **fields: object) -> None:
    """Changes the revision's plan, with its hash recomputed, and its `experiment.json` and the
    latest manifest's entries to match, so only the check under test can tell: the revision
    sent nothing, so no attempt names it."""
    plan = PlanV1_1.model_validate_json((out / "plans/2/plan.json").read_bytes())
    draft = plan.model_copy(update=fields)
    other = draft.model_copy(update={"plan_hash": plan_hash(draft)})
    data = (other.model_dump_json(indent=2) + "\n").encode()
    rewrite_record(out, "plans/2/plan.json", data)

    def record(content: Json) -> None:
        if "experiment_id" in fields:
            content["experiment_id"] = fields["experiment_id"]
        content["plans"][-1].update(
            plan_hash=other.plan_hash, plan_artifact_id="sha256:" + sha256_hex(data)
        )

    edit_record(out, "plans/2/experiment.json", record)


def _table(out: Path, case: int, name: str, change: dict[str, str]) -> None:
    """Changes a field of every row of the case's table, which stays valid."""
    path = f"cases/{EXAMPLE.cases[case].case_id}/normalized/{name}"
    if name == "metrics.csv":
        metrics = read_metrics_csv((out / path).read_bytes(), name)
        data = metrics_csv([row.model_copy(update=change) for row in metrics])
    else:
        settings = read_settings_csv((out / path).read_bytes(), name)
        data = settings_csv([row.model_copy(update=change) for row in settings])
    rewrite_record(out, path, data)


def _without_last_row(out: Path, case: int, name: str) -> None:
    """Drops the last row of the case's table, which stays a valid table."""
    path = f"cases/{EXAMPLE.cases[case].case_id}/normalized/{name}"
    if name == "metrics.csv":
        data = metrics_csv(read_metrics_csv((out / path).read_bytes(), name)[:-1])
    else:
        data = settings_csv(read_settings_csv((out / path).read_bytes(), name)[:-1])
    rewrite_record(out, path, data)


def _manifest_of_session_2(out: Path) -> None:
    """Changes the latest manifest, `sessions/3/manifest.json`, to name session 2, with its own
    session's files those of `sessions/2/`, so its model accepts it."""

    def change(manifest: Json) -> None:
        manifest["session"] = 2
        for artifact in manifest["artifacts"]:
            if artifact["path"].startswith("sessions/3/"):
                path = artifact["path"].replace("sessions/3/", "sessions/2/")
                data = (out / path).read_bytes()
                artifact.update(path=path, artifact_id="sha256:" + sha256_hex(data), size=len(data))

    edit_record(out, "sessions/3/manifest.json", change)


def _attempt_id(out: Path, case: int) -> str:
    """The `attempt_id` of the one attempt of `EXAMPLE`'s case at that place."""
    return json.loads((out / _attempt_of(out, case) / "attempt.json").read_bytes())["attempt_id"]


def _first_attempt_id(out: Path) -> str:
    return _attempt_id(out, 0)


_ANOTHER_ATTEMPT = str(uuid.uuid4())

BREAKS: dict[str, tuple[Callable[[Path], object], str]] = {
    "a listed file missing": (
        lambda out: (out / _attempt_of(out, 0) / "attempt.json").unlink(),
        "which is missing",
    ),
    "the first plan's experiment.json missing": (
        lambda out: (out / "plans/1/experiment.json").unlink(),
        "which is missing",
    ),
    "a listed file changed": (
        lambda out: (out / "plans/1/configuration.yaml").write_bytes(b"changed\n"),
        "doesn't match its artifact_id in the latest manifest",
    ),
    "a plan that doesn't recompute": (
        lambda out: edit_record(
            out, "plans/1/plan.json", lambda d: d.update(title="Another title")
        ),
        "doesn't recompute to its plan_hash",
    ),
    "experiment.json's last entry, by number": (
        lambda out: edit_record(
            out, "plans/2/experiment.json", lambda d: d["plans"][-1].update(plan=3)
        ),
        "last entry isn't its directory's plan: it gives another number",
    ),
    "experiment.json's last entry, by hash": (
        lambda out: edit_record(
            out,
            "plans/2/experiment.json",
            lambda d: d["plans"][-1].update(plan_hash="sha256:" + "0" * 64),
        ),
        "it gives another plan_hash than its plan.json",
    ),
    "experiment.json's last entry, by artifact_id": (
        lambda out: edit_record(
            out,
            "plans/2/experiment.json",
            lambda d: d["plans"][-1].update(configuration_artifact_id="sha256:" + "0" * 64),
        ),
        "has another artifact_id than it records",
    ),
    "experiment.json's last entry, by plan.json's artifact_id": (
        lambda out: edit_record(
            out,
            "plans/2/experiment.json",
            lambda d: d["plans"][-1].update(plan_artifact_id="sha256:" + "0" * 64),
        ),
        "has another artifact_id than it records",
    ),
    "experiment.json's earlier entries": (
        lambda out: edit_record(
            out, "plans/2/experiment.json", lambda d: d["plans"][0].update(approval="interactive")
        ),
        "earlier entries aren't those of the previous plan's",
    ),
    "a manifest that disagrees with the plans' approval": (
        lambda out: edit_record(
            out,
            "sessions/3/manifest.json",
            lambda d: d.update(synthetic=True, approval="not_required"),
        ),
        "is synthetic, though the experiment's plans don't record",
    ),
    "an attempt naming a case its plan doesn't have": (
        lambda out: copy_attempt(
            out, _attempt_of(out, 3), case_id="case-0123456789abcdef", sequence=9
        ),
        "name a case their plan doesn't have",
    ),
    "an attempt naming a plan the experiment doesn't have": (
        lambda out: edit_attempt(
            out, _attempt_of(out, 3), lambda d: d.update(plan_hash="sha256:" + "1" * 64)
        ),
        "name a plan the experiment doesn't have",
    ),
    "records that name another attempt than their directory's": (
        lambda out: edit_attempt(
            out, _attempt_of(out, 3), lambda d: d.update(attempt_id=_ANOTHER_ATTEMPT)
        ),
        "name another attempt",
    ),
    "an attempt naming a session the experiment doesn't have": (
        lambda out: edit_attempt(out, _attempt_of(out, 3), lambda d: d.update(session=9)),
        "name a session the experiment doesn't have",
    ),
    "two attempts of a session with one sequence": (
        lambda out: edit_attempt(out, _attempt_of(out, 3), lambda d: d.update(sequence=1)),
        "have the same sequence",
    ),
    "a request sent with another session's token": (
        lambda out: edit_attempt(
            out, _attempt_of(out, 3), lambda d: d.update(authenticated_by=_first_attempt_id(out))
        ),
        "was sent with a token no attempt of its session obtained",
    ),
    # The fifth case's request, sent with the token of the fourth, which sent with the third's.
    "a request sent with the token of an attempt that didn't authenticate": (
        lambda out: edit_attempt(
            out, _attempt_of(out, 4), lambda d: d.update(authenticated_by=_attempt_id(out, 3))
        ),
        "was sent with a token no attempt of its session obtained",
    ),
    "a repeat_of that names no charged attempt": (
        lambda out: edit_attempt(
            out, _attempt_of(out, 3), lambda d: d.update(repeat_of=_ANOTHER_ATTEMPT)
        ),
        "names in repeat_of an attempt",
    ),
    "an attempt after its case's succeeded attempt": (
        lambda out: copy_attempt(
            out, _attempt_of(out, 3), sequence=9, repeat_of=_first_attempt_id(out)
        ),
        "follows its case's succeeded attempt",
    ),
    "a table in a case without a succeeded attempt": (
        lambda out: shutil.copytree(
            out / "cases" / EXAMPLE.cases[0].case_id / "normalized",
            out / "cases" / "case-0123456789abcdef" / "normalized",
        ),
        "has normalized tables, but no succeeded attempt",
    ),
    # Tables are written after the attempt record, so a running attempt's case has none.
    "tables beside an attempt without its attempt record": (
        lambda out: unlist_record(out, f"{_attempt_of(out, 1)}/attempt.json"),
        "has normalized tables, but no succeeded attempt",
    ),
    "settings.csv without its metrics.csv": (
        lambda out: _stray(out, "cases/case-0123456789abcdef/normalized/settings.csv"),
        "is there without its metrics.csv",
    ),
    "a listed table missing": (
        lambda out: (out / "cases" / EXAMPLE.cases[0].case_id / "normalized/metrics.csv").rename(
            out / "cases" / EXAMPLE.cases[0].case_id / "normalized/.metrics.csv"
        ),
        "which is missing",
    ),
    "a stray file in an attempt's directory": (
        lambda out: _stray(out, f"{_attempt_of(out, 1)}/notes.txt"),
        "holds a file no attempt writes",
    ),
    "a stray entry in plans/": (
        lambda out: _stray(out, "plans/latest/plan.json"),
        "holds an entry that isn't a numbered directory",
    ),
    "a stray entry in cases/": (
        lambda out: _stray(out, "cases/notes.txt"),
        "holds an entry that isn't a case's directory",
    ),
    "a stray entry in a case's directory": (
        lambda out: _stray(out, f"cases/{EXAMPLE.cases[1].case_id}/notes.txt"),
        "holds an entry no case has",
    ),
    "a stray entry in a case's attempts": (
        lambda out: _stray(out, f"cases/{EXAMPLE.cases[1].case_id}/attempts/notes.txt"),
        "holds an entry that isn't an attempt's directory",
    ),
    "a stray file in a plan's directory": (
        lambda out: _stray(out, "plans/2/notes.txt"),
        "holds a file no plan has",
    ),
    "a stray file in a session's directory": (
        lambda out: _stray(out, "sessions/2/notes.txt"),
        "holds a file no session has",
    ),
    "a session record that names another session": (
        lambda out: edit_record(out, "sessions/1/session.json", lambda d: d.update(session=2)),
        "`sessions/1/session.json` names another session than its directory's",
    ),
    # Not an experiment's, whatever its version: the type is checked before the version.
    "a manifest that isn't an experiment's": (
        lambda out: edit_record(
            out,
            "sessions/3/manifest.json",
            lambda d: d.update(artifact_type="run", schema_version="9.9.9"),
        ),
        "isn't an experiment's manifest",
    ),
    "a manifest that names another session": (
        _manifest_of_session_2,
        "`sessions/3/manifest.json` names another session than its directory's",
    ),
    "an attempt record that doesn't hold its start record's": (
        lambda out: edit_record(
            out,
            f"{_attempt_of(out, 1)}/attempt.json",
            lambda d: d["transport"].update(urllib3="2.8.1"),
        ),
        "the attempt record doesn't hold its start record's",
    ),
    "records that give an attempt two starts": (
        lambda out: edit_record(
            out,
            f"{_attempt_of(out, 1)}/attempt.json",
            lambda d: d.update(started_at="2026-10-03T13:00:00Z", ended_at="2026-10-03T13:00:01Z"),
        ),
        "they give it another plan, place, or start",
    ),
    "an attempt that authenticated without its authentication record": (
        lambda out: unlist_record(out, f"{_attempt_of(out, 0)}/authenticating.json"),
        "exactly when it has its authentication record",
    ),
    "a file an attempt record references, changed": (
        lambda out: rewrite_record(
            out, f"{_attempt_of(out, 1)}/request.json", b'{"another": "request"}\n'
        ),
        "doesn't match the artifact_id its attempt record gives it",
    ),
    "an experiment.json that doesn't record its plan's declaration": (
        lambda out: edit_record(
            out, "plans/2/experiment.json", lambda d: d.update(title="Another")
        ),
        "doesn't record the experiment and its planned cases as its plan declares them",
    ),
    "an experiment.json that doesn't record its plan's cases": (
        lambda out: edit_record(
            out,
            "plans/2/experiment.json",
            lambda d: d["planned_cases"][1].update(description="Another description."),
        ),
        "doesn't record the experiment and its planned cases as its plan declares them",
    ),
    "a plan of another experiment": (
        lambda out: _revision_changed(out, experiment_id="another-experiment"),
        "is another experiment's plan",
    ),
    "a plan that doesn't revise the previous one": (
        lambda out: _revision_changed(out, revises="sha256:" + "0" * 64),
        "doesn't revise the previous plan",
    ),
    "a manifest of another experiment": (
        lambda out: edit_record(
            out, "sessions/3/manifest.json", lambda d: d.update(experiment_id="another-one")
        ),
        "is another experiment's manifest",
    ),
    "a manifest that names a plan the experiment doesn't have": (
        lambda out: edit_record(
            out, "sessions/3/manifest.json", lambda d: d.update(plan_hash="sha256:" + "0" * 64)
        ),
        "names a plan the experiment doesn't have",
    ),
    "an attempt record that names a token without its start record": (
        lambda out: unlist_record(out, f"{_attempt_of(out, 1)}/started.json"),
        "the attempt record names a token, without a start record",
    ),
    "an attempt record that references a file outside its directory": (
        lambda out: edit_record(
            out,
            f"{_attempt_of(out, 1)}/attempt.json",
            lambda d: d["request"].update(path=f"{_attempt_of(out, 2)}/request.json"),
        ),
        "references a file that isn't in its directory",
    ),
    "a stray file in a case's tables": (
        lambda out: _stray(out, f"cases/{EXAMPLE.cases[1].case_id}/normalized/notes.txt"),
        "holds a file no case has",
    ),
    "a metrics.csv labeled with another case": (
        lambda out: _table(out, 1, "metrics.csv", {"label": EXAMPLE.cases[2].case_id}),
        "labels its rows with another case",
    ),
    "a metrics.csv without one of the layout's metrics": (
        lambda out: _without_last_row(out, 1, "metrics.csv"),
        "doesn't hold one row for each of the layout's metrics",
    ),
    "a settings.csv without one of its plan's settings": (
        lambda out: _without_last_row(out, 1, "settings.csv"),
        "doesn't hold one row for each of its plan's settings",
    ),
    "a metrics.csv drawn from another response": (
        lambda out: _table(out, 1, "metrics.csv", {"source_artifact": "sha256:" + "0" * 64}),
        "was drawn from another response",
    ),
    "a settings.csv labeled with another case": (
        lambda out: _table(out, 1, "settings.csv", {"label": EXAMPLE.cases[2].case_id}),
        "settings.csv` labels its rows with another case",
    ),
    "a settings.csv drawn from another configuration": (
        lambda out: _table(out, 1, "settings.csv", {"source_artifact": "sha256:" + "0" * 64}),
        "was drawn from another configuration",
    ),
}


@pytest.mark.parametrize("name", sorted(BREAKS))
def test_records_that_are_broken_fail_the_check_and_nothing_is_written(lab: Lab, name: str) -> None:
    _completed(lab)
    breaking, problem = BREAKS[name]
    breaking(lab.out)
    before = snapshot(lab.out)

    ran = lab.resume("revisions/key-renamed.yaml")

    error = ran.refused("input.not_a_run")
    assert problem in error.message
    assert ran.received == () and ran.published == ()
    assert snapshot(lab.out) == before


@pytest.mark.parametrize(
    ("path", "listed"),
    [
        ("plans/2/experiment.json", False),
        ("plans/2/plan.json", False),
        ("sessions/1/session.json", False),
        ("sessions/3/manifest.json", False),
        ("{attempt}/authenticating.json", False),
        ("{attempt}/started.json", False),
        ("{attempt}/attempt.json", False),
        ("plans/1/plan.json", True),
    ],
)
def test_a_schema_version_without_a_reader_fails_the_check(
    lab: Lab, path: str, listed: bool
) -> None:
    _completed(lab)
    path = path.format(attempt=_attempt_of(lab.out, 0))
    if listed:
        edit_record(
            lab.out,
            "sessions/3/manifest.json",
            lambda d: next(a for a in d["artifacts"] if a["path"] == path).update(
                schema_version="9.9.9"
            ),
        )
    else:
        edit_record(lab.out, path, lambda d: d.update(schema_version="9.9.9"))

    ran = lab.resume("revisions/key-renamed.yaml")

    error = ran.refused("artifact.unknown_schema_version")
    assert f"`{path}`" in error.message
    assert ("the latest manifest gives it" in error.message) == listed
    assert ran.published == ()


def test_a_saved_configuration_whose_schema_version_has_no_reader_fails_the_check(
    lab: Lab,
) -> None:
    # A plan's configuration.yaml that no manifest lists, as when the run that recorded its plan
    # stopped before its manifest, gives its own schema version, and one without a reader fails
    # as a record's does, not as a broken record.
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"))
    lab.new("default-only.yaml", arm=lambda store: store.fail_os("attempt.json"))
    path = "plans/1/configuration.yaml"
    data = (lab.out / path).read_bytes().replace(b"schema_version: 1.0.0", b"schema_version: 9.9.9")
    assert b"9.9.9" in data
    (lab.out / path).write_bytes(data)
    # Its experiment.json records the file's new artifact_id, so only the version can fail.
    record = json.loads((lab.out / "plans/1/experiment.json").read_bytes())
    record["plans"][-1]["configuration_artifact_id"] = "sha256:" + sha256_hex(data)
    (lab.out / "plans/1/experiment.json").write_text(json.dumps(record, indent=2) + "\n")

    ran = lab.resume("default-only.yaml")

    error = ran.refused("artifact.unknown_schema_version")
    assert f"`{path}`" in error.message
    assert "It reads experiment configurations 1.0.0." in error.message
    assert ran.received == () and ran.published == ()


@pytest.mark.parametrize("status", [401, 403])
def test_a_request_sent_with_a_token_a_401_or_403_dropped_fails_the_check(
    lab: Lab, status: int
) -> None:
    # The second case's request got a 401 or 403, which dropped the token the first case
    # obtained, so the third case authenticated again. A copy of the fifth case's attempt that
    # names the first case's token can't have been sent.
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply(
        "/screen/backtest",
        response("complete.json"),
        Reply(status),
        response("complete.json"),
        response("complete.json"),
        response("complete.json"),
    )
    assert lab.new().refused("execution.partial")
    copy_attempt(
        lab.out, _attempt_of(lab.out, 4), sequence=9, authenticated_by=_first_attempt_id(lab.out)
    )

    ran = lab.resume()

    error = ran.refused("input.not_a_run")
    assert "a token that a 401 or 403 to an earlier request had dropped" in error.message
    assert ran.received == () and ran.published == ()


def test_a_request_sent_with_a_later_attempts_token_fails_the_check(lab: Lab) -> None:
    # The second case's request got a 403, so the third case authenticated again. The second
    # case's records, changed to name the third case's token, name one obtained after its send.
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply(
        "/screen/backtest",
        response("complete.json"),
        Reply(403),
        response("complete.json"),
        response("complete.json"),
        response("complete.json"),
    )
    assert lab.new().refused("execution.partial")
    later = json.loads((lab.out / _attempt_of(lab.out, 2) / "attempt.json").read_bytes())
    edit_attempt(
        lab.out, _attempt_of(lab.out, 1), lambda d: d.update(authenticated_by=later["attempt_id"])
    )

    ran = lab.resume()

    error = ran.refused("input.not_a_run")
    assert "was sent with a token no attempt of its session obtained before it" in error.message
    assert ran.received == () and ran.published == ()


def test_an_attempt_sent_again_without_a_confirmed_repeat_fails_the_check(lab: Lab) -> None:
    attempt_id = _unknown_baseline(lab)
    baseline = DEFAULT_ONLY.cases[0].case_id
    raised = (
        (EXPERIMENT_CONFIGS / "default-only.yaml")
        .read_bytes()
        .replace(b"provider_requests: 2", b"provider_requests: 3")
    )
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"))
    (lab.out.parent / "raised.yaml").write_bytes(raised)
    repeat = Repeat(baseline, attempt_id)
    assert (
        lab.resume(lab.out.parent / "raised.yaml", reason="More.", repeats=[repeat]).error is None
    )
    (_, repeated) = sorted(
        (lab.out / "cases" / baseline / "attempts").iterdir(),
        key=lambda p: json.loads((p / "attempt.json").read_bytes())["session"],
    )
    for name in ("authenticating.json", "started.json", "attempt.json"):
        edit_record(
            lab.out,
            f"{repeated.relative_to(lab.out).as_posix()}/{name}",
            lambda d: d.update(repeat_of=None),
        )

    ran = lab.resume(lab.out.parent / "raised.yaml")

    error = ran.refused("input.not_a_run")
    assert "without a confirmed repeat of it" in error.message


def test_an_attempt_record_with_an_authentication_but_no_record_of_it_fails_the_check(
    lab: Lab,
) -> None:
    # Trial Folio's own authentication call got a 401, so the attempt record holds its exchange,
    # and the attempt has no start record: its authentication record must be there.
    lab.server.reply("/auth", Reply(401))
    assert lab.new("default-only.yaml").refused("execution.partial")
    (directory,) = lab.attempt_directories(DEFAULT_ONLY.cases[0].case_id)
    unlist_record(lab.out, f"{directory.relative_to(lab.out).as_posix()}/authenticating.json")

    ran = lab.resume("default-only.yaml")

    error = ran.refused("input.not_a_run")
    assert "authenticated without writing its authentication record" in error.message


def test_a_synthetic_experiments_manifest_that_isnt_synthetic_fails_the_check(lab: Lab) -> None:
    assert lab.new("default-only.yaml", synthetic=True).error is None
    edit_record(
        lab.out, "sessions/1/manifest.json", lambda d: d.update(synthetic=False, approval="option")
    )

    ran = lab.resume("default-only.yaml", synthetic=True)

    assert "isn't synthetic, though" in ran.refused("input.not_a_run").message


def test_resuming_needs_the_plans_own_hash(lab: Lab) -> None:
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"))
    lab.new("default-only.yaml", cancel_after=1)

    ran = lab.resume("default-only.yaml", approve="sha256:" + "0" * 64)

    ran.refused("plan.approval_required")
    assert ran.received == () and ran.published == ()


def test_a_directory_whose_first_plan_wasnt_recorded_cant_be_resumed(lab: Lab) -> None:
    first = lab.new(arm=lambda store: store.fail_os("/plans/1/experiment.json"))
    assert first.refused("storage.write_failed")

    ran = lab.resume()

    error = ran.refused("output.not_empty")
    assert "Remove the directory, and run the command again" in error.message
    assert ran.published == ()
