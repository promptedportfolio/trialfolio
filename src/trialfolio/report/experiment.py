"""The experiment report: an experiment session's evidence, from an `ExperimentEvidence` (release
0.3.0, R03-T10).

`render_experiment` renders it from an `ExperimentContext`, section by section, each section a
function of the context. The case ledger, section 5, is in `trialfolio.report.experiment_cases`.
The report shows every planned case in the plan's order, each case's metrics side by side,
without a difference, and every plan with its reason. It orders, ranks, and marks no case by a
value.
"""

from collections.abc import Sequence
from typing import Final

from trialfolio.contracts.experiment_plan import ExperimentPlanCase, ExperimentPlanCaseV1_3
from trialfolio.contracts.experiment_record import PlanChanges, PlanChangesV1_1
from trialfolio.contracts.tables import MetricsRow
from trialfolio.display import series
from trialfolio.normalization import LAYOUT, METRICS, setting_text
from trialfolio.report.evidence import CaseView, ExperimentContext, experiment_manifest_path
from trialfolio.report.experiment_cases import case_description, ledger, variant_change
from trialfolio.report.fragments import (
    ASSUMPTIONS,
    COSTS,
    COVERAGE,
    NOT_ASSESSED,
    NOT_ASSESSED_FACTS,
    Listed,
    artifacts,
    data_facts,
    inferred_defaults,
    metric_definitions,
    metric_label,
    parsers_line,
    provenance,
    reproducibility_limitation,
    resolved_settings,
    settings_table,
    status,
    unavailable,
    unit,
)
from trialfolio.report.page import code, facts, page, table, text
from trialfolio.report.vocabulary import (
    EXPERIMENT_APPROVALS,
    EXPERIMENT_ROLES,
    EXPERIMENT_VERIFIED,
    LAYOUT_METRICS,
    METRIC_DEFINITIONS,
    PRIOR_RESEARCH,
    PROVENANCE,
    SYNTHETIC_EXPERIMENT_VERIFIED,
    TOKENS,
)

_SECTIONS: Final = (
    ("objective", "Objective, purpose, and research status"),
    ("definitions", "Definitions, and changes from the baseline"),
    ("data", "Data sources, coverage, provenance, and missing values"),
    ("results", "Returns, risks, costs, and assumptions"),
    ("cases", "Cases and attempts"),
    ("robustness", "Robustness and concentration"),
    ("statistics", "Statistical methods and uncertainty"),
    ("evidence", "Development, selection, holdout, and forward evidence"),
    ("feasibility", "Feasibility, capacity, and missing execution evidence"),
    ("conclusion", "Conclusion, limitations, and artifacts"),
)
"""An experiment report's sections: a run report's, with the same `id`s, and headings for an
experiment."""


def render_experiment(experiment: ExperimentContext) -> str:
    """The session's report, as an HTML document."""
    return page(
        version=experiment.version,
        title=experiment.plan.title,
        kind="experiment report",
        label=" · Synthetic experiment" if experiment.synthetic else "",
        top=[*_synthetic_banner(experiment), *_status(experiment)],
        headings=_SECTIONS,
        sections={
            "objective": _objective(experiment),
            "definitions": _definitions(experiment),
            "data": _data(experiment),
            "results": _results(experiment),
            "cases": ledger(experiment),
            "robustness": _robustness(),
            "statistics": _statistics(experiment),
            "evidence": _evidence(experiment),
            "feasibility": _feasibility(experiment),
            "conclusion": _conclusion(experiment),
        },
        records="the experiment's saved records",
    )


# The top of the report


def _synthetic_banner(experiment: ExperimentContext) -> list[str]:
    if not experiment.synthetic:
        return []
    return [
        (
            '<p class="synthetic"><strong>Synthetic experiment.</strong> Trial Folio wrote'
            " this experiment with the demo's client, from invented values. Every value,"
            " attempt, and count in it is invented: none comes from Portfolio123, and nothing"
            " was sent to it or charged.</p>"
        )
    ]


def _status(experiment: ExperimentContext) -> list[str]:
    evidence = experiment.evidence
    outcome = evidence.outcome
    if evidence.error is not None:
        outcome += f" ({code(evidence.error.code)})"
    return status(f"Session {evidence.session} outcome", outcome, _nature(experiment))


def _nature(experiment: ExperimentContext) -> str:
    """What kind of results the experiment holds (DSC-04)."""
    if experiment.synthetic:
        return "Synthetic: invented values, neither backtested nor actual results."
    return (
        "Backtested: from applying each case's screen rules to historical data, not from"
        " actual trades."
    )


# 1. Objective


def _objective(experiment: ExperimentContext) -> list[str]:
    plan = experiment.plan
    declared = plan.prior_research
    description = (
        f"<p>{text(declared.description)}</p>"
        if declared.description is not None
        else '<p class="muted">No description was declared.</p>'
    )
    objective = (
        "Unavailable: an experiment declares no research objective or criteria, only its title,"
        " purpose, and prior research."
    )
    benchmark = (
        f"{code(experiment.baseline_value('benchmark'))}, every case's: no variant changes it."
    )
    return [
        *facts(
            [
                ("Objective", objective),
                ("Experiment", code(plan.experiment_id)),
                ("Title", text(plan.title)),
                ("Benchmark", benchmark),
                *NOT_ASSESSED_FACTS,
            ]
        ),
        "<h3>Declared purpose</h3>",
        f"<p>{text(plan.purpose)}</p>",
        "<h3>Declared prior research</h3>",
        f"<p>Status: {code(declared.status)}: {PRIOR_RESEARCH[declared.status]}.</p>",
        description,
        (
            "<p>Trial Folio records the declaration as the user supplied it, and can't verify"
            " it.</p>"
        ),
        "<h3>Plans and revisions</h3>",
        *_plans(experiment),
    ]


def _plans(experiment: ExperimentContext) -> list[str]:
    entries = experiment.evidence.record.plans
    rows: list[str] = []
    for entry in entries:
        current = " (current)" if entry is entries[-1] else ""
        reason = "None: the first plan" if entry.reason is None else text(entry.reason)
        rows.append(
            f'<tr><td>{entry.plan}{current}</td><td class="long">{code(entry.plan_hash)}'
            f"</td><td>{code(entry.approval)}</td><td>{reason}</td>"
            f"<td>{_plan_changes(entry.changes)}</td></tr>"
        )
    used = {entry.approval for entry in entries}
    return [
        (
            "<p>Every plan of the experiment, oldest first. Each was approved before anything"
            " was sent under it. A revision records the reason the user gave for it, which"
            " Trial Folio can't verify, and what changed from the plan before it.</p>"
        ),
        *table(("Plan", "Plan hash", "Approval", "Reason", "Changes"), rows),
        "<ul>",
        *(
            f"<li>{code(approval)}: {meaning}</li>"
            for approval, meaning in EXPERIMENT_APPROVALS.items()
            if approval in used
        ),
        "</ul>",
    ]


def _plan_changes(changes: PlanChanges | PlanChangesV1_1 | None) -> str:
    """What a revision changed from the plan before it, one kind of change to a line."""
    if changes is None:
        return "The first plan"
    lines = [
        f"{code(change.package)} from {text(change.previous)} to {text(change.current)}"
        for change in changes.versions
    ]
    for cases, verb in ((changes.cases_added, "added"), (changes.cases_retired, "retired")):
        if cases:
            named = [f"{code(case.case_key)} ({code(case.case_id)})" for case in cases]
            lines.append(f"Cases {verb}: {series(named)}")
    if changes.parts:
        lines.append("Other parts changed: " + series([code(part) for part in changes.parts]))
    return "<br>".join(lines)


# 2. Definitions


def _definitions(experiment: ExperimentContext) -> list[str]:
    changes = [
        f"<tr><td>{code(view.case.case_key)}</td><td>{code(view.case.case_id)}</td>"
        f"<td>{variant_change(view.case.variant)}</td>"
        f"<td>{case_description(view.case.description)}</td></tr>"
        for view in experiment.cases
    ]
    overrides = LAYOUT_METRICS if experiment.synthetic else {}
    return [
        (
            "<p>Each case is the baseline screen with exactly one change, its variant, which"
            " the plan compiled before any request was sent. So each case's settings are the"
            " baseline's, apart from the one setting its change names.</p>"
        ),
        "<h3>Changes from the baseline</h3>",
        *table(("Case", "case_id", "Change", "Description"), changes),
        "<h3>The baseline's settings</h3>",
        *_baseline_table(experiment),
        "<h3>Metric definitions</h3>",
        *metric_definitions(_metric_source(experiment), overrides),
    ]


def _metric_source(experiment: ExperimentContext) -> str:
    layout = f"laid out as {code(LAYOUT)} version 1"
    if experiment.synthetic:
        return (
            f"The metrics are read from each case's invented response, {layout}: none comes"
            " from Portfolio123. Each is defined as that layout defines it."
        )
    return f"The metrics are read from each case's response from Portfolio123, {layout}."


def _baseline_table(experiment: ExperimentContext) -> list[str]:
    expected = experiment.baseline.settings is None
    if expected:
        intro = (
            "The baseline has no settings.csv, so these are the plan's resolved settings, each"
            " with the provenance the plan expects it to have once the request is sent."
        )
    else:
        intro = (
            "As the baseline's settings.csv records them. <em>As written</em> is the value's"
            " text in the experiment configuration."
        )
    settings = experiment.baseline_settings.values()
    return [
        f"<p>{intro}</p>",
        *settings_table(settings, expected=expected, notes=experiment.tokens),
    ]


# 3. Data sources


def _data(experiment: ExperimentContext) -> list[str]:
    if experiment.synthetic:
        source = (
            "Invented values: the demo's packaged response, in the layout of Portfolio123's"
            " screen backtest response, for every case. Nothing was sent to Portfolio123."
        )
    else:
        source = (
            "Portfolio123's screen backtest, through <code>p123api</code>'s"
            " <code>screen_backtest</code>, one request for each attempt that sent one."
        )
    if any(view.metrics is not None for view in experiment.cases):
        layouts = parsers_line(experiment.evidence.parsers)
    else:
        layouts = "Unavailable: no planned case's response was normalized."
    verified = SYNTHETIC_EXPERIMENT_VERIFIED if experiment.synthetic else EXPERIMENT_VERIFIED
    meanings = PROVENANCE | {"verified": verified}
    return [
        "<h3>Sources</h3>",
        *data_facts(source, layouts, experiment.baseline_settings),
        "<h3>Coverage</h3>",
        *_coverage(experiment),
        *provenance(meanings, _provenances(experiment)),
        "<h3>Missing values</h3>",
        *_missing(experiment),
        "<h3>Exclusions</h3>",
        f"<p>{_exclusions(experiment)}</p>",
    ]


def _provenances(experiment: ExperimentContext) -> set[str]:
    found: set[str] = set()
    for view in experiment.cases:
        settings = resolved_settings(view.settings, view.case.settings)
        found.update(setting.provenance for setting in settings)
        found.update(row.provenance for row in view.metrics or ())
    return found


def _coverage(experiment: ExperimentContext) -> list[str]:
    rows: list[str] = []
    for view in experiment.cases:
        if view.metrics is None:
            cells = ["Unavailable"] * 3 + [f"Unavailable: {_no_tables(view)}"]
        else:
            metrics = {row.metric_id: row for row in view.metrics if row.subject == "strategy"}
            cells = [
                *(_metric_value(metrics[metric_id]) for metric_id in COVERAGE),
                _coverage_against(experiment, view, metrics),
            ]
        rows.append(
            f"<tr><td>{code(view.case.case_key)}</td>"
            + "".join(f"<td>{cell}</td>" for cell in cells)
            + "</tr>"
        )
    heads = (
        "Case",
        "Coverage start",
        "Coverage end",
        "Coverage periods",
        "Against the requested dates",
    )
    return [
        (
            "<p>Each case's coverage is read from the dates of its response's periods, and"
            " compared with the requested dates, which every case shares:"
            f" {code(experiment.baseline_value('start_date'))} to"
            f" {code(experiment.baseline_value('end_date'))}. A case without normalized tables"
            " has none. Coverage that couldn't be established is never shown as"
            " matching.</p>"
        ),
        *table(heads, rows),
    ]


def _coverage_against(
    experiment: ExperimentContext, view: CaseView, metrics: dict[str, MetricsRow]
) -> str:
    flagged = {row.setting for row in view.settings or () if "coverage_mismatch" in row.flags}
    found: list[str] = []
    for name, metric_id, which in (
        ("start_date", "coverage_start", "start"),
        ("end_date", "coverage_end", "end"),
    ):
        value = metrics[metric_id].value
        if value is None:
            found.append(f"the {which} couldn't be established")
        elif value != experiment.baseline_value(name):
            flag = ", flagged <code>coverage_mismatch</code>" if name in flagged else ""
            found.append(f"the {which} differs{flag}")
    if not found:
        return "Matches"
    sentence = series(found)
    return f"{sentence[0].upper()}{sentence[1:]}."


def _missing(experiment: ExperimentContext) -> list[str]:
    tabled = [view for view in experiment.cases if view.metrics is not None]
    if not tabled:
        return ["<p>Unavailable: no planned case has normalized tables.</p>"]
    rows = [
        f"<tr><td>{code(view.case.case_key)}</td><td>{metric_label(row)}</td>"
        f"<td>{unavailable(row.unavailable_reason)}</td></tr>"
        for view in tabled
        for row in view.metrics or ()
        if row.value is None
    ]
    if not rows:
        return ["<p>None: every metric of every case with normalized tables is available.</p>"]
    metrics = "metric is" if len(rows) == 1 else "metrics are"
    cases = "case" if len(tabled) == 1 else "cases"
    return [
        (
            f"<p>{len(rows)} {metrics} unavailable, across the {len(tabled)} {cases} with"
            " normalized tables. None is shown as zero.</p>"
        ),
        *table(("Case", "Metric", "Reason"), rows),
    ]


def _exclusions(experiment: ExperimentContext) -> str:
    forms = {
        attempt.response.form
        for view in (*experiment.cases, *experiment.evidence.retired)
        for attempt in view.attempts
        if attempt.response is not None
    }
    if not forms:
        return "None: the experiment saved no response."
    kept = (
        "None. Trial Folio excludes nothing from the saved responses, and keeps each whole, as"
        " it was saved"
    )
    kept += ", an undecoded one as it came." if "undecoded" in forms else "."
    if experiment.evidence.capabilities.return_series == "source_only":
        kept += " Their per-period series are preserved there, but not interpreted."
    return kept


def _no_tables(view: CaseView) -> str:
    """Why a planned case has no normalized tables."""
    if view.invalid is not None:
        if any(
            attempt.response is not None and attempt.response.form == "undecoded"
            for attempt in view.attempts
        ):
            return (
                "its response couldn't be decoded as JSON, so it was saved as it came, and"
                " wasn't normalized."
            )
        return (
            "its saved response doesn't have the layout's required structure, so it wasn't"
            " normalized."
        )
    if view.outcome == "not_yet_run":
        return "it hasn't been run yet."
    return "no attempt of it succeeded, so there's no response to normalize."


# 4. Results


def _results(experiment: ExperimentContext) -> list[str]:
    shown = [view for view in experiment.cases if view.metrics is not None]
    parts: list[str] = []
    if not shown:
        parts.append(
            "<p>Unavailable: no planned case has normalized tables, so there are no metrics"
            " to show.</p>"
        )
    else:
        source = "invented, as every value here is" if experiment.synthetic else "Portfolio123's"
        parts.append(
            "<p>Each case's metrics, as its metrics.csv holds them, side by side in the"
            " plan's order. Each value has exactly the digits the response carries, never"
            f" padded or rounded. The risk statistics are {source}, for the period the"
            " settings give as <code>risk_stats_period</code>. The report computes no"
            " difference between cases, and orders, ranks, and marks no case by a value.</p>"
        )
        without = [view for view in experiment.cases if view.metrics is None]
        if without:
            parts.append(
                "<p>Not shown, without normalized tables: "
                + series([code(view.case.case_key) for view in without])
                + ". The coverage above says why.</p>"
            )
        for subject, heading in (("strategy", "Strategy"), ("benchmark", "Benchmark")):
            if subject == "benchmark":
                heading += f": {code(experiment.baseline_value('benchmark'))}"
            parts.extend([f"<h3>{heading}</h3>", *_metrics_across(experiment, shown, subject)])
    if experiment.evidence.retired:
        parts.append(
            "<p>The retired cases' tables are kept in their directories, and listed among the"
            " artifacts. They aren't shown here.</p>"
        )
    return [
        *parts,
        "<h3>Costs</h3>",
        *_settings_across(experiment, COSTS),
        "<h3>Exposures</h3>",
        "<p>Unavailable: the responses report no exposures.</p>",
        "<h3>Implementation assumptions</h3>",
        *_settings_across(experiment, ASSUMPTIONS),
    ]


def _metrics_across(
    experiment: ExperimentContext, shown: Sequence[CaseView], subject: str
) -> list[str]:
    by_case = [
        {row.metric_id: row for row in view.metrics or () if row.subject == subject}
        for view in shown
    ]
    metric_ids = [
        metric.metric_id
        for metric in METRICS
        if metric.subject == subject and metric.metric_id not in COVERAGE
    ]
    periods = {
        (rows[metric_id].period_start, rows[metric_id].period_end)
        for rows in by_case
        for metric_id in metric_ids
    }
    if len(periods) == 1:
        ((start, end),) = periods
        caption = (
            f"Over {start.isoformat()} to {end.isoformat()}, every case's coverage."
            if start is not None and end is not None
            else "Over a period that couldn't be established."
        )
    else:
        caption = "The cases' rows cover different periods; the coverage above gives each."
    if experiment.synthetic:
        caption += " Every value is invented."
    body: list[str] = []
    for metric_id in metric_ids:
        first = by_case[0][metric_id]
        name = text(METRIC_DEFINITIONS[metric_id][0])
        if first.benchmark is not None:
            name += f" vs. {text(first.benchmark)}"
        cells = "".join(f"<td>{_metric_value(rows[metric_id])}</td>" for rows in by_case)
        body.append(
            f"<tr><td>{name}<br>{code(metric_id)}</td><td>{code(first.unit)}</td>{cells}</tr>"
        )
    heads = ("Metric", "Unit", *(code(view.case.case_key) for view in shown))
    return table(heads, body, caption=caption)


def _metric_value(row: MetricsRow) -> str:
    """A metric's value as `metrics.csv` holds it, or why it's unavailable."""
    if row.value is None:
        reason = row.unavailable_reason
        return "Unavailable" if reason is None else f"Unavailable ({code(reason)})"
    return code(row.value)


def _settings_across(experiment: ExperimentContext, names: Sequence[str]) -> list[str]:
    rows: list[str] = []
    for name in names:
        setting = experiment.baseline_settings.get(name)
        if setting is None:
            continue
        changed = [
            f"{code(view.case.case_key)}: {code(_plan_value(view.case, name))}"
            for view in experiment.cases
            if view.case.variant is not None and view.case.variant.setting == name
        ]
        note = experiment.tokens.get(setting.value, "")
        rows.append(
            f"<tr><td>{code(name)}</td><td>{code(setting.value)}</td>"
            f"<td>{unit(setting.unit)}</td>"
            f"<td>{series(changed) if changed else 'No case'}</td><td>{note}</td></tr>"
        )
    return table(("Setting", "The baseline's", "Unit", "Changed by", "Notes"), rows)


def _plan_value(case: ExperimentPlanCase | ExperimentPlanCaseV1_3, name: str) -> str:
    """The case's resolved value of a setting, as `settings.csv` writes it."""
    return next(setting_text(row.value) for row in case.settings if row.setting == name)


# 6 to 9


def _robustness() -> list[str]:
    return [
        (
            f"<p>{NOT_ASSESSED}. The cases are variants of one baseline, predefined in the"
            " plan before any request was sent, but Trial Folio doesn't assess robustness or"
            " the concentration of contributions from them. A variant whose outcome is used"
            " to choose a candidate is part of the search, not independent evidence for that"
            " candidate.</p>"
        ),
    ]


def _statistics(experiment: ExperimentContext) -> list[str]:
    counts = experiment.evidence.counts
    attempts = counts.attempts
    made = attempts.succeeded + attempts.failed + attempts.unknown + attempts.running
    repeats = f"{attempts.repeats} {'repeat' if attempts.repeats == 1 else 'repeats'}"
    return [
        (
            f"<p>Statistical validation: {NOT_ASSESSED}. No statistical method was applied, so"
            " the report states no uncertainty, multiple-testing adjustment, or power. Summary"
            " statistics alone don't support intervals, a return series, or a drawdown"
            " history, so none is shown or reconstructed.</p>"
        ),
        (
            f"<p>The current plan has {counts.cases.planned} cases, and revisions retired"
            f" {counts.retired_cases}. Attempts made: {made}, with {repeats} among them. These"
            " counts are the experiment's research history, not a multiple-testing family: an"
            " attempt or a repeat is a provider operation, not a hypothesis, and a predefined"
            " variant isn't one either, unless its outcome informs a selection.</p>"
        ),
    ]


def _evidence(experiment: ExperimentContext) -> list[str]:
    each = "a synthetic example" if experiment.synthetic else "a backtest"
    return [
        (
            f"<p>Unavailable: each case is {each} over the same requested dates. The"
            " experiment has no separate development, selection, holdout, or forward"
            " period.</p>"
        ),
        f"<p>{_nature(experiment)}</p>",
    ]


def _feasibility(experiment: ExperimentContext) -> list[str]:
    missing = ["<li>Actual trades: none.</li>"]
    commission = experiment.baseline_settings.get("commission")
    if commission is not None and commission.value == "not_modeled":
        missing.append(f"<li>Commission: {TOKENS['not_modeled']}</li>")
    unsent = [
        setting.name
        for setting in experiment.baseline_settings.values()
        if setting.value == "not_sent"
    ]
    if unsent:
        missing.append(
            "<li>Parameters not sent, whose defaults aren't documented: "
            + ", ".join(code(name) for name in unsent)
            + ".</li>"
        )
    if experiment.evidence.capabilities.return_series == "source_only":
        missing.append(
            "<li>Turnover, positions, and per-period returns: preserved in the saved"
            " responses, but not interpreted.</li>"
        )
    return [
        f"<p>Trading readiness: {NOT_ASSESSED}. Feasibility and capacity aren't assessed.</p>",
        "<p>Execution evidence this experiment doesn't have:</p>",
        "<ul>",
        *missing,
        "</ul>",
    ]


# 10. Conclusion


def _conclusion(experiment: ExperimentContext) -> list[str]:
    evidence = experiment.evidence
    cases = evidence.counts.cases
    if evidence.outcome == "completed":
        response = "invented response" if experiment.synthetic else "response"
        execution = f"Every planned case succeeded: its {response} was saved and normalized."
    else:
        error = evidence.error.code if evidence.error is not None else ""
        execution = (
            f"Session {evidence.session} ended with {code(error)}: {cases.succeeded} of the"
            f" {cases.planned} planned cases succeeded, and section 5 gives each case's"
            " outcome."
        )
    conclusion = (
        f"{execution} That's a statement about execution, not about any strategy. No case is"
        " ranked, selected, or called best. Statistical validation and trading readiness are"
        " not assessed, so this report permits no conclusion about whether any case's"
        " strategy is useful, or whether its results could be achieved."
    )
    return [
        "<h3>Permitted conclusion</h3>",
        f"<p>{conclusion}</p>",
        "<h3>Limitations</h3>",
        "<ul>",
        *(f"<li>{item}</li>" for item in _limitations(experiment)),
        "</ul>",
        "<h3>Artifacts</h3>",
        *_artifacts(experiment),
    ]


def _limitations(experiment: ExperimentContext) -> list[str]:
    evidence = experiment.evidence
    items = [_nature(experiment), reproducibility_limitation(evidence.reproducibility)]
    if not experiment.synthetic:
        items.append(
            "Portfolio123's data and engines change, so sending a case's request again may"
            " give different results. A repeat is a new attempt, never a replacement."
        )
    items.append(_prior_research(experiment))
    items.extend(inferred_defaults(experiment.baseline_settings.values()))
    items.extend(_case_limitations(experiment))
    items.append(
        "Only summary statistics are reported: no return series, drawdown history, or"
        " interval is shown."
    )
    items.append(
        f"This is session {evidence.session}'s report. Each later run of the experiment"
        " that reaches its end writes its own report and manifest, which supersede this one,"
        " and replaces no file."
    )
    return items


def _prior_research(experiment: ExperimentContext) -> str:
    """What the declared prior research limits."""
    status = experiment.plan.prior_research.status
    prior = (
        f"The prior research is declared {code(status)}, and Trial Folio can't verify the"
        " declaration."
    )
    if status != "complete":
        prior += (
            " Earlier outcome-informed work on this idea isn't fully recorded, so a claim"
            " drawn from these cases is limited accordingly."
        )
    return prior


def _case_limitations(experiment: ExperimentContext) -> list[str]:
    """The limitations of the planned cases' tables: whose coverage differs from the requested
    dates, how many metrics are unavailable, and which cases have no normalized result."""
    items: list[str] = []
    mismatched = [
        view.case.case_key
        for view in experiment.cases
        if any("coverage_mismatch" in row.flags for row in view.settings or ())
    ]
    if mismatched:
        items.append(
            "The coverage differs from the requested dates for "
            + series([code(key) for key in mismatched])
            + "."
        )
    count = sum(row.value is None for view in experiment.cases for row in view.metrics or ())
    if count:
        items.append(
            "1 metric is unavailable, with its reason above."
            if count == 1
            else f"{count} metrics are unavailable, with their reasons above."
        )
    without = [view.case.case_key for view in experiment.cases if view.metrics is None]
    if without:
        items.append(
            "No normalized result for "
            + series([code(key) for key in without])
            + ": section 5 gives each case's outcome."
        )
    return items


def _artifacts(experiment: ExperimentContext) -> list[str]:
    evidence = experiment.evidence
    listed = [
        Listed(artifact.path, EXPERIMENT_ROLES[artifact.role], artifact.size, artifact.artifact_id)
        for artifact in evidence.artifacts
    ]
    # The report is in sessions/<s>/, two levels below the output root.
    return artifacts(
        "Each file links to the experiment's copy, by a path relative to this report.",
        ("..", ".."),
        (experiment_manifest_path(evidence.session), "Manifest, written last"),
        listed,
    )
