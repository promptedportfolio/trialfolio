"""`trialfolio report` re-renders a saved run's report offline into a new output directory: every
value of the run's normalized tables appears in it, and its links reach the run's files by
relative path. Anything that isn't a complete run is refused with `input.not_a_run`, and a run
directory that doesn't exist with `input.not_found`, before anything is written.

Traces to R01-AC08 (re-rendering with network access blocked matches the saved normalized data)
and R01-AC23 (an incomplete or non-run directory fails with `input.not_a_run` and exit 3, and
creates no output), through the CLI's entry function in the test process. The runs are written
by `trialfolio run`, over the fake server, and by `trialfolio demo`, and one is a copy of the
committed `runs/synthetic-run-1.0.0/`; the runs that are broken one way are copies of it. The
network guard is on throughout, so a re-render that connected anywhere but localhost would fail.
A run directory after a symbolic link is read where the file system leads, and under a symbolic
link above both the run and the report, the links reach the run from the report's path as given
and from where the file system puts it (docs/contracts.md, CLI behavior; corrected defects,
2026-10-10).

From release 0.4.0, R04-AC12's `trialfolio report` part, as its test pairing gives it for
`tests/interface/test_report_command.py`: `report` refuses a run with a ranking definition broken
the ways a resume's records check refuses an experiment's, each with `input.not_a_run`, and a
record 0.4.0 adds, of a schema version with no reader, with `artifact.unknown_schema_version`;
the broken runs are copies of the committed `runs/synthetic-run-1.1.0/`, which
`tests/support/broken_runs.py` breaks. And it reads a run whose `definition.xml` has Windows line
endings as complete, since the definition's hash reads each line end as a line feed
(docs/contracts.md, reports, a complete run). R04-T13 added them.
"""

import os
import shutil
from collections.abc import Callable
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import url2pathname

import pytest

from tests.support import broken_runs
from tests.support.cli import Cli, plan_hash_for
from tests.support.directories import snapshot
from tests.support.fake_portfolio123 import AUTHENTICATED, response, serve_success
from tests.support.html_report import Document, parse
from tests.support.paths import FIXTURES, RANKING_DEFINITIONS, screen_config
from trialfolio.contracts.manifest import RunManifest
from trialfolio.tables import read_metrics_csv, read_settings_csv

FIXTURE = FIXTURES / "runs" / "synthetic-run-1.0.0"
"""The committed historical run, which `trialfolio demo` wrote with the 1.0.0 schemas."""
RANKING_FIXTURE = FIXTURES / "runs" / "synthetic-run-1.1.0"
"""The committed historical run with a ranking definition, which the core wrote with the demo's
client, with release 0.4.0's schemas."""


def committed_run(cli: Cli, out: Path) -> Path:
    """A copy of the committed `runs/synthetic-run-1.0.0/`."""
    cli.accept_license()
    shutil.copytree(FIXTURE, out)
    return out


def demo_run(cli: Cli, out: Path) -> Path:
    """A run as `trialfolio demo` writes it."""
    cli.accept_license()
    outcome = cli("demo", "--out", out)
    assert outcome.exit_code == 0, outcome.stderr
    return out


def fake_server_run(cli: Cli, out: Path) -> Path:
    """A run as `trialfolio run` writes it, over the fake server, approved with `--approve`."""
    cli.ready()
    serve_success(cli.server)
    path = screen_config("formula.yaml")
    outcome = cli.run_approved(path, out)
    assert outcome.exit_code == 0, outcome.stderr
    return out


def report_document(out: Path) -> Document:
    return parse((out / "report.html").read_text(encoding="utf-8"))


def table_cells(document: Document) -> set[tuple[str, ...]]:
    """The text of each table row's cells, header rows included."""
    return {
        tuple(cell.text for cell in row)
        for table in document.root.find_all("table")
        for row in document.rows(table)
    }


# Re-rendering (R01-AC08)


@pytest.mark.parametrize(
    "write", [fake_server_run, demo_run, committed_run], ids=["run", "demo", "committed"]
)
def test_report_rerenders_every_value_of_the_saved_tables(
    cli: Cli, write: Callable[[Cli, Path], Path]
) -> None:
    run = write(cli, cli.tmp / "runs" / "baseline")
    before = len(cli.server.received)
    out = cli.tmp / "reports" / "baseline"

    outcome = cli("report", run, "--out", out)

    assert outcome.exit_code == 0, outcome.stderr
    assert len(cli.server.received) == before
    cells = table_cells(report_document(out))
    metrics = read_metrics_csv((run / "normalized/metrics.csv").read_bytes(), "metrics.csv")
    settings = read_settings_csv((run / "normalized/settings.csv").read_bytes(), "settings.csv")
    for metric in metrics:
        assert metric.value is not None
        assert any(metric.value in row and metric.unit in row for row in cells), metric.metric_id
    for setting in settings:
        assert any(
            row[:4] == (setting.setting, setting.category, setting.value, setting.unit or "")
            for row in cells
        ), setting.setting


def test_report_writes_only_the_report_and_its_logs_and_leaves_the_run_unchanged(
    cli: Cli,
) -> None:
    run = demo_run(cli, cli.tmp / "runs" / "baseline")
    before = snapshot(run)
    out = cli.tmp / "reports" / "baseline"

    outcome = cli("report", run, "--out", out, "--json")

    assert outcome.exit_code == 0
    assert snapshot(run) == before
    assert sorted(path.name for path in out.iterdir()) == ["logs", "report.html"]
    summary = outcome.summary
    assert summary["command"] == "report"
    assert summary["outcome"] == "completed"
    assert summary["output_dir"] == str(out)
    assert summary["outputs"] == {"report": "report.html"}
    assert summary["counts"] == {}
    assert summary["error"] is None


def test_rerendered_links_reach_the_runs_files_from_the_reports_directory(cli: Cli) -> None:
    run = demo_run(cli, cli.tmp / "runs" / "a #1 %20 & ü")
    manifest = RunManifest.model_validate_json((run / "manifest.json").read_bytes())
    out = cli.tmp / "reports" / "baseline"

    assert cli("report", run, "--out", out).exit_code == 0

    hrefs = [a.attrs["href"] or "" for a in report_document(out).root.find_all("a")]
    relative = [h for h in hrefs if not h.startswith("#") and not urlsplit(h).scheme]
    # The manifest's files, apart from the run's own report, and the manifest itself.
    assert len(relative) == len(manifest.artifacts)
    for href in relative:
        assert href.startswith("../../runs/a%20%231%20%2520%20%26%20%C3%BC/")
        assert (out / unquote(href)).resolve().is_file()


@pytest.mark.skipif(os.name == "nt", reason="creating a symbolic link needs a privilege there")
def test_a_run_directory_after_a_symbolic_link_is_read_where_the_file_system_leads(
    cli: Cli,
) -> None:
    # A corrected defect: the command found the run where the file system leads, but read it
    # where `..` leads when it's removed as text, with the segment before it: here, another run.
    archive = cli.tmp / "archive"
    run = fake_server_run(cli, archive / "baseline")
    other = demo_run(cli, cli.tmp / "baseline")
    (archive / "group").mkdir()
    (cli.tmp / "linked").symlink_to(archive / "group", target_is_directory=True)
    out = cli.tmp / "reports" / "baseline"

    outcome = cli("report", cli.tmp / "linked" / ".." / "baseline", "--out", out)

    assert outcome.exit_code == 0, outcome.stderr
    ((attempt,), (other_attempt,)) = ((r / "cases").glob("*/attempts/*") for r in (run, other))
    document = report_document(out)
    assert attempt.name in document.root.text
    assert other_attempt.name not in document.root.text
    hrefs = [a.attrs["href"] or "" for a in document.root.find_all("a")]
    relative = [h for h in hrefs if not h.startswith("#") and not urlsplit(h).scheme]
    assert relative
    for href in relative:
        assert (out / unquote(href)).resolve().is_relative_to(run.resolve())


@pytest.mark.skipif(os.name == "nt", reason="creating a symbolic link needs a privilege there")
def test_rerendered_links_reach_the_run_under_a_symbolic_link_above_both(cli: Cli) -> None:
    # A corrected defect: the links went from the output directory as given to the run where the
    # file system resolves it, so from where the report is, they missed the run. The link is at
    # another depth than its target, as macOS's /tmp is a link to /private/tmp.
    (cli.tmp / "private" / "tmp").mkdir(parents=True)
    (cli.tmp / "tmp").symlink_to(cli.tmp / "private" / "tmp", target_is_directory=True)
    run = demo_run(cli, cli.tmp / "tmp" / "study" / "run")
    out = cli.tmp / "tmp" / "study" / "report"

    assert cli("report", run, "--out", out).exit_code == 0

    hrefs = [a.attrs["href"] or "" for a in report_document(out).root.find_all("a")]
    relative = [h for h in hrefs if not h.startswith("#") and not urlsplit(h).scheme]
    assert relative
    # The report opened by the path it was written to, and where the file system puts it.
    for report in (out / "report.html", (out / "report.html").resolve()):
        for href in relative:
            # As a browser follows a link: the URL's `..` removed as text, then the file opened.
            target = Path(url2pathname(urlsplit(urljoin(report.as_uri(), href)).path))
            assert target.is_file(), (report, href)
    assert all(href.startswith("../run/") for href in relative)


# What isn't a complete run (R01-AC23)


BROKEN = {
    name: break_run
    for name, (break_run, _) in broken_runs.BROKEN.items()
    if name not in ("an empty directory", "a regular file")
}
"""R01-AC23's broken copies of a run. An empty directory and a regular file are below."""


@pytest.mark.parametrize("break_run", BROKEN.values(), ids=BROKEN.keys())
def test_an_incomplete_run_fails_and_creates_no_output(
    cli: Cli, break_run: Callable[[Path], None]
) -> None:
    run = committed_run(cli, cli.tmp / "run")
    break_run(run)
    out = cli.tmp / "report"

    outcome = cli("report", run, "--out", out, "--json")

    assert outcome.exit_code == 3
    assert outcome.error_code == "input.not_a_run"
    assert outcome.summary["output_dir"] is None
    assert outcome.summary["outputs"] == {}
    assert "Another title" not in outcome.stdout + outcome.stderr
    assert not out.exists()


def test_an_empty_directory_and_a_regular_file_arent_runs(cli: Cli) -> None:
    cli.accept_license()
    empty = cli.tmp / "empty"
    empty.mkdir()
    regular = cli.tmp / "file"
    regular.write_text("not a run")
    out = cli.tmp / "report"

    for given in (empty, regular):
        outcome = cli("report", given, "--out", out, "--json")
        assert outcome.exit_code == 3
        assert outcome.error_code == "input.not_a_run"
        assert not out.exists()


def test_a_run_directory_that_doesnt_exist_is_not_found(cli: Cli) -> None:
    cli.accept_license()
    out = cli.tmp / "report"

    outcome = cli("report", cli.tmp / "missing", "--out", out, "--json")

    assert outcome.exit_code == 3
    assert outcome.error_code == "input.not_found"
    assert not out.exists()


def test_a_provider_package_that_cant_be_imported_is_an_unsupported_environment(
    cli: Cli,
) -> None:
    # `report` reads runs with modules that import p123api, and checks no versions.
    cli.accept_license()
    given = cli.tmp / "not-a-run"
    given.mkdir()
    (given / "notes.txt").write_text("not a run\n")
    out = cli.tmp / "report"

    outcome = cli.without_module("p123api", "report", given, "--out", out, "--json")

    assert outcome.exit_code == 3, outcome.stderr
    error = outcome.error
    assert error["code"] == "environment.unsupported"
    assert "p123api can't be imported" in error["message"]
    assert "If you run it from a copy of its repository, run uv sync there" in error["message"]
    assert not out.exists()


def test_a_broken_copy_leaves_a_non_empty_output_directory_unchanged(cli: Cli) -> None:
    copy = committed_run(cli, cli.tmp / "copy")
    BROKEN["no manifest"](copy)
    out = cli.tmp / "report"
    out.mkdir()
    (out / "keep.txt").write_text("someone else's file")
    before = snapshot(out)

    outcome = cli("report", copy, "--out", out, "--json")

    # The run is read before the output directory is checked.
    assert outcome.error_code == "input.not_a_run"
    assert snapshot(out) == before


# A run with a ranking definition (release 0.4.0's R04-AC12)


def committed_ranking_run(cli: Cli, out: Path) -> Path:
    """A copy of the committed `runs/synthetic-run-1.1.0/`."""
    cli.accept_license()
    shutil.copytree(RANKING_FIXTURE, out)
    return out


def refused(cli: Cli, run: Path, code: str) -> str:
    """Runs `report` of `run`, checks that it fails with `code` and exit 3, creates no output,
    and leaves the run as it was, and gives the error's message."""
    before = snapshot(run)
    out = cli.tmp / "report"

    outcome = cli("report", run, "--out", out, "--json")

    assert outcome.exit_code == 3, outcome.stderr
    error = outcome.error
    assert error["code"] == code
    assert outcome.summary["output_dir"] is None
    assert not out.exists()
    assert snapshot(run) == before
    return error["message"]


def test_report_rerenders_a_copy_of_the_committed_run_with_a_definition(cli: Cli) -> None:
    # So each break below is what makes report refuse it.
    run = committed_ranking_run(cli, cli.tmp / "run")
    out = cli.tmp / "report"

    outcome = cli("report", run, "--out", out)

    assert outcome.exit_code == 0, outcome.stderr
    assert (out / "report.html").is_file()


@pytest.mark.parametrize(
    ("break_run", "problem"),
    broken_runs.BROKEN_RANKING_RUNS.values(),
    ids=broken_runs.BROKEN_RANKING_RUNS.keys(),
)
def test_a_broken_run_with_a_definition_is_refused_and_creates_no_output(
    cli: Cli, break_run: Callable[[Path], None], problem: str
) -> None:
    run = committed_ranking_run(cli, cli.tmp / "run")
    break_run(run)

    message = refused(cli, run, "input.not_a_run")

    assert message.startswith("The run directory isn't a complete Trial Folio run: ")
    assert problem in message


@pytest.mark.parametrize(
    ("target", "listed"),
    broken_runs.UNKNOWN_RANKING_RUN_SCHEMA_VERSIONS.values(),
    ids=broken_runs.UNKNOWN_RANKING_RUN_SCHEMA_VERSIONS.keys(),
)
def test_a_record_0_4_0_adds_with_no_reader_is_an_unknown_schema_version(
    cli: Cli, target: Callable[[Path], str], listed: bool
) -> None:
    run = committed_ranking_run(cli, cli.tmp / "run")
    path = target(run)
    if listed:
        broken_runs.edit_json(
            run,
            "manifest.json",
            lambda manifest: broken_runs.newer(
                next(a for a in manifest["artifacts"] if a["path"] == path)
            ),
        )
    else:
        broken_runs.edit_json(run, path, broken_runs.newer)

    message = refused(cli, run, "artifact.unknown_schema_version")

    assert f"`{path}`" in message
    assert "9.9.9" not in message


def test_report_reads_a_run_whose_definition_has_windows_line_endings_as_complete(
    cli: Cli,
) -> None:
    # `definition.yaml`, beside a copy of its definition with each line end a carriage return and
    # a line feed, as a checkout with Windows line endings gives it. The run's copy holds those
    # bytes, while the definition's hash reads each line end as a line feed, so the plan is
    # `definition.yaml`'s.
    cli.ready()
    definitions = RANKING_DEFINITIONS
    windows = (definitions / "value-momentum.xml").read_bytes().replace(b"\n", b"\r\n")
    directory = cli.tmp / "configs"
    directory.mkdir()
    (directory / "value-momentum.xml").write_bytes(windows)
    path = directory / "definition.yaml"
    text = screen_config("definition.yaml").read_text(encoding="utf-8")
    path.write_text(
        text.replace("'../experiment-configs/ranking/value-momentum.xml'", "'value-momentum.xml'"),
        encoding="utf-8",
    )
    assert plan_hash_for(path) == plan_hash_for(screen_config("definition.yaml"))
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/rank", response("rank-update.json"), method="POST")
    cli.server.reply("/screen/backtest", response("complete.json"))
    run = cli.tmp / "run"
    assert cli.run_approved(path, run).exit_code == 0
    assert (run / "definition.xml").read_bytes() == windows
    out = cli.tmp / "report"

    outcome = cli("report", run, "--out", out)

    assert outcome.exit_code == 0, outcome.stderr
    # The re-rendered report is the run's own, but for its links, which reach the run from the
    # new directory.
    rerendered = (out / "report.html").read_text(encoding="utf-8")
    assert "<code>ranking_weight</code> <code>Value/Earnings Yield</code>" in rerendered
