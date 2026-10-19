"""The review report: each result compared with the baseline, from a `ReviewEvidence` (release
0.2.0, R02-T07).

`render_review` renders it from a `ReviewContext`, section by section, each section a function of
the context. The comparison of settings is in `trialfolio.report.review_settings`. The report
compares; it ranks no result, and never links a run.
"""

from typing import Final

from trialfolio.differences import METHOD, AnyDifferencesRow
from trialfolio.normalization import LAYOUT, METRICS
from trialfolio.notices import LICENSE_ID, NOTICE_VERSION
from trialfolio.report.evidence import ReviewContext
from trialfolio.report.fragments import (
    ASSUMPTIONS,
    COSTS,
    COVERAGE,
    NOT_ASSESSED,
    NOT_ASSESSED_FACTS,
    Listed,
    artifacts,
    metric_definitions,
    metric_label,
    parsers_line,
    provenance,
    rendered_by,
    run_written_by,
    setting_brief,
    status,
    synthetic_writer,
    unavailable,
)
from trialfolio.report.page import code, facts, moment, page, table, text
from trialfolio.report.review_settings import benchmarks, changes, settings_across
from trialfolio.report.vocabulary import (
    DIFFERENCE_REASONS,
    LAYOUT_METRICS,
    METRIC_CLASSES,
    METRIC_DEFINITIONS,
    PROVENANCE,
    REVIEW_ROLES,
    SETTING_CLASSES,
    SYNTHETIC_VERIFIED,
    TOKENS,
)
from trialfolio.review_inputs import ReviewInput
from trialfolio.runs import MANIFEST_PATH

_SECTIONS: Final = (
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

_WEIGHT_ROWS: Final = (
    (
        "<p>A weight row compares one node's weight, named beside <code>ranking_weight</code> by"
        " its canonical path: the baseline's nodes, in its definition's order, then the"
        " result's other nodes, in its. A node is the same node in both runs when its canonical"
        " path is the same. A run that doesn't have the node gives <code>absent</code> when its"
        " record shows its ranking in full, as a definition or a formula, and leaves the weight"
        " unknown when it names a ranking system by name or ID, whose definition wasn't"
        " captured. A result that declares <code>ranking</code> declares each weight that"
        " differs, with its reason. A weight that's the same isn't flagged as a declared change"
        " that wasn't observed: the declaration is of the ranking, which its own row"
        " shows.</p>"
    ),
    (
        "<p>A removal shifts the positions of the nodes after the factor it removes, so a node"
        " without a name, or with a sibling's name, may have another canonical path in the"
        " other run, and be compared with another node, or with <code>absent</code>.</p>"
    ),
)
"""How a review compares weight rows, in section 2 of a review with any (R04-T11)."""


def render_review(review: ReviewContext) -> str:
    """The review's report, as an HTML document."""
    return page(
        version=review.version,
        title=review.evidence.configuration.title,
        kind="review report",
        label=_label(review),
        top=[*_synthetic_banner(review), *_status(review)],
        headings=_SECTIONS,
        sections={
            "objective": _objective(review),
            "definitions": _definitions(review),
            "data": _data(review),
            "results": _results(review),
            "cases": _cases(review),
            "robustness": _robustness(),
            "statistics": _statistics(),
            "evidence": _evidence(review),
            "feasibility": _feasibility(review),
            "conclusion": _conclusion(review),
        },
        records="the review's records",
    )


# The top of the report


def _label(review: ReviewContext) -> str:
    if not review.synthetic:
        return ""
    return " · Synthetic results" if review.all_synthetic else " · Includes synthetic results"


def _synthetic_banner(review: ReviewContext) -> list[str]:
    if not review.synthetic:
        return []
    one = len(review.synthetic) == 1
    writers = {
        synthetic_writer(checked.run.manifest)
        for checked in review.evidence.inputs
        if checked.run.manifest.synthetic
    }
    # Runs trialfolio demo wrote, those Trial Folio's core wrote with the demo's client, or both.
    writer = (
        writers.pop()
        if len(writers) == 1
        else "<code>trialfolio demo</code>, or Trial Folio's core with the demo's client,"
    )
    return [
        (
            '<p class="synthetic"><strong>Synthetic results.</strong>'
            f" {review.labels(review.synthetic)} {'is' if one else 'are'} synthetic: written by"
            f" {writer} from invented values. None of"
            f" {'its' if one else 'their'} values comes from Portfolio123, and nothing was"
            f" sent to it. {'It is' if one else 'Each is'} marked synthetic wherever its"
            " values appear.</p>"
        )
    ]


def _status(review: ReviewContext) -> list[str]:
    outcome = "completed: each result was compared with the baseline"
    return status("Review outcome", outcome, _nature(review))


def _nature(review: ReviewContext) -> str:
    """What kind of results the review compares (DSC-04)."""
    synthetic = "invented values, neither backtested nor actual results"
    backtested = "from applying each screen's rules to historical data, not from actual trades"
    if not review.synthetic:
        return f"Backtested: {backtested}."
    if review.all_synthetic:
        return f"Synthetic: {synthetic}."
    return (
        f"Backtested, {backtested}, apart from {review.labels(review.synthetic)}: synthetic,"
        f" {synthetic}."
    )


# 1. Objective


def _objective(review: ReviewContext) -> list[str]:
    configuration = review.evidence.configuration
    purpose = (
        f"<p>{text(configuration.purpose)}</p>"
        if configuration.purpose is not None
        else '<p class="muted">No purpose was declared.</p>'
    )
    objective = (
        "Unavailable: a review declares no research objective, only a title and an optional"
        " purpose."
    )
    return [
        *facts(
            [
                ("Objective", objective),
                ("Title", text(configuration.title)),
                ("Baseline", review.name(review.baseline)),
                *NOT_ASSESSED_FACTS,
            ]
        ),
        "<h3>Declared purpose</h3>",
        purpose,
        "<h3>Benchmarks</h3>",
        *benchmarks(review),
    ]


# 2. Definitions


def _definitions(review: ReviewContext) -> list[str]:
    differences = review.evidence.differences
    weights = (
        ", with a weight row after <code>ranking</code> for each node of either run's ranking"
        " definition"
        if differences.weighted
        else ""
    )
    return [
        (
            f"<p>Each result is compared with the baseline, {review.name(review.baseline)}, by"
            f" the rules of {code(METHOD)} version {differences.method_version}: its 23"
            f" settings{weights}, and then its 20 metrics."
            " <code>normalized/differences.csv</code> holds a row for each.</p>"
        ),
        "<h3>How settings are compared</h3>",
        "<ul>",
        *(f"<li>{code(name)}: {meaning}</li>" for name, meaning in SETTING_CLASSES),
        "</ul>",
        (
            "<p>A list or a ranking reads as JSON, and anything else as its text. The critical"
            " settings are the dates, the benchmark, the currency, the costs, the execution,"
            " the universe, the data source, and the strategy: an unexplained mismatch or an"
            " unknown value in one is flagged. An intended change to one is shown, but not as"
            " a defect.</p>"
        ),
        *(_WEIGHT_ROWS if differences.weighted else ()),
        "<h3>How metrics are compared</h3>",
        "<ul>",
        *(f"<li>{code(name)}: {meaning}</li>" for name, meaning in METRIC_CLASSES),
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
        *(f"<li>{code(reason)}: {meaning}</li>" for reason, meaning in DIFFERENCE_REASONS.items()),
        "</ul>",
        "<h3>Metric definitions</h3>",
        *metric_definitions(_metric_source(review), LAYOUT_METRICS if review.synthetic else {}),
        *changes(review),
    ]


def _metric_source(review: ReviewContext) -> str:
    layout = f"laid out as {code(LAYOUT)} version 1"
    if not review.synthetic:
        return f"The metrics are read from each run's response from Portfolio123, {layout}."
    if review.all_synthetic:
        return (
            f"The metrics are read from each run's invented response, {layout}: none comes"
            " from Portfolio123. Each is defined as that layout defines it."
        )
    return (
        f"The metrics are read from each run's response, {layout}: Portfolio123's for a"
        f" backtested result, and an invented one for {review.labels(review.synthetic)}, whose"
        " values don't come from Portfolio123. Each is defined as that layout defines it."
    )


# 3. Data sources


def _data(review: ReviewContext) -> list[str]:
    return [
        "<h3>Sources</h3>",
        *_sources(review),
        "<h3>Coverage</h3>",
        *_coverage(review),
        *_provenance(review),
        "<h3>External references</h3>",
        *_references(review),
        "<h3>Missing values</h3>",
        *_missing(review),
        "<h3>Exclusions</h3>",
        (
            "<p>The review copies each run's manifest, plan, and normalized tables, byte for"
            " byte, and excludes nothing from them. Each run's screen configuration, start and"
            " attempt records, request, response, and report stay in the run, and its copied"
            " manifest records the hash of each.</p>"
        ),
    ]


def _sources(review: ReviewContext) -> list[str]:
    rows: list[str] = []
    for checked in review.evidence.inputs:
        label = checked.result.label
        manifest = checked.run.manifest
        if manifest.synthetic:
            source = (
                f"Invented values, written by {synthetic_writer(manifest)} in the layout of"
                " Portfolio123's screen backtest response. Nothing was sent to Portfolio123."
            )
        else:
            source = (
                "Portfolio123's screen backtest, through <code>p123api</code>'s"
                " <code>screen_backtest</code>."
            )
        layouts = parsers_line(manifest.parsers)
        settings = review.settings[label]
        vendor, pit = settings.get("data_vendor"), settings.get("pit_method")
        rows.append(
            f"<tr><td>{review.name(label)}</td><td>{source}</td>"
            f"<td>{layouts or 'Unavailable: no response was read.'}</td>"
            f"<td>{setting_brief(vendor) if vendor else 'Missing'}</td>"
            f"<td>{setting_brief(pit) if pit else 'Missing'}</td></tr>"
        )
    heads = ("Result", "Source", "Response layout", "Data vendor", "Point-in-time method")
    return table(heads, rows)


def _coverage(review: ReviewContext) -> list[str]:
    rows: list[str] = []
    for checked in review.evidence.inputs:
        label = checked.result.label
        if checked.run.metrics is None:
            cells = ["Unavailable"] * 3
        else:
            cells = [
                _coverage_cell(review, label, "coverage_start", "start_date"),
                _coverage_cell(review, label, "coverage_end", "end_date"),
                _coverage_cell(review, label, "coverage_periods", None),
            ]
        if label == review.baseline:
            against = "The baseline"
        elif checked.run.metrics is None:
            against = "Unavailable: its run has no normalized tables."
        elif not review.metrics[review.baseline]:
            against = "Unavailable: the baseline's run has no normalized tables."
        else:
            against = _coverage_against(review, label)
        rows.append(
            f"<tr><td>{review.name(label)}</td>"
            + "".join(f"<td>{cell}</td>" for cell in cells)
            + f"<td>{against}</td></tr>"
        )
    heads = ("Result", "Coverage start", "Coverage end", "Coverage periods", "Against the baseline")
    return [
        (
            "<p>Each result's coverage is read from the dates of its response's periods. A"
            " run without normalized tables has none. The coverage rows are compared with the"
            " baseline's whatever the periods are, because they're the period: dates in days,"
            " and periods as a count. Coverage that couldn't be established is never shown as"
            " matching.</p>"
        ),
        *table(heads, rows),
    ]


def _coverage_cell(review: ReviewContext, label: str, metric_id: str, requested: str | None) -> str:
    row = review.metrics[label][("strategy", metric_id)]
    if row.value is None:
        return f"Couldn't be established. {unavailable(row.unavailable_reason)}"
    cell = code(row.value)
    setting = review.settings[label].get(requested) if requested is not None else None
    if setting is not None and "coverage_mismatch" in setting.flags:
        cell += f": requested {code(setting.value)}, flagged <code>coverage_mismatch</code>"
    return cell


def _coverage_against(review: ReviewContext, label: str) -> str:
    parts: list[str] = []
    for metric_id, name in (
        ("coverage_start", "Start"),
        ("coverage_end", "End"),
        ("coverage_periods", "Periods"),
    ):
        row = review.rows[(label, "metric", "strategy", metric_id)]
        if row.difference is None:
            parts.append(f"{name}: {_comparison(row)}")
        else:
            unit = "" if row.difference_unit == "count" else f" {row.difference_unit}"
            parts.append(f"{name}: {code(row.difference)}{unit}")
    return "<br>".join(parts)


def _provenance(review: ReviewContext) -> list[str]:
    found: set[str] = set()
    for label, settings in review.settings.items():
        found.update(setting.provenance for setting in settings.values())
        found.update(row.provenance for row in review.metrics[label].values())
    meanings = dict(PROVENANCE)
    meanings["verified"] = (
        "Sent in the request, or captured from Portfolio123's response, by the result's run."
    )
    if review.all_synthetic:
        meanings["verified"] = SYNTHETIC_VERIFIED
    elif review.synthetic:
        meanings["verified"] += (
            f" For {review.labels(review.synthetic)}, which"
            f" {'is' if len(review.synthetic) == 1 else 'are'} synthetic, it marks where a"
            " real run's value would be: nothing was sent, and no value came from"
            " Portfolio123."
        )
    return provenance(meanings, found)


def _references(review: ReviewContext) -> list[str]:
    items: list[str] = []
    for checked in review.evidence.inputs:
        label = checked.result.label
        for reference in checked.run.manifest.reproducibility.external_references:
            setting = review.settings[label].get(reference.setting)
            value = f" {code(setting.value)}" if setting is not None else ""
            state = (
                "snapshotted"
                if reference.snapshotted
                else "not snapshotted: its definition wasn't captured"
            )
            items.append(
                f"<li>{review.name(label)}: {code(reference.setting)}{value}, {state}.</li>"
            )
    intro = (
        "<p>Settings that name an object in the Portfolio123 account. A change to one that"
        " wasn't snapshotted between two runs doesn't show as a change in the settings.</p>"
    )
    if not items:
        return [intro, "<p>None.</p>"]
    return [intro, "<ul>", *items, "</ul>"]


def _missing(review: ReviewContext) -> list[str]:
    items: list[str] = []
    count = 0
    for checked in review.evidence.inputs:
        label = checked.result.label
        if checked.run.metrics is None:
            items.append(
                f"<li>{review.name(label)}: every metric, because its run has no normalized"
                " tables.</li>"
            )
            continue
        for row in checked.run.metrics:
            if row.value is None:
                count += 1
                items.append(
                    f"<li>{review.name(label)}: {metric_label(row)}:"
                    f" {unavailable(row.unavailable_reason)}</li>"
                )
    if not items:
        return ["<p>None: every metric of every result is available.</p>"]
    summary = (
        f"{count} metric {'value is' if count == 1 else 'values are'} unavailable,"
        " each with the reason its copied metrics.csv gives."
        if count
        else "Every value in the copied metrics.csv files is available."
    )
    return [
        (
            f"<p>{summary} A result without normalized tables has no values. None is shown as"
            " zero, and a comparison with an unavailable value is unavailable too, with"
            f" {code('input_unavailable')}.</p>"
        ),
        "<ul>",
        *items,
        "</ul>",
    ]


# 4. Results


def _results(review: ReviewContext) -> list[str]:
    return [
        (
            "<p>Each result's metrics beside the baseline's, as the copied metrics.csv files"
            " hold them, never padded or rounded, and the difference where the two values are"
            " comparable. The coverage rows are in the coverage table above.</p>"
        ),
        *(line for checked in review.others for line in _compared(review, checked)),
        "<h3>Costs</h3>",
        *settings_across(review, COSTS),
        "<h3>Exposures</h3>",
        "<p>Unavailable: the responses report no exposures.</p>",
        "<h3>Implementation assumptions</h3>",
        *settings_across(review, ASSUMPTIONS),
    ]


def _compared(review: ReviewContext, checked: ReviewInput) -> list[str]:
    label = checked.result.label
    baseline = review.name(review.baseline)
    parts = [f"<h3>{review.name(label)} against the baseline, {baseline}</h3>"]
    sharing = review.sharing(label)
    if sharing:
        parts.append(
            "<p>Every metric row is flagged <code>identical_source</code>: its run's saved"
            f" response is byte-identical to {review.labels(sharing)}'s.</p>"
        )
    body: list[str] = []
    for metric in METRICS:
        if metric.metric_id in COVERAGE:
            continue
        row = review.rows[(label, "metric", metric.subject, metric.metric_id)]
        name = text(METRIC_DEFINITIONS[metric.metric_id][0])
        difference = ""
        decimals = ""
        if row.difference is not None:
            difference = f"{code(row.difference)} {code(row.difference_unit or '')}"
            decimals = str(row.difference_decimals)
        body.append(
            f"<tr><td>{name}<br>{code(metric.metric_id)}</td><td>{metric.subject}</td>"
            f"<td>{_metric_value(review, review.baseline, metric.subject, metric.metric_id)}</td>"
            f"<td>{_metric_value(review, label, metric.subject, metric.metric_id)}</td>"
            f"<td>{code(metric.unit)}</td><td>{difference}</td><td>{decimals}</td>"
            f"<td>{_comparison(row)}</td></tr>"
        )
    heads = (
        "Metric",
        "Subject",
        baseline,
        review.name(label),
        "Unit",
        "Difference",
        "Decimals",
        "Comparison",
    )
    return [*parts, *table(heads, body)]


def _metric_value(review: ReviewContext, label: str, subject: str, metric_id: str) -> str:
    """A result's value of a metric, as its metrics.csv holds it, with the benchmark it
    concerns, or its own reason it's unavailable."""
    row = review.metrics[label].get((subject, metric_id))
    if row is None:
        return "Unavailable: the run has no normalized tables."
    if row.value is None:
        return unavailable(row.unavailable_reason)
    value = code(row.value)
    if row.benchmark is not None:
        value += f" vs. {code(row.benchmark)}"
    elif subject == "benchmark":
        benchmark = review.settings[label].get("benchmark")
        if benchmark is not None:
            value += f" for {code(benchmark.value)}"
    return value


def _comparison(row: AnyDifferencesRow) -> str:
    if row.classification == "differenced":
        return "Differenced"
    reason = row.reason or "input_unavailable"
    shown = "Not compared" if row.classification == "not_comparable" else "Unavailable"
    return f"{shown} ({code(reason)}): {DIFFERENCE_REASONS[reason]}"


# 5. Results compared, and their runs


def _cases(review: ReviewContext) -> list[str]:
    evidence = review.evidence
    count = len(evidence.inputs)
    versions = [
        (
            "Review written by",
            (
                f"Trial Folio {review.version}, command <code>review</code>, started"
                f" {moment(evidence.started_at)}"
            ),
        ),
        ("Review ID", code(str(evidence.review_id))),
        ("Method", f"{code(METHOD)} version {evidence.differences.method_version}"),
        (
            "License and notice",
            f"Recorded with the review: {code(LICENSE_ID)}, notice version {NOTICE_VERSION}",
        ),
        rendered_by(review.version),
    ]
    return [
        (
            f"<p>The review compares {count} results, in the configuration's order, and lists"
            " each, whatever its run's outcome. Under <code>inputs/</code>, each has a copy of"
            " its run's manifest, plan, and normalized tables, when it has them.</p>"
        ),
        *(line for checked in evidence.inputs for line in _result(review, checked)),
        "<h3>Shared responses</h3>",
        *_shared(review),
        "<h3>Versions</h3>",
        *facts(versions),
    ]


def _result(review: ReviewContext, checked: ReviewInput) -> list[str]:
    label = checked.result.label
    run = checked.run
    manifest = run.manifest
    reviewed = checked.reviewed
    baseline = label == review.baseline
    outcome = code(manifest.outcome)
    if manifest.error is not None:
        outcome += f" ({code(manifest.error.code)})"
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
    entries = [
        ("Role", "The baseline" if baseline else "Compared with the baseline"),
        ("Description", text(description) if description is not None else "None given."),
        ("Run title", text(run.plan.title)),
        ("Run purpose", text(purpose) if purpose is not None else "No purpose was declared."),
        ("Results", nature),
        ("Run outcome", f"{outcome}. An execution status, not a research finding."),
        ("Normalized tables", _normalized_tables(checked)),
        ("Run manifest", code(reviewed.run_manifest)),
        ("Plan hash", code(reviewed.plan_hash)),
        ("Case", code(reviewed.case_id)),
        ("Saved response", _saved_response(review, checked)),
        run_written_by(manifest),
    ]
    return [
        f"<h3>{review.name(label)}" + (", the baseline" if baseline else "") + "</h3>",
        *facts(entries),
    ]


def _normalized_tables(checked: ReviewInput) -> str:
    """Whether a result's run has normalized tables, which the review copies, and why not."""
    error = checked.run.manifest.error
    if checked.run.metrics is not None:
        return "Yes: its metrics.csv and settings.csv are copied."
    if error is not None:
        return (
            f"No. Its run ended with {code(error.code)}, and its manifest says:"
            f" {text(error.message)}"
        )
    return "No: its run wrote no normalized tables."


def _saved_response(review: ReviewContext, checked: ReviewInput) -> str:
    """The `artifact_id` of a result's saved response, and the results that share it."""
    if checked.reviewed.response is None:
        return "None: the run saved no response."
    response = code(checked.reviewed.response)
    sharing = review.sharing(checked.result.label)
    if sharing:
        response += f". Byte-identical to {review.labels(sharing)}'s."
    return response


def _shared(review: ReviewContext) -> list[str]:
    shared = review.evidence.differences.shared_responses
    if not shared:
        return ["<p>None: no two results have byte-identical saved responses.</p>"]
    items = [f"<li>{review.labels(group.labels)}: {code(group.response)}</li>" for group in shared]
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


def _robustness() -> list[str]:
    return [
        (
            f"<p>{NOT_ASSESSED}. Robustness results and the concentration of contributions need"
            " more than the runs' summary statistics, and Trial Folio doesn't assess them.</p>"
        ),
    ]


def _statistics() -> list[str]:
    return [
        (
            f"<p>Statistical validation: {NOT_ASSESSED}. A difference is one summary statistic"
            " minus another. No statistical method was applied, so the report states no"
            " uncertainty, significance, multiple-testing adjustment, or power. Summary"
            " statistics alone don't support intervals, a return series, or a drawdown"
            " history, so none is shown or reconstructed.</p>"
        ),
    ]


def _evidence(review: ReviewContext) -> list[str]:
    if not review.synthetic:
        each = "each result is one backtest"
    elif review.all_synthetic:
        each = "each result is one synthetic example"
    else:
        each = "each backtested result is one backtest, and each synthetic one an example,"
    return [
        (
            f"<p>Unavailable: {each} over its requested dates. None has a separate"
            " development, selection, holdout, or forward period, and the review makes no"
            " result another's holdout.</p>"
        ),
        f"<p>{_nature(review)}</p>",
    ]


def _feasibility(review: ReviewContext) -> list[str]:
    missing = ["<li>Actual trades: none.</li>"]
    commissions = {
        setting.value
        for settings in review.settings.values()
        if (setting := settings.get("commission")) is not None
    }
    if "not_modeled" in commissions:
        missing.append(f"<li>Commission: {TOKENS['not_modeled']}</li>")
    missing.append(
        "<li>Turnover, positions, and per-period returns: a review copies no response, and"
        " compares none.</li>"
    )
    return [
        f"<p>Trading readiness: {NOT_ASSESSED}. Feasibility and capacity aren't assessed.</p>",
        "<p>Execution evidence the results don't have:</p>",
        "<ul>",
        *missing,
        "</ul>",
    ]


# 10. Conclusion


def _conclusion(review: ReviewContext) -> list[str]:
    others = len(review.others)
    conclusion = (
        f"The review compared {others} {'result' if others == 1 else 'results'} with the"
        f" baseline, {review.name(review.baseline)}: it shows which settings differ, and the"
        " difference between each pair of comparable metrics. That's a statement about what"
        " differs, not about which strategy is better: the review ranks no result."
        " Statistical validation and trading readiness are not assessed, so this report"
        " permits no conclusion about whether any strategy is useful, or whether its results"
        " could be achieved."
    )
    return [
        "<h3>Permitted conclusion</h3>",
        f"<p>{conclusion}</p>",
        "<h3>Limitations</h3>",
        "<ul>",
        *(f"<li>{item}</li>" for item in _limitations(review)),
        "</ul>",
        "<h3>Artifacts</h3>",
        *_artifacts(review),
    ]


def _limitations(review: ReviewContext) -> list[str]:
    evidence = review.evidence
    settings = evidence.differences.setting_counts
    items = [_nature(review)]
    if settings.flagged:
        items.append(
            f"{settings.flagged} setting"
            f" {'comparison is' if settings.flagged == 1 else 'comparisons are'} flagged,"
            " each listed with the changes from the baseline."
        )
    incomplete = [
        checked.result.label
        for checked in evidence.inputs
        if checked.run.manifest.reproducibility.status == "incomplete"
    ]
    if incomplete:
        items.append(
            f"Reproducibility is incomplete for {review.labels(incomplete)}: each names an"
            " object in the Portfolio123 account whose definition wasn't captured, as the"
            " external references list. If one changed between two runs, the review can't"
            " show it."
        )
    if not review.all_synthetic:
        items.append(
            "Portfolio123's data and engines change, so running a configuration again may"
            " give different results, and two runs of one configuration may differ for that"
            " reason alone."
        )
    items.extend(_metric_limitations(review))
    items.append(
        "Only summary statistics are compared: no return series, drawdown history, or"
        " interval is shown."
    )
    return items


def _metric_limitations(review: ReviewContext) -> list[str]:
    """The limitations of the metrics' comparison: those not differenced, those unavailable, the
    results without normalized tables, and the results that share a saved response."""
    evidence = review.evidence
    metrics = evidence.differences.metric_counts
    items: list[str] = []
    if metrics.not_comparable:
        items.append(
            f"{metrics.not_comparable} metric comparisons aren't differenced, because a"
            " context differs. Each gives its reason."
        )
    if metrics.unavailable:
        items.append(
            f"{metrics.unavailable} metric comparisons are unavailable, because a value is."
        )
    without = [c.result.label for c in evidence.inputs if c.run.metrics is None]
    if without:
        one = len(without) == 1
        items.append(
            f"{review.labels(without)} {'has' if one else 'have'} no normalized tables, so"
            f" {'its' if one else 'their'} metrics are unavailable."
        )
    if evidence.differences.shared_responses:
        items.append(
            "Some results share a saved response, so their metrics come from one response."
        )
    return items


def _artifacts(review: ReviewContext) -> list[str]:
    listed = [
        Listed(
            artifact.path,
            REVIEW_ROLES[artifact.role],
            artifact.size,
            artifact.artifact_id,
            "" if artifact.label is None else review.name(artifact.label),
        )
        for artifact in review.evidence.artifacts
    ]
    return artifacts(
        "Each file links to the review's copy, by its path relative to this report. None links"
        " to a run.",
        (),
        (MANIFEST_PATH, "Review manifest, written last"),
        listed,
        results=True,
    )
