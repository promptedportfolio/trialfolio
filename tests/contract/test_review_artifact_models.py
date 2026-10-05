"""The review's artifact models accept what docs/contracts.md describes, and reject what it calls
invalid.

Traces to docs/contracts.md: review output (the review manifest), `differences.csv` and its
differences between screen runs, flag codes, and the JSON summary's version 1.1.0, which release
0.2.0's open questions settled. Each document below is synthetic, and read as a reader reads it:
from JSON text, with `model_validate_json`.
"""

import json
from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from trialfolio.contracts.review_manifest import ReviewManifest
from trialfolio.contracts.summary import JsonSummaryV1_1
from trialfolio.contracts.tables import DIFFERENCES_COLUMNS, DifferencesRow

type Document = dict[str, Any]
type Change = Callable[[Document], object]


def digest(seed: str) -> str:
    return "sha256:" + seed * 32


REVIEW_ID = "6f1c2a3b-4d5e-4f60-8a71-b2c3d4e5f607"
CASE_ID = "case-0123456789abcdef"


def source_record() -> Document:
    return {
        "acquired_at": "2026-10-05T12:00:00Z",
        "format": "review-configuration",
        "format_version": "1.0.0",
        "parser_version": None,
        "provenance": "user_supplied",
        "operation": None,
    }


def artifact(path: str, seed: str, role: str, label: str | None) -> Document:
    return {
        "path": path,
        "artifact_id": digest(seed),
        "size": 100,
        "role": role,
        "schema_version": None if role == "report" else "1.0.0",
        "source": source_record() if role == "configuration" else None,
        "label": label,
    }


def review_manifest() -> Document:
    """Two results: `hold25`, the baseline, with tables, and `hold50`, whose run has none."""
    return {
        "schema_version": "1.0.0",
        "artifact_type": "review",
        "trialfolio_version": "0.2.0",
        "created_at": "2026-10-05T12:00:01Z",
        "review_id": REVIEW_ID,
        "command": {
            "name": "review",
            "options": {"json": False},
            "started_at": "2026-10-05T12:00:00Z",
        },
        "synthetic": False,
        "outcome": "completed",
        "error": None,
        "baseline": "hold25",
        "results": [
            {
                "label": "hold25",
                "run_manifest": digest("a1"),
                "synthetic": False,
                "plan_hash": digest("a2"),
                "case_id": CASE_ID,
                "normalized_tables": True,
                "response": digest("a3"),
            },
            {
                "label": "hold50",
                "run_manifest": digest("b1"),
                "synthetic": False,
                "plan_hash": digest("b2"),
                "case_id": "case-fedcba9876543210",
                "normalized_tables": False,
                "response": None,
            },
        ],
        "artifacts": [
            artifact("configuration.yaml", "c0", "configuration", None),
            artifact("inputs/hold25/manifest.json", "a1", "run_manifest", "hold25"),
            artifact("inputs/hold25/plan.json", "a4", "plan", "hold25"),
            artifact("inputs/hold25/normalized/metrics.csv", "a5", "metrics", "hold25"),
            artifact("inputs/hold25/normalized/settings.csv", "a6", "settings", "hold25"),
            artifact("inputs/hold50/manifest.json", "b1", "run_manifest", "hold50"),
            artifact("inputs/hold50/plan.json", "b4", "plan", "hold50"),
            artifact("normalized/differences.csv", "d0", "differences", None),
            artifact("report.html", "e0", "report", None),
        ],
        "methods": [{"name": "screen-run-differences", "version": 1}],
        "license_id": "LicenseRef-NSPRL-1.0",
        "notice_version": "1.0",
        "capabilities": {
            "return_series": "absent",
            "statistical_validation": "not_assessed",
            "trading_readiness": "not_assessed",
        },
        "counts": {
            "results": 2,
            "settings": {
                "same": 22,
                "intended_change": 1,
                "unexplained_mismatch": 0,
                "unknown": 0,
                "flagged": 0,
            },
            "metrics": {"differenced": 0, "not_comparable": 0, "unavailable": 20, "flagged": 0},
        },
    }


def setting_row() -> Document:
    """`hold50`'s declared change to `max_holdings`."""
    return {
        "label": "hold50",
        "baseline_label": "hold25",
        "kind": "setting",
        "name": "max_holdings",
        "subject": None,
        "category": "strategy",
        "critical": True,
        "baseline_value": "25",
        "value": "50",
        "unit": "count",
        "classification": "intended_change",
        "difference": None,
        "difference_unit": None,
        "difference_decimals": None,
        "reason": None,
        "declared_reason": "Doubling holdings is the change under review.",
        "flagged": False,
        "flags": [],
    }


def metric_row() -> Document:
    """The strategy's annualized return, differenced in percentage points."""
    return {
        "label": "hold50",
        "baseline_label": "hold25",
        "kind": "metric",
        "name": "annualized_return",
        "subject": "strategy",
        "category": None,
        "critical": None,
        "baseline_value": "12.30",
        "value": "12.4",
        "unit": "percent",
        "classification": "differenced",
        "difference": "0.1",
        "difference_unit": "pp",
        "difference_decimals": 1,
        "reason": None,
        "declared_reason": None,
        "flagged": False,
        "flags": [],
    }


def summary() -> Document:
    """A review that completed."""
    return {
        "schema_version": "1.1.0",
        "command": "review",
        "trialfolio_version": "0.2.0",
        "outcome": "completed",
        "exit_code": 0,
        "ids": {"review_id": REVIEW_ID},
        "output_dir": "review/",
        "outputs": {
            "manifest": "manifest.json",
            "report": "report.html",
            "differences": "normalized/differences.csv",
        },
        "counts": {"results": 2, "settings_flagged": 0, "metrics_unavailable": 20, "warnings": 0},
        "statistical_validation": "not_assessed",
        "trading_readiness": "not_assessed",
        "error": None,
    }


VALID: list[tuple[type[BaseModel], Callable[[], Document]]] = [
    (ReviewManifest, review_manifest),
    (DifferencesRow, setting_row),
    (DifferencesRow, metric_row),
    (JsonSummaryV1_1, summary),
]


def changed(build: Callable[[], Document], change: Change) -> Document:
    document = deepcopy(build())
    change(document)
    return document


def accepts(model: type[BaseModel], document: Document) -> None:
    model.model_validate_json(json.dumps(document))


def rejects(model: type[BaseModel], document: Document) -> None:
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(document))


@pytest.mark.parametrize(("model", "build"), VALID, ids=lambda item: getattr(item, "__name__", ""))
def test_documents_round_trip(model: type[BaseModel], build: Callable[[], Document]) -> None:
    """A valid document reads, and writes back as the same JSON."""
    document = build()

    written = model.model_validate_json(json.dumps(document)).model_dump_json()

    assert json.loads(written) == document


@pytest.mark.parametrize(("model", "build"), VALID, ids=lambda item: getattr(item, "__name__", ""))
def test_unknown_fields_are_rejected(model: type[BaseModel], build: Callable[[], Document]) -> None:
    rejects(model, build() | {"unexpected": 1})


# The review manifest


def artifacts_of(document: Document, label: str | None, role: str) -> Document:
    (found,) = (
        item for item in document["artifacts"] if item["label"] == label and item["role"] == role
    )
    return found


def synthetic_demo(document: Document) -> None:
    document["results"][1]["synthetic"] = True
    document["synthetic"] = True


def both_name_one_run(document: Document) -> None:
    """Two results may name the same run, under two labels."""
    second = document["results"][1]
    second.update(
        {key: document["results"][0][key] for key in second if key != "label"},
    )
    document["artifacts"][5:7] = [
        artifact("inputs/hold50/manifest.json", "a1", "run_manifest", "hold50"),
        artifact("inputs/hold50/plan.json", "a4", "plan", "hold50"),
        artifact("inputs/hold50/normalized/metrics.csv", "a5", "metrics", "hold50"),
        artifact("inputs/hold50/normalized/settings.csv", "a6", "settings", "hold50"),
    ]


@pytest.mark.parametrize("change", [synthetic_demo, both_name_one_run])
def test_review_manifest_accepts(change: Change) -> None:
    accepts(ReviewManifest, changed(review_manifest, change))


def remove(document: Document, label: str | None, role: str) -> None:
    document["artifacts"].remove(artifacts_of(document, label, role))


MANIFEST_CHANGES: dict[str, Change] = {
    "synthetic without a synthetic result": lambda d: d.update(synthetic=True),
    "a synthetic result in a review that isn't": lambda d: d["results"][1].update(synthetic=True),
    "failed": lambda d: d.update(outcome="failed"),
    "an error": lambda d: d.update(error={"code": "storage.write_failed", "message": "x"}),
    "baseline not a result": lambda d: d.update(baseline="hold100"),
    "one result": lambda d: d.update(results=d["results"][:1]),
    "a label twice": lambda d: d["results"][1].update(label="hold25"),
    "a device name as a label": lambda d: d["results"][1].update(label="aux"),
    "a plan hash": lambda d: d.update(plan_hash=digest("f0")),
    "an approval": lambda d: d.update(approval="option"),
    "parsers": lambda d: d.update(parsers=[]),
    "reproducibility": lambda d: d.update(reproducibility={}),
    "the configuration's path among the options": lambda d: d["command"]["options"].update(
        config="comparison.yaml"
    ),
    "--out among the options": lambda d: d["command"]["options"].update(out="review/"),
    "no json option": lambda d: d["command"].update(options={}),
    "another command": lambda d: d["command"].update(name="run"),
    "a review_id not in canonical form": lambda d: d.update(review_id=REVIEW_ID.upper()),
    "return series": lambda d: d["capabilities"].update(return_series="source_only"),
    "assessed": lambda d: d["capabilities"].update(trading_readiness="ready"),
    "no method": lambda d: d.update(methods=[]),
    "a method twice": lambda d: d["methods"].append(d["methods"][0]),
    "another method": lambda d: d["methods"][0].update(name="relative-differences"),
    "method version 0": lambda d: d["methods"][0].update(version=0),
    "results miscounted": lambda d: d["counts"].update(results=3),
    "more flagged settings than rows": lambda d: d["counts"]["settings"].update(flagged=24),
    "more flagged metrics than rows": lambda d: d["counts"]["metrics"].update(flagged=21),
    "a path twice": lambda d: d["artifacts"].append(d["artifacts"][-1]),
    "logs listed": lambda d: d["artifacts"].append(
        artifact("logs/trialfolio.jsonl", "f1", "report", None)
    ),
    "its own manifest listed": lambda d: d["artifacts"].append(
        artifact("manifest.json", "f2", "report", None)
    ),
    "a second report": lambda d: d["artifacts"].append(
        artifact("report-2.html", "f3", "report", None)
    ),
    "no differences": lambda d: remove(d, None, "differences"),
    "no configuration": lambda d: remove(d, None, "configuration"),
    "a run's configuration copied": lambda d: d["artifacts"].append(
        artifact("inputs/hold25/configuration.yaml", "f4", "configuration", "hold25")
    ),
    "a copy outside its label's directory": lambda d: artifacts_of(d, "hold50", "plan").update(
        path="inputs/hold25/plan-50.json"
    ),
    "a copy without its label": lambda d: artifacts_of(d, "hold50", "plan").update(label=None),
    "a copy of an unknown result": lambda d: d["artifacts"].append(
        artifact("inputs/hold100/plan.json", "f5", "plan", "hold100")
    ),
    "an own file with a label": lambda d: artifacts_of(d, None, "report").update(label="hold25"),
    "an own file under inputs": lambda d: artifacts_of(d, None, "report").update(
        path="inputs/report.html"
    ),
    "a result without its plan": lambda d: remove(d, "hold50", "plan"),
    "a result without its manifest": lambda d: remove(d, "hold50", "run_manifest"),
    "tables missing from a run that has them": lambda d: remove(d, "hold25", "metrics"),
    "tables for a run that has none": lambda d: d["results"][1].update(normalized_tables=True),
    "run_manifest not the copy's": lambda d: d["results"][0].update(run_manifest=digest("f6")),
    "a copy without its schema version": lambda d: artifacts_of(d, "hold25", "plan").update(
        schema_version=None
    ),
    "a report with a schema version": lambda d: artifacts_of(d, None, "report").update(
        schema_version="1.0.0"
    ),
    "a source record on a copy": lambda d: artifacts_of(d, "hold25", "plan").update(
        source=source_record()
    ),
    "the configuration without its source record": lambda d: artifacts_of(
        d, None, "configuration"
    ).update(source=None),
    "a screen configuration's format": lambda d: artifacts_of(d, None, "configuration")[
        "source"
    ].update(format="screen-configuration"),
    "a parser version": lambda d: artifacts_of(d, None, "configuration")["source"].update(
        parser_version=1
    ),
    "verified provenance": lambda d: artifacts_of(d, None, "configuration")["source"].update(
        provenance="verified"
    ),
    "a provider operation": lambda d: artifacts_of(d, None, "configuration")["source"].update(
        operation="screen_backtest"
    ),
}


@pytest.mark.parametrize("change", MANIFEST_CHANGES.values(), ids=MANIFEST_CHANGES.keys())
def test_review_manifest_rejects(change: Change) -> None:
    rejects(ReviewManifest, changed(review_manifest, change))


# differences.csv


def test_differences_columns_are_in_the_documented_order() -> None:
    assert DIFFERENCES_COLUMNS == (
        "label",
        "baseline_label",
        "kind",
        "name",
        "subject",
        "category",
        "critical",
        "baseline_value",
        "value",
        "unit",
        "classification",
        "difference",
        "difference_unit",
        "difference_decimals",
        "reason",
        "declared_reason",
        "flagged",
        "flags",
    )


def setting(
    name: str, category: str, unit: str | None, baseline: str | None, value: str | None
) -> Change:
    """A setting row of `name`, which the change then classifies."""

    def change(document: Document) -> None:
        document.update(
            name=name,
            category=category,
            critical=category != "other",
            unit=unit,
            baseline_value=baseline,
            value=value,
            declared_reason=None,
        )

    return change


SLIPPAGE = setting("slippage_percent", "costs", "percent", "0.25", "1")
FORMULA = '{"formula": "EarnYield", "lower_is_better": false}'
REORDERED = '{"lower_is_better": false, "formula": "EarnYield"}'
BY_NAME = '{"name": "Synthetic Value Composite"}'
RANKING = setting("ranking", "strategy", None, FORMULA, BY_NAME)
UNIVERSE = setting("universe", "universe", None, "SP500", "SP500")
START = setting("start_date", "dates", None, "2016-01-01", "2016-01-01")
PRECISION = setting("precision", "other", None, "4", "4")


def classified(classification: str, *flags: str) -> Change:
    flagging = {
        "critical_unexplained_mismatch",
        "critical_unknown",
        "intended_change_not_observed",
        "coverage_mismatch",
        "identical_source",
    }
    return lambda d: d.update(
        classification=classification, flags=list(flags), flagged=bool(flagging & set(flags))
    )


def steps(*changes: Change) -> Change:
    def change(document: Document) -> None:
        for step in changes:
            step(document)

    return change


SETTING_ACCEPTS: dict[str, Change] = {
    "an undeclared critical change": steps(
        SLIPPAGE, classified("unexplained_mismatch", "critical_unexplained_mismatch")
    ),
    "the same slippage": steps(SLIPPAGE, lambda d: d.update(value="0.25"), classified("same")),
    "a declared change not observed": steps(
        lambda d: d.update(value="25"), classified("same", "intended_change_not_observed")
    ),
    "a declared change that can't be observed in 1.0.0": steps(
        PRECISION,
        lambda d: d.update(declared_reason="Not yet variable."),
        classified("same", "intended_change_not_observed"),
    ),
    "a ranking by name, which isn't snapshotted": steps(
        RANKING,
        classified("unexplained_mismatch", "not_snapshotted", "critical_unexplained_mismatch"),
    ),
    "a ranking with its keys in another order": steps(
        RANKING, lambda d: d.update(value=REORDERED), classified("same")
    ),
    "a universe, never snapshotted, which doesn't set flagged": steps(
        UNIVERSE, classified("same", "not_snapshotted")
    ),
    "an inferred default, which doesn't set flagged": steps(
        setting("data_vendor", "data_source", None, "FactSet", "FactSet"),
        classified("same", "inferred_default"),
    ),
    "a coverage mismatch on a date": steps(START, classified("same", "coverage_mismatch")),
    "an unknown critical setting": steps(
        SLIPPAGE, lambda d: d.update(value=None), classified("unknown", "critical_unknown")
    ),
    "an unknown setting that isn't critical": steps(
        PRECISION, lambda d: d.update(baseline_value=None), classified("unknown")
    ),
    "a declared change that can't be confirmed": steps(
        lambda d: d.update(value=None), classified("unknown", "critical_unknown")
    ),
}


@pytest.mark.parametrize("change", SETTING_ACCEPTS.values(), ids=SETTING_ACCEPTS.keys())
def test_setting_row_accepts(change: Change) -> None:
    accepts(DifferencesRow, changed(setting_row, change))


SETTING_REJECTS: dict[str, Change] = {
    "the baseline compared with itself": lambda d: d.update(label="hold25"),
    "a device name as a label": lambda d: d.update(label="prn"),
    "an unknown setting": lambda d: d.update(name="max_holding"),
    "another category": lambda d: d.update(category="other", critical=False),
    "critical in category other": steps(
        PRECISION, classified("same"), lambda d: d.update(critical=True)
    ),
    "another unit": lambda d: d.update(unit="percent"),
    "a subject": lambda d: d.update(subject="strategy"),
    "a reason": lambda d: d.update(reason="different_period"),
    "a difference": lambda d: d.update(
        difference="25", difference_unit="count", difference_decimals=0
    ),
    "a metric's classification": lambda d: d.update(classification="differenced"),
    "an invalid value": lambda d: d.update(value="fifty"),
    "a value that isn't normalized": steps(
        SLIPPAGE, lambda d: d.update(value="0.250"), classified("same")
    ),
    "same though the values differ": classified("same"),
    "a change though the values are the same": lambda d: d.update(value="25"),
    "a missing value that isn't unknown": lambda d: d.update(value=None),
    "unknown though both values are known": steps(
        lambda d: d.update(value="25"), classified("unknown", "critical_unknown")
    ),
    "unknown though both values are known, not critical": steps(PRECISION, classified("unknown")),
    "an intended change without its reason": lambda d: d.update(declared_reason=None),
    "a declared reason on a setting that can't be declared": steps(
        setting("commission", "costs", None, "not_modeled", "not_modeled"),
        lambda d: d.update(declared_reason="Commission isn't modeled."),
        classified("same", "intended_change_not_observed"),
    ),
    "a declared reason on a parameter that isn't sent": steps(
        setting("carry_cost", "costs", None, "not_sent", "not_sent"),
        lambda d: d.update(declared_reason="Carry cost isn't sent."),
        classified("same", "intended_change_not_observed"),
    ),
    "a declared change that's unexplained": classified(
        "unexplained_mismatch", "critical_unexplained_mismatch"
    ),
    "an undeclared critical change not flagged": steps(
        SLIPPAGE, classified("unexplained_mismatch")
    ),
    "a critical flag on a change that was declared": classified(
        "intended_change", "critical_unexplained_mismatch"
    ),
    "a change not observed without its flag": steps(
        lambda d: d.update(value="25"), classified("same")
    ),
    "an unknown critical setting not flagged": steps(
        SLIPPAGE, lambda d: d.update(value=None), classified("unknown")
    ),
    "a critical flag on a setting that isn't critical": steps(
        PRECISION, lambda d: d.update(value=None), classified("unknown", "critical_unknown")
    ),
    "a universe without not_snapshotted": steps(UNIVERSE, classified("same")),
    "a ranking by name without not_snapshotted": steps(
        RANKING, classified("unexplained_mismatch", "critical_unexplained_mismatch")
    ),
    "not_snapshotted on a formula ranking": steps(
        RANKING, lambda d: d.update(value=REORDERED), classified("same", "not_snapshotted")
    ),
    "coverage_mismatch on a setting that isn't a date": steps(
        SLIPPAGE, lambda d: d.update(value="0.25"), classified("same", "coverage_mismatch")
    ),
    "identical_source on a setting": classified("intended_change", "identical_source"),
    "flagged without a flag that sets it": steps(
        UNIVERSE, classified("same", "not_snapshotted"), lambda d: d.update(flagged=True)
    ),
    "a flag twice": steps(START, classified("same", "coverage_mismatch", "coverage_mismatch")),
}


@pytest.mark.parametrize("change", SETTING_REJECTS.values(), ids=SETTING_REJECTS.keys())
def test_setting_row_rejects(change: Change) -> None:
    rejects(DifferencesRow, changed(setting_row, change))


def metric(
    name: str, unit: str, baseline: str | None, value: str | None, *difference: object
) -> Change:
    """A metric row of `name`; differenced when `difference` gives the difference, its unit,
    and its decimals."""

    def change(document: Document) -> None:
        given = difference or (None, None, None)
        document.update(
            name=name,
            unit=unit,
            baseline_value=baseline,
            value=value,
            difference=given[0],
            difference_unit=given[1],
            difference_decimals=given[2],
        )

    return change


def not_differenced(classification: str, reason: str | None) -> Change:
    return lambda d: d.update(
        classification=classification,
        reason=reason,
        difference=None,
        difference_unit=None,
        difference_decimals=None,
    )


METRIC_ACCEPTS: dict[str, Change] = {
    "a trailing zero kept": metric("total_return", "percent", "12.25", "12.35", "0.10", "pp", 2),
    "a whole number saved as a float": metric(
        "total_return", "percent", "12.0", "12.46", "0.5", "pp", 1
    ),
    "a zero written without a sign": metric(
        "total_return", "percent", "151.7", "151.68", "0.0", "pp", 1
    ),
    "a negative difference": metric("max_drawdown", "percent", "-20.5", "-22.75", "-2.3", "pp", 1),
    "a ratio": metric("sharpe_ratio", "ratio", "0.85", "0.9", "0.0", "ratio", 1),
    "a count": metric("coverage_periods", "count", "120", "116", "-4", "count", 0),
    "dates, in days": metric("coverage_start", "date", "2016-01-04", "2016-01-07", "3", "days", 0),
    "the benchmark's own metric": lambda d: d.update(subject="benchmark"),
    "a different benchmark": not_differenced("not_comparable", "different_benchmark"),
    "an unknown period": not_differenced("not_comparable", "unknown_period"),
    "a missing value": steps(
        lambda d: d.update(value=None), not_differenced("unavailable", "input_unavailable")
    ),
    "both missing": steps(
        lambda d: d.update(value=None, baseline_value=None),
        not_differenced("unavailable", "input_unavailable"),
    ),
    "an identical source": lambda d: d.update(flags=["identical_source"], flagged=True),
}


@pytest.mark.parametrize("change", METRIC_ACCEPTS.values(), ids=METRIC_ACCEPTS.keys())
def test_metric_row_accepts(change: Change) -> None:
    accepts(DifferencesRow, changed(metric_row, change))


METRIC_REJECTS: dict[str, Change] = {
    "no subject": lambda d: d.update(subject=None),
    "a category": lambda d: d.update(category="strategy", critical=True),
    "a declared reason": lambda d: d.update(declared_reason="Doubling holdings."),
    "a setting's unit": lambda d: d.update(unit="weeks"),
    "no unit": lambda d: d.update(unit=None),
    "a setting's classification": not_differenced("same", None),
    "a value that isn't a decimal": lambda d: d.update(value="12.4%"),
    "a value in exponent notation": lambda d: d.update(value="1.24e1"),
    "a count with decimals": metric("coverage_periods", "count", "120", "116.0", "-4", "count", 0),
    "a date that isn't one": metric(
        "coverage_start", "date", "2016-02-30", "2016-01-07", "3", "days", 0
    ),
    "percent differenced in percent": lambda d: d.update(difference_unit="percent"),
    "dates differenced in dates": metric(
        "coverage_start", "date", "2016-01-04", "2016-01-07", "3", "date", 0
    ),
    "more decimals than the source": lambda d: d.update(difference="0.10", difference_decimals=2),
    "fewer digits than its decimals": lambda d: d.update(difference="0", difference_decimals=1),
    "a count with decimals in its difference": metric(
        "coverage_periods", "count", "120", "116", "-4.0", "count", 1
    ),
    "a signed zero": metric("total_return", "percent", "151.7", "151.68", "-0.0", "pp", 1),
    "a difference in exponent notation": lambda d: d.update(difference="1e-1"),
    "differenced without a difference": lambda d: d.update(difference=None),
    "differenced without its unit": lambda d: d.update(difference_unit=None),
    "differenced with a reason": lambda d: d.update(reason="different_period"),
    "differenced with a missing value": lambda d: d.update(value=None),
    "not comparable with a difference": lambda d: d.update(
        classification="not_comparable", reason="different_benchmark"
    ),
    "not comparable without a reason": not_differenced("not_comparable", None),
    "not comparable for a missing input": not_differenced("not_comparable", "input_unavailable"),
    "not comparable with a value missing": steps(
        lambda d: d.update(value=None), not_differenced("not_comparable", "different_period")
    ),
    "unavailable with both values": not_differenced("unavailable", "input_unavailable"),
    "unavailable for another reason": steps(
        lambda d: d.update(value=None), not_differenced("unavailable", "different_period")
    ),
    "a missing value written as zero": steps(
        lambda d: d.update(value="0"), not_differenced("unavailable", "input_unavailable")
    ),
    "a setting's flag": lambda d: d.update(flags=["not_snapshotted"]),
    "identical_source without flagged": lambda d: d.update(flags=["identical_source"]),
}


@pytest.mark.parametrize("change", METRIC_REJECTS.values(), ids=METRIC_REJECTS.keys())
def test_metric_row_rejects(change: Change) -> None:
    rejects(DifferencesRow, changed(metric_row, change))


# The JSON summary, version 1.1.0


def failed_before_the_claim(document: Document) -> None:
    document.update(
        outcome="failed",
        exit_code=3,
        ids={},
        output_dir=None,
        outputs={},
        counts={"results": 0, "settings_flagged": 0, "metrics_unavailable": 0, "warnings": 0},
        error={"code": "config.invalid", "message": "comparison.yaml isn't valid."},
    )


def failed_after_the_claim(document: Document) -> None:
    document.update(
        outcome="failed",
        exit_code=4,
        outputs={"differences": "normalized/differences.csv"},
        counts={"results": 3, "settings_flagged": 3, "metrics_unavailable": 3, "warnings": 0},
        error={"code": "storage.write_failed", "message": "report.html couldn't be written."},
    )


def a_run(document: Document) -> None:
    document.update(
        command="run",
        ids={"plan_hash": digest("a1"), "case_id": CASE_ID},
        output_dir="runs/hold25",
        outputs={"manifest": "manifest.json"},
        counts={
            "attempts": 1,
            "provider_requests": 1,
            "metrics_unavailable": 0,
            "warnings": 0,
            "cost": 5,
        },
    )


@pytest.mark.parametrize(
    "change",
    [
        failed_before_the_claim,
        failed_after_the_claim,
        a_run,
        lambda d: d.update(command="report", ids={}, counts={}),
    ],
    ids=["failed-before-the-claim", "failed-after-the-claim", "run", "report"],
)
def test_summary_accepts(change: Change) -> None:
    accepts(JsonSummaryV1_1, changed(summary, change))


SUMMARY_REJECTS: dict[str, Change] = {
    "version 1.0.0": lambda d: d.update(schema_version="1.0.0"),
    "a review without its counts": lambda d: d.update(counts={}),
    "a review with a run's counts": lambda d: (a_run(d), d.update(command="review")),
    "a run with a review's counts": lambda d: (a_run(d), d.update(counts=summary()["counts"])),
    "a report with a review's counts": lambda d: d.update(command="report", ids={}),
    "a review_id before the claim": lambda d: (
        failed_before_the_claim(d),
        d.update(ids={"review_id": REVIEW_ID}),
    ),
    "no review_id after the claim": lambda d: d.update(ids={}),
    "a review_id on a run": lambda d: (a_run(d), d["ids"].update(review_id=REVIEW_ID)),
    "a review_id without hyphens": lambda d: d.update(
        ids={"review_id": REVIEW_ID.replace("-", "")}
    ),
    "a review count of another command": lambda d: d["counts"].update(cost=0),
    "a negative count": lambda d: d["counts"].update(settings_flagged=-1),
    "an unknown command": lambda d: d.update(command="experiment"),
}


@pytest.mark.parametrize("change", SUMMARY_REJECTS.values(), ids=SUMMARY_REJECTS.keys())
def test_summary_rejects(change: Change) -> None:
    rejects(JsonSummaryV1_1, changed(summary, change))
