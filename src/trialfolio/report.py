"""The report: one self-contained, script-free HTML file showing a run's or a review's evidence,
with the notices (docs/contracts.md, reports; docs/disclaimers.md, DSC-02, DSC-03, and DSC-06;
REQ-08 and REQ-13).

`ReportRenderer` is the protocol, and `HtmlReportRenderer` its implementation. Rendering reads
only the `SavedRun` or the `ReviewEvidence` it's given, so it needs no provider or network
access.

- `write_report` writes `report.html` into the output directory of the run being written. `run`
  and `demo` do that just before the manifest.
- `rerender_report` is the core of `trialfolio report`: it reads and checks a saved run, renders
  its report, and claims a new output directory with it.
- `write_experiment_report` writes an experiment session's `sessions/<s>/report.html`, just
  before its manifest (release 0.3.0). R03-T08 wrote this first version, which shows each case
  and its outcome, and the notices; R03-T10 builds the full report.
- `write_review_report` writes a review's `report.html`, just before its manifest (release 0.2.0,
  R02-T07). The review report compares each result with the baseline: intended changes apart from
  unexplained mismatches, and each result's metrics beside the baseline's, with the difference
  where they're comparable.

What a report holds:

- **Nothing that runs or loads.** Inline CSS only: no script, event-handler attribute, or
  external resource. Its only links are in-page fragments, relative paths to the run's artifacts,
  or to the review's files, and the two outside links D-21 allows: the LICENSE of the version
  that rendered it, and Portfolio123's terms. A review report never links a run.
- **The notices.** The concise notice near the top, before any result, linking to the full
  notice. The Portfolio123 data statement in the closing section, and after it the full notice in
  a `<details>` element, with the license's name and identifier, the notice version, and the
  LICENSE link.
- **The ten sections docs/contracts.md lists,** in order. A section the run's evidence can't
  support says it's unavailable, or not assessed, and why. Nothing is filled in.
- **Values exactly as the normalized tables hold them,** with their units, never padded or
  rounded. An unavailable metric shows its reason. A synthetic result's values are labeled
  wherever they appear, and never called Portfolio123's (DSC-04).
- **Text Trial Folio didn't write,** such as the title, the formulas, or a provider message,
  HTML-escaped, with its control and formatting characters written as escapes such as `\\u202e`,
  so it can't add markup or reorder what's shown.
- **No account information:** `quotaRemaining` stays in the attempt record.
- **Neutral status.** No status is styled as a pass; execution success is kept apart from any
  statement about the strategy.

Rendering is deterministic: the same run, or review, and version give the same bytes. Nothing
here logs the report's contents.
"""

import html
import logging
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, Protocol
from urllib.parse import quote
from uuid import UUID

from trialfolio.contracts.attempt import SavedResponse
from trialfolio.contracts.common import ErrorDetail, UnavailableReason
from trialfolio.contracts.experiment_manifest import ExperimentArtifact, ExperimentManifestCounts
from trialfolio.contracts.experiment_plan import ExperimentPlanCase, PlanV1_1
from trialfolio.contracts.experiment_record import ExperimentRecord
from trialfolio.contracts.manifest import ArtifactRole, ManifestArtifact
from trialfolio.contracts.review_configuration import ReviewConfiguration
from trialfolio.contracts.review_manifest import ReviewArtifact, ReviewArtifactRole
from trialfolio.contracts.tables import DifferenceReason, DifferencesRow, MetricsRow
from trialfolio.differences import METHOD, METHOD_VERSION, Differences
from trialfolio.display import visible
from trialfolio.normalization import LAYOUT, METRICS, setting_text
from trialfolio.notices import (
    CONCISE_NOTICE,
    CONCISE_NOTICE_LINK,
    FULL_NOTICE,
    LICENSE_ID,
    LICENSE_NAME,
    NOTICE_VERSION,
    PORTFOLIO123_DATA_LABEL,
    PORTFOLIO123_DATA_STATEMENT,
    PORTFOLIO123_TERMS_LINK,
    PORTFOLIO123_TERMS_URL,
    license_url,
)
from trialfolio.review_inputs import ReviewInput
from trialfolio.runs import MANIFEST_PATH, SavedAttempt, SavedRun, read_run
from trialfolio.storage import ArtifactStore, StoredFile

_logger = logging.getLogger(__name__)

REPORT_PATH: Final = "report.html"

FULL_NOTICE_ID: Final = "full-notice"
"""The `id` of the `<details>` element that holds the full notice."""

NOT_ASSESSED: Final = "Not assessed"

_VERSION: Final = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


@dataclass(frozen=True)
class ReviewEvidence:
    """What a review's report shows: its configuration, each result's run as the input check read
    it, the comparison, and what the review manifest will record.

    The report is written before the manifest, so `artifacts` holds each file the manifest will
    list apart from the report itself: `configuration.yaml`, the copies, and `differences.csv`.
    """

    configuration: ReviewConfiguration
    inputs: tuple[ReviewInput, ...]
    """One for each result, in the configuration's order."""
    differences: Differences
    review_id: UUID
    started_at: datetime
    """When the command started, as the manifest's `command.started_at`."""
    artifacts: tuple[ReviewArtifact, ...]

    def __post_init__(self) -> None:
        labels = tuple(result.label for result in self.configuration.results)
        if tuple(checked.result.label for checked in self.inputs) != labels:
            raise ValueError("each result has one input, in the configuration's order")
        if any(artifact.role == "report" for artifact in self.artifacts):
            raise ValueError("the artifacts are the ones the report links, so not the report")


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

    def render_experiment(self, experiment: "ExperimentEvidence") -> str:
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
        return _Report(run, _base(run_path), self._version).document()

    def render_review(self, review: ReviewEvidence) -> str:
        return _ReviewReport(review, self._version).document()

    def render_experiment(self, experiment: "ExperimentEvidence") -> str:
        return _ExperimentReport(experiment, self._version).document()


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


# What the report says about each code it shows.

_METRICS: Final[dict[str, tuple[str, str]]] = {
    "coverage_start": ("Coverage start", "The first transaction date in the response's periods."),
    "coverage_end": ("Coverage end", "The end of the response's last period."),
    "coverage_periods": ("Coverage periods", "The number of rebalance periods."),
    "total_return": ("Total return", "Cumulative return over the backtest."),
    "annualized_return": (
        "Annualized return",
        (
            "Compound annual growth rate over the calendar days from the first to the last date of"
            " the daily series, with 365.25-day years."
        ),
    ),
    "max_drawdown": (
        "Maximum drawdown",
        "The largest peak-to-trough decline in the daily series, as a negative number.",
    ),
    "standard_deviation": (
        "Standard deviation",
        "Annualized standard deviation of monthly returns.",
    ),
    "sharpe_ratio": (
        "Sharpe ratio",
        "Portfolio123's Sharpe ratio. Its risk-free rate isn't documented.",
    ),
    "sortino_ratio": (
        "Sortino ratio",
        "Portfolio123's Sortino ratio. Its risk-free rate and target aren't documented.",
    ),
    "correlation": ("Correlation", "Correlation with the benchmark."),
    "r_squared": ("R squared", "The square of the correlation."),
    "beta": ("Beta", "Beta against the benchmark."),
    "alpha": (
        "Alpha",
        (
            "Portfolio123's alpha against the benchmark. Its unit is inferred from the value's"
            " magnitude, and its method isn't documented."
        ),
    ),
    "risk_samples": ("Risk samples", "The number of returns behind the risk statistics."),
}
"""Each metric's name and definition, from `p123api-screen-backtest` version 1's metrics."""

_COVERAGE: Final = ("coverage_start", "coverage_end", "coverage_periods")

_REASONS: Final[dict[UnavailableReason, str]] = {
    "absent_from_layout": "The response layout has no such metric.",
    "blank_in_source": "The response gives no value for it.",
    "unparseable_in_source": (
        "Its value couldn't be interpreted. The saved response keeps it as it came."
    ),
    "not_applicable": "The metric has no meaning here.",
    "not_supported": "Trial Folio doesn't interpret this field.",
    "input_unavailable": "A value it's calculated from is unavailable.",
}

_FLAGS: Final[dict[str, str]] = {
    "critical_unexplained_mismatch": "A critical setting differs, and no change was declared.",
    "critical_unknown": "A critical setting is missing or can't be interpreted.",
    "intended_change_not_observed": "A declared change isn't present.",
    "inferred_default": (
        "A default the provider applies, inferred from its documentation or an owner decision,"
        " not reported by the provider."
    ),
    "time_dependent_default": "A default that depends on when the tool ran.",
    "unsupported_value": "Recorded, but unsupported and unverified.",
    "not_snapshotted": (
        "Names an object in the Portfolio123 account whose definition wasn't captured, so"
        " reproducibility is incomplete."
    ),
    "coverage_mismatch": "The response's coverage differs from this date.",
    "identical_source": "Two results have byte-identical saved responses.",
}

_TOKENS: Final[dict[str, str]] = {
    "not_sent": "Not sent. Portfolio123's default applies, and it isn't documented.",
    "not_modeled": (
        "Not modeled by this provider path: the API documents no commission parameter, and"
        " slippage is its only trading-cost input."
    ),
}

_PROVENANCE: Final[dict[str, str]] = {
    "verified": "Sent in the request, or captured from Portfolio123's response, by this run.",
    "user_supplied": "Provided by the user as a description, not as a request setting.",
    "inferred": "Derived under a documented rule, which the setting or metric records.",
    "unknown": "Not available from any source.",
}

_SYNTHETIC_VERIFIED: Final = (
    "Where a real run's value is sent to Portfolio123 or captured from its response. Here it comes"
    " from the run's configuration or its invented response: nothing was sent, and no value came"
    " from Portfolio123."
)
"""What `verified` means in a synthetic run's report, which never calls its values Portfolio123's
(DSC-04)."""

_ATTEMPT_OUTCOMES: Final[dict[str, str]] = {
    "succeeded": (
        "Portfolio123 returned a response, which was saved. That says nothing about the strategy."
    ),
    "failed": "The attempt ended with a recorded error.",
    "unknown": (
        "A request may have been sent, and no response was durably recorded. It's never retried"
        " automatically."
    ),
    "running": (
        "The attempt has a start record and no attempt record: the request may have been sent,"
        " and how the attempt ended wasn't recorded."
    ),
}

_EXCHANGE_RESULTS: Final[dict[str, str]] = {
    "response": "Response",
    "not_connected": "Not connected: nothing was sent",
    "interrupted": "Interrupted: no complete response arrived",
}

_APPROVALS: Final[dict[str, str]] = {
    "interactive": "Approved interactively: the plan was shown, and <code>approve</code> typed.",
    "option": "Approved with <code>--approve</code> and the plan's full hash.",
    "not_required": "Not required: the synthetic run sends nothing.",
}
"""How the plan was approved, as HTML."""

_ROLES: Final[dict[ArtifactRole, str]] = {
    "plan": "Plan",
    "configuration": "Screen configuration, byte for byte",
    "start_record": "Start record",
    "attempt_record": "Attempt record",
    "provider_request": "Request, redacted",
    "provider_response": "Response, decoded",
    "provider_response_undecoded": "Response, undecoded",
    "metrics": "Normalized metrics",
    "settings": "Normalized settings",
    "report": "Report",
}

_CSS: Final = """\
:root{color-scheme:light dark;--text:#1d232b;--muted:#5b6573;--back:#ffffff;--panel:#f4f5f7;\
--rule:#d5d9df;--mark:#46556b}
@media (prefers-color-scheme:dark){:root{--text:#e3e6ea;--muted:#9aa3ae;--back:#14171b;\
--panel:#1d2127;--rule:#363c45;--mark:#a9b6c8}}
*{box-sizing:border-box}
body{margin:0;background:var(--back);color:var(--text);\
font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.page{max-width:70rem;margin:0 auto;padding:2rem 1rem 4rem}
h1{font-size:1.75rem;line-height:1.25;margin:.25rem 0 1rem}
h2{font-size:1.25rem;margin:2.5rem 0 .75rem;padding-top:1rem;border-top:1px solid var(--rule)}
h3{font-size:1rem;margin:1.5rem 0 .5rem}
p,ul{margin:.5rem 0}
.kind{margin:0;color:var(--muted);font-size:.875rem;letter-spacing:.04em;text-transform:uppercase}
.notice{margin:1rem 0;padding:.75rem 1rem;background:var(--panel);border:1px solid var(--rule);\
border-left:4px solid var(--mark)}
.synthetic{margin:1rem 0;padding:.75rem 1rem;border:2px dashed var(--mark)}
.muted{color:var(--muted)}
dl{display:grid;grid-template-columns:max-content 1fr;gap:.25rem 1.25rem;margin:.75rem 0}
dt{color:var(--muted)}
dd{margin:0}
.wide{overflow-x:auto;margin:.5rem 0 1rem}
table{border-collapse:collapse;width:100%;font-size:.9375rem}
caption{text-align:left;color:var(--muted);padding:.25rem 0}
th,td{text-align:left;vertical-align:top;padding:.375rem .625rem;border-bottom:1px solid var(--rule)}
th{font-weight:600;background:var(--panel)}
td{font-variant-numeric:tabular-nums}
code{font:.875em/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:pre-wrap;\
overflow-wrap:break-word}
.long code{overflow-wrap:anywhere}
a{color:inherit;text-underline-offset:2px}
nav ol{columns:2 18rem;padding-left:1.5rem}
footer{margin-top:3rem;padding-top:1rem;border-top:2px solid var(--rule)}
details{margin:1rem 0;padding:.75rem 1rem;background:var(--panel);border:1px solid var(--rule)}
summary{cursor:pointer;font-weight:600}
"""
"""The report's only styling. It's neutral: no status looks like a pass."""

_SECTIONS: Final = (
    ("objective", "Objective, purpose, and research status"),
    ("definitions", "Definitions, and changes from a baseline"),
    ("data", "Data sources, coverage, provenance, and missing values"),
    ("results", "Returns, risks, costs, and assumptions"),
    ("cases", "Cases and attempts"),
    ("robustness", "Robustness and concentration"),
    ("statistics", "Statistical methods and uncertainty"),
    ("evidence", "Development, selection, holdout, and forward evidence"),
    ("feasibility", "Feasibility, capacity, and missing execution evidence"),
    ("conclusion", "Conclusion, limitations, and artifacts"),
)
"""The sections docs/contracts.md lists, in order, by `id` and heading."""


def _text(value: str) -> str:
    """Text Trial Folio didn't write, as HTML: control and formatting characters, apart from tabs
    and line breaks, written as escapes, and then HTML-escaped."""
    return html.escape(visible(value, keep="\t\n\r"))


def _code(value: str) -> str:
    return f"<code>{_text(value)}</code>"


def _moment(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class _Setting:
    """One resolved setting, from `settings.csv` or, without it, from the plan."""

    name: str
    category: str
    value: str
    unit: str | None
    provenance: str
    inference_rule: str | None
    flags: tuple[str, ...]
    original_value: str | None
    expected: bool
    """Whether `provenance` is the plan's expectation, because `settings.csv` wasn't written."""


def _settings_of(run: SavedRun) -> tuple[_Setting, ...]:
    """The run's resolved settings: its `settings.csv` rows, or, without them, its plan's."""
    if run.settings is not None:
        return tuple(
            _Setting(
                row.setting,
                row.category,
                row.value,
                row.unit,
                row.provenance,
                row.inference_rule,
                row.flags,
                row.original_value,
                expected=False,
            )
            for row in run.settings
        )
    return tuple(
        _Setting(
            row.setting,
            row.category,
            setting_text(row.value),
            row.unit,
            row.expected_provenance,
            row.inference_rule,
            row.flags,
            None,
            expected=True,
        )
        for row in run.plan.cases[0].settings
    )


def _setting_brief(setting: _Setting) -> str:
    expected = "expected to be " if setting.expected else ""
    brief = f"{_code(setting.value)} ({expected}{setting.provenance})"
    if setting.inference_rule is not None:
        brief += f". {_text(setting.inference_rule)}"
    return brief


def _metric_label(row: MetricsRow) -> str:
    name = _METRICS.get(row.metric_id, (row.metric_id, ""))[0]
    return f"{_text(name)}, {row.subject} ({_code(row.metric_id)})"


def _unavailable(reason: UnavailableReason | None) -> str:
    if reason is None:
        return "Unavailable"
    return f"Unavailable ({_code(reason)}): {_REASONS[reason]}"


# The parts every report shares


def _concise_notice() -> str:
    lead = CONCISE_NOTICE.removesuffix(f"{CONCISE_NOTICE_LINK}.")
    link = f'<a href="#{FULL_NOTICE_ID}">{html.escape(CONCISE_NOTICE_LINK)}</a>'
    return f'<p class="notice" id="notice">{html.escape(lead)}{link}.</p>'


def _contents(sections: Sequence[tuple[str, str]]) -> list[str]:
    items = [f'<li><a href="#{key}">{heading}</a></li>' for key, heading in sections]
    return [
        '<nav aria-label="Contents">',
        "<ol>",
        *items,
        '<li><a href="#closing">Portfolio123 data, notices, and license</a></li>',
        "</ol>",
        "</nav>",
    ]


def _heading(key: str, sections: Sequence[tuple[str, str]] = _SECTIONS) -> str:
    number = next(i for i, (k, _) in enumerate(sections, 1) if k == key)
    return f'<section id="{key}">\n<h2>{number}. {dict(sections)[key]}</h2>'


def _closing(version: str, records: str) -> list[str]:
    """The closing section, by the report of `version`, rendered from `records`, such as "the
    run's saved records"."""
    statement_lead, _, statement_rest = PORTFOLIO123_DATA_STATEMENT.partition(
        PORTFOLIO123_TERMS_LINK
    )
    terms = f'<a href="{PORTFOLIO123_TERMS_URL}">{html.escape(PORTFOLIO123_TERMS_LINK)}</a>'
    notice = [f"<p>{html.escape(paragraph)}</p>" for paragraph in FULL_NOTICE]
    return [
        '<footer id="closing">',
        (
            f'<p id="portfolio123-data"><strong>{html.escape(PORTFOLIO123_DATA_LABEL)}</strong>'
            f" {html.escape(statement_lead)}{terms}{html.escape(statement_rest)}</p>"
        ),
        f'<details id="{FULL_NOTICE_ID}">',
        "<summary>Full research and financial-result notice, and license</summary>",
        *notice,
        (
            f"<p>License: {html.escape(LICENSE_NAME)}, <code>{LICENSE_ID}</code>. Notice version"
            f' {NOTICE_VERSION}. Read <a href="{license_url(version)}">the LICENSE'
            f" published with Trial Folio {version}</a>.</p>"
        ),
        "</details>",
        f'<p class="muted">Rendered by Trial Folio {version} from {records}.</p>',
        "</footer>",
    ]


class _Report:
    def __init__(self, run: SavedRun, base: tuple[str, ...] | None, version: str) -> None:
        self._run = run
        self._base = base
        self._version = version
        self._case = run.plan.cases[0]
        self._settings = _settings_of(run)
        self._by_name = {setting.name: setting for setting in self._settings}
        self._metrics = {(row.subject, row.metric_id): row for row in run.metrics or ()}

    def document(self) -> str:
        manifest = self._run.manifest
        title = self._run.plan.title
        parts = [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f'<meta name="generator" content="Trial Folio {self._version}">',
            f"<title>{_text(title)} · Trial Folio run report</title>",
            f"<style>\n{_CSS}</style>",
            "</head>",
            "<body>",
            '<div class="page">',
            "<header>",
            '<p class="kind">Trial Folio run report'
            + (" · Synthetic example" if manifest.synthetic else "")
            + "</p>",
            f"<h1>{_text(title)}</h1>",
            _concise_notice(),
            *self._synthetic_banner(),
            *self._status(),
            *_contents(_SECTIONS),
            "</header>",
            "<main>",
            *self._objective(),
            *self._definitions(),
            *self._data(),
            *self._results(),
            *self._cases(),
            *self._robustness(),
            *self._statistics(),
            *self._evidence(),
            *self._feasibility(),
            *self._conclusion(),
            "</main>",
            *_closing(self._version, "the run's saved records"),
            "</div>",
            "</body>",
            "</html>",
        ]
        return "\n".join(parts) + "\n"

    # The top of the report

    def _synthetic_banner(self) -> list[str]:
        if not self._run.manifest.synthetic:
            return []
        return [
            (
                '<p class="synthetic"><strong>Synthetic example.</strong> This run was written by'
                " <code>trialfolio demo</code> from invented values. None of them comes from"
                " Portfolio123, and nothing was sent to it.</p>"
            )
        ]

    def _status(self) -> list[str]:
        manifest = self._run.manifest
        outcome = manifest.outcome
        if manifest.error is not None:
            outcome += f" ({_code(manifest.error.code)})"
        return [
            "<dl>",
            f"<dt>Run outcome</dt><dd>{outcome}. An execution status, not a research finding.</dd>",
            f"<dt>Statistical validation</dt><dd>{NOT_ASSESSED}</dd>",
            f"<dt>Trading readiness</dt><dd>{NOT_ASSESSED}</dd>",
            f"<dt>Results</dt><dd>{self._nature()}</dd>",
            "</dl>",
        ]

    def _nature(self) -> str:
        """What kind of results the run holds (DSC-04)."""
        if self._run.manifest.synthetic:
            return "Synthetic: invented values, neither backtested nor actual results."
        return (
            "Backtested: from applying the screen's rules to historical data, not from actual"
            " trades."
        )

    # 1. Objective

    def _objective(self) -> list[str]:
        plan = self._run.plan
        purpose = (
            f"<p>{_text(plan.purpose)}</p>"
            if plan.purpose is not None
            else '<p class="muted">No purpose was declared.</p>'
        )
        benchmark = self._by_name.get("benchmark")
        return [
            _heading("objective"),
            "<dl>",
            (
                "<dt>Objective</dt><dd>Unavailable: a screen run declares no research objective,"
                " only a title and an optional purpose.</dd>"
            ),
            f"<dt>Title</dt><dd>{_text(plan.title)}</dd>",
            "<dt>Benchmark</dt><dd>"
            + (_code(benchmark.value) if benchmark else "Unavailable: the run has none.")
            + "</dd>",
            f"<dt>Statistical validation</dt><dd>{NOT_ASSESSED}</dd>",
            f"<dt>Trading readiness</dt><dd>{NOT_ASSESSED}</dd>",
            "</dl>",
            "<h3>Declared purpose</h3>",
            purpose,
            "</section>",
        ]

    # 2. Definitions

    def _definitions(self) -> list[str]:
        rows = [
            f"<tr><td>{name}</td><td>{_code(metric_id)}</td><td>{definition}</td></tr>"
            for metric_id, (name, definition) in _METRICS.items()
        ]
        source = (
            f"the run's invented response, laid out as {_code(LAYOUT)} version 1: none comes from"
            " Portfolio123. Each is defined as that layout defines it"
            if self._run.manifest.synthetic
            else f"Portfolio123's response, laid out as {_code(LAYOUT)} version 1"
        )
        return [
            _heading("definitions"),
            (
                f"<p>The metrics are read from {source}. The benchmark's metrics are defined as the"
                " strategy's.</p>"
            ),
            '<div class="wide"><table>',
            "<thead><tr><th>Metric</th><th>Identifier</th><th>Definition</th></tr></thead>",
            "<tbody>",
            *rows,
            "</tbody></table></div>",
            "<h3>Changes from a baseline</h3>",
            (
                "<p>Unavailable: a single run has no baseline, so no setting is classified as an"
                " intended change or an unexplained mismatch.</p>"
            ),
            "</section>",
        ]

    # 3. Data sources

    def _data(self) -> list[str]:
        manifest = self._run.manifest
        parsers = ", ".join(
            f"{_code(parser.layout)} version {parser.layout_version}, parser version"
            f" {parser.parser_version}"
            for parser in manifest.parsers
        )
        source = (
            "Invented values, packaged with Trial Folio for the demo, in the layout of"
            " Portfolio123's screen backtest response. Nothing was sent to Portfolio123."
            if manifest.synthetic
            else "Portfolio123's screen backtest, through <code>p123api</code>'s"
            " <code>screen_backtest</code>."
        )
        vendor = self._by_name.get("data_vendor")
        pit = self._by_name.get("pit_method")
        meanings = _PROVENANCE | ({"verified": _SYNTHETIC_VERIFIED} if manifest.synthetic else {})
        return [
            _heading("data"),
            "<dl>",
            f"<dt>Source</dt><dd>{source}</dd>",
            f"<dt>Response layout</dt><dd>{parsers or 'Unavailable: no response was read.'}</dd>",
            "<dt>Data vendor</dt><dd>"
            + (_setting_brief(vendor) if vendor else "Unavailable")
            + "</dd>",
            "<dt>Point-in-time method</dt><dd>"
            + (_setting_brief(pit) if pit else "Unavailable")
            + "</dd>",
            "</dl>",
            "<h3>Coverage</h3>",
            *self._coverage(),
            "<h3>Provenance</h3>",
            "<p>Each setting and metric records where its value came from:</p>",
            "<ul>",
            *(
                f"<li>{_code(name)}: {meaning}</li>"
                for name, meaning in meanings.items()
                if name in self._provenances()
            ),
            "</ul>",
            "<h3>Missing values</h3>",
            *self._missing(),
            "<h3>Exclusions</h3>",
            f"<p>{self._exclusions()}</p>",
            "</section>",
        ]

    def _exclusions(self) -> str:
        forms = {response.form for response in self._responses()}
        if not forms:
            return "None: the run saved no response."
        if "decoded" in forms:
            kept = (
                "None. Trial Folio excludes nothing from the response, and keeps it whole as it"
                " was saved."
            )
            if self._run.manifest.capabilities.return_series == "source_only":
                kept += " Its per-period series is preserved there, but not interpreted."
            return kept
        return "None. The response is kept whole, as it came, undecoded."

    def _responses(self) -> list[SavedResponse]:
        return [
            attempt.record.response
            for attempt in self._run.attempts
            if attempt.record is not None and attempt.record.response is not None
        ]

    def _provenances(self) -> set[str]:
        found = {setting.provenance for setting in self._settings}
        found.update(row.provenance for row in self._metrics.values())
        return found

    def _coverage(self) -> list[str]:
        if self._run.metrics is None:
            return [
                "<p>The coverage couldn't be established: "
                + self._no_tables_reason()
                + " The requested dates are in the settings below.</p>"
            ]
        rows: list[str] = []
        established = False
        for setting_name, metric_id in (
            ("start_date", "coverage_start"),
            ("end_date", "coverage_end"),
        ):
            setting = self._by_name.get(setting_name)
            metric = self._metrics.get(("strategy", metric_id))
            requested = _code(setting.value) if setting else "Unavailable"
            if metric is None or metric.value is None:
                reason = metric.unavailable_reason if metric else None
                actual = _unavailable(reason)
                status = "Couldn't be established"
            else:
                established = True
                actual = _code(metric.value)
                if setting is None:
                    status = "Not compared: the requested date is unavailable"
                elif metric.value == setting.value:
                    status = "Matches"
                elif "coverage_mismatch" in setting.flags:
                    status = "Differs: flagged <code>coverage_mismatch</code>"
                else:
                    status = "Differs"
            label = _METRICS[metric_id][0]
            rows.append(
                f"<tr><td>{label}</td><td>{requested}</td><td>{actual}</td>"
                f"<td>{_code('date')}</td><td>{status}</td></tr>"
            )
        periods = self._metrics.get(("strategy", "coverage_periods"))
        if periods is not None:
            count = (
                _code(periods.value)
                if periods.value is not None
                else _unavailable(periods.unavailable_reason)
            )
            rows.append(
                f"<tr><td>{_METRICS['coverage_periods'][0]}</td><td></td><td>{count}</td>"
                f"<td>{_code(periods.unit)}</td><td></td></tr>"
            )
        summary = (
            "The coverage is read from the dates of the response's periods, and compared with"
            " the requested dates."
            if established
            else "The coverage couldn't be established: the response's periods give no dates."
            " It isn't shown as matching the requested dates."
        )
        return [
            f"<p>{summary}</p>",
            '<div class="wide"><table>',
            (
                "<thead><tr><th>Date</th><th>Requested</th><th>Coverage</th><th>Unit</th>"
                "<th>Comparison</th></tr></thead>"
            ),
            "<tbody>",
            *rows,
            "</tbody></table></div>",
        ]

    def _missing(self) -> list[str]:
        if self._run.metrics is None:
            return [f"<p>Unavailable: {self._no_tables_reason()}</p>"]
        missing = [row for row in self._run.metrics if row.value is None]
        if not missing:
            return ["<p>None: every metric is available.</p>"]
        items = [
            f"<li>{_metric_label(row)}: {_unavailable(row.unavailable_reason)}</li>"
            for row in missing
        ]
        return [
            (
                f"<p>{len(missing)} of {len(self._run.metrics)} metrics are unavailable. None is shown"
                " as zero.</p>"
            ),
            "<ul>",
            *items,
            "</ul>",
        ]

    def _no_tables_reason(self) -> str:
        """Why the run has no normalized result."""
        responses = self._responses()
        if any(response.form == "undecoded" for response in responses):
            return (
                "the response couldn't be decoded as JSON, so it was saved as it came, and wasn't"
                " normalized."
            )
        if responses:
            error = self._run.manifest.error
            if error is not None and error.code == "provider.response_invalid":
                return (
                    "the saved response doesn't have the layout's required structure, so it"
                    " wasn't normalized."
                )
            return "the run wrote no normalized tables."
        return "no attempt succeeded, so there's no response to normalize."

    # 4. Results

    def _results(self) -> list[str]:
        parts = [_heading("results")]
        if self._run.metrics is None:
            parts.append(f"<p>The normalized result is unavailable: {self._no_tables_reason()}</p>")
        else:
            synthetic = self._run.manifest.synthetic
            source = "invented, as every value here is" if synthetic else "Portfolio123's"
            parts.append(
                "<p>Each value has exactly the digits the response carries, never padded or"
                f" rounded; Decimals counts them. The risk statistics are {source}, for the"
                " period the settings give as <code>risk_stats_period</code>.</p>"
            )
            benchmark = self._by_name.get("benchmark")
            for subject, heading in (("strategy", "Strategy"), ("benchmark", "Benchmark")):
                rows = [
                    row
                    for row in self._run.metrics
                    if row.subject == subject and row.metric_id not in _COVERAGE
                ]
                if subject == "benchmark" and benchmark is not None:
                    heading += f": {_code(benchmark.value)}"
                parts.extend([f"<h3>{heading}</h3>", *self._metrics_table(rows)])
        parts.extend(
            [
                "<h3>Costs</h3>",
                *self._settings_list(("slippage_percent", "commission", "carry_cost")),
                "<h3>Exposures</h3>",
                "<p>Unavailable: the response reports no exposures.</p>",
                "<h3>Implementation assumptions</h3>",
                *self._settings_list(
                    ("transaction_price", "rebalance_weeks", "max_holdings", "pit_method")
                ),
                "<h3>All settings</h3>",
                *self._settings_table(),
                "</section>",
            ]
        )
        return parts

    def _metrics_table(self, rows: Sequence[MetricsRow]) -> list[str]:
        if not rows:
            return ["<p>Unavailable: metrics.csv has no such metrics.</p>"]
        periods = {(row.period_start, row.period_end) for row in rows}
        if len(periods) == 1:
            ((start, end),) = periods
            caption = (
                f"Over {start.isoformat()} to {end.isoformat()}, the response's coverage."
                if start is not None and end is not None
                else "Over a period that couldn't be established."
            )
        else:
            caption = "The rows cover different periods; metrics.csv gives each one."
        body: list[str] = []
        for row in rows:
            if row.value is None:
                value = _unavailable(row.unavailable_reason)
            else:
                value = _code(row.value)
            name = _text(_METRICS.get(row.metric_id, (row.metric_id, ""))[0])
            if row.benchmark is not None:
                name += f" vs. {_text(row.benchmark)}"
            decimals = "" if row.source_decimals is None else str(row.source_decimals)
            location = _code(row.source_location) if row.source_location is not None else ""
            body.append(
                f"<tr><td>{name}<br>{_code(row.metric_id)}</td><td>{value}</td>"
                f"<td>{_code(row.unit)}</td><td>{decimals}</td><td>{_code(row.provenance)}</td>"
                f"<td>{location}</td></tr>"
            )
        return [
            '<div class="wide"><table>',
            f"<caption>{caption}</caption>",
            (
                "<thead><tr><th>Metric</th><th>Value</th><th>Unit</th><th>Decimals</th>"
                "<th>Provenance</th><th>Source</th></tr></thead>"
            ),
            "<tbody>",
            *body,
            "</tbody></table></div>",
        ]

    def _settings_list(self, names: Sequence[str]) -> list[str]:
        items: list[str] = []
        for name in names:
            setting = self._by_name.get(name)
            if setting is None:
                continue
            unit = f" {_code(setting.unit)}" if setting.unit is not None else ""
            note = _TOKENS.get(setting.value)
            items.append(
                f"<li>{_code(name)}: {_code(setting.value)}{unit}"
                + (f". {note}" if note else "")
                + "</li>"
            )
        return ["<ul>", *items, "</ul>"]

    def _settings_table(self) -> list[str]:
        provenance = "Provenance"
        if self._run.settings is None:
            provenance = "Expected provenance"
            intro = (
                "<p>settings.csv wasn't written, so these are the plan's resolved settings, each"
                " with the provenance the plan expects it to have once the request is sent.</p>"
            )
        else:
            intro = (
                "<p>As settings.csv records them. <em>As written</em> is the value's text in the"
                " screen configuration.</p>"
            )
        body: list[str] = []
        for setting in self._settings:
            if setting.inference_rule is not None:
                note = _text(setting.inference_rule)
            else:
                note = _TOKENS.get(setting.value, "")
            flags = "<br>".join(f"{_code(flag)}: {_FLAGS.get(flag, '')}" for flag in setting.flags)
            original = _code(setting.original_value) if setting.original_value is not None else ""
            body.append(
                f"<tr><td>{_code(setting.name)}</td><td>{_code(setting.category)}</td>"
                f"<td>{_code(setting.value)}</td>"
                f"<td>{_code(setting.unit) if setting.unit is not None else ''}</td>"
                f"<td>{_code(setting.provenance)}</td><td>{flags}</td><td>{original}</td>"
                f"<td>{note}</td></tr>"
            )
        return [
            intro,
            '<div class="wide"><table>',
            (
                "<thead><tr><th>Setting</th><th>Category</th><th>Value</th><th>Unit</th>"
                f"<th>{provenance}</th><th>Flags</th><th>As written</th><th>Notes</th></tr></thead>"
            ),
            "<tbody>",
            *body,
            "</tbody></table></div>",
        ]

    # 5. Cases and attempts

    def _cases(self) -> list[str]:
        manifest = self._run.manifest
        plan = self._run.plan
        budget = plan.budget
        counts = manifest.counts
        attempts = counts.attempts
        cost = (
            f"{counts.cost} credits, as Portfolio123 reported"
            if counts.cost is not None
            else "Not reported"
        )
        parts = [
            _heading("cases"),
            (
                "<p>A run has one case: the resolved settings, identified by their case ID. Every"
                " attempt of it is listed, whatever its outcome.</p>"
            ),
            *self._synthetic_records(),
            "<dl>",
            f"<dt>Case</dt><dd>{_code(self._case.case_id)}</dd>",
            f"<dt>Plan hash</dt><dd>{_code(plan.plan_hash)}</dd>",
            f"<dt>Approval</dt><dd>{_APPROVALS[manifest.approval]}</dd>",
            (
                f"<dt>Budget</dt><dd>{budget.provider_requests} provider request, at most"
                f" {budget.credits} credits at Portfolio123's documented cost"
                f" ({_text(budget.credits_per_request_source.title)}, checked"
                f" {budget.credits_per_request_source.checked.isoformat()}), and at most"
                f" {budget.authentication_calls} authentication call.</dd>"
            ),
            (
                f"<dt>Attempts</dt><dd>{attempts.succeeded} succeeded, {attempts.failed} failed,"
                f" {attempts.unknown} unknown, {attempts.running} running</dd>"
            ),
            (
                f"<dt>Provider requests</dt><dd>{counts.provider_requests}: the sends that may have"
                " reached Portfolio123, which may be charged even when they fail. Authentication"
                " isn't counted.</dd>"
            ),
            f"<dt>Retries</dt><dd>{counts.retries}</dd>",
            f"<dt>Cost</dt><dd>{cost}</dd>",
            "</dl>",
        ]
        if not self._run.attempts:
            parts.append("<p>The run has no attempt record.</p>")
        for attempt in self._run.attempts:
            parts.extend(self._attempt(attempt))
        parts.extend(
            [
                "<h3>Versions</h3>",
                "<dl>",
                (
                    f"<dt>Run written by</dt><dd>Trial Folio {_text(manifest.trialfolio_version)},"
                    f" command {_code(manifest.command.name)}, started"
                    f" {_moment(manifest.command.started_at)}</dd>"
                ),
                (
                    f"<dt>Plan built by</dt><dd>Trial Folio {_text(plan.trialfolio_version)},"
                    f" canonicalization version {plan.canonicalization_version}</dd>"
                ),
                (
                    f"<dt>Provider wrapper</dt><dd><code>p123api</code>"
                    f" {_text(plan.provider_wrapper.p123api)}</dd>"
                ),
                (
                    f"<dt>Transport</dt><dd><code>requests</code> {_text(plan.transport.requests)},"
                    f" <code>urllib3</code> {_text(plan.transport.urllib3)}</dd>"
                ),
                (
                    f"<dt>License and notice</dt><dd>Recorded with the run:"
                    f" {_code(manifest.license_id)}, notice version"
                    f" {_text(manifest.notice_version)}</dd>"
                ),
                f"<dt>Report rendered by</dt><dd>Trial Folio {self._version}</dd>",
                "</dl>",
                "</section>",
            ]
        )
        return parts

    def _synthetic_records(self) -> list[str]:
        if not self._run.manifest.synthetic:
            return []
        return [
            (
                "<p>The run is synthetic, so its attempt, the attempt's exchanges, and the counts"
                " below are invented, as a real run would record them. Nothing was sent to"
                " Portfolio123, and nothing was charged.</p>"
            )
        ]

    def _attempt(self, attempt: SavedAttempt) -> list[str]:
        status = attempt.status
        record = attempt.record
        first = record if record is not None else attempt.start
        exchanges = first.exchanges if first is not None else ()
        meaning = _ATTEMPT_OUTCOMES[status.outcome]
        if status.outcome == "succeeded" and self._run.manifest.synthetic:
            meaning = "The run's invented response was saved. That says nothing about the strategy."
        facts = [f"<dt>Outcome</dt><dd>{_code(status.outcome)}: {meaning}</dd>"]
        if record is not None and record.error is not None:
            facts.append(
                f"<dt>Error</dt><dd>{_code(record.error.code)}: {_text(record.error.message)}</dd>"
            )
        facts.append(
            f"<dt>Possibly charged</dt><dd>{'Yes' if status.possibly_charged else 'No'}</dd>"
        )
        facts.append(f"<dt>Provider requests</dt><dd>{status.provider_requests}</dd>")
        if first is not None:
            facts.append(f"<dt>Started</dt><dd>{_moment(first.started_at)}</dd>")
        if record is not None:
            facts.append(f"<dt>Ended</dt><dd>{_moment(record.ended_at)}</dd>")
            cost = record.provider_metadata.cost
            facts.append(
                "<dt>Cost</dt><dd>"
                + (
                    f"{cost} credits, as Portfolio123 reported"
                    if cost is not None
                    else "Not reported"
                )
                + "</dd>"
            )
        rows = [
            f"<tr><td>{index}</td><td>{_code(exchange.request)}</td>"
            f"<td>{_EXCHANGE_RESULTS[exchange.result]}</td>"
            f"<td>{'' if exchange.status is None else exchange.status}</td>"
            f"<td>{_code(exchange.note) if exchange.note else ''}</td></tr>"
            for index, exchange in enumerate(exchanges, 1)
        ]
        return [
            f"<h3>Attempt {_code(str(status.attempt_id))}</h3>",
            "<dl>",
            *facts,
            "</dl>",
            '<div class="wide"><table>',
            "<caption>Its HTTP exchanges, in order</caption>",
            (
                "<thead><tr><th>#</th><th>Request</th><th>Result</th><th>Status</th><th>Note</th>"
                "</tr></thead>"
            ),
            "<tbody>",
            *rows,
            "</tbody></table></div>",
        ]

    # 6 to 9

    def _robustness(self) -> list[str]:
        return [
            _heading("robustness"),
            (
                f"<p>{NOT_ASSESSED}. Robustness results and the concentration of contributions need"
                " more than one run's summary statistics, and Trial Folio doesn't assess them.</p>"
            ),
            "</section>",
        ]

    def _statistics(self) -> list[str]:
        return [
            _heading("statistics"),
            (
                f"<p>Statistical validation: {NOT_ASSESSED}. No statistical method was applied, so"
                " the report states no uncertainty, multiple-testing adjustment, or power. Summary"
                " statistics alone don't support intervals, a return series, or a drawdown history,"
                " so none is shown or reconstructed.</p>"
            ),
            "</section>",
        ]

    def _evidence(self) -> list[str]:
        run = "one synthetic example" if self._run.manifest.synthetic else "one backtest"
        return [
            _heading("evidence"),
            (
                f"<p>Unavailable: the run is {run} over the requested dates. It has no separate"
                " development, selection, holdout, or forward period.</p>"
            ),
            f"<p>{self._nature()}</p>",
            "</section>",
        ]

    def _feasibility(self) -> list[str]:
        missing = ["<li>Actual trades: none.</li>"]
        commission = self._by_name.get("commission")
        if commission is not None and commission.value == "not_modeled":
            missing.append(f"<li>Commission: {_TOKENS['not_modeled']}</li>")
        unsent = [s.name for s in self._settings if s.value == "not_sent"]
        if unsent:
            missing.append(
                "<li>Parameters not sent, whose defaults aren't documented: "
                + ", ".join(_code(name) for name in unsent)
                + ".</li>"
            )
        if self._run.manifest.capabilities.return_series == "source_only":
            missing.append(
                "<li>Turnover, positions, and per-period returns: preserved in the saved"
                " response, but not interpreted.</li>"
            )
        return [
            _heading("feasibility"),
            f"<p>Trading readiness: {NOT_ASSESSED}. Feasibility and capacity aren't assessed.</p>",
            "<p>Execution evidence this run doesn't have:</p>",
            "<ul>",
            *missing,
            "</ul>",
            "</section>",
        ]

    # 10. Conclusion

    def _conclusion(self) -> list[str]:
        manifest = self._run.manifest
        if manifest.outcome == "completed":
            execution = (
                "The run completed: Trial Folio sent the planned request, saved the response,"
                " and normalized it."
                if not manifest.synthetic
                else "The run completed: Trial Folio wrote the synthetic run and normalized it."
            )
        else:
            code = manifest.error.code if manifest.error is not None else ""
            execution = f"The run didn't complete: it ended with {_code(code)}."
        conclusion = (
            f"{execution} That's a statement about execution, not about the strategy."
            " Statistical validation and trading readiness are not assessed, so this report"
            " permits no conclusion about whether the strategy is useful, or whether its results"
            " could be achieved."
        )
        return [
            _heading("conclusion"),
            "<h3>Permitted conclusion</h3>",
            f"<p>{conclusion}</p>",
            "<h3>Limitations</h3>",
            "<ul>",
            *(f"<li>{item}</li>" for item in self._limitations()),
            "</ul>",
            "<h3>Artifacts</h3>",
            *self._artifacts(),
            "</section>",
        ]

    def _limitations(self) -> list[str]:
        manifest = self._run.manifest
        items = [self._nature()]
        reproducibility = manifest.reproducibility
        unsnapshotted = [
            reference.setting
            for reference in reproducibility.external_references
            if not reference.snapshotted
        ]
        if reproducibility.status == "incomplete":
            names = " and ".join(_code(name) for name in unsnapshotted)
            verb = "names an object" if len(unsnapshotted) == 1 else "name objects"
            items.append(
                f"Reproducibility is incomplete: {names} {verb} in the Portfolio123 account whose"
                " definition wasn't captured. If it changes, the same configuration can give"
                " different results."
            )
        else:
            items.append("Reproducibility is complete: every setting is recorded in full.")
        if not manifest.synthetic:
            items.append(
                "Portfolio123's data and engines change, so running the configuration again may"
                " give different results. A rerun is a new attempt, never a replacement."
            )
        inferred = [s.name for s in self._settings if "inferred_default" in s.flags]
        if inferred:
            items.append(
                "Inferred defaults, not reported by Portfolio123: "
                + ", ".join(_code(name) for name in inferred)
                + "."
            )
        mismatched = [s.name for s in self._settings if "coverage_mismatch" in s.flags]
        if mismatched:
            items.append(
                "The coverage differs from the requested "
                + " and ".join(_code(name) for name in mismatched)
                + "."
            )
        if self._run.metrics is not None:
            unavailable = sum(row.value is None for row in self._run.metrics)
            if unavailable:
                items.append(f"{unavailable} metrics are unavailable, with their reasons above.")
        else:
            items.append(f"The normalized result is unavailable: {self._no_tables_reason()}")
        items.append(
            "Only summary statistics are reported: no return series, drawdown history, or"
            " interval is shown."
        )
        return items

    def _artifacts(self) -> list[str]:
        artifacts = [a for a in self._run.manifest.artifacts if a.role != "report"]
        rows = [
            (
                f"<tr><td>{self._link(MANIFEST_PATH)}</td><td>Manifest, written last</td><td></td>"
                "<td></td></tr>"
            ),
            *(self._artifact_row(artifact) for artifact in artifacts),
        ]
        where = (
            "Each file is named by its path in the run's directory."
            if self._base is None
            else "Each file links to the run's copy, by a path relative to this report."
        )
        return [
            f"<p>{where} An <code>artifact_id</code> is the SHA-256 of the file's bytes.</p>",
            '<div class="wide"><table>',
            (
                "<thead><tr><th>File</th><th>Role</th><th>Size, bytes</th><th>artifact_id</th>"
                "</tr></thead>"
            ),
            "<tbody>",
            *rows,
            "</tbody></table></div>",
        ]

    def _artifact_row(self, artifact: ManifestArtifact) -> str:
        return (
            f'<tr><td class="long">{self._link(artifact.path)}</td>'
            f"<td>{_ROLES[artifact.role]}</td><td>{artifact.size}</td>"
            f'<td class="long">{_code(artifact.artifact_id)}</td></tr>'
        )

    def _link(self, path: str) -> str:
        if self._base is None:
            return _code(path)
        segments = (*self._base, *(quote(part, safe="") for part in path.split("/")))
        return f'<a href="{html.escape("/".join(segments))}">{_code(path)}</a>'


# The review report (R02-T07)

_REVIEW_SECTIONS: Final = (
    ("objective", "Objective, purpose, and research status"),
    ("definitions", "Definitions, and changes from the baseline"),
    ("data", "Data sources, coverage, provenance, and missing values"),
    ("results", "Returns, risks, costs, and assumptions"),
    ("cases", "Results compared, and their runs"),
    ("robustness", "Robustness and concentration"),
    ("statistics", "Statistical methods and uncertainty"),
    ("evidence", "Development, selection, holdout, and forward evidence"),
    ("feasibility", "Feasibility, capacity, and missing execution evidence"),
    ("conclusion", "Conclusion, limitations, and artifacts"),
)
"""A review report's sections: a run report's, with the same `id`s, and headings for a
review."""

_SETTING_CLASSES: Final = (
    ("same", "The two values read the same."),
    ("intended_change", "The values differ, and the result declares the change."),
    ("unexplained_mismatch", "The values differ, and the result doesn't declare the change."),
    ("unknown", "The setting is missing from one of the two runs, so it can't be compared."),
)

_METRIC_CLASSES: Final = (
    ("differenced", "Both values are available and comparable, so their difference is given."),
    (
        "not_comparable",
        (
            "Both values are available, but their contexts differ, so both are shown, without a"
            " difference."
        ),
    ),
    ("unavailable", "A value is unavailable, so there's no difference."),
)

_DIFFERENCE_REASONS: Final[dict[DifferenceReason, str]] = {
    "input_unavailable": "A value is unavailable.",
    "different_unit": "The two values are in different units.",
    "different_benchmark": "The runs' benchmarks differ.",
    "unknown_period": "A run's period couldn't be established, so it isn't shown as matching.",
    "different_period": "The runs' periods differ.",
}
"""Why a metric isn't differenced, as `differences.csv`'s `reason` gives it, in the order the
comparison applies them."""

_REVIEW_ROLES: Final[dict[ReviewArtifactRole, str]] = {
    "configuration": "Review configuration, byte for byte",
    "run_manifest": "Run manifest, copied",
    "plan": "Plan, copied",
    "metrics": "Normalized metrics, copied",
    "settings": "Normalized settings, copied",
    "differences": "Differences from the baseline",
    "report": "Report",
}

_LAYOUT_METRICS: Final[dict[str, str]] = {
    "total_return": "Cumulative return over the response's periods.",
    "sharpe_ratio": (
        "The Sharpe ratio, as the response layout defines it. Its risk-free rate isn't documented."
    ),
    "sortino_ratio": (
        "The Sortino ratio, as the response layout defines it. Its risk-free rate and target"
        " aren't documented."
    ),
    "alpha": (
        "Alpha against the benchmark, as the response layout defines it. Its unit is inferred from"
        " the value's magnitude, and its method isn't documented."
    ),
}
"""A review with a synthetic result gives these definitions in place of a run report's, which call
a value Portfolio123's or a backtest's. They hold for a synthetic result's values and a backtested
one's alike (DSC-04)."""

_SYNTHETIC_NOT_SENT: Final = (
    "Not sent: where a real run leaves it to Portfolio123's default, which isn't documented. Here"
    " nothing was sent, and no value came from Portfolio123."
)
"""What `not_sent` means in a review whose results are all synthetic, whose runs sent nothing."""

_SETTING_COUNT: Final = 23
"""The screen settings each result's rows compare."""

_COMPARISON_FLAGS: Final = frozenset(
    {"critical_unexplained_mismatch", "critical_unknown", "intended_change_not_observed"}
)
"""The flags a setting row's comparison gives it, rather than its runs' rows."""


def _flag_list(flags: Sequence[str]) -> str:
    """Each flag code, with what it means, one to a line."""
    return "<br>".join(f"{_code(flag)}: {_FLAGS.get(flag, '')}" for flag in flags)


def _series(items: Sequence[str]) -> str:
    """`a`, `a and b`, or `a, b, and c`."""
    if len(items) <= 2:
        return " and ".join(items)
    return f"{', '.join(items[:-1])}, and {items[-1]}"


class _ReviewReport:
    def __init__(self, review: ReviewEvidence, version: str) -> None:
        self._review = review
        self._version = version
        self._baseline = review.configuration.baseline
        self._others = tuple(
            checked for checked in review.inputs if checked.result.label != self._baseline
        )
        self._synthetic = tuple(
            checked.result.label for checked in review.inputs if checked.run.manifest.synthetic
        )
        self._settings = {
            checked.result.label: {setting.name: setting for setting in _settings_of(checked.run)}
            for checked in review.inputs
        }
        self._metrics = {
            checked.result.label: {
                (row.subject, row.metric_id): row for row in checked.run.metrics or ()
            }
            for checked in review.inputs
        }
        self._rows = {
            (row.label, row.kind, row.subject, row.name): row for row in review.differences.rows
        }

    def document(self) -> str:
        title = self._review.configuration.title
        kind = ""
        if self._synthetic:
            everything = len(self._synthetic) == len(self._review.inputs)
            kind = " · Synthetic results" if everything else " · Includes synthetic results"
        parts = [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f'<meta name="generator" content="Trial Folio {self._version}">',
            f"<title>{_text(title)} · Trial Folio review report</title>",
            f"<style>\n{_CSS}</style>",
            "</head>",
            "<body>",
            '<div class="page">',
            "<header>",
            f'<p class="kind">Trial Folio review report{kind}</p>',
            f"<h1>{_text(title)}</h1>",
            _concise_notice(),
            *self._synthetic_banner(),
            *self._status(),
            *_contents(_REVIEW_SECTIONS),
            "</header>",
            "<main>",
            *self._objective(),
            *self._definitions(),
            *self._data(),
            *self._results(),
            *self._cases(),
            *self._robustness(),
            *self._statistics(),
            *self._evidence(),
            *self._feasibility(),
            *self._conclusion(),
            "</main>",
            *_closing(self._version, "the review's records"),
            "</div>",
            "</body>",
            "</html>",
        ]
        return "\n".join(parts) + "\n"

    # How results are named

    def _name(self, label: str) -> str:
        """A result's label, marked when it's synthetic, as it appears beside its values."""
        return _code(label) + (" (synthetic)" if label in self._synthetic else "")

    def _labels(self, labels: Sequence[str]) -> str:
        return _series([_code(label) for label in labels])

    def _sharing(self, label: str) -> tuple[str, ...]:
        """The other results whose runs saved the response `label`'s run did."""
        for shared in self._review.differences.shared_responses:
            if label in shared.labels:
                return tuple(other for other in shared.labels if other != label)
        return ()

    # The top of the report

    def _synthetic_banner(self) -> list[str]:
        if not self._synthetic:
            return []
        one = len(self._synthetic) == 1
        return [
            (
                '<p class="synthetic"><strong>Synthetic results.</strong>'
                f" {self._labels(self._synthetic)} {'is' if one else 'are'} synthetic: written by"
                " <code>trialfolio demo</code> from invented values. None of"
                f" {'its' if one else 'their'} values comes from Portfolio123, and nothing was"
                f" sent to it. {'It is' if one else 'Each is'} marked synthetic wherever its"
                " values appear.</p>"
            )
        ]

    def _status(self) -> list[str]:
        return [
            "<dl>",
            (
                "<dt>Review outcome</dt><dd>completed: each result was compared with the"
                " baseline. An execution status, not a research finding.</dd>"
            ),
            f"<dt>Statistical validation</dt><dd>{NOT_ASSESSED}</dd>",
            f"<dt>Trading readiness</dt><dd>{NOT_ASSESSED}</dd>",
            f"<dt>Results</dt><dd>{self._nature()}</dd>",
            "</dl>",
        ]

    def _nature(self) -> str:
        """What kind of results the review compares (DSC-04)."""
        synthetic = "invented values, neither backtested nor actual results"
        backtested = "from applying each screen's rules to historical data, not from actual trades"
        if not self._synthetic:
            return f"Backtested: {backtested}."
        if len(self._synthetic) == len(self._review.inputs):
            return f"Synthetic: {synthetic}."
        return (
            f"Backtested, {backtested}, apart from {self._labels(self._synthetic)}: synthetic,"
            f" {synthetic}."
        )

    # 1. Objective

    def _objective(self) -> list[str]:
        configuration = self._review.configuration
        purpose = (
            f"<p>{_text(configuration.purpose)}</p>"
            if configuration.purpose is not None
            else '<p class="muted">No purpose was declared.</p>'
        )
        return [
            _heading("objective", _REVIEW_SECTIONS),
            "<dl>",
            (
                "<dt>Objective</dt><dd>Unavailable: a review declares no research objective,"
                " only a title and an optional purpose.</dd>"
            ),
            f"<dt>Title</dt><dd>{_text(configuration.title)}</dd>",
            f"<dt>Baseline</dt><dd>{self._name(self._baseline)}</dd>",
            f"<dt>Statistical validation</dt><dd>{NOT_ASSESSED}</dd>",
            f"<dt>Trading readiness</dt><dd>{NOT_ASSESSED}</dd>",
            "</dl>",
            "<h3>Declared purpose</h3>",
            purpose,
            "<h3>Benchmarks</h3>",
            *self._benchmarks(),
            "</section>",
        ]

    def _benchmarks(self) -> list[str]:
        rows: list[str] = []
        for checked in self._review.inputs:
            label = checked.result.label
            setting = self._settings[label].get("benchmark")
            value = _code(setting.value) if setting is not None else "Missing"
            if label == self._baseline:
                comparison = "The baseline's"
            else:
                comparison = self._setting_comparison(self._setting_row(label, "benchmark"))
            rows.append(
                f"<tr><td>{self._name(label)}</td><td>{value}</td><td>{comparison}</td></tr>"
            )
        return [
            "<p>Each result's benchmark, compared with the baseline's.</p>",
            '<div class="wide"><table>',
            (
                "<thead><tr><th>Result</th><th>Benchmark</th><th>Against the baseline</th>"
                "</tr></thead>"
            ),
            "<tbody>",
            *rows,
            "</tbody></table></div>",
        ]

    def _setting_row(self, label: str, name: str) -> DifferencesRow:
        return self._rows[(label, "setting", None, name)]

    def _setting_comparison(self, row: DifferencesRow) -> str:
        meanings = {
            "same": "Same",
            "intended_change": "Differs: an intended change",
            "unexplained_mismatch": "Differs: an unexplained mismatch",
            "unknown": "Unknown: missing from a run",
        }
        shown = meanings[row.classification]
        flagged = [flag for flag in row.flags if flag in _COMPARISON_FLAGS]
        if flagged:
            shown += ", flagged " + _series([_code(flag) for flag in flagged])
        return shown

    # 2. Definitions

    def _definitions(self) -> list[str]:
        own = _LAYOUT_METRICS if self._synthetic else {}
        definitions = [
            f"<tr><td>{name}</td><td>{_code(metric_id)}</td>"
            f"<td>{own.get(metric_id, definition)}</td></tr>"
            for metric_id, (name, definition) in _METRICS.items()
        ]
        return [
            _heading("definitions", _REVIEW_SECTIONS),
            (
                f"<p>Each result is compared with the baseline, {self._name(self._baseline)}, by"
                f" the rules of {_code(METHOD)} version {METHOD_VERSION}: its 23 settings, and"
                " then its 20 metrics. <code>normalized/differences.csv</code> holds a row for"
                " each.</p>"
            ),
            "<h3>How settings are compared</h3>",
            "<ul>",
            *(f"<li>{_code(code)}: {meaning}</li>" for code, meaning in _SETTING_CLASSES),
            "</ul>",
            (
                "<p>A list or a ranking reads as JSON, and anything else as its text. The critical"
                " settings are the dates, the benchmark, the currency, the costs, the execution,"
                " the universe, the data source, and the strategy: an unexplained mismatch or an"
                " unknown value in one is flagged. An intended change to one is shown, but not as"
                " a defect.</p>"
            ),
            "<h3>How metrics are compared</h3>",
            "<ul>",
            *(f"<li>{_code(code)}: {meaning}</li>" for code, meaning in _METRIC_CLASSES),
            "</ul>",
            (
                "<p>A difference is the result's value minus the baseline's: in percentage points"
                " (<code>pp</code>) for percent metrics, in days for dates, and otherwise in the"
                " metric's unit. It has the smaller of the two values' decimal places, rounded"
                " half to even, so it never shows more precision than its source. The coverage"
                " rows are differenced whatever the periods are, because they're the period."
                " Every other metric is differenced only when the two periods are the same, and a"
                " benchmark-relative metric, or the benchmark's own, only when the two benchmarks"
                " are too. A metric that isn't differenced gives one reason, the first of these"
                " that applies:</p>"
            ),
            "<ul>",
            *(
                f"<li>{_code(reason)}: {meaning}</li>"
                for reason, meaning in _DIFFERENCE_REASONS.items()
            ),
            "</ul>",
            "<h3>Metric definitions</h3>",
            (
                f"<p>{self._metric_source()} The benchmark's metrics are defined as the"
                " strategy's.</p>"
            ),
            '<div class="wide"><table>',
            "<thead><tr><th>Metric</th><th>Identifier</th><th>Definition</th></tr></thead>",
            "<tbody>",
            *definitions,
            "</tbody></table></div>",
            *self._intended_changes(),
            *self._mismatches(),
            *self._unknown(),
            *self._same(),
            *self._baseline_settings(),
            "</section>",
        ]

    def _metric_source(self) -> str:
        layout = f"laid out as {_code(LAYOUT)} version 1"
        if not self._synthetic:
            return f"The metrics are read from each run's response from Portfolio123, {layout}."
        if len(self._synthetic) == len(self._review.inputs):
            return (
                f"The metrics are read from each run's invented response, {layout}: none comes"
                " from Portfolio123. Each is defined as that layout defines it."
            )
        return (
            f"The metrics are read from each run's response, {layout}: Portfolio123's for a"
            f" backtested result, and an invented one for {self._labels(self._synthetic)}, whose"
            " values don't come from Portfolio123. Each is defined as that layout defines it."
        )

    def _setting_rows(self) -> list[DifferencesRow]:
        return [row for row in self._review.differences.rows if row.kind == "setting"]

    def _baseline_value(self) -> str:
        """The heading of a column of the baseline's values, which names it, so a synthetic
        baseline's values are marked there too."""
        return f"<th>Baseline value, {self._name(self._baseline)}</th>"

    def _intended_changes(self) -> list[str]:
        declared = [row for row in self._setting_rows() if row.declared_reason is not None]
        parts = [
            "<h3>Intended changes</h3>",
            "<p>The changes each result declares, against the baseline, with its reason.</p>",
        ]
        if not declared:
            return [*parts, "<p>None: no result declares a change.</p>"]
        observed = {
            "intended_change": "Yes: the values differ.",
            "same": "No: the values are equal.",
            "unknown": "Can't be confirmed: the setting is missing from a run.",
            "unexplained_mismatch": "",
        }
        body = [
            f"<tr><td>{self._name(row.label)}</td><td>{_code(row.name)}</td>"
            f"<td>{self._value(row.baseline_value)}</td><td>{self._value(row.value)}</td>"
            f"<td>{self._unit(row.unit)}</td><td>{_text(row.declared_reason or '')}</td>"
            f"<td>{observed[row.classification]}</td><td>{self._flags(row)}</td></tr>"
            for row in declared
        ]
        return [
            *parts,
            '<div class="wide"><table>',
            (
                f"<thead><tr><th>Result</th><th>Setting</th>{self._baseline_value()}<th>Value</th>"
                "<th>Unit</th><th>Declared reason</th><th>Observed</th><th>Flags</th></tr></thead>"
            ),
            "<tbody>",
            *body,
            "</tbody></table></div>",
        ]

    def _mismatches(self) -> list[str]:
        rows = [row for row in self._setting_rows() if row.classification == "unexplained_mismatch"]
        parts = [
            "<h3>Unexplained mismatches</h3>",
            (
                "<p>Settings that differ from the baseline's without a declared change. In a"
                " critical category, each is flagged.</p>"
            ),
        ]
        if not rows:
            return [*parts, "<p>None: every setting that differs is declared.</p>"]
        body = [
            f"<tr><td>{self._name(row.label)}</td><td>{_code(row.name)}</td>"
            f"<td>{_code(row.category or '')}</td><td>{self._value(row.baseline_value)}</td>"
            f"<td>{self._value(row.value)}</td><td>{self._unit(row.unit)}</td>"
            f"<td>{self._flags(row)}</td></tr>"
            for row in rows
        ]
        return [
            *parts,
            '<div class="wide"><table>',
            (
                "<thead><tr><th>Result</th><th>Setting</th><th>Category</th>"
                f"{self._baseline_value()}<th>Value</th><th>Unit</th><th>Flags</th></tr></thead>"
            ),
            "<tbody>",
            *body,
            "</tbody></table></div>",
        ]

    def _unknown(self) -> list[str]:
        rows = [
            row
            for row in self._setting_rows()
            if row.classification == "unknown" and row.declared_reason is None
        ]
        if not rows:
            return []
        body = [
            f"<tr><td>{self._name(row.label)}</td><td>{_code(row.name)}</td>"
            f"<td>{_code(row.category or '')}</td><td>{self._value(row.baseline_value)}</td>"
            f"<td>{self._value(row.value)}</td><td>{self._flags(row)}</td></tr>"
            for row in rows
        ]
        return [
            "<h3>Unknown settings</h3>",
            "<p>Settings missing from one of the two runs, so they can't be compared.</p>",
            '<div class="wide"><table>',
            (
                "<thead><tr><th>Result</th><th>Setting</th><th>Category</th>"
                f"{self._baseline_value()}<th>Value</th><th>Flags</th></tr></thead>"
            ),
            "<tbody>",
            *body,
            "</tbody></table></div>",
        ]

    def _same(self) -> list[str]:
        rows = self._setting_rows()
        counts = [
            f"{sum(row.label == label and row.classification == 'same' for row in rows)}"
            f" of {_SETTING_COUNT} for {self._name(label)}"
            for label in (checked.result.label for checked in self._others)
        ]
        flagged = [
            row
            for row in rows
            if row.classification == "same" and row.flagged and row.declared_reason is None
        ]
        parts = [
            "<h3>Settings that are the same</h3>",
            f"<p>The settings that read the same as the baseline's: {_series(counts)}.</p>",
        ]
        if not flagged:
            return parts
        body = [
            f"<tr><td>{self._name(row.label)}</td><td>{_code(row.name)}</td>"
            f"<td>{self._value(row.value)}</td><td>{self._unit(row.unit)}</td>"
            f"<td>{self._flags(row)}</td></tr>"
            for row in flagged
        ]
        return [
            *parts,
            "<p>These are the same, but flagged:</p>",
            '<div class="wide"><table>',
            (
                "<thead><tr><th>Result</th><th>Setting</th><th>Value</th><th>Unit</th>"
                "<th>Flags</th></tr></thead>"
            ),
            "<tbody>",
            *body,
            "</tbody></table></div>",
        ]

    def _baseline_settings(self) -> list[str]:
        checked = next(c for c in self._review.inputs if c.result.label == self._baseline)
        settings = self._settings[self._baseline].values()
        expected = checked.run.settings is None
        intro = (
            "Its run has no settings.csv, so these are its plan's resolved settings, each with the"
            " provenance the plan expects it to have once the request is sent."
            if expected
            else "As its settings.csv records them."
        )
        body = [
            f"<tr><td>{_code(setting.name)}</td><td>{_code(setting.category)}</td>"
            f"<td>{_code(setting.value)}</td><td>{self._unit(setting.unit)}</td>"
            f"<td>{_code(setting.provenance)}</td>"
            f"<td>{_flag_list(setting.flags)}</td></tr>"
            for setting in settings
        ]
        return [
            f"<h3>The baseline's settings, {self._name(self._baseline)}</h3>",
            f"<p>{intro}</p>",
            '<div class="wide"><table>',
            (
                "<thead><tr><th>Setting</th><th>Category</th><th>Value</th><th>Unit</th>"
                f"<th>{'Expected provenance' if expected else 'Provenance'}</th><th>Flags</th>"
                "</tr></thead>"
            ),
            "<tbody>",
            *body,
            "</tbody></table></div>",
        ]

    @staticmethod
    def _value(value: str | None) -> str:
        return "Missing" if value is None else _code(value)

    @staticmethod
    def _unit(unit: str | None) -> str:
        return "" if unit is None else _code(unit)

    @staticmethod
    def _flags(row: DifferencesRow) -> str:
        if not row.flags:
            return ""
        flags = _flag_list(row.flags)
        return f"<strong>Flagged.</strong> {flags}" if row.flagged else flags

    # 3. Data sources

    def _data(self) -> list[str]:
        return [
            _heading("data", _REVIEW_SECTIONS),
            "<h3>Sources</h3>",
            *self._sources(),
            "<h3>Coverage</h3>",
            *self._coverage(),
            "<h3>Provenance</h3>",
            "<p>Each setting and metric records where its value came from:</p>",
            "<ul>",
            *self._provenance(),
            "</ul>",
            "<h3>External references</h3>",
            *self._references(),
            "<h3>Missing values</h3>",
            *self._missing(),
            "<h3>Exclusions</h3>",
            (
                "<p>The review copies each run's manifest, plan, and normalized tables, byte for"
                " byte, and excludes nothing from them. Each run's screen configuration, start and"
                " attempt records, request, response, and report stay in the run, and its copied"
                " manifest records the hash of each.</p>"
            ),
            "</section>",
        ]

    def _sources(self) -> list[str]:
        rows: list[str] = []
        for checked in self._review.inputs:
            label = checked.result.label
            manifest = checked.run.manifest
            if manifest.synthetic:
                source = (
                    "Invented values, written by <code>trialfolio demo</code> in the layout of"
                    " Portfolio123's screen backtest response. Nothing was sent to Portfolio123."
                )
            else:
                source = (
                    "Portfolio123's screen backtest, through <code>p123api</code>'s"
                    " <code>screen_backtest</code>."
                )
            layouts = ", ".join(
                f"{_code(parser.layout)} version {parser.layout_version}, parser version"
                f" {parser.parser_version}"
                for parser in manifest.parsers
            )
            settings = self._settings[label]
            vendor, pit = settings.get("data_vendor"), settings.get("pit_method")
            rows.append(
                f"<tr><td>{self._name(label)}</td><td>{source}</td>"
                f"<td>{layouts or 'Unavailable: no response was read.'}</td>"
                f"<td>{_setting_brief(vendor) if vendor else 'Missing'}</td>"
                f"<td>{_setting_brief(pit) if pit else 'Missing'}</td></tr>"
            )
        return [
            '<div class="wide"><table>',
            (
                "<thead><tr><th>Result</th><th>Source</th><th>Response layout</th>"
                "<th>Data vendor</th><th>Point-in-time method</th></tr></thead>"
            ),
            "<tbody>",
            *rows,
            "</tbody></table></div>",
        ]

    def _coverage(self) -> list[str]:
        rows: list[str] = []
        for checked in self._review.inputs:
            label = checked.result.label
            if checked.run.metrics is None:
                cells = ["Unavailable"] * 3
            else:
                cells = [
                    self._coverage_cell(label, "coverage_start", "start_date"),
                    self._coverage_cell(label, "coverage_end", "end_date"),
                    self._coverage_cell(label, "coverage_periods", None),
                ]
            if label == self._baseline:
                against = "The baseline"
            elif checked.run.metrics is None:
                against = "Unavailable: its run has no normalized tables."
            elif not self._metrics[self._baseline]:
                against = "Unavailable: the baseline's run has no normalized tables."
            else:
                against = self._coverage_against(label)
            rows.append(
                f"<tr><td>{self._name(label)}</td>"
                + "".join(f"<td>{cell}</td>" for cell in cells)
                + f"<td>{against}</td></tr>"
            )
        return [
            (
                "<p>Each result's coverage is read from the dates of its response's periods. A"
                " run without normalized tables has none. The coverage rows are compared with the"
                " baseline's whatever the periods are, because they're the period: dates in days,"
                " and periods as a count. Coverage that couldn't be established is never shown as"
                " matching.</p>"
            ),
            '<div class="wide"><table>',
            (
                "<thead><tr><th>Result</th><th>Coverage start</th><th>Coverage end</th>"
                "<th>Coverage periods</th><th>Against the baseline</th></tr></thead>"
            ),
            "<tbody>",
            *rows,
            "</tbody></table></div>",
        ]

    def _coverage_cell(self, label: str, metric_id: str, requested: str | None) -> str:
        row = self._metrics[label][("strategy", metric_id)]
        if row.value is None:
            return f"Couldn't be established. {_unavailable(row.unavailable_reason)}"
        cell = _code(row.value)
        setting = self._settings[label].get(requested) if requested is not None else None
        if setting is not None and "coverage_mismatch" in setting.flags:
            cell += f": requested {_code(setting.value)}, flagged <code>coverage_mismatch</code>"
        return cell

    def _coverage_against(self, label: str) -> str:
        parts: list[str] = []
        for metric_id, name in (
            ("coverage_start", "Start"),
            ("coverage_end", "End"),
            ("coverage_periods", "Periods"),
        ):
            row = self._rows[(label, "metric", "strategy", metric_id)]
            if row.difference is None:
                parts.append(f"{name}: {self._comparison(row)}")
            else:
                unit = "" if row.difference_unit == "count" else f" {row.difference_unit}"
                parts.append(f"{name}: {_code(row.difference)}{unit}")
        return "<br>".join(parts)

    def _provenance(self) -> list[str]:
        found: set[str] = set()
        for label, settings in self._settings.items():
            found.update(setting.provenance for setting in settings.values())
            found.update(row.provenance for row in self._metrics[label].values())
        meanings = dict(_PROVENANCE)
        meanings["verified"] = (
            "Sent in the request, or captured from Portfolio123's response, by the result's run."
        )
        if len(self._synthetic) == len(self._review.inputs):
            meanings["verified"] = _SYNTHETIC_VERIFIED
        elif self._synthetic:
            meanings["verified"] += (
                f" For {self._labels(self._synthetic)}, which"
                f" {'is' if len(self._synthetic) == 1 else 'are'} synthetic, it marks where a"
                " real run's value would be: nothing was sent, and no value came from"
                " Portfolio123."
            )
        return [
            f"<li>{_code(name)}: {meaning}</li>"
            for name, meaning in meanings.items()
            if name in found
        ]

    def _references(self) -> list[str]:
        items: list[str] = []
        for checked in self._review.inputs:
            label = checked.result.label
            for reference in checked.run.manifest.reproducibility.external_references:
                setting = self._settings[label].get(reference.setting)
                value = f" {_code(setting.value)}" if setting is not None else ""
                state = (
                    "snapshotted"
                    if reference.snapshotted
                    else "not snapshotted: its definition wasn't captured"
                )
                items.append(
                    f"<li>{self._name(label)}: {_code(reference.setting)}{value}, {state}.</li>"
                )
        intro = (
            "<p>Settings that name an object in the Portfolio123 account. A change to one that"
            " wasn't snapshotted between two runs doesn't show as a change in the settings.</p>"
        )
        if not items:
            return [intro, "<p>None.</p>"]
        return [intro, "<ul>", *items, "</ul>"]

    def _missing(self) -> list[str]:
        items: list[str] = []
        unavailable = 0
        for checked in self._review.inputs:
            label = checked.result.label
            if checked.run.metrics is None:
                items.append(
                    f"<li>{self._name(label)}: every metric, because its run has no normalized"
                    " tables.</li>"
                )
                continue
            for row in checked.run.metrics:
                if row.value is None:
                    unavailable += 1
                    items.append(
                        f"<li>{self._name(label)}: {_metric_label(row)}:"
                        f" {_unavailable(row.unavailable_reason)}</li>"
                    )
        if not items:
            return ["<p>None: every metric of every result is available.</p>"]
        summary = (
            f"{unavailable} metric {'value is' if unavailable == 1 else 'values are'} unavailable,"
            " each with the reason its copied metrics.csv gives."
            if unavailable
            else "Every value in the copied metrics.csv files is available."
        )
        return [
            (
                f"<p>{summary} A result without normalized tables has no values. None is shown as"
                " zero, and a comparison with an unavailable value is unavailable too, with"
                f" {_code('input_unavailable')}.</p>"
            ),
            "<ul>",
            *items,
            "</ul>",
        ]

    # 4. Results

    def _results(self) -> list[str]:
        parts = [
            _heading("results", _REVIEW_SECTIONS),
            (
                "<p>Each result's metrics beside the baseline's, as the copied metrics.csv files"
                " hold them, never padded or rounded, and the difference where the two values are"
                " comparable. The coverage rows are in the coverage table above.</p>"
            ),
        ]
        for checked in self._others:
            parts.extend(self._compared(checked.result.label))
        parts.extend(
            [
                "<h3>Costs</h3>",
                *self._settings_across(("slippage_percent", "commission", "carry_cost")),
                "<h3>Exposures</h3>",
                "<p>Unavailable: the responses report no exposures.</p>",
                "<h3>Implementation assumptions</h3>",
                *self._settings_across(
                    ("transaction_price", "rebalance_weeks", "max_holdings", "pit_method")
                ),
                "</section>",
            ]
        )
        return parts

    def _compared(self, label: str) -> list[str]:
        parts = [f"<h3>{self._name(label)} against the baseline, {self._name(self._baseline)}</h3>"]
        sharing = self._sharing(label)
        if sharing:
            parts.append(
                "<p>Every metric row is flagged <code>identical_source</code>: its run's saved"
                f" response is byte-identical to {self._labels(sharing)}'s.</p>"
            )
        body: list[str] = []
        for metric in METRICS:
            if metric.metric_id in _COVERAGE:
                continue
            row = self._rows[(label, "metric", metric.subject, metric.metric_id)]
            name = _text(_METRICS[metric.metric_id][0])
            difference = ""
            decimals = ""
            if row.difference is not None:
                difference = f"{_code(row.difference)} {_code(row.difference_unit or '')}"
                decimals = str(row.difference_decimals)
            body.append(
                f"<tr><td>{name}<br>{_code(metric.metric_id)}</td><td>{metric.subject}</td>"
                f"<td>{self._metric_value(self._baseline, metric.subject, metric.metric_id)}</td>"
                f"<td>{self._metric_value(label, metric.subject, metric.metric_id)}</td>"
                f"<td>{_code(metric.unit)}</td><td>{difference}</td><td>{decimals}</td>"
                f"<td>{self._comparison(row)}</td></tr>"
            )
        return [
            *parts,
            '<div class="wide"><table>',
            (
                f"<thead><tr><th>Metric</th><th>Subject</th><th>{self._name(self._baseline)}"
                f"</th><th>{self._name(label)}</th><th>Unit</th><th>Difference</th>"
                "<th>Decimals</th><th>Comparison</th></tr></thead>"
            ),
            "<tbody>",
            *body,
            "</tbody></table></div>",
        ]

    def _metric_value(self, label: str, subject: str, metric_id: str) -> str:
        """A result's value of a metric, as its metrics.csv holds it, with the benchmark it
        concerns, or its own reason it's unavailable."""
        row = self._metrics[label].get((subject, metric_id))
        if row is None:
            return "Unavailable: the run has no normalized tables."
        if row.value is None:
            return _unavailable(row.unavailable_reason)
        value = _code(row.value)
        if row.benchmark is not None:
            value += f" vs. {_code(row.benchmark)}"
        elif subject == "benchmark":
            benchmark = self._settings[label].get("benchmark")
            if benchmark is not None:
                value += f" for {_code(benchmark.value)}"
        return value

    def _comparison(self, row: DifferencesRow) -> str:
        if row.classification == "differenced":
            return "Differenced"
        reason = row.reason or "input_unavailable"
        shown = "Not compared" if row.classification == "not_comparable" else "Unavailable"
        return f"{shown} ({_code(reason)}): {_DIFFERENCE_REASONS[reason]}"

    def _settings_across(self, names: Sequence[str]) -> list[str]:
        """The settings `names`, for each result."""
        rows: list[str] = []
        tokens: set[str] = set()
        for checked in self._review.inputs:
            label = checked.result.label
            cells: list[str] = []
            for name in names:
                setting = self._settings[label].get(name)
                if setting is None:
                    cells.append("Missing")
                    continue
                tokens.add(setting.value)
                cells.append(f"{_code(setting.value)} {self._unit(setting.unit)}".rstrip())
            rows.append(
                f"<tr><td>{self._name(label)}</td>"
                + "".join(f"<td>{cell}</td>" for cell in cells)
                + "</tr>"
            )
        notes = [
            f"<li>{_code(token)}: {self._token(token)}</li>" for token in _TOKENS if token in tokens
        ]
        return [
            '<div class="wide"><table>',
            "<thead><tr><th>Result</th>"
            + "".join(f"<th>{_code(name)}</th>" for name in names)
            + "</tr></thead>",
            "<tbody>",
            *rows,
            "</tbody></table></div>",
            *(["<ul>", *notes, "</ul>"] if notes else []),
        ]

    def _token(self, token: str) -> str:
        """What a setting's token means. A synthetic result's run sent nothing, so no default of
        Portfolio123's applied to it (DSC-04)."""
        meaning = _TOKENS[token]
        if token != "not_sent" or not self._synthetic:
            return meaning
        if len(self._synthetic) == len(self._review.inputs):
            return _SYNTHETIC_NOT_SENT
        one = len(self._synthetic) == 1
        return (
            "Not sent. For a backtested result, Portfolio123's default applies, and it isn't"
            f" documented. For {self._labels(self._synthetic)}, which {'is' if one else 'are'}"
            " synthetic, nothing was sent."
        )

    # 5. Results compared, and their runs

    def _cases(self) -> list[str]:
        count = len(self._review.inputs)
        parts = [
            _heading("cases", _REVIEW_SECTIONS),
            (
                f"<p>The review compares {count} results, in the configuration's order, and lists"
                " each, whatever its run's outcome. Under <code>inputs/</code>, each has a copy of"
                " its run's manifest, plan, and normalized tables, when it has them.</p>"
            ),
        ]
        for checked in self._review.inputs:
            parts.extend(self._result(checked))
        parts.extend(
            [
                "<h3>Shared responses</h3>",
                *self._shared(),
                "<h3>Versions</h3>",
                "<dl>",
                (
                    f"<dt>Review written by</dt><dd>Trial Folio {self._version}, command"
                    f" <code>review</code>, started {_moment(self._review.started_at)}</dd>"
                ),
                f"<dt>Review ID</dt><dd>{_code(str(self._review.review_id))}</dd>",
                f"<dt>Method</dt><dd>{_code(METHOD)} version {METHOD_VERSION}</dd>",
                (
                    f"<dt>License and notice</dt><dd>Recorded with the review: {_code(LICENSE_ID)},"
                    f" notice version {NOTICE_VERSION}</dd>"
                ),
                f"<dt>Report rendered by</dt><dd>Trial Folio {self._version}</dd>",
                "</dl>",
                "</section>",
            ]
        )
        return parts

    def _result(self, checked: ReviewInput) -> list[str]:
        label = checked.result.label
        run = checked.run
        manifest = run.manifest
        reviewed = checked.reviewed
        baseline = label == self._baseline
        outcome = _code(manifest.outcome)
        if manifest.error is not None:
            outcome += f" ({_code(manifest.error.code)})"
        if run.metrics is not None:
            tables = "Yes: its metrics.csv and settings.csv are copied."
        elif manifest.error is not None:
            tables = (
                f"No. Its run ended with {_code(manifest.error.code)}, and its manifest says:"
                f" {_text(manifest.error.message)}"
            )
        else:
            tables = "No: its run wrote no normalized tables."
        if reviewed.response is None:
            response = "None: the run saved no response."
        else:
            response = _code(reviewed.response)
            sharing = self._sharing(label)
            if sharing:
                response += f". Byte-identical to {self._labels(sharing)}'s."
        nature = (
            "Synthetic: invented values, neither backtested nor actual results."
            if manifest.synthetic
            else (
                "Backtested: from applying the screen's rules to historical data, not from actual"
                " trades."
            )
        )
        description = checked.result.description
        purpose = run.plan.purpose
        facts = [
            (
                "<dt>Role</dt><dd>"
                + ("The baseline" if baseline else "Compared with the baseline")
                + "</dd>"
            ),
            "<dt>Description</dt><dd>"
            + (_text(description) if description is not None else "None given.")
            + "</dd>",
            f"<dt>Run title</dt><dd>{_text(run.plan.title)}</dd>",
            "<dt>Run purpose</dt><dd>"
            + (_text(purpose) if purpose is not None else "No purpose was declared.")
            + "</dd>",
            f"<dt>Results</dt><dd>{nature}</dd>",
            f"<dt>Run outcome</dt><dd>{outcome}. An execution status, not a research finding.</dd>",
            f"<dt>Normalized tables</dt><dd>{tables}</dd>",
            f"<dt>Run manifest</dt><dd>{_code(reviewed.run_manifest)}</dd>",
            f"<dt>Plan hash</dt><dd>{_code(reviewed.plan_hash)}</dd>",
            f"<dt>Case</dt><dd>{_code(reviewed.case_id)}</dd>",
            f"<dt>Saved response</dt><dd>{response}</dd>",
            (
                f"<dt>Run written by</dt><dd>Trial Folio {_text(manifest.trialfolio_version)},"
                f" command {_code(manifest.command.name)}, started"
                f" {_moment(manifest.command.started_at)}</dd>"
            ),
        ]
        return [
            f"<h3>{self._name(label)}" + (", the baseline" if baseline else "") + "</h3>",
            "<dl>",
            *facts,
            "</dl>",
        ]

    def _shared(self) -> list[str]:
        shared = self._review.differences.shared_responses
        if not shared:
            return ["<p>None: no two results have byte-identical saved responses.</p>"]
        items = [
            f"<li>{self._labels(group.labels)}: {_code(group.response)}</li>" for group in shared
        ]
        return [
            (
                "<p>Results whose runs saved one response, byte for byte. Their metrics come from"
                " that one response, so equal values between them say nothing about whether two"
                " runs agree. Every metric row of each, apart from the baseline's, is flagged"
                " <code>identical_source</code>.</p>"
            ),
            "<ul>",
            *items,
            "</ul>",
        ]

    # 6 to 9

    def _robustness(self) -> list[str]:
        return [
            _heading("robustness", _REVIEW_SECTIONS),
            (
                f"<p>{NOT_ASSESSED}. Robustness results and the concentration of contributions need"
                " more than the runs' summary statistics, and Trial Folio doesn't assess them.</p>"
            ),
            "</section>",
        ]

    def _statistics(self) -> list[str]:
        return [
            _heading("statistics", _REVIEW_SECTIONS),
            (
                f"<p>Statistical validation: {NOT_ASSESSED}. A difference is one summary statistic"
                " minus another. No statistical method was applied, so the report states no"
                " uncertainty, significance, multiple-testing adjustment, or power. Summary"
                " statistics alone don't support intervals, a return series, or a drawdown"
                " history, so none is shown or reconstructed.</p>"
            ),
            "</section>",
        ]

    def _evidence(self) -> list[str]:
        if not self._synthetic:
            each = "each result is one backtest"
        elif len(self._synthetic) == len(self._review.inputs):
            each = "each result is one synthetic example"
        else:
            each = "each backtested result is one backtest, and each synthetic one an example,"
        return [
            _heading("evidence", _REVIEW_SECTIONS),
            (
                f"<p>Unavailable: {each} over its requested dates. None has a separate"
                " development, selection, holdout, or forward period, and the review makes no"
                " result another's holdout.</p>"
            ),
            f"<p>{self._nature()}</p>",
            "</section>",
        ]

    def _feasibility(self) -> list[str]:
        missing = ["<li>Actual trades: none.</li>"]
        commissions = {
            setting.value
            for settings in self._settings.values()
            if (setting := settings.get("commission")) is not None
        }
        if "not_modeled" in commissions:
            missing.append(f"<li>Commission: {_TOKENS['not_modeled']}</li>")
        missing.append(
            "<li>Turnover, positions, and per-period returns: a review copies no response, and"
            " compares none.</li>"
        )
        return [
            _heading("feasibility", _REVIEW_SECTIONS),
            f"<p>Trading readiness: {NOT_ASSESSED}. Feasibility and capacity aren't assessed.</p>",
            "<p>Execution evidence the results don't have:</p>",
            "<ul>",
            *missing,
            "</ul>",
            "</section>",
        ]

    # 10. Conclusion

    def _conclusion(self) -> list[str]:
        others = len(self._others)
        conclusion = (
            f"The review compared {others} {'result' if others == 1 else 'results'} with the"
            f" baseline, {self._name(self._baseline)}: it shows which settings differ, and the"
            " difference between each pair of comparable metrics. That's a statement about what"
            " differs, not about which strategy is better: the review ranks no result."
            " Statistical validation and trading readiness are not assessed, so this report"
            " permits no conclusion about whether any strategy is useful, or whether its results"
            " could be achieved."
        )
        return [
            _heading("conclusion", _REVIEW_SECTIONS),
            "<h3>Permitted conclusion</h3>",
            f"<p>{conclusion}</p>",
            "<h3>Limitations</h3>",
            "<ul>",
            *(f"<li>{item}</li>" for item in self._limitations()),
            "</ul>",
            "<h3>Artifacts</h3>",
            *self._artifacts(),
            "</section>",
        ]

    def _limitations(self) -> list[str]:
        differences = self._review.differences
        settings, metrics = differences.setting_counts, differences.metric_counts
        items = [self._nature()]
        if settings.flagged:
            items.append(
                f"{settings.flagged} setting"
                f" {'comparison is' if settings.flagged == 1 else 'comparisons are'} flagged,"
                " each listed with the changes from the baseline."
            )
        incomplete = [
            checked.result.label
            for checked in self._review.inputs
            if checked.run.manifest.reproducibility.status == "incomplete"
        ]
        if incomplete:
            items.append(
                f"Reproducibility is incomplete for {self._labels(incomplete)}: each names an"
                " object in the Portfolio123 account whose definition wasn't captured, as the"
                " external references list. If one changed between two runs, the review can't"
                " show it."
            )
        if len(self._synthetic) < len(self._review.inputs):
            items.append(
                "Portfolio123's data and engines change, so running a configuration again may"
                " give different results, and two runs of one configuration may differ for that"
                " reason alone."
            )
        if metrics.not_comparable:
            items.append(
                f"{metrics.not_comparable} metric comparisons aren't differenced, because a"
                " context differs. Each gives its reason."
            )
        if metrics.unavailable:
            items.append(
                f"{metrics.unavailable} metric comparisons are unavailable, because a value is."
            )
        without = [c.result.label for c in self._review.inputs if c.run.metrics is None]
        if without:
            one = len(without) == 1
            items.append(
                f"{self._labels(without)} {'has' if one else 'have'} no normalized tables, so"
                f" {'its' if one else 'their'} metrics are unavailable."
            )
        if differences.shared_responses:
            items.append(
                "Some results share a saved response, so their metrics come from one response."
            )
        items.append(
            "Only summary statistics are compared: no return series, drawdown history, or"
            " interval is shown."
        )
        return items

    def _artifacts(self) -> list[str]:
        rows = [
            (
                f"<tr><td>{self._link(MANIFEST_PATH)}</td><td>Review manifest, written last</td>"
                "<td></td><td></td><td></td></tr>"
            ),
            *(
                f'<tr><td class="long">{self._link(artifact.path)}</td>'
                f"<td>{_REVIEW_ROLES[artifact.role]}</td>"
                f"<td>{'' if artifact.label is None else self._name(artifact.label)}</td>"
                f'<td>{artifact.size}</td><td class="long">{_code(artifact.artifact_id)}</td></tr>'
                for artifact in self._review.artifacts
            ),
        ]
        return [
            (
                "<p>Each file links to the review's copy, by its path relative to this report. None"
                " links to a run. An <code>artifact_id</code> is the SHA-256 of the file's"
                " bytes.</p>"
            ),
            '<div class="wide"><table>',
            (
                "<thead><tr><th>File</th><th>Role</th><th>Result</th><th>Size, bytes</th>"
                "<th>artifact_id</th></tr></thead>"
            ),
            "<tbody>",
            *rows,
            "</tbody></table></div>",
        ]

    @staticmethod
    def _link(path: str) -> str:
        href = "/".join(quote(part, safe="") for part in path.split("/"))
        return f'<a href="{html.escape(href)}">{_code(path)}</a>'


# The experiment report (R03-T08's first version; R03-T10 builds the full report)


@dataclass(frozen=True)
class CaseView:
    """A planned case, as an experiment's report shows it."""

    case: ExperimentPlanCase
    outcome: Literal["succeeded", "failed", "unknown", "not_yet_run"]
    """As the manifest counts it."""
    attempts: int
    """Its attempts, of every session."""
    tables: bool
    """Whether it has its normalized tables."""


@dataclass(frozen=True)
class ExperimentEvidence:
    """What an experiment session's report shows: the current plan and its `experiment.json`,
    each planned case's outcome, and what the session's manifest will record.

    The report is written before the manifest, so `artifacts` holds each file the manifest will
    list apart from the report itself.
    """

    plan: PlanV1_1
    plan_number: int
    record: ExperimentRecord
    session: int
    synthetic: bool
    outcome: Literal["completed", "partial"]
    error: ErrorDetail | None
    cases: tuple[CaseView, ...]
    """One for each planned case, in the plan's order."""
    counts: ExperimentManifestCounts
    artifacts: tuple[ExperimentArtifact, ...]

    def __post_init__(self) -> None:
        if tuple(view.case for view in self.cases) != self.plan.cases:
            raise ValueError("each planned case has one view, in the plan's order")
        if any(artifact.role == "report" for artifact in self.artifacts):
            raise ValueError("the artifacts are the ones the report links, so not the report")


def experiment_report_path(session: int) -> str:
    """`sessions/<session>/report.html`, relative to the output root."""
    return f"sessions/{session}/{REPORT_PATH}"


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


_CASE_OUTCOMES: Final[dict[str, str]] = {
    "succeeded": "Succeeded: its response was saved and normalized",
    "failed": "Failed",
    "unknown": "Unknown: its request may have been charged, and no response was saved",
    "not_yet_run": "Not yet run",
}


class _ExperimentReport:
    def __init__(self, experiment: ExperimentEvidence, version: str) -> None:
        self._experiment = experiment
        self._version = version
        self._plan = experiment.plan

    def document(self) -> str:
        title = self._plan.title
        parts = [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f'<meta name="generator" content="Trial Folio {self._version}">',
            f"<title>{_text(title)} · Trial Folio experiment report</title>",
            f"<style>\n{_CSS}</style>",
            "</head>",
            "<body>",
            '<div class="page">',
            "<header>",
            '<p class="kind">Trial Folio experiment report'
            + (" · Synthetic experiment" if self._experiment.synthetic else "")
            + "</p>",
            f"<h1>{_text(title)}</h1>",
            _concise_notice(),
            *self._synthetic_banner(),
            *self._status(),
            *_contents(_SECTIONS),
            "</header>",
            "<main>",
            *self._objective(),
            *self._definitions(),
            *self._data(),
            *self._results(),
            *self._cases(),
            *self._not_assessed("robustness", "No robustness or concentration analysis is run."),
            *self._not_assessed(
                "statistics",
                "No statistical method is applied, so no multiplicity correction either."
                f" The experiment's plan has {len(self._plan.cases)} cases, each recorded with"
                " its outcome.",
            ),
            *self._not_assessed(
                "evidence",
                "The cases share one period. There's no separate holdout or forward period.",
            ),
            *self._not_assessed(
                "feasibility",
                "Neither feasibility nor capacity is assessed, and no execution evidence beyond"
                " the backtests is held.",
            ),
            *self._conclusion(),
            "</main>",
            *_closing(self._version, "the experiment's saved records"),
            "</div>",
            "</body>",
            "</html>",
        ]
        return "\n".join(parts) + "\n"

    def _synthetic_banner(self) -> list[str]:
        if not self._experiment.synthetic:
            return []
        return [
            (
                '<p class="synthetic"><strong>Synthetic experiment.</strong> Trial Folio wrote'
                " this experiment with the demo's client, from invented values. Every value,"
                " attempt, and count in it is invented: none comes from Portfolio123, and nothing"
                " was sent to it or charged.</p>"
            )
        ]

    def _status(self) -> list[str]:
        experiment = self._experiment
        outcome = experiment.outcome
        if experiment.error is not None:
            outcome += f" ({_code(experiment.error.code)})"
        return [
            "<dl>",
            (
                f"<dt>Session {experiment.session} outcome</dt><dd>{outcome}. An execution"
                " status, not a research finding.</dd>"
            ),
            f"<dt>Statistical validation</dt><dd>{NOT_ASSESSED}</dd>",
            f"<dt>Trading readiness</dt><dd>{NOT_ASSESSED}</dd>",
            f"<dt>Results</dt><dd>{self._nature()}</dd>",
            "</dl>",
        ]

    def _nature(self) -> str:
        if self._experiment.synthetic:
            return "Synthetic: invented values, neither backtested nor actual results."
        return (
            "Backtested: from applying each case's screen rules to historical data, not from"
            " actual trades."
        )

    def _objective(self) -> list[str]:
        plan = self._plan
        declared = plan.prior_research
        description = (
            f"<p>{_text(declared.description)}</p>" if declared.description is not None else ""
        )
        return [
            _heading("objective"),
            "<dl>",
            f"<dt>Experiment</dt><dd>{_code(plan.experiment_id)}</dd>",
            f"<dt>Purpose</dt><dd>{_text(plan.purpose)}</dd>",
            (f"<dt>Plan</dt><dd>Plan {self._experiment.plan_number}, {_code(plan.plan_hash)}</dd>"),
            "</dl>",
            "<h3>Declared prior research</h3>",
            f"<p>Status: {_code(declared.status)}, as the configuration declares it.</p>",
            description,
            (
                "<p>Trial Folio records the declaration as the user supplied it, and can't verify"
                " it.</p>"
            ),
            "</section>",
        ]

    def _definitions(self) -> list[str]:
        (baseline, *_) = self._plan.cases
        rows = [
            f"<tr><th>{_code(row.setting)}</th><td>{_code(setting_text(row.value))}</td></tr>"
            for row in baseline.settings
        ]
        return [
            _heading("definitions"),
            (
                "<p>Each case is the baseline screen with exactly one change. The baseline's"
                " resolved settings:</p>"
            ),
            '<div class="wide"><table>',
            "<tbody>",
            *rows,
            "</tbody></table></div>",
            "</section>",
        ]

    def _data(self) -> list[str]:
        return [
            _heading("data"),
            (
                "<p>Each case that succeeded has its own normalized tables,"
                " <code>metrics.csv</code> and <code>settings.csv</code>, in"
                " <code>cases/&lt;case_id&gt;/normalized/</code>, with each setting's provenance"
                " and the response's coverage. They're listed among the artifacts below. This"
                " version of the experiment report doesn't repeat them.</p>"
            ),
            "</section>",
        ]

    def _results(self) -> list[str]:
        return [
            _heading("results"),
            (
                "<p>Each case's metrics are in its <code>metrics.csv</code>. This report doesn't"
                " compare them, and orders and marks no case by any metric.</p>"
            ),
            "</section>",
        ]

    def _cases(self) -> list[str]:
        counts = self._experiment.counts
        cases = counts.cases
        rows: list[str] = []
        for view in self._experiment.cases:
            case = view.case
            change = "The baseline" if case.variant is None else _variant_change(case)
            description = "" if case.description is None else _text(case.description)
            rows.append(
                f"<tr><td>{_code(case.case_key)}</td><td>{_code(case.case_id)}</td>"
                f"<td>{change}</td><td>{description}</td>"
                f"<td>{_CASE_OUTCOMES[view.outcome]}</td><td>{view.attempts}</td></tr>"
            )
        budget = counts.budget
        return [
            _heading("cases"),
            (
                f"<p>Planned cases: {cases.planned} = {cases.succeeded} succeeded +"
                f" {cases.failed} failed + {cases.skipped} skipped + {cases.unknown} unknown +"
                f" {cases.not_yet_run} not yet run. Every case appears below, in the plan's"
                " order.</p>"
            ),
            '<div class="wide"><table>',
            (
                "<thead><tr><th>Case</th><th>case_id</th><th>Change</th><th>Description</th>"
                "<th>Outcome</th><th>Attempts</th></tr></thead>"
            ),
            "<tbody>",
            *rows,
            "</tbody></table></div>",
            (
                f"<p>Attempts: {counts.attempts.succeeded} succeeded, {counts.attempts.failed}"
                f" failed, {counts.attempts.unknown} unknown. Provider requests counted against"
                f" the budget: {counts.provider_requests} of {budget.provider_requests}."
                f" Authentication calls: {counts.authentication_calls} of"
                f" {budget.authentication_calls}.</p>"
            ),
            "</section>",
        ]

    def _not_assessed(self, key: str, why: str) -> list[str]:
        return [_heading(key), f"<p>{NOT_ASSESSED}. {why}</p>", "</section>"]

    def _conclusion(self) -> list[str]:
        experiment = self._experiment
        if experiment.outcome == "completed":
            execution = "Every planned case succeeded."
        else:
            execution = "Not every planned case succeeded; each one's outcome is listed above."
        rows = [
            (
                f"<tr><td>{self._link('sessions/' + str(experiment.session) + '/manifest.json')}"
                "</td><td>manifest</td><td></td><td></td></tr>"
            ),
            *(
                f'<tr><td class="long">{self._link(artifact.path)}</td>'
                f"<td>{_code(artifact.role)}</td><td>{artifact.size}</td>"
                f'<td class="long">{_code(artifact.artifact_id)}</td></tr>'
                for artifact in experiment.artifacts
            ),
        ]
        return [
            _heading("conclusion"),
            "<h3>Permitted conclusion</h3>",
            (
                f"<p>{execution} That's a statement about execution, not about any strategy. No"
                " case is ranked or called best. Statistical validation and trading readiness are"
                " not assessed, so this report permits no conclusion about whether a strategy is"
                " useful.</p>"
            ),
            "<h3>Artifacts</h3>",
            (
                "<p>Each file links to the experiment's copy, by a path relative to this report."
                " An <code>artifact_id</code> is the SHA-256 of the file's bytes.</p>"
            ),
            '<div class="wide"><table>',
            (
                "<thead><tr><th>File</th><th>Role</th><th>Size, bytes</th><th>artifact_id</th>"
                "</tr></thead>"
            ),
            "<tbody>",
            *rows,
            "</tbody></table></div>",
            "</section>",
        ]

    @staticmethod
    def _link(path: str) -> str:
        # The report is in sessions/<s>/, two levels below the output root.
        segments = ("..", "..", *(quote(part, safe="") for part in path.split("/")))
        return f'<a href="{html.escape("/".join(segments))}">{_code(path)}</a>'


def _variant_change(case: ExperimentPlanCase) -> str:
    variant = case.variant
    if variant is None:
        return "The baseline"
    if variant.value is not None:
        default = ", the default rebalance variant" if variant.default else ""
        return f"{_code(variant.setting)} set to {_code(str(variant.value))}{default}"
    if variant.add is not None:
        return f"Adds the rule {_code(variant.add)}"
    return f"Replaces the rule {_code(variant.replace or '')} with {_code(variant.with_ or '')}"
