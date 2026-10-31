"""`trialfolio report`'s core reads a screen run with a ranking definition back, and checks its
records: a complete run's report renders again, and a review's check reads the run as `report` does;
records with a definition that are incomplete or changed are refused, and nothing is written; an
attempt without its attempt record reads as running, with the files written before it; a run without
a definition refuses the versions only a definition gives; and a record 0.4.0 adds whose schema
version has no reader is unknown.

Traces to docs/contracts.md, sending a definition (an attempt stopped after its update record),
uncertain completion, weight rows, and reports (a complete run); and, at the core, to R04-AC12
(`trialfolio report`'s core refuses a run whose records with a ranking definition are incomplete or
changed with `input.not_a_run`, as a resume refuses an experiment's; a record with no reader fails
with `artifact.unknown_schema_version`). The real client, `requests`, and `urllib3` run over the
fake server, whose end-of-test check reads every `POST /rank` body (R04-AC09); and the ranking
lock's file is in the test's temporary directory.

Each run is written during the test, through the core, with `Execution`, and its breaks are made
with the editors of `tests/support/broken_runs.py`: `rewrite`, `edit_json`, and `unlist`. TS-T07
separated these tests from tests/core/test_ranking_resume.py, whose last 420 lines they were, since
they check how `trialfolio report` and a review read a run, not a resume (docs/test-refactoring.md,
modules to separate). Its name follows tests/core/test_saved_runs.py's, which checks the same of a
run without a definition.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.support.broken_runs import (
    Json,
    edit_json,
    labeled_1_1_0,
    rank_update_status,
    rewrite,
    transport_changed,
    unlist,
)
from tests.support.clock import FixedClock, no_wait
from tests.support.directories import snapshot
from tests.support.fake_portfolio123 import AUTHENTICATED, CREDENTIALS, FakePortfolio123, response
from tests.support.paths import RANKING_DEFINITIONS, screen_config
from trialfolio.canonical import sha256_hex
from trialfolio.configuration import read_screen_configuration_v1_1
from trialfolio.contracts.manifest import CommandRecord
from trialfolio.contracts.plan import PlanV1_2
from trialfolio.errors import TrialFolioError
from trialfolio.execution import Execution
from trialfolio.planning import build_plan_v1_1, installed_versions, plan_hash
from trialfolio.provider import P123ScreenBacktestClient
from trialfolio.ranking_lock import LOCK_FILE
from trialfolio.report import HtmlReportRenderer
from trialfolio.runs import check_run, read_run
from trialfolio.storage import LocalArtifactStore
from trialfolio.tables import read_settings_csv_v1_1, settings_csv_v1_1

COMMAND = CommandRecord(name="run", options={}, started_at=FixedClock()())


SCREEN = screen_config("definition.yaml")


# The records check of a run with a definition, which `trialfolio report` reads (R04-AC12)


@dataclass(frozen=True)
class Screen:
    out: Path
    plan: PlanV1_2

    @property
    def attempt(self) -> str:
        case_id = self.plan.cases[0].case_id
        (directory,) = sorted((self.out / "cases" / case_id / "attempts").iterdir())
        return directory.relative_to(self.out).as_posix()


def write_screen(tmp: Path, server: FakePortfolio123, definition: bytes | None = None) -> Screen:
    """A screen run of `definition.yaml`, through the core, over the fake server, whose ranking
    is the definition the file names, or `definition`'s bytes."""
    content = SCREEN.read_bytes()
    read = read_screen_configuration_v1_1(content, SCREEN.name, SCREEN, definition=definition)
    plan = build_plan_v1_1(read, installed_versions())
    assert isinstance(plan, PlanV1_2) and read.definition is not None
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", response("rank-update.json"), method="POST")
    server.reply("/screen/backtest", response("complete.json"))
    out = tmp / "run"
    with LocalArtifactStore(out) as store:
        error = Execution(
            plan,
            plan.plan_hash,
            "option",
            store,
            COMMAND,
            ranking_lock=tmp / LOCK_FILE,
            pause=no_wait(),
        ).run(
            content,
            lambda: P123ScreenBacktestClient(CREDENTIALS, endpoint=server.endpoint),
            definition=read.definition.content,
        )
    assert error is None
    return Screen(out, plan)


def test_report_reads_a_run_with_a_definition_and_renders_its_own_report(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    run = write_screen(tmp_path, server)

    saved = read_run(LocalArtifactStore(run.out))

    assert saved.plan == run.plan
    (attempt,) = saved.attempts
    assert attempt.update is not None and attempt.update.operation == "rank_update"
    assert attempt.status.provider_requests == 2
    assert saved.settings is not None
    assert len([row for row in saved.settings if getattr(row, "node", None)]) == 9
    renderer = HtmlReportRenderer(run.plan.trialfolio_version)
    assert renderer.render(saved, "") == (run.out / "report.html").read_text(encoding="utf-8")


def test_report_reads_a_run_whose_definition_has_windows_line_endings(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    # The copy holds the file's bytes, so its artifact_id differs from the definition's hash,
    # which reads each line end as a line feed.
    windows = (RANKING_DEFINITIONS / "value-momentum.xml").read_bytes().replace(b"\n", b"\r\n")
    run = write_screen(tmp_path, server, definition=windows)

    saved = read_run(LocalArtifactStore(run.out))

    assert (run.out / "definition.xml").read_bytes() == windows
    assert saved.plan.plan_hash == plan_hash(run.plan)
    copy = "sha256:" + sha256_hex(windows)
    assert isinstance(saved.plan, PlanV1_2)
    assert saved.plan.ranking_source.definition != copy


def test_a_reviews_check_reads_a_run_with_a_definition_as_report_does(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    # A review compares weight rows from release 0.4.0's R04-T11, so its check reads the run, as
    # `read_run` does, where R04-T09's refused it by its manifest's version.
    run = write_screen(tmp_path, server)

    checked = check_run(LocalArtifactStore(run.out))

    assert checked.saved == read_run(LocalArtifactStore(run.out))
    assert checked.contents["manifest.json"] == (run.out / "manifest.json").read_bytes()


def _run_weight_row_changed(run: Screen) -> None:
    rows = read_settings_csv_v1_1((run.out / "normalized/settings.csv").read_bytes(), "settings")
    changed = [
        row.model_copy(update={"value": "45"}) if row.node == "Value" else row for row in rows
    ]
    rewrite(run.out, "normalized/settings.csv", settings_csv_v1_1(changed))


def _run_record_1_0_0(run: Screen) -> None:
    edit_json(
        run.out,
        f"{run.attempt}/attempt.json",
        lambda d: d.update(schema_version="1.0.0"),
    )


RUN_BREAKS: dict[str, tuple[Callable[[Screen], object], str]] = {
    "an attempt with started.json and no updating.json": (
        lambda run: unlist(run.out, f"{run.attempt}/updating.json"),
        "wrote its update record first",
    ),
    "an update record that disagrees with its start record": (
        lambda run: edit_json(run.out, f"{run.attempt}/updating.json", transport_changed),
        "doesn't hold the update record's values and exchanges",
    ),
    "a started.json whose exchanges don't end with the rank_update's 200": (
        lambda run: edit_json(run.out, f"{run.attempt}/started.json", rank_update_status(500)),
        "isn't a valid start record",
    ),
    "a rank-update-request.json whose bytes aren't what the attempt record records": (
        lambda run: rewrite(run.out, f"{run.attempt}/rank-update-request.json", b"{}\n"),
        "which its manifest doesn't list as that file",
    ),
    "an attempt record 1.0.0 under a plan 1.2.0": (
        _run_record_1_0_0,
        "isn't the version an attempt under its plan writes",
    ),
    "a backtest's exchange after a rank_update that didn't get a 200": (
        lambda run: edit_json(run.out, f"{run.attempt}/attempt.json", rank_update_status(500)),
        "isn't a valid attempt record",
    ),
    "a run whose definition.xml is missing": (
        lambda run: unlist(run.out, "definition.xml"),
        "doesn't list definition.xml as the run's one ranking_definition",
    ),
    "a run whose definition.xml isn't its ranking_source's": (
        lambda run: rewrite(
            run.out,
            "definition.xml",
            (RANKING_DEFINITIONS / "value-heavy.xml").read_bytes(),
        ),
        "isn't its plan's ranking definition",
    ),
    "a weight row that isn't its definition's": (
        _run_weight_row_changed,
        "weight rows aren't its definition's",
    ),
}


@pytest.mark.parametrize("name", sorted(RUN_BREAKS))
def test_a_runs_broken_records_are_refused_and_nothing_is_written(
    tmp_path: Path, server: FakePortfolio123, name: str
) -> None:
    run = write_screen(tmp_path, server)
    breaking, problem = RUN_BREAKS[name]
    breaking(run)
    before = snapshot(run.out)

    with pytest.raises(TrialFolioError) as caught:
        read_run(LocalArtifactStore(run.out))

    assert caught.value.code == "input.not_a_run"
    assert problem in caught.value.message, caught.value.message
    assert snapshot(run.out) == before


def test_a_runs_attempt_with_only_its_update_record_reads_as_running(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    # As a run's attempt with only its start record does: one request, possibly charged.
    run = write_screen(tmp_path, server)
    kept = (f"{run.attempt}/updating.json", f"{run.attempt}/rank-update-request.json")

    def update_only(content: Json) -> None:
        content["artifacts"] = [
            a
            for a in content["artifacts"]
            if a["path"] in ("plan.json", "configuration.yaml", "definition.xml", *kept)
        ]

    edit_json(run.out, "manifest.json", update_only)

    saved = read_run(LocalArtifactStore(run.out))

    (attempt,) = saved.attempts
    assert (attempt.start, attempt.record) == (None, None)
    status = attempt.status
    assert (status.outcome, status.possibly_charged, status.provider_requests) == (
        "running",
        True,
        1,
    )


def _listing_only(run: Screen, *names: str) -> None:
    """The run's manifest lists its plan's files, and only these of its attempt's, as a run whose
    attempt record wasn't written would list them."""
    kept = {f"{run.attempt}/{name}" for name in names}

    def only(content: Json) -> None:
        content["artifacts"] = [
            a
            for a in content["artifacts"]
            if a["path"] in ("plan.json", "configuration.yaml", "definition.xml")
            or a["path"] in kept
        ]

    edit_json(run.out, "manifest.json", only)


def _undecoded_rank_update_response_listed(run: Screen) -> None:
    """A `rank-update-response.raw` beside the decoded response, listed with its role."""
    data = b"<html>not JSON</html>"
    path = f"{run.attempt}/rank-update-response.raw"
    (run.out / path).write_bytes(data)

    def listed(content: Json) -> None:
        (decoded,) = [a for a in content["artifacts"] if a["role"] == "rank_update_response"]
        raw = json.loads(json.dumps(decoded))
        raw.update(
            path=path,
            artifact_id="sha256:" + sha256_hex(data),
            size=len(data),
            role="rank_update_response_undecoded",
        )
        raw["source"]["format"] = "p123api-rank-update-response_undecoded"
        content["artifacts"].append(raw)

    edit_json(run.out, "manifest.json", listed)


def _rank_update_request_listed_as(role: str) -> Callable[[Screen], None]:
    """The manifest's entry for `rank-update-request.json`, with another role."""

    def change(content: Json) -> None:
        (entry,) = [a for a in content["artifacts"] if a["role"] == "rank_update_request"]
        entry["role"] = role

    return lambda run: edit_json(run.out, "manifest.json", change)


@pytest.mark.parametrize(
    ("names", "change", "problem"),
    [
        (("updating.json",), None, "not the rank-update-request.json written before it"),
        (
            ("rank-update-request.json", "updating.json"),
            _rank_update_request_listed_as("provider_request"),
            "not the rank-update-request.json written before it",
        ),
        (
            ("rank-update-request.json", "updating.json", "rank-update-response.json"),
            _undecoded_rank_update_response_listed,
            "two saved rank_update responses",
        ),
        (
            ("rank-update-request.json", "updating.json", "request.json", "started.json"),
            None,
            "not the rank-update-response.json saved before it",
        ),
        (
            (
                "rank-update-request.json",
                "updating.json",
                "rank-update-response.json",
                "started.json",
            ),
            None,
            "not the request.json written before it",
        ),
        (
            ("rank-update-request.json", "rank-update-response.json"),
            None,
            "but not the update record written before its send",
        ),
    ],
    ids=[
        "an update record without its request",
        "an update record whose request is listed as another file",
        "two saved rank_update responses",
        "a start record without the rank_update's response",
        "a start record without its request",
        "a rank_update's response without any record",
    ],
)
def test_a_runs_attempt_without_its_record_lists_the_files_written_before_it(
    tmp_path: Path,
    server: FakePortfolio123,
    names: tuple[str, ...],
    change: Callable[[Screen], object] | None,
    problem: str,
) -> None:
    # As an experiment's attempt without its attempt record has them (resuming, in the core).
    run = write_screen(tmp_path, server)
    _listing_only(run, *names)
    if change is not None:
        change(run)
    before = snapshot(run.out)

    with pytest.raises(TrialFolioError) as caught:
        read_run(LocalArtifactStore(run.out))

    assert caught.value.code == "input.not_a_run"
    assert problem in caught.value.message, caught.value.message
    assert snapshot(run.out) == before


def test_a_runs_attempt_with_its_start_record_and_no_attempt_record_reads_as_running(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    # Its files written before `started.json` are listed, so it's complete: two requests.
    run = write_screen(tmp_path, server)
    _listing_only(
        run,
        "rank-update-request.json",
        "updating.json",
        "rank-update-response.json",
        "request.json",
        "started.json",
    )

    saved = read_run(LocalArtifactStore(run.out))

    (attempt,) = saved.attempts
    assert attempt.record is None and attempt.start is not None
    status = attempt.status
    assert (status.outcome, status.provider_requests) == ("running", 2)


def _settings_listed_1_1_0(manifest: Json) -> None:
    (entry,) = [a for a in manifest["artifacts"] if a["role"] == "settings"]
    entry["schema_version"] = "1.1.0"


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (labeled_1_1_0, "isn't the version a run of its plan writes"),
        (_settings_listed_1_1_0, "another version than a run of its plan writes"),
    ],
    ids=["its manifest 1.1.0", "its settings.csv listed as 1.1.0"],
)
def test_a_run_without_a_definition_refuses_versions_only_a_definition_gives(
    tmp_path: Path, server: FakePortfolio123, change: Callable[[Json], None], problem: str
) -> None:
    # Each version has a reader, and a run manifest 1.1.0 is valid with 1.0.0's fields, but only
    # a run of a plan 1.2.0 writes them.
    formula = screen_config("formula.yaml")
    content = formula.read_bytes()
    read = read_screen_configuration_v1_1(content, formula.name, formula)
    plan = build_plan_v1_1(read, installed_versions())
    server.reply("/auth", AUTHENTICATED)
    server.reply("/screen/backtest", response("complete.json"))
    out = tmp_path / "run"
    with LocalArtifactStore(out) as store:
        assert (
            Execution(plan, plan.plan_hash, "option", store, COMMAND).run(
                content, lambda: P123ScreenBacktestClient(CREDENTIALS, endpoint=server.endpoint)
            )
            is None
        )
    assert read_run(LocalArtifactStore(out)).plan == plan
    edit_json(out, "manifest.json", change)

    with pytest.raises(TrialFolioError) as caught:
        read_run(LocalArtifactStore(out))

    assert caught.value.code == "input.not_a_run"
    assert problem in caught.value.message, caught.value.message


@pytest.mark.parametrize(
    ("path", "listed"),
    [
        ("manifest.json", False),
        ("plan.json", False),
        ("{attempt}/updating.json", False),
        ("{attempt}/started.json", False),
        ("{attempt}/attempt.json", False),
        ("normalized/settings.csv", True),
    ],
)
def test_a_runs_record_0_4_0_adds_without_a_reader_is_unknown(
    tmp_path: Path, server: FakePortfolio123, path: str, listed: bool
) -> None:
    run = write_screen(tmp_path, server)
    path = path.format(attempt=run.attempt)
    if listed:
        edit_json(
            run.out,
            "manifest.json",
            lambda d: next(a for a in d["artifacts"] if a["path"] == path).update(
                schema_version="9.9.9"
            ),
        )
    else:
        edit_json(run.out, path, lambda d: d.update(schema_version="9.9.9"))

    with pytest.raises(TrialFolioError) as caught:
        read_run(LocalArtifactStore(run.out))

    assert caught.value.code == "artifact.unknown_schema_version"
    assert f"`{path}`" in caught.value.message
    assert "9.9.9" not in caught.value.message
