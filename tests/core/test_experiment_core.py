"""An experiment runs through the core functions alone, as another interface would run it, with
no CLI: it's planned, approved, and executed, its progress arrives as events, each once what it
reports is written, it's cancelled between provider requests, and it's resumed. An exception the
progress callback raises propagates from the execution.

Traces to R03-AC13 (D-30) and docs/contracts.md, interface-independent core, progress and
cancellation, and the executor (when the progress events come). R03-T08 wrote the first execution,
and R03-T09 the second, which resumes the experiment. The real client, `requests`, and `urllib3`
run over the fake server, with credentials the test passes in, and the clock is fixed; the tests
of a raising callback run a synthetic experiment with the demo's client.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support.clock import FixedClock
from tests.support.experiment_lab import RELEASE_0_3_0, Lab
from tests.support.fake_portfolio123 import (
    AUTH,
    AUTHENTICATED,
    BACKTEST,
    FakePortfolio123,
    response,
)
from tests.support.paths import EXPERIMENT_CONFIGS, ROOT
from trialfolio.configuration import read_experiment_configuration
from trialfolio.contracts.experiment_manifest import ExperimentManifest
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes
from trialfolio.experiment_execution import (
    AttemptEnded,
    AttemptStarted,
    ExperimentExecution,
    ProgressEvent,
    SessionEnded,
    SessionStarted,
)
from trialfolio.planning import (
    build_experiment_plan,
    check_approval,
    installed_versions,
)
from trialfolio.storage import LocalArtifactStore

EXAMPLE = EXPERIMENT_CONFIGS / "example.yaml"
DEFAULT_ONLY = EXAMPLE.with_name("default-only.yaml")


class _NoInput:
    """Standard input that fails the test if anything reads it: the core never prompts."""

    def read(self, *_: object) -> str:
        raise AssertionError("the core read standard input")

    readline = read

    def isatty(self) -> bool:
        return False


class Recorder:
    """What was on disk, and how many requests the server had received, at each event: the
    session's start once its session record and its plan are recorded; each attempt's start
    before it authenticates or sends anything, or writes a file; each attempt's end once its
    attempt record and its case's tables are written; and the session's end once its report and
    manifest are (docs/contracts.md, the executor)."""

    def __init__(self, out: Path, server: FakePortfolio123) -> None:
        self._out = out
        self._server = server
        self.seen: list[tuple[object, ...]] = []

    def __call__(self, event: ProgressEvent) -> None:
        match event:
            case SessionStarted():
                self.seen.append(
                    self._written(
                        "sessions/1/session.json",
                        "plans/1/configuration.yaml",
                        "plans/1/plan.json",
                        "plans/1/experiment.json",
                    )
                )
            case AttemptStarted(case_id=case_id, attempt_id=attempt_id):
                attempt = self._out / "cases" / case_id / "attempts" / str(attempt_id)
                self.seen.append((len(self._server.received), attempt.exists()))
            case AttemptEnded(case_id=case_id, attempt_id=attempt_id):
                self.seen.append(
                    self._written(
                        f"cases/{case_id}/attempts/{attempt_id}/attempt.json",
                        f"cases/{case_id}/normalized/metrics.csv",
                        f"cases/{case_id}/normalized/settings.csv",
                    )
                )
            case SessionEnded():
                self.seen.append(
                    self._written("sessions/1/report.html", "sessions/1/manifest.json")
                )

    def _written(self, *paths: str) -> tuple[bool, ...]:
        return tuple((self._out / path).is_file() for path in paths)


def test_the_core_plans_approves_executes_and_cancels_an_experiment_without_the_cli(
    tmp_path: Path,
    server: FakePortfolio123,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    for name in [name for name in os.environ if name.startswith("TRIALFOLIO_")]:
        monkeypatch.delenv(name)
    monkeypatch.setattr(sys, "stdin", _NoInput())
    server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    server.reply("/screen/backtest", *(response("complete.json") for _ in range(5)))
    lab = Lab(tmp_path, server, reader=RELEASE_0_3_0)
    recorder = Recorder(lab.out, server)

    # Read from its text and a source name, as an uploaded file would be.
    configuration = read_experiment_configuration(EXAMPLE.read_bytes(), "uploaded study")
    plan = build_experiment_plan(configuration, installed_versions())
    approved = check_approval(plan, plan.plan_hash)
    first = lab.new(
        EXAMPLE,
        plan=plan,
        approve=approved,
        approval="interactive",
        cancel_after=2,
        progress=recorder,
    )
    # The second execution resumes the experiment: its records are read under the lock, the
    # configuration gives the same plan, and the same hash approves it.
    resumed = lab.resume(EXAMPLE, source="uploaded study", approve=approved, approval="interactive")
    events, error, received = first.events, first.error, first.received
    resumed_events, resumed_error = resumed.events, resumed.error
    assert resumed.plan == plan

    case_ids = tuple(case.case_id for case in plan.cases)
    started = [e for e in events if isinstance(e, AttemptStarted)]
    assert events[0] == SessionStarted(session=1, cases=case_ids)
    assert [type(e) for e in events] == [
        SessionStarted,
        AttemptStarted,
        AttemptEnded,
        AttemptStarted,
        AttemptEnded,
        SessionEnded,
    ]
    assert [e.case_id for e in started] == list(case_ids[:2])
    # When each event comes, as the recorder says.
    assert recorder.seen == [
        (True, True, True, True),
        (0, False),
        (True, True, True),
        (2, False),
        (True, True, True),
        (True, True),
    ]
    ended = [e for e in events if isinstance(e, AttemptEnded)]
    assert [(e.case_id, e.attempt_id, e.outcome, e.possibly_charged) for e in ended] == [
        (s.case_id, s.attempt_id, "succeeded", True) for s in started
    ]
    # Cancelled between provider requests: no third request.
    assert received == (AUTH, BACKTEST, BACKTEST)
    assert error is not None and error.code == "execution.partial"
    assert "The run was cancelled" in error.message
    manifest = lab.manifest(1, ExperimentManifest)
    assert (lab.out / "sessions/1/report.html").is_file()
    assert manifest.outcome == "partial" and manifest.command is None
    assert manifest.approval == "interactive"
    assert first.outcomes == [
        "succeeded",
        "succeeded",
        "not_yet_run",
        "not_yet_run",
        "not_yet_run",
    ]
    session_ended = events[-1]
    assert isinstance(session_ended, SessionEnded)
    assert session_ended.counts == manifest.counts
    assert manifest.counts.cases.not_yet_run == 3
    # The resume sends cases 3 to 5, after one authentication, and ends completed.
    assert resumed_error is None
    assert resumed.received == (AUTH, *(BACKTEST for _ in range(3)))
    assert resumed_events[0] == SessionStarted(session=2, cases=case_ids[2:])
    assert [type(e) for e in resumed_events] == [
        SessionStarted,
        *((AttemptStarted, AttemptEnded) * 3),
        SessionEnded,
    ]
    assert [e.case_id for e in resumed_events if isinstance(e, AttemptStarted)] == list(
        case_ids[2:]
    )
    second = lab.manifest(2, ExperimentManifest)
    assert (second.outcome, second.plan_hash, second.approval) == (
        "completed",
        plan.plan_hash,
        "interactive",
    )
    assert second.counts.cases.succeeded == 5
    assert resumed.outcomes == ["succeeded"] * 5
    # Nothing printed, nothing prompted.
    assert capfd.readouterr() == ("", "")
    # The events hold no text from the configuration: each names a case by its case_id.
    keys = {case.case_key for case in plan.cases} - {"baseline"}
    assert not any(key in repr(event) for event in (*events, *resumed_events) for key in keys)


class _CallbackFailed(Exception):
    """What the progress callback of the tests below raises."""


def _raising_at(
    out: Path, event_type: type[ProgressEvent]
) -> tuple[ExperimentExecution, list[ProgressEvent]]:
    """Runs a synthetic experiment of `default-only.yaml`'s two cases into `out`, with a progress
    callback that raises at the first event of `event_type`, and checks that the exception
    propagates from the execution, as an unexpected exception's would."""
    content = DEFAULT_ONLY.read_bytes()
    plan = build_experiment_plan(
        read_experiment_configuration(content, "study"), installed_versions()
    )
    events: list[ProgressEvent] = []

    def progress(event: ProgressEvent) -> None:
        events.append(event)
        if isinstance(event, event_type):
            raise _CallbackFailed

    with LocalArtifactStore(out) as store:
        execution = ExperimentExecution(
            plan,
            plan.plan_hash,
            "not_required",
            store,
            SyntheticScreenBacktestClient(response_bytes()),
            command=None,
            clock=FixedClock(),
            progress=progress,
        )
        with pytest.raises(_CallbackFailed):
            execution.run(content)
    return execution, events


def test_an_exception_the_callback_raises_ends_the_session_without_its_manifest(
    tmp_path: Path,
) -> None:
    out = tmp_path / "experiment"

    execution, events = _raising_at(out, AttemptEnded)

    assert [type(e) for e in events] == [SessionStarted, AttemptStarted, AttemptEnded]
    assert execution.manifest is None
    assert not (out / "sessions/1/manifest.json").exists()
    assert not (out / "sessions/1/report.html").exists()
    # The first case's records stay; the second case never started.
    (first, second) = (case.case_id for case, _ in execution.outcomes)
    assert (out / "cases" / first / "normalized/settings.csv").is_file()
    assert not (out / "cases" / second).exists()


def test_an_exception_the_callback_raises_at_the_sessions_end_leaves_its_manifest(
    tmp_path: Path,
) -> None:
    # The end event comes once the manifest is written, and no record is ever removed, so the
    # session is complete although the exception propagates (R03-T08's review).
    out = tmp_path / "experiment"

    execution, events = _raising_at(out, SessionEnded)

    assert type(events[-1]) is SessionEnded
    manifest = execution.manifest
    assert manifest is not None and manifest.outcome == "completed"
    written = ExperimentManifest.model_validate_json(
        (out / "sessions/1/manifest.json").read_bytes()
    )
    assert written == manifest


def test_the_core_imports_nothing_from_the_cli_and_prints_nothing_on_its_own(
    tmp_path: Path,
) -> None:
    # In a new process, so what other tests imported doesn't count, and no handler pytest
    # installs hides what the core would print: it runs a synthetic experiment, cancelled before
    # its first case, which logs warnings, with no logging configured.
    script = f"""
import sys
from tests.core import test_experiment_core
from trialfolio.configuration import read_experiment_configuration
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes
from trialfolio.experiment_execution import Cancellation, ExperimentExecution
from trialfolio.planning import build_experiment_plan, installed_versions
from trialfolio.storage import LocalArtifactStore

content = test_experiment_core.EXAMPLE.read_bytes()
plan = build_experiment_plan(read_experiment_configuration(content, "study"), installed_versions())
cancellation = Cancellation()
cancellation.cancel()
with LocalArtifactStore({str(tmp_path / "synthetic")!r}) as store:
    error = ExperimentExecution(
        plan, plan.plan_hash, "not_required", store,
        SyntheticScreenBacktestClient(response_bytes()), command=None, cancellation=cancellation,
    ).run(content)
assert error is not None and error.code == "execution.partial", error
assert "trialfolio.cli" not in sys.modules, "trialfolio.cli was imported"
"""
    finished = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True, check=False
    )

    assert (finished.returncode, finished.stdout, finished.stderr) == (0, "", "")
    assert (tmp_path / "synthetic/sessions/1/manifest.json").is_file()
