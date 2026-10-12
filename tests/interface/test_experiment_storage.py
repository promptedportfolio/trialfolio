"""A storage failure or an interrupt during `trialfolio run` with an experiment's configuration
exits with `storage.write_failed` and 4, or `command.interrupted` and 130, leaves its session
without a manifest, writes no file twice, and replaces no record. Before the first plan's
`experiment.json` is written, nothing was sent, and the message says the directory can't be
resumed, and to remove it: the same command then fails with `output.not_empty`, and says so too.
After it, the message says the output is incomplete until the same command resumes the
experiment, which it then does, sending only the cases that are due. A 200 whose response couldn't
be saved leaves its case `unknown`, and possibly charged. On Linux and macOS, a file system
without hard links fails at `sessions/1/session.json`, before any request.

Traces to R03-AC19, and to docs/contracts.md: running an experiment (an ending without a
manifest, and step 4's directory without `plans/1/experiment.json`), experiment output (a session
ends with its manifest), endings that decide the error code, and artifact storage (atomic writes
that never replace a file, and no hard links). Through the CLI's entry function in the test
process, over the fake server, with storage faults wrapping the real store, at a whole path, such
as `/sessions/1/session.json`, or at a file of a case, in its attempt or its `normalized/`. A
failure after the store published the manifest stands for its directory's sync failing: the
session discards it, as a run does (CLI behavior, what a run writes after its attempt).
"""

import re
import sys
from pathlib import Path
from typing import Final, cast

import pytest

from tests.interface.conftest import Cli, FaultyStores, Outcome, snapshot
from tests.support.experiment_builder import (
    ExperimentBuilder,
    experiment_config,
    plan_hash,
    returns,
)
from tests.support.storage_faults import placeholder_identities
from trialfolio.configuration import read_experiment_configuration
from trialfolio.contracts.attempt import AttemptRecordV1_1
from trialfolio.contracts.experiment_plan import ExperimentPlanCase
from trialfolio.errors import TrialFolioError
from trialfolio.planning import build_experiment_plan, installed_versions

DEFAULT_ONLY = experiment_config("default-only.yaml")
EXAMPLE = experiment_config("example.yaml")

FAULTS: Final = {
    "session-record": "/sessions/1/session.json",
    "plan": "/plans/1/plan.json",
    "experiment-record": "/plans/1/experiment.json",
    "authentication-record": "{case}/authenticating.json",
    "start-record": "{case}/started.json",
    "response": "{case}/response.json",
    "attempt-record": "{case}/attempt.json",
    "metrics": "{case}/metrics.csv",
    "report": "/sessions/1/report.html",
    "manifest": "/sessions/1/manifest.json",
    "published-manifest": "/sessions/1/manifest.json",
}
"""Where each fault strikes, in the order a new experiment writes the files. `{case}` is
`default-only.yaml`'s first case, `baseline`, whose attempt authenticates: the session's other
attempt sends with its token. A `published-manifest` fault strikes once the store has published
the file."""

BEFORE_THE_PLAN: Final = ("session-record", "plan", "experiment-record")
"""The faults before the first plan's `experiment.json` is written."""

RESUMED: Final = {
    "authentication-record": (("baseline", "rebalance-weeks-1"), 0),
    "start-record": (("baseline", "rebalance-weeks-1"), 0),
    "response": (("rebalance-weeks-1",), 6),
    "attempt-record": (("rebalance-weeks-1",), 0),
    "metrics": (("rebalance-weeks-1",), 0),
    "report": ((), 0),
    "manifest": ((), 0),
    "published-manifest": ((), 0),
}
"""For each fault after the first plan is recorded, the cases the resume sends, by key, and its
exit code, as written by hand. A fault before `baseline`'s send leaves it due, so the resume sends
both cases. One at its response, after the 200, leaves it `unknown`, awaiting a repeat, which the
resume doesn't send, so it ends with `execution.partial`. One after its response was saved leaves
it complete, and one at the session's report or manifest leaves both cases complete, so the
resume sends nothing."""

INCOMPLETE: Final = (
    "The session has no manifest, so the experiment's output reads as incomplete until running"
    " the same command again resumes it."
)
UNRECORDED: Final = (
    "Nothing was sent. The experiment's first plan wasn't recorded, so its output is incomplete,"
    " and the directory can't be resumed: remove the directory, and run the command again."
)

SYNC_FAILED: Final = TrialFolioError(
    "storage.write_failed",
    "Couldn't write sessions/1/manifest.json durably: Input/output error. Check the output"
    " directory's free space and permissions.",
)
"""What the store raises when the sync after publishing a file fails."""

type Builder = ExperimentBuilder[Outcome]


def cases_of(path: Path) -> tuple[ExperimentPlanCase, ...]:
    """The planned cases of a new experiment of the configuration at `path`, in order."""
    configuration = read_experiment_configuration(path.read_bytes(), str(path))
    return build_experiment_plan(configuration, installed_versions()).cases


def where(at: str) -> str:
    """The name the storage faults strike for the fault `at`."""
    return FAULTS[at].format(case=cases_of(DEFAULT_ONLY)[0].case_id)


def failed(outcome: Outcome, code: str, exit_code: int) -> str:
    """The error's message, once the outcome is checked."""
    assert outcome.exit_code == exit_code, outcome.stderr
    error = cast("dict[str, str]", outcome.summary["error"])
    assert error["code"] == code
    message = error["message"]
    assert f"Error ({code}): {message}" in outcome.stderr
    return message


def repeated(message: str) -> list[str]:
    """Each sentence or clause, ending with a period or a colon, that `message` says more than
    once."""
    parts = [part for part in re.split(r"(?<=[.:])\s+", message) if part]
    return sorted({part for part in parts if parts.count(part) > 1})


def attempts(out: Path) -> dict[str, int]:
    """How many attempts each of `default-only.yaml`'s cases has, by its key."""
    counts: dict[str, int] = {}
    for case in cases_of(DEFAULT_ONLY):
        directory = out / "cases" / case.case_id / "attempts"
        counts[case.case_key] = len(list(directory.iterdir())) if directory.is_dir() else 0
    return counts


def records(out: Path) -> dict[str, bytes]:
    """Each file of the experiment's records, by path: everything but its logs."""
    return {
        path: content
        for path, content in snapshot(out).items()
        if content is not None and not path.startswith("logs/")
    }


def stops_and_runs_again(
    cli: Cli,
    experiments: Builder,
    faults: FaultyStores,
    monkeypatch: pytest.MonkeyPatch,
    at: str,
    code: str,
    exit_code: int,
) -> None:
    """Runs `default-only.yaml` with `faults` set at `at`, checks that it stops with `code` and
    `exit_code` without its session's manifest, and runs the same command again."""
    cli.ready()
    out = cli.tmp / "experiment"
    # The same command, run twice: approved by the new experiment's plan hash.
    approve = ("--approve", plan_hash(DEFAULT_ONLY, out))
    sends = [returns(), returns()]

    stopped = experiments.run(
        DEFAULT_ONLY, out, *approve, sends=sends, approve=False, store_factory=faults
    )

    message = failed(stopped, code, exit_code)
    # The attempt's error says what happened to its request, and the session adds what its
    # records say: a fault during the attempt doesn't say the same thing twice. A defect found
    # by R03-T12's walk-through of the user guide (PR #73): after an attempt record was written,
    # the session repeated its request's sentence, after "Of the last attempt:".
    assert repeated(message) == []
    assert not (out / "sessions/1/manifest.json").exists()
    assert "manifest" not in cast("dict[str, str]", stopped.summary["outputs"])
    # Each file was written once, and nothing after the fault.
    published = faults.published
    assert len(published) == len(set(published))
    if at == "published-manifest":
        assert published[-1] == "sessions/1/manifest.json"
    left = snapshot(out)
    kept = records(out)
    before = attempts(out)
    received = len(cli.server.received)
    again_faults = FaultyStores(monkeypatch)

    again = experiments.run(
        DEFAULT_ONLY, out, *approve, sends=sends, approve=False, store_factory=again_faults
    )

    if at in BEFORE_THE_PLAN:
        assert UNRECORDED in message
        assert cli.server.received == ()
        refused = failed(again, "output.not_empty", 4)
        assert "Remove the directory, and run the command again." in refused
        assert cli.server.received == ()
        assert again_faults.published == []
        assert snapshot(out) == left
        return
    assert INCOMPLETE in message
    sent, resumed_exit_code = RESUMED[at]
    assert again.exit_code == resumed_exit_code, again.stderr
    assert cast("dict[str, int]", again.summary["ids"])["session"] == 2
    assert (out / "sessions/2/manifest.json").is_file()
    expected = ["POST /auth", *["POST /screen/backtest"] * len(sent)] if sent else []
    assert cli.server.requests()[received:] == expected
    after = attempts(out)
    assert {key: after[key] - before[key] for key in after} == {
        key: int(key in sent) for key in after
    }
    # No record was replaced: each file the stopped run left is as it was, and the resume wrote
    # none of them, nor any file twice.
    for path, content in kept.items():
        assert (out / path).read_bytes() == content
    resumed = again_faults.published
    assert len(resumed) == len(set(resumed))
    assert set(resumed).isdisjoint(published)


# A storage failure, and an interrupt, at each of the session's files


@pytest.mark.parametrize("at", FAULTS)
def test_a_storage_failure_leaves_the_session_without_its_manifest(
    cli: Cli,
    experiments: Builder,
    faults: FaultyStores,
    monkeypatch: pytest.MonkeyPatch,
    at: str,
) -> None:
    if at == "published-manifest":
        faults.fail_after(where(at), SYNC_FAILED)
    else:
        faults.fail_os(where(at))

    stops_and_runs_again(cli, experiments, faults, monkeypatch, at, "storage.write_failed", 4)


@pytest.mark.parametrize("at", FAULTS)
def test_an_interrupt_leaves_the_session_without_its_manifest(
    cli: Cli,
    experiments: Builder,
    faults: FaultyStores,
    monkeypatch: pytest.MonkeyPatch,
    at: str,
) -> None:
    if at == "published-manifest":
        faults.fail_after(where(at), KeyboardInterrupt())
    else:
        faults.fail_before(where(at), KeyboardInterrupt())

    stops_and_runs_again(cli, experiments, faults, monkeypatch, at, "command.interrupted", 130)


# A response that couldn't be saved


@pytest.mark.parametrize(
    ("interrupted", "code", "exit_code"),
    [(False, "storage.write_failed", 4), (True, "command.interrupted", 130)],
    ids=["storage", "interrupt"],
)
def test_a_fault_at_the_response_after_a_200_leaves_the_case_unknown_and_possibly_charged(
    cli: Cli,
    experiments: Builder,
    faults: FaultyStores,
    interrupted: bool,
    code: str,
    exit_code: int,
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    first, second, *later = cases_of(EXAMPLE)
    name = f"{second.case_id}/response.json"
    if interrupted:
        faults.fail_before(name, KeyboardInterrupt())
    else:
        faults.fail_os(name)

    stopped = experiments.run(EXAMPLE, out, sends=[returns(), returns()], store_factory=faults)

    failed(stopped, code, exit_code)
    (attempt,) = (out / "cases" / second.case_id / "attempts").iterdir()
    assert not (attempt / "response.json").exists()
    record = AttemptRecordV1_1.model_validate_json((attempt / "attempt.json").read_bytes())
    assert (record.outcome, record.possibly_charged, record.response) == ("unknown", True, None)
    assert record.error is not None
    assert record.error.code == code
    # It sent with the first case's token, and got its 200.
    assert [(e.request, e.result, e.status) for e in record.exchanges] == [
        ("POST /screen/backtest", "response", 200)
    ]
    cases = cast("list[dict[str, str | None]]", stopped.summary["cases"])
    assert [(case["case_id"], case["outcome"]) for case in cases] == [
        (first.case_id, "succeeded"),
        (second.case_id, "unknown"),
        *((case.case_id, "not_yet_run") for case in later),
    ]
    assert cases[1]["repeat_attempt_id"] == attempt.name
    received = len(cli.server.received)

    # The resume never sends it again on its own: it awaits a repeat.
    resumed = experiments.run(EXAMPLE, out, sends=[returns()] * 3)

    failed(resumed, "execution.partial", 6)
    assert cli.server.requests()[received:] == ["POST /auth", *["POST /screen/backtest"] * 3]
    assert [path.name for path in (out / "cases" / second.case_id / "attempts").iterdir()] == [
        attempt.name
    ]
    outcomes = cast("list[dict[str, str]]", resumed.summary["cases"])
    assert outcomes[1]["outcome"] == "unknown"


# A file system without hard links


@pytest.mark.skipif(sys.platform == "win32", reason="Windows publishes files by renaming them")
@pytest.mark.parametrize("placeholder", [False, True], ids=["own-identity", "placeholder-identity"])
def test_a_file_system_without_hard_links_fails_at_the_session_record_before_any_request(
    cli: Cli,
    experiments: Builder,
    faults: FaultyStores,
    monkeypatch: pytest.MonkeyPatch,
    placeholder: bool,
) -> None:
    if placeholder:
        # FAT and exFAT on macOS also give each new, empty file a temporary inode until its first
        # write.
        placeholder_identities(monkeypatch)
    cli.ready()
    out = cli.tmp / "experiment"
    faults.fail_link("session.json")

    outcome = experiments.run(EXAMPLE, out, sends=[returns()] * 5, store_factory=faults)

    message = failed(outcome, "storage.write_failed", 4)
    assert message.startswith("Couldn't write sessions/1/session.json")
    assert "doesn't support hard links" in message
    assert UNRECORDED in message
    assert cli.server.received == ()
    # The claim's lock file is the only record left, with the log the claim started, and no
    # temporary file.
    files = sorted(path.relative_to(out).as_posix() for path in out.rglob("*") if path.is_file())
    assert files == ["experiment.lock", "logs/trialfolio.log"]
