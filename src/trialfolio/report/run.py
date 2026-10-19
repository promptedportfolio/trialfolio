"""The run report: a screen run's evidence, from its saved records (release 0.1.0, R01-T13).

`render_run` renders it from a `RunContext`, section by section, each section a function of the
context. A run has one case, no baseline, and no research objective, so the sections that need
them say they're unavailable, and why.
"""

from collections.abc import Sequence
from typing import Final

from trialfolio.contracts.attempt import SavedResponse
from trialfolio.contracts.plan import PlanV1_2
from trialfolio.contracts.tables import MetricsRow
from trialfolio.normalization import LAYOUT
from trialfolio.report.evidence import RunContext
from trialfolio.report.fragments import (
    ASSUMPTIONS,
    COSTS,
    COVERAGE,
    NOT_ASSESSED,
    NOT_ASSESSED_FACTS,
    Listed,
    artifacts,
    attempt_counts,
    budget_limit,
    data_facts,
    inferred_defaults,
    invented_cost,
    metric_definitions,
    metric_label,
    parsers_line,
    plan_versions,
    provenance,
    rendered_by,
    reported_cost,
    reproducibility_limitation,
    run_written_by,
    settings_table,
    status,
    synthetic_writer,
    unavailable,
)
from trialfolio.report.page import code, facts, moment, page, table, text
from trialfolio.report.ranking import costs, limitations, run_source, run_weights
from trialfolio.report.vocabulary import (
    APPROVALS,
    ATTEMPT_OUTCOMES,
    EXCHANGE_RESULTS,
    METRIC_DEFINITIONS,
    PROVENANCE,
    ROLES,
    SYNTHETIC_VERIFIED,
    TOKENS,
)
from trialfolio.runs import MANIFEST_PATH, SavedAttempt

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


def render_run(run: RunContext) -> str:
    """The run's report, as an HTML document."""
    return page(
        version=run.version,
        title=run.saved.plan.title,
        kind="run report",
        label=" · Synthetic example" if run.synthetic else "",
        top=[*_synthetic_banner(run), *_status(run)],
        headings=_SECTIONS,
        sections={
            "objective": _objective(run),
            "definitions": _definitions(run),
            "data": _data(run),
            "results": _results(run),
            "cases": _cases(run),
            "robustness": _robustness(),
            "statistics": _statistics(),
            "evidence": _evidence(run),
            "feasibility": _feasibility(run),
            "conclusion": _conclusion(run),
        },
        records="the run's saved records",
    )


# The top of the report


def _synthetic_banner(run: RunContext) -> list[str]:
    if not run.synthetic:
        return []
    return [
        (
            '<p class="synthetic"><strong>Synthetic example.</strong> This run was written by'
            f" {synthetic_writer(run.saved.manifest)} from invented values. None of them comes"
            " from Portfolio123, and nothing was sent to it.</p>"
        )
    ]


def _status(run: RunContext) -> list[str]:
    manifest = run.saved.manifest
    outcome = manifest.outcome
    if manifest.error is not None:
        outcome += f" ({code(manifest.error.code)})"
    return status("Run outcome", outcome, _nature(run))


def _nature(run: RunContext) -> str:
    """What kind of results the run holds (DSC-04)."""
    if run.synthetic:
        return "Synthetic: invented values, neither backtested nor actual results."
    return (
        "Backtested: from applying the screen's rules to historical data, not from actual trades."
    )


# 1. Objective


def _objective(run: RunContext) -> list[str]:
    plan = run.saved.plan
    purpose = (
        f"<p>{text(plan.purpose)}</p>"
        if plan.purpose is not None
        else '<p class="muted">No purpose was declared.</p>'
    )
    benchmark = run.by_name.get("benchmark")
    objective = (
        "Unavailable: a screen run declares no research objective, only a title and an optional"
        " purpose."
    )
    return [
        *facts(
            [
                ("Objective", objective),
                ("Title", text(plan.title)),
                (
                    "Benchmark",
                    code(benchmark.value) if benchmark else "Unavailable: the run has none.",
                ),
                *NOT_ASSESSED_FACTS,
            ]
        ),
        "<h3>Declared purpose</h3>",
        purpose,
    ]


# 2. Definitions


def _definitions(run: RunContext) -> list[str]:
    source = (
        f"the run's invented response, laid out as {code(LAYOUT)} version 1: none comes from"
        " Portfolio123. Each is defined as that layout defines it"
        if run.synthetic
        else f"Portfolio123's response, laid out as {code(LAYOUT)} version 1"
    )
    return [
        *metric_definitions(f"The metrics are read from {source}.", {}),
        "<h3>Changes from a baseline</h3>",
        (
            "<p>Unavailable: a single run has no baseline, so no setting is classified as an"
            " intended change or an unexplained mismatch.</p>"
        ),
        *run_weights(run.settings),
    ]


# 3. Data sources


def _data(run: RunContext) -> list[str]:
    manifest = run.saved.manifest
    source = (
        "Invented values, packaged with Trial Folio for the demo, in the layout of"
        " Portfolio123's screen backtest response. Nothing was sent to Portfolio123."
        if manifest.synthetic
        else "Portfolio123's screen backtest, through <code>p123api</code>'s"
        " <code>screen_backtest</code>."
    )
    layouts = parsers_line(manifest.parsers) or "Unavailable: no response was read."
    meanings = PROVENANCE | ({"verified": SYNTHETIC_VERIFIED} if manifest.synthetic else {})
    plan = run.saved.plan
    return [
        *data_facts(source, layouts, run.by_name),
        *(
            run_source(plan.ranking_source, run.saved.snapshot)
            if isinstance(plan, PlanV1_2)
            else ()
        ),
        "<h3>Coverage</h3>",
        *_coverage(run),
        *provenance(meanings, _provenances(run)),
        "<h3>Missing values</h3>",
        *_missing(run),
        "<h3>Exclusions</h3>",
        f"<p>{_exclusions(run)}</p>",
    ]


def _exclusions(run: RunContext) -> str:
    forms = {response.form for response in _responses(run)}
    if not forms:
        return "None: the run saved no response."
    if "decoded" in forms:
        kept = (
            "None. Trial Folio excludes nothing from the response, and keeps it whole as it"
            " was saved."
        )
        if run.saved.manifest.capabilities.return_series == "source_only":
            kept += " Its per-period series is preserved there, but not interpreted."
        return kept
    return "None. The response is kept whole, as it came, undecoded."


def _responses(run: RunContext) -> list[SavedResponse]:
    return [
        attempt.record.response
        for attempt in run.saved.attempts
        if attempt.record is not None and attempt.record.response is not None
    ]


def _provenances(run: RunContext) -> set[str]:
    found = {setting.provenance for setting in run.settings}
    found.update(row.provenance for row in run.metrics.values())
    return found


def _coverage(run: RunContext) -> list[str]:
    if run.saved.metrics is None:
        return [
            "<p>The coverage couldn't be established: "
            + _no_tables_reason(run)
            + " The requested dates are in the settings below.</p>"
        ]
    dates = [
        _coverage_date(run, "start_date", "coverage_start"),
        _coverage_date(run, "end_date", "coverage_end"),
    ]
    rows = [row for row, _ in dates]
    established = any(found for _, found in dates)
    periods = run.metrics.get(("strategy", "coverage_periods"))
    if periods is not None:
        count = (
            code(periods.value)
            if periods.value is not None
            else unavailable(periods.unavailable_reason)
        )
        rows.append(
            f"<tr><td>{METRIC_DEFINITIONS['coverage_periods'][0]}</td><td></td><td>{count}</td>"
            f"<td>{code(periods.unit)}</td><td></td></tr>"
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
        *table(("Date", "Requested", "Coverage", "Unit", "Comparison"), rows),
    ]


def _coverage_date(run: RunContext, setting_name: str, metric_id: str) -> tuple[str, bool]:
    """The row of one coverage date, compared with the requested date, `setting_name`, and
    whether the response's periods established it."""
    setting = run.by_name.get(setting_name)
    metric = run.metrics.get(("strategy", metric_id))
    requested = code(setting.value) if setting else "Unavailable"
    if metric is None or metric.value is None:
        reason = metric.unavailable_reason if metric else None
        actual = unavailable(reason)
        comparison = "Couldn't be established"
    else:
        actual = code(metric.value)
        if setting is None:
            comparison = "Not compared: the requested date is unavailable"
        elif metric.value == setting.value:
            comparison = "Matches"
        elif "coverage_mismatch" in setting.flags:
            comparison = "Differs: flagged <code>coverage_mismatch</code>"
        else:
            comparison = "Differs"
    label = METRIC_DEFINITIONS[metric_id][0]
    row = (
        f"<tr><td>{label}</td><td>{requested}</td><td>{actual}</td>"
        f"<td>{code('date')}</td><td>{comparison}</td></tr>"
    )
    return row, metric is not None and metric.value is not None


def _missing(run: RunContext) -> list[str]:
    metrics = run.saved.metrics
    if metrics is None:
        return [f"<p>Unavailable: {_no_tables_reason(run)}</p>"]
    missing = [row for row in metrics if row.value is None]
    if not missing:
        return ["<p>None: every metric is available.</p>"]
    items = [
        f"<li>{metric_label(row)}: {unavailable(row.unavailable_reason)}</li>" for row in missing
    ]
    return [
        (
            f"<p>{len(missing)} of {len(metrics)} metrics are unavailable. None is shown"
            " as zero.</p>"
        ),
        "<ul>",
        *items,
        "</ul>",
    ]


def _no_tables_reason(run: RunContext) -> str:
    """Why the run has no normalized result."""
    responses = _responses(run)
    if any(response.form == "undecoded" for response in responses):
        return (
            "the response couldn't be decoded as JSON, so it was saved as it came, and wasn't"
            " normalized."
        )
    if responses:
        error = run.saved.manifest.error
        if error is not None and error.code == "provider.response_invalid":
            return (
                "the saved response doesn't have the layout's required structure, so it"
                " wasn't normalized."
            )
        return "the run wrote no normalized tables."
    return "no attempt succeeded, so there's no response to normalize."


# 4. Results


def _results(run: RunContext) -> list[str]:
    metrics = run.saved.metrics
    parts: list[str] = []
    if metrics is None:
        parts.append(f"<p>The normalized result is unavailable: {_no_tables_reason(run)}</p>")
    else:
        source = "invented, as every value here is" if run.synthetic else "Portfolio123's"
        parts.append(
            "<p>Each value has exactly the digits the response carries, never padded or"
            f" rounded; Decimals counts them. The risk statistics are {source}, for the"
            " period the settings give as <code>risk_stats_period</code>.</p>"
        )
        benchmark = run.by_name.get("benchmark")
        for subject, heading in (("strategy", "Strategy"), ("benchmark", "Benchmark")):
            rows = [
                row for row in metrics if row.subject == subject and row.metric_id not in COVERAGE
            ]
            if subject == "benchmark" and benchmark is not None:
                heading += f": {code(benchmark.value)}"
            parts.extend([f"<h3>{heading}</h3>", *_metrics_table(rows)])
    return [
        *parts,
        "<h3>Costs</h3>",
        *_settings_list(run, COSTS),
        "<h3>Exposures</h3>",
        "<p>Unavailable: the response reports no exposures.</p>",
        "<h3>Implementation assumptions</h3>",
        *_settings_list(run, ASSUMPTIONS),
        "<h3>All settings</h3>",
        *_settings_table(run),
    ]


def _metrics_table(rows: Sequence[MetricsRow]) -> list[str]:
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
            value = unavailable(row.unavailable_reason)
        else:
            value = code(row.value)
        name = text(METRIC_DEFINITIONS.get(row.metric_id, (row.metric_id, ""))[0])
        if row.benchmark is not None:
            name += f" vs. {text(row.benchmark)}"
        decimals = "" if row.source_decimals is None else str(row.source_decimals)
        location = code(row.source_location) if row.source_location is not None else ""
        body.append(
            f"<tr><td>{name}<br>{code(row.metric_id)}</td><td>{value}</td>"
            f"<td>{code(row.unit)}</td><td>{decimals}</td><td>{code(row.provenance)}</td>"
            f"<td>{location}</td></tr>"
        )
    heads = ("Metric", "Value", "Unit", "Decimals", "Provenance", "Source")
    return table(heads, body, caption=caption)


def _settings_list(run: RunContext, names: Sequence[str]) -> list[str]:
    items: list[str] = []
    for name in names:
        setting = run.by_name.get(name)
        if setting is None:
            continue
        unit = f" {code(setting.unit)}" if setting.unit is not None else ""
        note = TOKENS.get(setting.value)
        items.append(
            f"<li>{code(name)}: {code(setting.value)}{unit}"
            + (f". {note}" if note else "")
            + "</li>"
        )
    return ["<ul>", *items, "</ul>"]


def _settings_table(run: RunContext) -> list[str]:
    expected = run.saved.settings is None
    if expected:
        intro = (
            "<p>settings.csv wasn't written, so these are the plan's resolved settings, each"
            " with the provenance the plan expects it to have once the request is sent.</p>"
        )
    else:
        intro = (
            "<p>As settings.csv records them. <em>As written</em> is the value's text in the"
            " screen configuration.</p>"
        )
    return [intro, *settings_table(run.settings, expected=expected, notes=TOKENS)]


# 5. Cases and attempts


def _cases(run: RunContext) -> list[str]:
    attempts = [line for attempt in run.saved.attempts for line in _attempt(run, attempt)]
    return [
        (
            "<p>A run has one case: the resolved settings, identified by their case ID. Every"
            " attempt of it is listed, whatever its outcome.</p>"
        ),
        *_synthetic_records(run),
        *facts(_case_facts(run)),
        *(attempts or ["<p>The run has no attempt record.</p>"]),
        "<h3>Versions</h3>",
        *facts(_versions(run)),
    ]


def _case_facts(run: RunContext) -> list[tuple[str, str]]:
    manifest = run.saved.manifest
    plan = run.saved.plan
    budget = plan.budget
    counts = manifest.counts
    return [
        ("Case", code(run.case.case_id)),
        ("Plan hash", code(plan.plan_hash)),
        ("Approval", APPROVALS[manifest.approval]),
        (
            "Budget",
            (
                f"{budget.provider_requests} provider"
                f" {'request' if budget.provider_requests == 1 else 'requests'},"
                f" {budget_limit(budget)}, and at most"
                f" {budget.authentication_calls} authentication call."
            ),
        ),
        attempt_counts(counts.attempts),
        (
            "Provider requests",
            (
                f"{counts.provider_requests}: the sends that may have reached Portfolio123, which"
                " may be charged even when they fail. Authentication isn't counted."
            ),
        ),
        ("Retries", str(counts.retries)),
        ("Cost", _cost(run)),
    ]


def _cost(run: RunContext) -> str:
    cost = run.saved.manifest.counts.cost
    if run.synthetic:
        return invented_cost(cost, "the invented responses report")
    return reported_cost(cost)


def _versions(run: RunContext) -> list[tuple[str, str]]:
    manifest = run.saved.manifest
    return [
        run_written_by(manifest),
        *plan_versions(run.saved.plan),
        (
            "License and notice",
            (
                f"Recorded with the run: {code(manifest.license_id)}, notice version"
                f" {text(manifest.notice_version)}"
            ),
        ),
        rendered_by(run.version),
    ]


def _synthetic_records(run: RunContext) -> list[str]:
    if not run.synthetic:
        return []
    return [
        (
            "<p>The run is synthetic, so its attempt, the attempt's exchanges, and the counts"
            " below are invented, as a real run would record them. Nothing was sent to"
            " Portfolio123, and nothing was charged.</p>"
        )
    ]


def _attempt(run: RunContext, attempt: SavedAttempt) -> list[str]:
    state = attempt.status
    record = attempt.record
    first = record if record is not None else attempt.start
    exchanges = first.exchanges if first is not None else ()
    meaning = ATTEMPT_OUTCOMES[state.outcome]
    if state.outcome == "succeeded" and run.synthetic:
        meaning = "The run's invented response was saved. That says nothing about the strategy."
    entries = [("Outcome", f"{code(state.outcome)}: {meaning}")]
    if record is not None and record.error is not None:
        entries.append(("Error", f"{code(record.error.code)}: {text(record.error.message)}"))
    entries.append(("Possibly charged", "Yes" if state.possibly_charged else "No"))
    entries.append(("Provider requests", str(state.provider_requests)))
    if first is not None:
        entries.append(("Started", moment(first.started_at)))
    if record is not None:
        entries.append(("Ended", moment(record.ended_at)))
        entries.append(("Cost", costs(record, synthetic=run.synthetic)))
    rows = [
        f"<tr><td>{index}</td><td>{code(exchange.request)}</td>"
        f"<td>{EXCHANGE_RESULTS[exchange.result]}</td>"
        f"<td>{'' if exchange.status is None else exchange.status}</td>"
        f"<td>{code(exchange.note) if exchange.note else ''}</td></tr>"
        for index, exchange in enumerate(exchanges, 1)
    ]
    return [
        f"<h3>Attempt {code(str(state.attempt_id))}</h3>",
        *facts(entries),
        *table(
            ("#", "Request", "Result", "Status", "Note"),
            rows,
            caption="Its HTTP exchanges, in order",
        ),
    ]


# 6 to 9


def _robustness() -> list[str]:
    return [
        (
            f"<p>{NOT_ASSESSED}. Robustness results and the concentration of contributions need"
            " more than one run's summary statistics, and Trial Folio doesn't assess them.</p>"
        ),
    ]


def _statistics() -> list[str]:
    return [
        (
            f"<p>Statistical validation: {NOT_ASSESSED}. No statistical method was applied, so"
            " the report states no uncertainty, multiple-testing adjustment, or power. Summary"
            " statistics alone don't support intervals, a return series, or a drawdown history,"
            " so none is shown or reconstructed.</p>"
        ),
    ]


def _evidence(run: RunContext) -> list[str]:
    each = "one synthetic example" if run.synthetic else "one backtest"
    return [
        (
            f"<p>Unavailable: the run is {each} over the requested dates. It has no separate"
            " development, selection, holdout, or forward period.</p>"
        ),
        f"<p>{_nature(run)}</p>",
    ]


def _feasibility(run: RunContext) -> list[str]:
    missing = ["<li>Actual trades: none.</li>"]
    commission = run.by_name.get("commission")
    if commission is not None and commission.value == "not_modeled":
        missing.append(f"<li>Commission: {TOKENS['not_modeled']}</li>")
    unsent = [setting.name for setting in run.settings if setting.value == "not_sent"]
    if unsent:
        missing.append(
            "<li>Parameters not sent, whose defaults aren't documented: "
            + ", ".join(code(name) for name in unsent)
            + ".</li>"
        )
    if run.saved.manifest.capabilities.return_series == "source_only":
        missing.append(
            "<li>Turnover, positions, and per-period returns: preserved in the saved"
            " response, but not interpreted.</li>"
        )
    return [
        f"<p>Trading readiness: {NOT_ASSESSED}. Feasibility and capacity aren't assessed.</p>",
        "<p>Execution evidence this run doesn't have:</p>",
        "<ul>",
        *missing,
        "</ul>",
    ]


# 10. Conclusion


def _conclusion(run: RunContext) -> list[str]:
    manifest = run.saved.manifest
    if manifest.outcome == "completed":
        execution = (
            "The run completed: Trial Folio sent the planned request, saved the response,"
            " and normalized it."
            if not manifest.synthetic
            else "The run completed: Trial Folio wrote the synthetic run and normalized it."
        )
    else:
        error = manifest.error.code if manifest.error is not None else ""
        execution = f"The run didn't complete: it ended with {code(error)}."
    conclusion = (
        f"{execution} That's a statement about execution, not about the strategy."
        " Statistical validation and trading readiness are not assessed, so this report"
        " permits no conclusion about whether the strategy is useful, or whether its results"
        " could be achieved."
    )
    return [
        "<h3>Permitted conclusion</h3>",
        f"<p>{conclusion}</p>",
        "<h3>Limitations</h3>",
        "<ul>",
        *(f"<li>{item}</li>" for item in _limitations(run)),
        "</ul>",
        "<h3>Artifacts</h3>",
        *_artifacts(run),
    ]


def _limitations(run: RunContext) -> list[str]:
    manifest = run.saved.manifest
    items = [_nature(run), reproducibility_limitation(manifest.reproducibility)]
    if not manifest.synthetic:
        items.append(
            "Portfolio123's data and engines change, so running the configuration again may"
            " give different results. A rerun is a new attempt, never a replacement."
        )
    if isinstance(run.saved.plan, PlanV1_2):
        items.extend(
            limitations(synthetic=manifest.synthetic, each="The run's definition", kind="run")
        )
    items.extend(inferred_defaults(run.settings))
    mismatched = [setting.name for setting in run.settings if "coverage_mismatch" in setting.flags]
    if mismatched:
        items.append(
            "The coverage differs from the requested "
            + " and ".join(code(name) for name in mismatched)
            + "."
        )
    if run.saved.metrics is not None:
        count = sum(row.value is None for row in run.saved.metrics)
        if count:
            items.append(f"{count} metrics are unavailable, with their reasons above.")
    else:
        items.append(f"The normalized result is unavailable: {_no_tables_reason(run)}")
    items.append(
        "Only summary statistics are reported: no return series, drawdown history, or"
        " interval is shown."
    )
    return items


def _artifacts(run: RunContext) -> list[str]:
    where = (
        "Each file is named by its path in the run's directory."
        if run.base is None
        else "Each file links to the run's copy, by a path relative to this report."
    )
    listed = [
        Listed(artifact.path, ROLES[artifact.role], artifact.size, artifact.artifact_id)
        for artifact in run.saved.manifest.artifacts
        if artifact.role != "report"
    ]
    return artifacts(where, run.base, (MANIFEST_PATH, "Manifest, written last"), listed)
