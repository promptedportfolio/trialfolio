"""The commands that send nothing: `trialfolio report`, which renders a saved run's report again
offline, and `trialfolio review`, which compares saved runs with a baseline offline, as a review
configuration names them (docs/contracts.md, CLI behavior and review output; releases 0.1.0 and
0.2.0).

Neither checks the installed versions, but each reads runs with modules that import `p123api`,
`requests`, or `urllib3`: an `ImportError` there is `environment.unsupported`. A review's outcome
is a `ReviewOutcome`.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from trialfolio.cli.invocation import FilesOutcome, Invocation, shown
from trialfolio.cli.license import require_acknowledgment
from trialfolio.cli.steps import empty_store, opened, read_input
from trialfolio.configuration import read_review_configuration
from trialfolio.contracts.review_manifest import ReviewCommandRecord
from trialfolio.contracts.summary import ReviewCounts, SummaryCase, SummaryIdsV1_2
from trialfolio.errors import TrialFolioError
from trialfolio.paths import existing_path
from trialfolio.storage import LocalArtifactStore

if TYPE_CHECKING:
    from trialfolio.review import Review


@dataclass
class ReviewOutcome:
    """What `review` has done so far, for its summary: how many results its configuration names,
    once it's read, and the review, once it has one."""

    out: str
    """`--out`, as given."""
    results: int = 0
    """The results a valid review configuration names, once it's read."""
    review: "Review | None" = None

    def output_dir(self, claimed: str | None) -> str | None:
        """The review's once it has claimed its directory. A review's claim is read from the
        review, as its `review_id` is, so the summary gives both even when an interrupt stops the
        review before `claimed` has run."""
        if self.review is not None and self.review.claimed:
            return self.out
        return claimed

    def ids(self) -> SummaryIdsV1_2:
        if self.review is not None and self.review.claimed:
            return SummaryIdsV1_2(review_id=self.review.review_id)
        return SummaryIdsV1_2()

    def outputs(self) -> dict[str, str]:
        outputs: dict[str, str] = {}
        if self.review is None:
            return outputs
        for role, stored in (
            ("manifest", self.review.manifest),
            ("report", self.review.report),
            ("differences", self.review.differences_file),
        ):
            if stored is not None:
                outputs[role] = stored.path
        return outputs

    def cases(self) -> tuple[SummaryCase, ...] | None:
        return None

    def counts(self, error: TrialFolioError | None, warnings: int) -> ReviewCounts:
        differences = None if self.review is None else self.review.differences
        return ReviewCounts(
            results=self.results,
            settings_flagged=0 if differences is None else differences.setting_counts.flagged,
            metrics_unavailable=(
                0 if differences is None else differences.metric_counts.unavailable
            ),
            warnings=warnings,
        )

    def ending_detail(self) -> str | None:
        """Whether the review has its manifest, once it has claimed its directory."""
        if self.review is None or not self.review.claimed:
            return None
        return self.review.ending_detail()

    def records(self, output_dir: str) -> str | None:
        return None


def report(invocation: Invocation) -> TrialFolioError | None:
    """Renders a saved run's report again, offline, into a new output directory."""
    context = invocation.context
    args = context.args
    require_acknowledgment(invocation)
    # Where the file system resolves it, as a review finds its runs.
    run_dir = existing_path(args.run_dir)
    if run_dir is None:
        raise TrialFolioError(
            "input.not_found",
            f"The run directory {shown(args.run_dir)} doesn't exist. Give the output directory of"
            " a run that trialfolio run or trialfolio demo wrote. No output was created.",
        )

    try:
        from trialfolio.report import HtmlReportRenderer, rerender_report
    except ImportError as failure:
        raise _cant_read_runs(failure) from None

    rendered = rerender_report(
        LocalArtifactStore(run_dir),
        context.store_factory(args.out),
        HtmlReportRenderer(context.version),
        run_path=_run_path(run_dir, args.out),
    )
    invocation.outcome = FilesOutcome({"report": rendered.path})
    invocation.claimed(args.out)
    invocation.result = [f"Report written: {os.path.join(args.out, rendered.path)}"]
    return None


def review(invocation: Invocation) -> TrialFolioError | None:
    """Compares saved runs with a baseline, in the order of steps docs/contracts.md's review
    output gives: the configuration, each run, the output directory, and then the review's files,
    which `Review` writes."""
    context = invocation.context
    args = context.args
    outcome = ReviewOutcome(args.out)
    invocation.outcome = outcome
    started_at = opened(invocation)
    content = read_input(args.config)
    configuration = read_review_configuration(content, shown(args.config))
    outcome.results = len(configuration.results)
    try:
        from trialfolio.review import Review
        from trialfolio.review_inputs import check_review_inputs, local_run_stores
    except ImportError as failure:
        raise _cant_read_runs(failure) from None

    inputs = check_review_inputs(configuration, local_run_stores(args.config))
    store = empty_store(context, args.out)
    review = Review(
        configuration,
        content,
        inputs,
        store,
        # No path: one can name the user, and the manifest is in the output directory.
        ReviewCommandRecord(name="review", options={"json": args.json}, started_at=started_at),
        trialfolio_version=context.version,
        clock=context.clock,
    )
    outcome.review = review
    error = review.write(on_claimed=lambda: invocation.claimed(args.out))
    return invocation.ended(error, lambda: _review_result(args.out, review))


def _cant_read_runs(failure: ImportError) -> TrialFolioError:
    """`environment.unsupported` for a module that reads runs, which imports `p123api`,
    `requests`, or `urllib3`, but can't be imported."""
    missing = "a package it needs" if failure.name is None else failure.name
    return TrialFolioError(
        "environment.unsupported",
        f"Trial Folio can't read runs in this environment: {missing} can't be imported,"
        " because its files, or a package it needs, are missing or broken. No output was"
        " created. Reinstall Trial Folio, whose package pins its dependencies exactly, for"
        " example in a new virtual environment. If you run it from a copy of its repository,"
        " run uv sync there instead.",
    )


def _run_path(run_dir: str, out: str) -> str | None:
    """The run's directory relative to the report's, with `/` separators, or None when there's
    no relative path, as between two Windows drives. Both are where the file system puts them:
    `run_dir` is resolved already, and the report's directory is resolved here, so the path
    reaches the run from where the report is, and a symbolic link above both, such as macOS's
    `/tmp`, stays out of it."""
    try:
        # The store's `abspath` first, which removes the output directory's `..` as text.
        report_dir = os.path.realpath(os.path.abspath(out))
        relative = os.path.relpath(run_dir, report_dir)
    except ValueError:
        return None
    return Path(relative).as_posix()


def _review_result(out: str, review: "Review") -> list[str]:
    differences = review.differences
    report = review.report
    lines = [f"Review completed: {out}"]
    if report is not None:
        lines.append(f"Report: {os.path.join(out, report.path)}")
    if differences is not None:
        lines.append(
            f"Flagged setting rows: {differences.setting_counts.flagged}. Unavailable metric"
            f" rows: {differences.metric_counts.unavailable}."
        )
    if review.synthetic:
        lines.append(
            "It includes synthetic results, whose values are invented, never Portfolio123's. The"
            " report names them."
        )
    lines += [
        f"Review ID: {review.review_id}",
        "Statistical validation and trading readiness: not assessed.",
    ]
    return lines
