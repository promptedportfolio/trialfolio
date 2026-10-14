"""The parts of a report that more than one kind of report shows the same way, word for word.

- **The settings.** `resolved_settings` gives a run's or a case's settings from its `settings.csv`,
  or from its plan without it, and `settings_table` shows them.
- **The status,** at the top of every report, and the two things no report assesses.
- **The definitions** of the metrics, and where the metrics are read from.
- **The data section's facts:** the source, the response layouts, the data vendor, and the
  point-in-time method; and the provenance codes, with what each means.
- **Section 5's facts:** the budget, the attempts, the cost, and the versions.
- **The limitations** on reproducibility and on inferred defaults.
- **The artifacts table,** with each file linked by its path relative to the report.

Each kind of report keeps its own wording (DSC-04), so a fragment holds only what each report
that shows it words the same way.
"""

import html
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final
from urllib.parse import quote

from trialfolio.contracts.common import UnavailableReason
from trialfolio.contracts.experiment_plan import PlanBudgetV1_1, PlanV1_1
from trialfolio.contracts.manifest import (
    AttemptCounts,
    ParserVersion,
    Reproducibility,
    RunManifest,
)
from trialfolio.contracts.plan import Budget, Plan, PlanSetting
from trialfolio.contracts.tables import MetricsRow, SettingsRow
from trialfolio.normalization import setting_text
from trialfolio.report.page import code, facts, moment, table, text
from trialfolio.report.vocabulary import FLAGS, METRIC_DEFINITIONS, UNAVAILABLE_REASONS

NOT_ASSESSED: Final = "Not assessed"

NOT_ASSESSED_FACTS: Final = (
    ("Statistical validation", NOT_ASSESSED),
    ("Trading readiness", NOT_ASSESSED),
)
"""What each report's status, and its objective, say of statistical validation and trading
readiness."""

COVERAGE: Final = ("coverage_start", "coverage_end", "coverage_periods")
"""The metrics that give a response's coverage, which each report shows apart from the others."""

COSTS: Final = ("slippage_percent", "commission", "carry_cost")
"""The settings each report shows as its costs."""

ASSUMPTIONS: Final = ("transaction_price", "rebalance_weeks", "max_holdings", "pit_method")
"""The settings each report shows as its implementation assumptions."""


# The settings


@dataclass(frozen=True)
class Setting:
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


def resolved_settings(
    rows: Sequence[SettingsRow] | None, planned: Sequence[PlanSetting]
) -> tuple[Setting, ...]:
    """A run's or a case's resolved settings: its `settings.csv` rows, or, without them, its
    plan's, `planned`."""
    if rows is not None:
        return tuple(
            Setting(
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
            for row in rows
        )
    return tuple(
        Setting(
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
        for row in planned
    )


def setting_brief(setting: Setting) -> str:
    expected = "expected to be " if setting.expected else ""
    brief = f"{code(setting.value)} ({expected}{setting.provenance})"
    if setting.inference_rule is not None:
        brief += f". {text(setting.inference_rule)}"
    return brief


def unit(value: str | None) -> str:
    return "" if value is None else code(value)


def flag_list(flags: Sequence[str]) -> str:
    """Each flag code, with what it means, one to a line."""
    return "<br>".join(f"{code(flag)}: {FLAGS.get(flag, '')}" for flag in flags)


def settings_table(
    settings: Iterable[Setting], *, expected: bool, notes: Mapping[str, str] | None
) -> list[str]:
    """The table of a run's or a baseline's resolved settings, each with its category, value,
    unit, provenance, or the provenance the plan expects when `expected`, and flags.

    Unless `notes` is None, each also has its value as written in the configuration, and its
    notes: its inference rule, or else what its value's token means, from `notes`.
    """
    heads = ["Setting", "Category", "Value", "Unit"]
    heads += ["Expected provenance" if expected else "Provenance", "Flags"]
    if notes is not None:
        heads += ["As written", "Notes"]
    rows: list[str] = []
    for setting in settings:
        row = (
            f"<tr><td>{code(setting.name)}</td><td>{code(setting.category)}</td>"
            f"<td>{code(setting.value)}</td><td>{unit(setting.unit)}</td>"
            f"<td>{code(setting.provenance)}</td><td>{flag_list(setting.flags)}</td>"
        )
        if notes is not None:
            if setting.inference_rule is not None:
                note = text(setting.inference_rule)
            else:
                note = notes.get(setting.value, "")
            original = code(setting.original_value) if setting.original_value is not None else ""
            row += f"<td>{original}</td><td>{note}</td>"
        rows.append(f"{row}</tr>")
    return table(heads, rows)


# The metrics


def metric_label(row: MetricsRow) -> str:
    name = METRIC_DEFINITIONS.get(row.metric_id, (row.metric_id, ""))[0]
    return f"{text(name)}, {row.subject} ({code(row.metric_id)})"


def unavailable(reason: UnavailableReason | None) -> str:
    if reason is None:
        return "Unavailable"
    return f"Unavailable ({code(reason)}): {UNAVAILABLE_REASONS[reason]}"


def metric_definitions(source: str, overrides: Mapping[str, str]) -> list[str]:
    """`source`, the sentence that says where the metrics are read from, then each metric's
    definition, or its definition in `overrides`."""
    rows = [
        f"<tr><td>{name}</td><td>{code(metric_id)}</td>"
        f"<td>{overrides.get(metric_id, definition)}</td></tr>"
        for metric_id, (name, definition) in METRIC_DEFINITIONS.items()
    ]
    return [
        f"<p>{source} The benchmark's metrics are defined as the strategy's.</p>",
        *table(("Metric", "Identifier", "Definition"), rows),
    ]


# The top of a report


def status(term: str, outcome: str, nature: str) -> list[str]:
    """A report's status: its outcome, under `term`, as an execution status; statistical
    validation and trading readiness, not assessed; and `nature`, the kind of results it holds."""
    return facts(
        [
            (term, f"{outcome}. An execution status, not a research finding."),
            *NOT_ASSESSED_FACTS,
            ("Results", nature),
        ]
    )


# 3. Data sources


def parsers_line(parsers: Iterable[ParserVersion]) -> str:
    """Each response layout read, with its version and its parser's; empty when none was."""
    return ", ".join(
        f"{code(parser.layout)} version {parser.layout_version}, parser version"
        f" {parser.parser_version}"
        for parser in parsers
    )


def data_facts(source: str, layouts: str, settings: Mapping[str, Setting]) -> list[str]:
    """Where a run's or an experiment's data came from, `source`; the response layouts read,
    `layouts`; and its data vendor and point-in-time method, from `settings`."""
    vendor = settings.get("data_vendor")
    pit = settings.get("pit_method")
    return facts(
        [
            ("Source", source),
            ("Response layout", layouts),
            ("Data vendor", setting_brief(vendor) if vendor else "Unavailable"),
            ("Point-in-time method", setting_brief(pit) if pit else "Unavailable"),
        ]
    )


def provenance(meanings: Mapping[str, str], found: Collection[str]) -> list[str]:
    """The provenance codes the report's settings and metrics give, `found`, each with what it
    means, in the order of `meanings`."""
    return [
        "<h3>Provenance</h3>",
        "<p>Each setting and metric records where its value came from:</p>",
        "<ul>",
        *(
            f"<li>{code(name)}: {meaning}</li>"
            for name, meaning in meanings.items()
            if name in found
        ),
        "</ul>",
    ]


# 5. Cases and attempts


def budget_limit(budget: Budget | PlanBudgetV1_1) -> str:
    """The budget's credits, at Portfolio123's documented cost, with where it's documented."""
    source = budget.credits_per_request_source
    return (
        f"at most {budget.credits} credits at Portfolio123's documented cost"
        f" ({text(source.title)}, checked {source.checked.isoformat()})"
    )


def attempt_counts(attempts: AttemptCounts) -> tuple[str, str]:
    return (
        "Attempts",
        (
            f"{attempts.succeeded} succeeded, {attempts.failed} failed, {attempts.unknown} unknown,"
            f" {attempts.running} running"
        ),
    )


def reported_cost(cost: int | None) -> str:
    """The credits Portfolio123 reported charging, or that it reported none."""
    return "Not reported" if cost is None else f"{cost} credits, as Portfolio123 reported"


def run_written_by(manifest: RunManifest) -> tuple[str, str]:
    """The Trial Folio version and command that wrote a run, and when the command started."""
    return (
        "Run written by",
        (
            f"Trial Folio {text(manifest.trialfolio_version)}, command"
            f" {code(manifest.command.name)}, started {moment(manifest.command.started_at)}"
        ),
    )


def plan_versions(plan: Plan | PlanV1_1) -> list[tuple[str, str]]:
    """The versions a plan records: Trial Folio's, which built it, the provider wrapper's, and
    the transport's."""
    return [
        (
            "Plan built by",
            (
                f"Trial Folio {text(plan.trialfolio_version)}, canonicalization version"
                f" {plan.canonicalization_version}"
            ),
        ),
        ("Provider wrapper", f"<code>p123api</code> {text(plan.provider_wrapper.p123api)}"),
        (
            "Transport",
            (
                f"<code>requests</code> {text(plan.transport.requests)}, <code>urllib3</code>"
                f" {text(plan.transport.urllib3)}"
            ),
        ),
    ]


def rendered_by(version: str) -> tuple[str, str]:
    return ("Report rendered by", f"Trial Folio {version}")


# 10. Conclusion


def reproducibility_limitation(reproducibility: Reproducibility) -> str:
    """Whether every setting is recorded in full, or which name an object in the Portfolio123
    account whose definition wasn't captured."""
    if reproducibility.status != "incomplete":
        return "Reproducibility is complete: every setting is recorded in full."
    unsnapshotted = [
        reference.setting
        for reference in reproducibility.external_references
        if not reference.snapshotted
    ]
    names = " and ".join(code(name) for name in unsnapshotted)
    verb = "names an object" if len(unsnapshotted) == 1 else "name objects"
    return (
        f"Reproducibility is incomplete: {names} {verb} in the Portfolio123 account whose"
        " definition wasn't captured. If it changes, the same configuration can give"
        " different results."
    )


def inferred_defaults(settings: Iterable[Setting]) -> list[str]:
    """The limitation that names the settings whose defaults are inferred, when there are
    any."""
    inferred = [setting.name for setting in settings if "inferred_default" in setting.flags]
    if not inferred:
        return []
    return [
        "Inferred defaults, not reported by Portfolio123: "
        + ", ".join(code(name) for name in inferred)
        + "."
    ]


@dataclass(frozen=True)
class Listed:
    """A file the artifacts table lists, apart from the manifest."""

    path: str
    """Its path in the run's, the review's, or the experiment's directory."""
    role: str
    """Its role, as the report words it."""
    size: int
    artifact_id: str
    result: str = ""
    """In a review, the result it belongs to, as HTML, or nothing."""


def _link(path: str, base: tuple[str, ...] | None) -> str:
    """`path`, a file's path in the run's, the review's, or the experiment's directory, linked by
    its path relative to the report: `base`, the percent-encoded segments from the report's
    directory to that one, then `path`'s own. None names it without a link."""
    if base is None:
        return code(path)
    segments = (*base, *(quote(part, safe="") for part in path.split("/")))
    return f'<a href="{html.escape("/".join(segments))}">{code(path)}</a>'


def artifacts(
    where: str,
    base: tuple[str, ...] | None,
    manifest: tuple[str, str],
    files: Iterable[Listed],
    *,
    results: bool = False,
) -> list[str]:
    """The artifacts table: `manifest`, the manifest's path and its role, then each of `files`,
    each linked as `_link` gives it, with its role, size, and `artifact_id`, and in a review's
    report, `results`, the result it belongs to. `where` says how they're linked."""
    path, role = manifest
    rows = [
        f"<tr><td>{_link(path, base)}</td><td>{role}</td>{'<td></td>' * (3 if results else 2)}</tr>"
    ]
    rows.extend(
        f'<tr><td class="long">{_link(file.path, base)}</td><td>{file.role}</td>'
        + (f"<td>{file.result}</td>" if results else "")
        + f'<td>{file.size}</td><td class="long">{code(file.artifact_id)}</td></tr>'
        for file in files
    )
    heads = ("File", "Role", *(("Result",) if results else ()), "Size, bytes", "artifact_id")
    return [
        f"<p>{where} An <code>artifact_id</code> is the SHA-256 of the file's bytes.</p>",
        *table(heads, rows),
    ]
