"""The review report's comparison of settings: each result's settings against the baseline's, as
`differences.csv`'s setting rows classify them (release 0.2.0, R02-T07).

- `benchmarks`, in section 1: each result's benchmark, compared with the baseline's.
- `changes`, in section 2: the intended changes, the unexplained mismatches, the unknown
  settings, the settings that are the same, and the baseline's own settings.
- `settings_across`, in section 4: the costs and the implementation assumptions, for each
  result, with what each token means.
"""

from collections.abc import Callable, Sequence
from typing import Final

from trialfolio.contracts.tables import DifferencesRow
from trialfolio.display import series
from trialfolio.report.evidence import ReviewContext
from trialfolio.report.fragments import flag_list, settings_table, unit
from trialfolio.report.page import code, table, text
from trialfolio.report.vocabulary import SYNTHETIC_NOT_SENT, TOKENS

_SETTING_COUNT: Final = 23
"""The screen settings each result's rows compare."""

_COMPARISON_FLAGS: Final = frozenset(
    {"critical_unexplained_mismatch", "critical_unknown", "intended_change_not_observed"}
)
"""The flags a setting row's comparison gives it, rather than its runs' rows."""

_OBSERVED: Final[dict[str, str]] = {
    "intended_change": "Yes: the values differ.",
    "same": "No: the values are equal.",
    "unknown": "Can't be confirmed: the setting is missing from a run.",
    "unexplained_mismatch": "",
}
"""Whether a declared change is observed, by its row's classification."""

_CELLS: Final[dict[str, Callable[[ReviewContext, DifferencesRow], str]]] = {
    "result": lambda review, row: review.name(row.label),
    "setting": lambda review, row: code(row.name),
    "category": lambda review, row: code(row.category or ""),
    "baseline": lambda review, row: _value(row.baseline_value),
    "value": lambda review, row: _value(row.value),
    "unit": lambda review, row: unit(row.unit),
    "reason": lambda review, row: text(row.declared_reason or ""),
    "observed": lambda review, row: _OBSERVED[row.classification],
    "flags": lambda review, row: _flags(row),
}
"""The columns a table of setting rows can have, each with its cell for a row."""

_HEADS: Final = {
    "result": "Result",
    "setting": "Setting",
    "category": "Category",
    "value": "Value",
    "unit": "Unit",
    "reason": "Declared reason",
    "observed": "Observed",
    "flags": "Flags",
}
"""Each column's heading, apart from the baseline's, which names the baseline."""


# 1. Objective


def benchmarks(review: ReviewContext) -> list[str]:
    """Each result's benchmark, compared with the baseline's."""
    rows: list[str] = []
    for checked in review.evidence.inputs:
        label = checked.result.label
        setting = review.settings[label].get("benchmark")
        value = code(setting.value) if setting is not None else "Missing"
        if label == review.baseline:
            comparison = "The baseline's"
        else:
            comparison = _setting_comparison(review.rows[(label, "setting", None, "benchmark")])
        rows.append(f"<tr><td>{review.name(label)}</td><td>{value}</td><td>{comparison}</td></tr>")
    return [
        "<p>Each result's benchmark, compared with the baseline's.</p>",
        *table(("Result", "Benchmark", "Against the baseline"), rows),
    ]


def _setting_comparison(row: DifferencesRow) -> str:
    meanings = {
        "same": "Same",
        "intended_change": "Differs: an intended change",
        "unexplained_mismatch": "Differs: an unexplained mismatch",
        "unknown": "Unknown: missing from a run",
    }
    shown = meanings[row.classification]
    flagged = [flag for flag in row.flags if flag in _COMPARISON_FLAGS]
    if flagged:
        shown += ", flagged " + series([code(flag) for flag in flagged])
    return shown


# 2. Definitions, and changes from the baseline


def changes(review: ReviewContext) -> list[str]:
    """The changes from the baseline: the setting rows each table lists, then the baseline's own
    settings."""
    return [
        *_intended_changes(review),
        *_mismatches(review),
        *_unknown(review),
        *_same(review),
        *_baseline_settings(review),
    ]


def _setting_rows(review: ReviewContext) -> list[DifferencesRow]:
    return [row for row in review.evidence.differences.rows if row.kind == "setting"]


def _change_table(
    review: ReviewContext, rows: Sequence[DifferencesRow], columns: Sequence[str]
) -> list[str]:
    """A table of setting rows, with `columns`, from `_CELLS`. The baseline's column names it,
    so a synthetic baseline's values are marked there too."""
    baseline = f"Baseline value, {review.name(review.baseline)}"
    heads = [_HEADS.get(column, baseline) for column in columns]
    body = [
        "<tr>" + "".join(f"<td>{_CELLS[column](review, row)}</td>" for column in columns) + "</tr>"
        for row in rows
    ]
    return table(heads, body)


def _intended_changes(review: ReviewContext) -> list[str]:
    declared = [row for row in _setting_rows(review) if row.declared_reason is not None]
    parts = [
        "<h3>Intended changes</h3>",
        "<p>The changes each result declares, against the baseline, with its reason.</p>",
    ]
    if not declared:
        return [*parts, "<p>None: no result declares a change.</p>"]
    columns = ("result", "setting", "baseline", "value", "unit", "reason", "observed", "flags")
    return [*parts, *_change_table(review, declared, columns)]


def _mismatches(review: ReviewContext) -> list[str]:
    rows = [row for row in _setting_rows(review) if row.classification == "unexplained_mismatch"]
    parts = [
        "<h3>Unexplained mismatches</h3>",
        (
            "<p>Settings that differ from the baseline's without a declared change. In a"
            " critical category, each is flagged.</p>"
        ),
    ]
    if not rows:
        return [*parts, "<p>None: every setting that differs is declared.</p>"]
    columns = ("result", "setting", "category", "baseline", "value", "unit", "flags")
    return [*parts, *_change_table(review, rows, columns)]


def _unknown(review: ReviewContext) -> list[str]:
    rows = [
        row
        for row in _setting_rows(review)
        if row.classification == "unknown" and row.declared_reason is None
    ]
    if not rows:
        return []
    return [
        "<h3>Unknown settings</h3>",
        "<p>Settings missing from one of the two runs, so they can't be compared.</p>",
        *_change_table(
            review, rows, ("result", "setting", "category", "baseline", "value", "flags")
        ),
    ]


def _same(review: ReviewContext) -> list[str]:
    rows = _setting_rows(review)
    counts = [
        f"{sum(row.label == label and row.classification == 'same' for row in rows)}"
        f" of {_SETTING_COUNT} for {review.name(label)}"
        for label in (checked.result.label for checked in review.others)
    ]
    flagged = [
        row
        for row in rows
        if row.classification == "same" and row.flagged and row.declared_reason is None
    ]
    parts = [
        "<h3>Settings that are the same</h3>",
        f"<p>The settings that read the same as the baseline's: {series(counts)}.</p>",
    ]
    if not flagged:
        return parts
    return [
        *parts,
        "<p>These are the same, but flagged:</p>",
        *_change_table(review, flagged, ("result", "setting", "value", "unit", "flags")),
    ]


def _baseline_settings(review: ReviewContext) -> list[str]:
    checked = next(c for c in review.evidence.inputs if c.result.label == review.baseline)
    expected = checked.run.settings is None
    intro = (
        "Its run has no settings.csv, so these are its plan's resolved settings, each with the"
        " provenance the plan expects it to have once the request is sent."
        if expected
        else "As its settings.csv records them."
    )
    return [
        f"<h3>The baseline's settings, {review.name(review.baseline)}</h3>",
        f"<p>{intro}</p>",
        *settings_table(review.settings[review.baseline].values(), expected=expected, notes=None),
    ]


def _value(value: str | None) -> str:
    return "Missing" if value is None else code(value)


def _flags(row: DifferencesRow) -> str:
    if not row.flags:
        return ""
    flags = flag_list(row.flags)
    return f"<strong>Flagged.</strong> {flags}" if row.flagged else flags


# 4. Results


def settings_across(review: ReviewContext, names: Sequence[str]) -> list[str]:
    """The settings `names`, for each result."""
    rows: list[str] = []
    tokens: set[str] = set()
    for checked in review.evidence.inputs:
        label = checked.result.label
        cells: list[str] = []
        for name in names:
            setting = review.settings[label].get(name)
            if setting is None:
                cells.append("Missing")
                continue
            tokens.add(setting.value)
            cells.append(f"{code(setting.value)} {unit(setting.unit)}".rstrip())
        rows.append(
            f"<tr><td>{review.name(label)}</td>"
            + "".join(f"<td>{cell}</td>" for cell in cells)
            + "</tr>"
        )
    notes = [
        f"<li>{code(token)}: {_token(review, token)}</li>" for token in TOKENS if token in tokens
    ]
    return [
        *table(("Result", *(code(name) for name in names)), rows),
        *(["<ul>", *notes, "</ul>"] if notes else []),
    ]


def _token(review: ReviewContext, token: str) -> str:
    """What a setting's token means. A synthetic result's run sent nothing, so no default of
    Portfolio123's applied to it (DSC-04)."""
    meaning = TOKENS[token]
    if token != "not_sent" or not review.synthetic:
        return meaning
    if review.all_synthetic:
        return SYNTHETIC_NOT_SENT
    one = len(review.synthetic) == 1
    return (
        "Not sent. For a backtested result, Portfolio123's default applies, and it isn't"
        f" documented. For {review.labels(review.synthetic)}, which {'is' if one else 'are'}"
        " synthetic, nothing was sent."
    )
