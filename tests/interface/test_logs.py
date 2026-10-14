"""`trialfolio run`'s logs hold no configuration value, formula, or response content at any level;
they're written only under `<out>/logs/`, and only once the run has claimed the directory, except
that an internal error before the claim writes them to the per-user log directory; and a run
whose claim fails writes no log file anywhere.

Traces to R01-AC17, and to docs/contracts.md, logging and local diagnostics (content, format,
levels, and storage), through the CLI's entry function in the test process at
`TRIALFOLIO_LOG_LEVEL=DEBUG`, with `canaries.yaml` and the real client, `requests`, and `urllib3`
over the fake server, which answers with `responses/canaries.json`: `complete.json` with canary
strings in an extra key and in the chart, and canary numbers as a metric and in a period. The
canaries' scan looks for them in every log file. The per-user directories are under a temporary
home.

`trialfolio review`'s logs follow the same rules. Those checks trace to R02-AC12: with
`review-configs/canaries.yaml`, whose runs the run builder writes from `screen-configs/canaries.yaml`
with `canaries.json`, no canary appears in any log file after a review that completes, one whose
input isn't a complete run, and one that fails with a storage fault at a copy. The review's own
canaries are its title, purpose, descriptions, reasons, labels, and `run` paths' directory names,
and each of its results' runs holds the screen configuration's and the response's.

`trialfolio run` with an experiment's configuration follows them too. Those checks trace to
R03-AC15, and to docs/contracts.md, the experiment manifest (logs name the plans by number and
hash, and the cases by `case_id`, never the `experiment_id`, a case key, a description, or a
revision's reason): with `experiment-configs/canaries.yaml`, whose `experiment_id` and variant keys
are canary-like slugs, its cases answered with `canaries.json`, and a 400 whose message holds a
canary, no canary appears in any log file after a new experiment, a failed case, a resume, a
revision whose reason holds a canary, a repeat, and a run that fails with `experiment.locked`. The
experiment's logs are only under `<out>/logs/`, and the run that found the lock held, by a resume
waiting at its approval prompt in another process under the terminal, wrote none. Each experiment
is written with the experiment builder, and the revision's configuration is `canaries.yaml` with
one variant's value and the budget changed, written in the test's directory.
"""

import json
import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from tests.interface.conftest import (
    AUTHENTICATED,
    CONFIGS,
    Cli,
    FaultyStores,
    Outcome,
    plan_hash_for,
    response,
)
from tests.support import canaries
from tests.support.experiment_builder import (
    UNAVAILABLE,
    ExperimentBuilder,
    experiment_config,
    returns,
)
from tests.support.fake_portfolio123 import Reply
from trialfolio.contracts.attempt import AttemptRecordV1_1
from trialfolio.contracts.experiment_plan import PlanV1_1
from trialfolio.storage import LocalArtifactStore, StoredFile
from trialfolio.userdirs import log_directory

CANARY_CONFIGURATION = CONFIGS / "canaries.yaml"

UNEXPECTED_CANARY = "canary-exception-message-4d8e2a71"
"""The message of an unexpected exception, which logs give only by its type."""

FIELDS = {"timestamp", "level", "event", "message", "trialfolio_version", "component"}
"""The fields every log line holds; linked IDs are added when they apply."""


def approved_run(cli: Cli, out: Path, **options: object) -> Outcome:
    return cli(
        "run",
        CANARY_CONFIGURATION,
        "--out",
        out,
        "--approve",
        plan_hash_for(CANARY_CONFIGURATION),
        "--json",
        **options,  # pyright: ignore[reportArgumentType]
    )


def log_files(cli: Cli) -> list[Path]:
    """Every log file under the test's directory: the output directories and the temporary
    home, which holds the per-user log directory."""
    return canaries.log_files([cli.tmp])


def logged_canaries(cli: Cli) -> list[str]:
    """Where a canary appears in a log file under the test's directory."""
    return canaries.logged([cli.tmp], more=[UNEXPECTED_CANARY])


def lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(autouse=True)
def debug(cli: Cli, monkeypatch: pytest.MonkeyPatch) -> None:
    """DEBUG level, set once `cli` has cleared the environment it starts with."""
    monkeypatch.setenv("TRIALFOLIO_LOG_LEVEL", "DEBUG")


class Interloper:
    """The output directory's real store, with another process writing a file into the directory
    just before the claim."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self._store = LocalArtifactStore(root)

    def check_empty(self) -> None:
        self._store.check_empty()

    def claim(self, path: str, data: bytes) -> StoredFile:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "other.txt").write_text("another process's file\n")
        return self._store.claim(path, data)

    def write(self, path: str, data: bytes) -> StoredFile:
        return self._store.write(path, data)

    def discard(self, path: str, data: bytes) -> None:
        self._store.discard(path, data)

    def read(self, path: str) -> bytes:
        return self._store.read(path)


class Defective(Interloper):
    """The output directory's real store, whose claim fails unexpectedly, as a defect would."""

    def claim(self, path: str, data: bytes) -> StoredFile:
        raise RuntimeError(UNEXPECTED_CANARY)


def test_a_success_logs_only_under_the_output_directory_and_no_canary(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", response("canaries.json"))
    out = cli.tmp / "out"

    outcome = approved_run(cli, out)

    assert outcome.exit_code == 0, outcome.stderr
    assert log_files(cli) == [out / "logs" / "trialfolio.log"]
    assert not log_directory(os.environ).exists()
    assert logged_canaries(cli) == []
    # Every canary does reach the run's artifacts, so the scan of the logs means something.
    configuration = (out / "configuration.yaml").read_text()
    assert all(canary in configuration for canary in canaries.CONFIGURATION)
    saved = next(out.glob("cases/*/attempts/*/response.json")).read_text()
    assert all(canary in saved for canary in canaries.RESPONSE)


def test_each_log_line_is_one_json_object_with_the_documented_fields(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", response("canaries.json"))
    out = cli.tmp / "out"

    approved_run(cli, out)

    events = lines(out / "logs" / "trialfolio.log")
    assert events
    for event in events:
        assert FIELDS <= set(event)
        assert isinstance(event["timestamp"], str)
        assert event["timestamp"].endswith("Z")
        assert event["level"] in ("DEBUG", "INFO", "WARNING", "ERROR")
        # 0.4.0, whose specification R04-T04 completed (D-26).
        assert event["trialfolio_version"] == "0.4.0"
        assert isinstance(event["event"], str)
        assert "." in event["event"]
    names = [event["event"] for event in events]
    assert names[0] == "cli.command.started"
    assert names[-1] == "cli.command.completed"
    # DEBUG is recorded at that level.
    assert "artifact.write.completed" in names
    # Logs record the plan hash and the case ID, never the plan's contents.
    (created,) = (event for event in events if event["event"] == "plan.created")
    assert created["plan_hash"] == plan_hash_for(CANARY_CONFIGURATION)
    assert str(created["case_id"]).startswith("case-")


def test_an_authentication_failure_logs_no_canary(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", Reply(401, b"Unauthorized"))
    out = cli.tmp / "out"

    outcome = approved_run(cli, out)

    assert outcome.exit_code == 5
    assert log_files(cli) == [out / "logs" / "trialfolio.log"]
    assert logged_canaries(cli) == []
    # The error's message ends the line with its own period, never a second one (corrected on
    # 2026-10-04).
    events = lines(out / "logs" / "trialfolio.log")
    (completed,) = (event for event in events if event["event"] == "cli.command.completed")
    assert str(completed["message"]).endswith(".")
    assert not str(completed["message"]).endswith("..")


def test_a_claim_that_fails_writes_no_log_file_anywhere(cli: Cli) -> None:
    cli.ready()
    out = cli.tmp / "out"

    outcome = approved_run(cli, out, store_factory=Interloper)

    assert outcome.exit_code == 4
    assert outcome.summary["error"]["code"] == "output.not_empty"  # pyright: ignore[reportIndexIssue]
    assert sorted(p.name for p in out.iterdir()) == ["other.txt"]
    assert log_files(cli) == []
    assert not log_directory(os.environ).exists()
    assert cli.server.requests() == []


def test_an_internal_error_before_the_claim_logs_to_the_per_user_directory(cli: Cli) -> None:
    cli.ready()
    out = cli.tmp / "out"

    outcome = approved_run(cli, out, store_factory=Defective)

    assert outcome.exit_code == 1
    error = outcome.summary["error"]
    assert isinstance(error, dict)
    assert error["code"] == "internal.unexpected"
    (logged,) = log_files(cli)
    assert logged.parent == log_directory(os.environ)
    assert str(logged) in str(error["message"])  # pyright: ignore[reportUnknownArgumentType]
    assert UNEXPECTED_CANARY not in str(error["message"])  # pyright: ignore[reportUnknownArgumentType]
    assert logged_canaries(cli) == []
    assert not out.exists()
    events = [event["event"] for event in lines(logged)]
    assert "cli.command.unexpected" in events
    assert events[-1] == "cli.command.completed"


def test_an_unknown_log_level_is_ignored_with_a_warning(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli.ready()
    monkeypatch.setenv("TRIALFOLIO_LOG_LEVEL", "verbose")
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", response("canaries.json"))
    out = cli.tmp / "out"

    outcome = approved_run(cli, out)

    assert outcome.exit_code == 0
    assert "Warning: TRIALFOLIO_LOG_LEVEL" in outcome.stderr
    events = lines(out / "logs" / "trialfolio.log")
    levels = {event["level"] for event in events}
    assert "INFO" in levels
    assert "DEBUG" not in levels
    assert "cli.environment.ignored" in [event["event"] for event in events]
    assert outcome.summary["counts"]["warnings"] == 1  # pyright: ignore[reportIndexIssue]


def test_the_warning_level_leaves_info_out_of_the_log_file(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli.ready()
    monkeypatch.setenv("TRIALFOLIO_LOG_LEVEL", "WARNING")
    # A warning, logged before the claim and held until it.
    monkeypatch.setenv("SSLKEYLOGFILE", str(cli.tmp / "keys.log"))
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", response("canaries.json"))
    out = cli.tmp / "out"

    outcome = approved_run(cli, out)

    assert outcome.exit_code == 0
    events = lines(out / "logs" / "trialfolio.log")
    assert [(event["level"], event["event"]) for event in events] == [
        ("WARNING", "cli.environment.ignored")
    ]
    # stderr still shows progress, whatever the log file's level.
    assert "Claimed the output directory." in outcome.stderr


# A review (R02-AC12)

REVIEW_RUNS = [f"runs/{name}" for name in canaries.REVIEW if name.startswith("canary-run-")]
"""`review-configs/canaries.yaml`'s `run` paths, in its results' order."""


def review(cli: Cli, path: Path, out: Path, **options: object) -> Outcome:
    cli.accept_license()
    return cli(
        "review",
        path,
        "--out",
        out,
        "--json",
        **options,  # pyright: ignore[reportArgumentType]
    )


def test_a_review_logs_only_under_its_output_directory_and_no_canary(
    cli: Cli, built: Callable[[str], Path]
) -> None:
    out = cli.tmp / "review"

    outcome = review(cli, built("canaries.yaml"), out)

    assert outcome.exit_code == 0, outcome.stderr
    assert log_files(cli) == [out / "logs" / "trialfolio.log"]
    assert not log_directory(os.environ).exists()
    assert logged_canaries(cli) == []
    events = [event["event"] for event in lines(out / "logs" / "trialfolio.log")]
    # DEBUG is recorded, and so is the warning that the three results share one response.
    assert "artifact.write.completed" in events
    assert "review.response.shared" in events
    # Every canary does reach the review's outputs, so the scan of the logs means something:
    # the review's own in its configuration and, but the run paths, its report, and the runs'
    # in the copied plans and tables.
    configuration = (out / "configuration.yaml").read_text(encoding="utf-8")
    assert all(canary in configuration for canary in canaries.REVIEW)
    report = (out / "report.html").read_text(encoding="utf-8")
    assert all(canary in report for canary in canaries.REVIEW if canary not in "".join(REVIEW_RUNS))
    copies = "".join(
        path.read_text(encoding="utf-8") for path in sorted((out / "inputs").rglob("*.*"))
    )
    assert all(canary in copies for canary in canaries.CONFIGURATION)
    assert "87654.3219" in copies


def test_a_review_whose_input_isnt_a_complete_run_writes_no_log_file_anywhere(
    cli: Cli, built: Callable[[str], Path], tmp_path_factory: pytest.TempPathFactory
) -> None:
    # A copy outside the test's directory, so the scan of it sees only what the review wrote.
    built_path = built("canaries.yaml")
    directory = tmp_path_factory.mktemp("broken") / "canaries"
    shutil.copytree(built_path.parent, directory)
    (directory / REVIEW_RUNS[1] / "plan.json").unlink()
    out = cli.tmp / "review"

    outcome = review(cli, directory / built_path.name, out)

    assert outcome.exit_code == 3
    assert outcome.summary["error"]["code"] == "input.not_a_run"  # pyright: ignore[reportIndexIssue]
    assert not out.exists()
    assert log_files(cli) == []
    assert not log_directory(os.environ).exists()


def test_a_review_that_fails_at_a_copy_logs_no_canary(
    cli: Cli, built: Callable[[str], Path], faults: FaultyStores
) -> None:
    faults.fail_os("plan.json")
    out = cli.tmp / "review"

    outcome = review(cli, built("canaries.yaml"), out, store_factory=faults)

    assert outcome.exit_code == 4
    assert outcome.summary["error"]["code"] == "storage.write_failed"  # pyright: ignore[reportIndexIssue]
    # The first result's copied manifest, before its plan.
    assert faults.published[-1].endswith("/manifest.json")
    assert log_files(cli) == [out / "logs" / "trialfolio.log"]
    assert logged_canaries(cli) == []
    events = lines(out / "logs" / "trialfolio.log")
    assert [event["event"] for event in events][-1] == "cli.command.completed"


# An experiment (R03-AC15)

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Windows has no pseudo-terminals")

CANARY_EXPERIMENT = experiment_config("canaries.yaml")
"""Its cases, in order: the baseline, the rule's variant, the holdings' variant, the default
`rebalance-weeks-1`, and the slippage's variant."""

HOLDINGS_KEY = "canary-key-0d3b7e19"
"""The holdings' variant's key, a canary: the third case's."""

REJECTED_WITH_CANARY = Reply(400, f"Unsupported value: {canaries.PROVIDER_MESSAGE}".encode())
"""A 400 whose message holds a canary: the case is `failed`, possibly charged."""

type Builder = ExperimentBuilder[Outcome]


def answered() -> Reply:
    """A 200 whose body is `canaries.json`, the response that holds canaries."""
    return returns("canaries.json")


def experiment_log(out: Path) -> Path:
    return out / "logs" / "trialfolio.log"


def assert_logged_only_under(cli: Cli, out: Path) -> None:
    """The experiment's logs are only under `<out>/logs/`, and hold no canary."""
    assert log_files(cli) == [experiment_log(out)]
    assert not log_directory(os.environ).exists()
    assert logged_canaries(cli) == []


def completed(cli: Cli, experiments: Builder) -> Path:
    """Writes `canaries.yaml`'s experiment, each case answered with `canaries.json`, and returns
    its directory."""
    cli.ready()
    out = cli.tmp / "experiment"
    outcome = experiments.run(CANARY_EXPERIMENT, out, sends=[answered() for _ in range(5)])
    assert outcome.exit_code == 0, outcome.stderr
    return out


def partial(cli: Cli, experiments: Builder) -> tuple[Path, Outcome]:
    """Writes `canaries.yaml`'s experiment with the holdings' variant's request answered with
    `REJECTED_WITH_CANARY`, so it's `failed`, and the default's with a 503, so it's `unknown`."""
    cli.ready()
    out = cli.tmp / "experiment"
    sends = [answered(), answered(), REJECTED_WITH_CANARY, UNAVAILABLE, answered()]
    outcome = experiments.run(CANARY_EXPERIMENT, out, sends=sends)
    assert outcome.exit_code == 6, outcome.stderr
    return out, outcome


def test_a_new_experiment_logs_only_under_its_output_directory_and_no_canary(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = experiments.run(CANARY_EXPERIMENT, out, sends=[answered() for _ in range(5)])

    assert outcome.exit_code == 0, outcome.stderr
    assert_logged_only_under(cli, out)
    events = [event["event"] for event in lines(experiment_log(out))]
    # DEBUG is recorded, and so are the session's events.
    assert "artifact.write.completed" in events
    for name in (
        "experiment.plan.recorded",
        "experiment.session.started",
        "experiment.session.ended",
    ):
        assert name in events
    # Every canary does reach the experiment's records, so the scan of the logs means something.
    configuration = (out / "plans/1/configuration.yaml").read_text(encoding="utf-8")
    assert all(canary in configuration for canary in canaries.EXPERIMENT)
    saved = [path.read_text() for path in out.glob("cases/*/attempts/*/response.json")]
    assert len(saved) == 5
    assert all(canary in text for text in saved for canary in canaries.RESPONSE)


def test_a_failed_case_logs_no_canary_of_portfolio123s_message(
    cli: Cli, experiments: Builder
) -> None:
    out, _ = partial(cli, experiments)

    assert_logged_only_under(cli, out)
    # Portfolio123's message does reach the failed attempt's record.
    records = [
        AttemptRecordV1_1.model_validate_json(path.read_bytes())
        for path in out.glob("cases/*/attempts/*/attempt.json")
    ]
    (failed,) = (record for record in records if record.outcome == "failed")
    assert failed.error is not None
    assert canaries.PROVIDER_MESSAGE in failed.error.message


def test_an_experiments_logs_name_each_case_by_its_case_id_never_its_key(
    cli: Cli, experiments: Builder
) -> None:
    out, outcome = partial(cli, experiments)
    plan = PlanV1_1.model_validate_json((out / "plans/1/plan.json").read_bytes())

    log = experiment_log(out)
    events = lines(log)
    # Every case is named, by its case_id, and the plan by its hash.
    assert {event["case_id"] for event in events if "case_id" in event} == {
        case.case_id for case in plan.cases
    }
    assert {event["plan_hash"] for event in events if "plan_hash" in event} == {plan.plan_hash}
    # No key, the default's and the baseline's included, though stderr names the cases that
    # didn't succeed by their keys, and the log line of the same error by their case_ids.
    text = log.read_text(encoding="utf-8")
    assert all(case.case_key not in text for case in plan.cases)
    (ended,) = (event for event in events if event["event"] == "cli.command.completed")
    for case in plan.cases[2:4]:
        assert f"`{case.case_key}`" in outcome.stderr
        assert case.case_id in str(ended["message"])


def test_a_resume_logs_no_canary(cli: Cli, experiments: Builder, faults: FaultyStores) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # The first case's attempt record can't be written, once its response is saved, so the run
    # stops, and the resume writes the record from the saved response.
    faults.fail_os("attempt.json")
    stopped = experiments.run(CANARY_EXPERIMENT, out, sends=[answered()], store_factory=faults)
    assert stopped.exit_code == 4, stopped.stderr

    resumed = experiments.run(CANARY_EXPERIMENT, out, sends=[answered() for _ in range(4)])

    assert resumed.exit_code == 0, resumed.stderr
    assert_logged_only_under(cli, out)
    events = [event["event"] for event in lines(experiment_log(out))]
    assert "experiment.resumed" in events
    assert "experiment.attempt.recorded" in events
    assert events.count("experiment.session.started") == 2


def test_a_revision_logs_no_canary_and_not_its_reason(cli: Cli, experiments: Builder) -> None:
    out = completed(cli, experiments)
    # The holdings' variant's value 40 under its key, which adds a case and retires one, and a
    # budget of 8.
    text = CANARY_EXPERIMENT.read_text(encoding="utf-8")
    text = text.replace("value: 50", "value: 40")
    revised = cli.tmp / "canaries-revised.yaml"
    revised.write_text(text.replace("provider_requests: 6", "provider_requests: 8"), "utf-8")

    outcome = experiments.run(
        revised, out, "--revision-reason", canaries.REVISION_REASON, sends=[answered()]
    )

    assert outcome.exit_code == 0, outcome.stderr
    assert_logged_only_under(cli, out)
    events = [event["event"] for event in lines(experiment_log(out))]
    assert events.count("experiment.plan.recorded") == 2
    # The reason does reach the revision's record.
    record = (out / "plans/2/experiment.json").read_text(encoding="utf-8")
    assert canaries.REVISION_REASON in record


def test_a_repeat_logs_no_canary(cli: Cli, experiments: Builder) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    first = experiments.run(
        CANARY_EXPERIMENT,
        out,
        sends=[answered(), answered(), UNAVAILABLE, answered(), answered()],
    )
    assert first.exit_code == 6, first.stderr
    case = cast("list[dict[str, str]]", first.summary["cases"])[2]
    assert (case["case_key"], case["outcome"]) == (HOLDINGS_KEY, "unknown")
    option = f"{HOLDINGS_KEY}:{case['repeat_attempt_id']}"

    repeated = experiments.run(CANARY_EXPERIMENT, out, "--repeat", option, sends=[answered()])
    # The same command, run again: the confirmation is used.
    again = experiments.run(CANARY_EXPERIMENT, out, "--repeat", option)

    assert (repeated.exit_code, again.exit_code) == (0, 0), again.stderr
    assert_logged_only_under(cli, out)
    events = [event["event"] for event in lines(experiment_log(out))]
    assert "experiment.repeat.started" in events
    assert "experiment.repeat.used" in events
    # stderr says the confirmation was used, with the case's key, which the log never holds.
    assert HOLDINGS_KEY in again.stderr


@posix_only
def test_a_run_that_finds_the_experiment_locked_writes_no_log(
    cli: Cli, experiments: Builder
) -> None:
    out = completed(cli, experiments)
    log = experiment_log(out)
    before = log.read_bytes()

    # A resume waits at its approval prompt, in another process, holding the lock.
    with cli.on_terminal("run", CANARY_EXPERIMENT, "--out", out, "--json") as holder:
        holder.wait_for("Type approve")
        locked = experiments.run(CANARY_EXPERIMENT, out)
        found = (log_files(cli), log.read_bytes(), log_directory(os.environ).exists())
        holder.press("no\n")
        holder.wait()

    assert locked.exit_code == 4, locked.stderr
    assert cast("dict[str, str]", locked.summary["error"])["code"] == "experiment.locked"
    assert found == ([log], before, False)
    assert logged_canaries(cli) == []
