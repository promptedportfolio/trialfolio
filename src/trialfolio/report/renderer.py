"""How a report is rendered and written: the `ReportRenderer` protocol, `HtmlReportRenderer`, its
implementation, and the functions that write each kind of report into its directory.

- `write_report` writes `report.html` into the output directory of the run being written. `run`
  and `demo` do that just before the manifest.
- `rerender_report` is the core of `trialfolio report`: it reads and checks a saved run, renders
  its report, and claims a new output directory with it.
- `write_review_report` writes a review's `report.html`, just before its manifest.
- `write_experiment_report` writes an experiment session's `sessions/<s>/report.html`, just
  before its manifest.

Each logs that it rendered the report under `trialfolio.report`, the name the report's module
had before it became a package, so no log event's `component` changes (docs/contracts.md,
logging and local diagnostics). The log never holds the report's contents.
"""

import logging
import os
import re
from typing import Final, Protocol
from urllib.parse import quote

from trialfolio.report.evidence import (
    REPORT_PATH,
    ExperimentContext,
    ExperimentEvidence,
    ReviewContext,
    ReviewEvidence,
    RunContext,
    experiment_report_path,
)
from trialfolio.report.experiment import render_experiment
from trialfolio.report.review import render_review
from trialfolio.report.run import render_run
from trialfolio.runs import SavedRun, read_run
from trialfolio.storage import ArtifactStore, StoredFile

_logger = logging.getLogger("trialfolio.report")

_VERSION: Final = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


class ReportRenderer(Protocol):
    """Renders a saved run's report as HTML, without provider or network access."""

    def render(self, run: SavedRun, run_path: str | None) -> str:
        """The report of `run`, as an HTML document.

        `run_path` is where the run's directory is, relative to the report's: `""` when the report
        is in it, as `run` writes it, or a path such as `../../runs/baseline` with `/` separators,
        as the file system gives it. Each artifact is linked by that path, each segment
        percent-encoded from its bytes in the file system, so a name that isn't UTF-8 is linked as
        it is. None names the artifacts without links, for a report with no relative path to the
        run.

        Raises `ValueError` if `run_path` is absolute or has an empty segment.
        """
        ...

    def render_review(self, review: ReviewEvidence) -> str:
        """The report of `review`, as an HTML document, for `report.html` in the review's output
        directory. It links `manifest.json` and each of `review.artifacts` by its path in the
        review, and never links a run."""
        ...

    def render_experiment(self, experiment: ExperimentEvidence) -> str:
        """The report of an experiment's session, as an HTML document, for
        `sessions/<s>/report.html`. It links the session's `manifest.json` and each of
        `experiment.artifacts` by its path relative to the report."""
        ...


def write_report(store: ArtifactStore, run: SavedRun, renderer: ReportRenderer) -> StoredFile:
    """Renders the report of the run being written into `store`, and writes it as `report.html`.

    The manifest is written after the report, so `run.manifest` is the manifest as it will be
    written, without the report. Raises `TrialFolioError` with `storage.write_failed` when the
    report can't be written.
    """
    report = store.write(REPORT_PATH, renderer.render(run, "").encode("utf-8"))
    _logged(report, run)
    return report


def rerender_report(
    run_store: ArtifactStore,
    out_store: ArtifactStore,
    renderer: ReportRenderer,
    *,
    run_path: str | None,
) -> StoredFile:
    """`trialfolio report`'s core: reads the saved run in `run_store` and checks it's complete,
    then renders its report, and claims `out_store`'s directory with it, as `report.html`.

    `run_path` is the run's directory relative to `out_store`'s, as `ReportRenderer.render` takes
    it. Nothing is written before the run is read and the output directory is checked.

    Raises `TrialFolioError` with `input.not_a_run` or `artifact.unknown_schema_version` when the
    run can't be read (`read_run`), and with `output.not_empty` or `storage.write_failed` when
    the output directory can't be claimed.
    """
    run = read_run(run_store)
    out_store.check_empty()
    report = out_store.claim(REPORT_PATH, renderer.render(run, run_path).encode("utf-8"))
    _logged(report, run)
    return report


def write_review_report(
    store: ArtifactStore, review: ReviewEvidence, renderer: ReportRenderer
) -> StoredFile:
    """Renders the report of the review being written into `store`, and writes it as
    `report.html`.

    The review manifest is written after the report, so `review.artifacts` are the files it will
    list, without the report. Raises `TrialFolioError` with `storage.write_failed` when the report
    can't be written.
    """
    report = store.write(REPORT_PATH, renderer.render_review(review).encode("utf-8"))
    _logger.info(
        "Rendered the review's report, %s.",
        report.artifact_id,
        extra={"event": "report.render.completed", "review_id": str(review.review_id)},
    )
    return report


def write_experiment_report(
    store: ArtifactStore, experiment: ExperimentEvidence, renderer: ReportRenderer
) -> StoredFile:
    """Renders the report of the experiment session being written into `store`, and writes it
    as `sessions/<s>/report.html`, just before the session's manifest. Raises `TrialFolioError`
    with `storage.write_failed` when the report can't be written."""
    path = experiment_report_path(experiment.session)
    report = store.write(path, renderer.render_experiment(experiment).encode("utf-8"))
    _logger.info(
        "Rendered the session's report, %s.",
        report.artifact_id,
        extra={"event": "report.render.completed", "plan_hash": experiment.plan.plan_hash},
    )
    return report


def _logged(report: StoredFile, run: SavedRun) -> None:
    _logger.info(
        "Rendered the report, %s.",
        report.artifact_id,
        extra={
            "event": "report.render.completed",
            "plan_hash": run.plan.plan_hash,
            "case_id": run.plan.cases[0].case_id,
        },
    )


class HtmlReportRenderer:
    """Renders a run's report as one self-contained HTML document, for one Trial Folio version,
    which the report names, and whose LICENSE it links to."""

    def __init__(self, trialfolio_version: str) -> None:
        """Raises `ValueError` unless `trialfolio_version` is `<major>.<minor>.<patch>`."""
        if not _VERSION.fullmatch(trialfolio_version):
            raise ValueError("the version must be <major>.<minor>.<patch>")
        self._version = trialfolio_version

    def render(self, run: SavedRun, run_path: str | None) -> str:
        return render_run(RunContext.of(run, _base(run_path), self._version))

    def render_review(self, review: ReviewEvidence) -> str:
        return render_review(ReviewContext.of(review, self._version))

    def render_experiment(self, experiment: ExperimentEvidence) -> str:
        return render_experiment(ExperimentContext.of(experiment, self._version))


def _base(run_path: str | None) -> tuple[str, ...] | None:
    """The run's directory as percent-encoded path segments, or None for no links.

    Each segment is encoded from its bytes in the file system, which `os.fsencode` gives back: a
    name that isn't UTF-8 reaches Python as surrogate escapes, which UTF-8 can't encode.
    """
    if run_path is None:
        return None
    if run_path in ("", "."):
        return ()
    segments = run_path.removesuffix("/").split("/")
    if any(segment in ("", ".") for segment in segments):
        raise ValueError("the run's path must be relative, with no empty or . segments")
    return tuple(quote(os.fsencode(segment), safe="") for segment in segments)
