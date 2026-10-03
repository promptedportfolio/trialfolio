"""The report: one self-contained, script-free HTML file showing a run's evidence, with the
notices (docs/contracts.md, reports; docs/disclaimers.md, DSC-02, DSC-03, and DSC-06; REQ-08 and
REQ-13).

`ReportRenderer` is the protocol, and `HtmlReportRenderer` its implementation. Rendering reads
only the `SavedRun` it's given, so it needs no provider or network access.

- `write_report` writes `report.html` into the output directory of the run being written. `run`
  and `demo` do that just before the manifest.
- `rerender_report` is the core of `trialfolio report`: it reads and checks a saved run, renders
  its report, and claims a new output directory with it.

What a report holds:

- **Nothing that runs or loads.** Inline CSS only: no script, event-handler attribute, or
  external resource. Its only links are in-page fragments, relative paths to the run's artifacts,
  and the two outside links D-21 allows: the LICENSE of the version that rendered it, and
  Portfolio123's terms.
- **The notices.** The concise notice near the top, before any result, linking to the full
  notice. The Portfolio123 data statement in the closing section, and after it the full notice in
  a `<details>` element, with the license's name and identifier, the notice version, and the
  LICENSE link.
- **The ten sections docs/contracts.md lists,** in order. A section the run's evidence can't
  support says it's unavailable, or not assessed, and why. Nothing is filled in.
- **Values exactly as the normalized tables hold them,** with their units, never padded or
  rounded. An unavailable metric shows its reason.
- **Text Trial Folio didn't write,** such as the title, the formulas, or a provider message,
  HTML-escaped, with its control and formatting characters written as escapes such as `\\u202e`,
  so it can't add markup or reorder what's shown.
- **No account information:** `quotaRemaining` stays in the attempt record.
- **Neutral status.** No status is styled as a pass; execution success is kept apart from any
  statement about the strategy.

Rendering is deterministic: the same run and version give the same bytes. Nothing here logs the
report's contents.
"""

import html
import logging
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol
from urllib.parse import quote

from trialfolio.contracts.attempt import SavedResponse
from trialfolio.contracts.common import UnavailableReason
from trialfolio.contracts.manifest import ArtifactRole, ManifestArtifact
from trialfolio.contracts.tables import MetricsRow
from trialfolio.display import visible
from trialfolio.normalization import LAYOUT, setting_text
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
from trialfolio.runs import MANIFEST_PATH, SavedAttempt, SavedRun, read_run
from trialfolio.storage import ArtifactStore, StoredFile

_logger = logging.getLogger(__name__)

REPORT_PATH: Final = "report.html"

FULL_NOTICE_ID: Final = "full-notice"
"""The `id` of the `<details>` element that holds the full notice."""

NOT_ASSESSED: Final = "Not assessed"

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


class _Report:
    def __init__(self, run: SavedRun, base: tuple[str, ...] | None, version: str) -> None:
        self._run = run
        self._base = base
        self._version = version
        self._case = run.plan.cases[0]
        if run.settings is not None:
            self._settings = tuple(
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
        else:
            self._settings = tuple(
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
                for row in self._case.settings
            )
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
            self._concise_notice(),
            *self._synthetic_banner(),
            *self._status(),
            *self._contents(),
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
            *self._closing(),
            "</div>",
            "</body>",
            "</html>",
        ]
        return "\n".join(parts) + "\n"

    # The top of the report

    def _concise_notice(self) -> str:
        lead = CONCISE_NOTICE.removesuffix(f"{CONCISE_NOTICE_LINK}.")
        link = f'<a href="#{FULL_NOTICE_ID}">{html.escape(CONCISE_NOTICE_LINK)}</a>'
        return f'<p class="notice" id="notice">{html.escape(lead)}{link}.</p>'

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

    def _contents(self) -> list[str]:
        items = [f'<li><a href="#{key}">{heading}</a></li>' for key, heading in _SECTIONS]
        return [
            '<nav aria-label="Contents">',
            "<ol>",
            *items,
            '<li><a href="#closing">Portfolio123 data, notices, and license</a></li>',
            "</ol>",
            "</nav>",
        ]

    @staticmethod
    def _heading(key: str) -> str:
        number = next(i for i, (k, _) in enumerate(_SECTIONS, 1) if k == key)
        return f'<section id="{key}">\n<h2>{number}. {dict(_SECTIONS)[key]}</h2>'

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
            self._heading("objective"),
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
            self._heading("definitions"),
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
            self._heading("data"),
            "<dl>",
            f"<dt>Source</dt><dd>{source}</dd>",
            f"<dt>Response layout</dt><dd>{parsers or 'Unavailable: no response was read.'}</dd>",
            "<dt>Data vendor</dt><dd>"
            + (self._setting_brief(vendor) if vendor else "Unavailable")
            + "</dd>",
            "<dt>Point-in-time method</dt><dd>"
            + (self._setting_brief(pit) if pit else "Unavailable")
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
            return (
                "None. Trial Folio excludes nothing from the response, and keeps it whole as it"
                " was saved. Its per-period series is preserved there, but not interpreted."
            )
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

    def _setting_brief(self, setting: _Setting) -> str:
        expected = "expected to be " if setting.expected else ""
        brief = f"{_code(setting.value)} ({expected}{setting.provenance})"
        if setting.inference_rule is not None:
            brief += f". {_text(setting.inference_rule)}"
        return brief

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
                actual = self._unavailable(reason)
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
                else self._unavailable(periods.unavailable_reason)
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
            f"<li>{self._metric_label(row)}: {self._unavailable(row.unavailable_reason)}</li>"
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

    def _unavailable(self, reason: UnavailableReason | None) -> str:
        if reason is None:
            return "Unavailable"
        return f"Unavailable ({_code(reason)}): {_REASONS[reason]}"

    def _metric_label(self, row: MetricsRow) -> str:
        name = _METRICS.get(row.metric_id, (row.metric_id, ""))[0]
        return f"{_text(name)}, {row.subject} ({_code(row.metric_id)})"

    # 4. Results

    def _results(self) -> list[str]:
        parts = [self._heading("results")]
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
                value = self._unavailable(row.unavailable_reason)
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
            self._heading("cases"),
            (
                "<p>A run has one case: the resolved settings, identified by their case ID. Every"
                " attempt of it is listed, whatever its outcome.</p>"
            ),
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
            self._heading("robustness"),
            (
                f"<p>{NOT_ASSESSED}. Robustness results and the concentration of contributions need"
                " more than one run's summary statistics, and Trial Folio doesn't assess them.</p>"
            ),
            "</section>",
        ]

    def _statistics(self) -> list[str]:
        return [
            self._heading("statistics"),
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
            self._heading("evidence"),
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
            self._heading("feasibility"),
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
            self._heading("conclusion"),
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

    # The closing section

    def _closing(self) -> list[str]:
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
                f' {NOTICE_VERSION}. Read <a href="{license_url(self._version)}">the LICENSE'
                f" published with Trial Folio {self._version}</a>.</p>"
            ),
            "</details>",
            (
                f'<p class="muted">Rendered by Trial Folio {self._version} from the run\'s saved'
                " records.</p>"
            ),
            "</footer>",
        ]
