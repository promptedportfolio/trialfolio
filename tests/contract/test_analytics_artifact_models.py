"""The records and the tables' rows release 0.5.0 adds accept what docs/contracts.md describes,
and reject what it calls invalid.

Traces to release 0.5.0's test pairing, which names this module for the contract tests of the
records and the tables' rows (R05-T05): plans 1.4.0 to 1.7.0 (plans with period splits), which
record the splits with `user_supplied` provenance (R05-AC12); run manifest 1.2.0 (a run 0.5.0
writes) and experiment manifest 1.2.0 (the experiment manifest), whose models refuse a manifest
that lists some of the four tables but not all, or whose `methods` or `return_series` disagree
with its tables (R05-AC13); the report manifest (`trialfolio report`'s output, R05-AC09); and the
rows of `series.csv` (R05-AC01), `analysis.csv`, whose values record that they're calculated, with
the analysis set's version and the Trial Folio version (R05-AC03), and `comparison.csv` (R05-AC05).
And to R05-AC10: a plan or a manifest of a version 0.4.0 writes keeps its shape, and refuses what
0.5.0 adds to it. Each model checks the rules one document shows; whether a table is exactly what
its response, its analysis set, or its comparison gives is the records check's, which R05-T09
builds.

Each plan and manifest is a committed historical fixture, read as JSON, with the change its new
version makes; each row is the hand-checkable example's, from docs/methodology.md. Each is
synthetic, and read as a reader reads it: from JSON text, with `model_validate_json`. Each
rejected document is a valid one changed one way, so it fails for that rule alone.
"""

import json
import re
from copy import deepcopy
from typing import Any, get_args

import pytest
from pydantic import BaseModel

from tests.support.contract_checks import Change, Document, accepts, changed, digest, rejects
from tests.support.paths import FIXTURES, ROOT
from trialfolio.contracts.common import AnalysisUnavailableReason
from trialfolio.contracts.experiment_manifest import (
    ExperimentManifestV1_1,
    ExperimentManifestV1_2,
)
from trialfolio.contracts.experiment_plan import PlanV1_1, PlanV1_3, PlanV1_5, PlanV1_7
from trialfolio.contracts.manifest import RunManifestV1_1, RunManifestV1_2
from trialfolio.contracts.plan import Plan, PlanV1_2, PlanV1_4, PlanV1_6
from trialfolio.contracts.report_manifest import ReportManifest
from trialfolio.contracts.tables import (
    ANALYSIS_COLUMNS,
    ANALYSIS_SET_1_0_0,
    ANALYSIS_SETS,
    COMPARISON_COLUMNS,
    ROLLING_WINDOWS_1_0_0,
    SERIES_COLUMNS,
    AnalysisRow,
    ComparisonRow,
    SeriesRow,
)


def fixture(path: str) -> Document:
    """A committed historical fixture's JSON document, under tests/fixtures/."""
    document: Document = json.loads((FIXTURES / path).read_text(encoding="utf-8"))
    return document


def inserted(document: Document, after: str, key: str, value: object) -> Document:
    """`document` with `key` set to `value` right after `after`, as a model writes its fields."""
    result: Document = {}
    for name, item in document.items():
        result[name] = item
        if name == after:
            result[key] = deepcopy(value)
    return result


# Plans 1.4.0 to 1.7.0

ANALYSIS: Document = {
    "period_splits": [{"date": "2024-01-05", "label": "End of the example's first week"}]
}

PLANS: dict[str, tuple[type[BaseModel], type[BaseModel], str, str]] = {
    "1.4.0": (PlanV1_4, Plan, "runs/synthetic-run-1.0.0/plan.json", "purpose"),
    "1.5.0": (
        PlanV1_5,
        PlanV1_1,
        "experiments/synthetic-experiment-1.0.0/plans/1/plan.json",
        "prior_research",
    ),
    "1.6.0": (PlanV1_6, PlanV1_2, "runs/synthetic-run-1.1.0/plan.json", "ranking_source"),
    "1.7.0": (
        PlanV1_7,
        PlanV1_3,
        "experiments/synthetic-experiment-1.1.0/plans/1/plan.json",
        "ranking_source",
    ),
}
"""Each plan with splits: its model, the model of the plan without splits beside it, a committed
plan of that version, and the field `analysis` follows (plans with period splits)."""


def split_plan(version: str) -> Document:
    """The committed plan beside `version`, with the hand-checkable split, as that version."""
    _, _, path, after = PLANS[version]
    document = inserted(fixture(path), after, "analysis", ANALYSIS)
    document["schema_version"] = version
    return document


@pytest.mark.parametrize("version", PLANS)
def test_a_plan_with_splits_is_its_version_s_plan_with_analysis(version: str) -> None:
    model, earlier, path, after = PLANS[version]
    document = split_plan(version)

    plan = model.model_validate_json(json.dumps(document))

    written = plan.model_dump(mode="json")
    assert written == document
    assert list(written) == list(document)
    fields = list(earlier.model_fields)
    assert list(model.model_fields) == [
        *fields[: fields.index(after) + 1],
        "analysis",
        *fields[fields.index(after) + 1 :],
    ]
    assert earlier.model_validate_json((FIXTURES / path).read_text(encoding="utf-8"))


@pytest.mark.parametrize("version", PLANS)
def test_a_plan_without_splits_keeps_its_shape(version: str) -> None:
    """A plan of a version 0.4.0 writes has no `analysis`, so a configuration without splits gives
    the plan it gave."""
    _, earlier, path, after = PLANS[version]

    rejects(earlier, inserted(fixture(path), after, "analysis", ANALYSIS))


def splits(*splits: tuple[str, str]) -> Change:
    def change(document: Document) -> None:
        document["analysis"]["period_splits"] = [
            {"date": when, "label": label} for when, label in splits
        ]

    return change


def split_changed(**field: object) -> Change:
    def change(document: Document) -> None:
        document["analysis"]["period_splits"][0].update(field)

    return change


INVALID_ANALYSES: dict[str, Change] = {
    "analysis missing": lambda d: d.pop("analysis"),
    "analysis null": lambda d: d.update(analysis=None),
    "no split": splits(),
    "eleven splits": splits(*((f"2024-01-{day:02d}", f"Split {day}") for day in range(1, 12))),
    "dates equal": splits(("2024-01-05", "First"), ("2024-01-05", "Second")),
    "dates decreasing": splits(("2024-01-05", "First"), ("2024-01-04", "Second")),
    "labels equal": splits(("2024-01-05", "First"), ("2024-01-08", "First")),
    "date not YYYY-MM-DD": split_changed(date="2024-1-5"),
    "date not a calendar date": split_changed(date="2024-02-30"),
    "date with a time": split_changed(date="2024-01-05T00:00:00Z"),
    "label blank": split_changed(label=" \t"),
    "label too long": split_changed(label="a" * 201),
    "split with another key": split_changed(provenance="user_supplied"),
    "analysis with another key": lambda d: d["analysis"].update(windows=[7]),
}


@pytest.mark.parametrize("version", PLANS)
@pytest.mark.parametrize("case", INVALID_ANALYSES)
def test_a_plan_with_splits_rejects_splits_that_break_a_rule(version: str, case: str) -> None:
    rejects(PLANS[version][0], changed(lambda: split_plan(version), INVALID_ANALYSES[case]))


@pytest.mark.parametrize("version", PLANS)
def test_a_plan_with_splits_accepts_ten_and_labels_that_differ_in_case(version: str) -> None:
    ten = splits(*((f"2024-01-{day:02d}", f"split {day}") for day in range(1, 11)))
    cased = splits(("2012-12-31", "Publication"), ("2016-06-30", "publication"))

    for change in (ten, cased):
        accepts(PLANS[version][0], changed(lambda: split_plan(version), change))


def duplicated_category(document: Document) -> None:
    document["data_sent"][1] = deepcopy(document["data_sent"][0])


def revises_itself(document: Document) -> None:
    document["revises"] = document["plan_hash"]


KEPT_RULES: dict[str, Change] = {
    "1.4.0": duplicated_category,
    "1.5.0": revises_itself,
    "1.6.0": lambda d: d["ranking_source"].update(definition=digest("0f")),
    "1.7.0": lambda d: d["ranking_source"].update(definition=digest("0f")),
}
"""A change each plan's version beside it refuses, one of its consistency rules."""


@pytest.mark.parametrize("version", PLANS)
def test_a_plan_with_splits_keeps_its_version_s_rules(version: str) -> None:
    model, earlier, path, _ = PLANS[version]

    rejects(model, changed(lambda: split_plan(version), KEPT_RULES[version]))
    rejects(earlier, changed(lambda: fixture(path), KEPT_RULES[version]))


# Run manifest 1.2.0

TABLE_ID = digest("5e")
METHOD = {"name": "analysis-set", "version": "1.0.0"}
COMPARISON = {"name": "baseline-comparison", "version": 1}


def table(path: str, role: str, schema_version: str | None = "1.0.0") -> Document:
    return {
        "path": path,
        "artifact_id": TABLE_ID,
        "size": 1024,
        "role": role,
        "schema_version": schema_version,
        "source": None,
    }


def run_manifest_1_2(base: str = "runs/synthetic-run-1.1.0/manifest.json") -> Document:
    """A committed run manifest, as a run 0.5.0 writes it: with `series.csv` and `analysis.csv`
    after `settings.csv`, `return_series` `normalized`, and `methods` after `parsers`."""
    document = inserted(fixture(base), "parsers", "methods", [METHOD])
    document["schema_version"] = "1.2.0"
    artifacts = document["artifacts"]
    after = next(i for i, artifact in enumerate(artifacts) if artifact["role"] == "settings") + 1
    artifacts[after:after] = [
        table("normalized/series.csv", "series"),
        table("normalized/analysis.csv", "analysis"),
    ]
    document["capabilities"]["return_series"] = "normalized"
    return document


def without_tables(document: Document) -> None:
    tables = ("metrics", "settings", "series", "analysis")
    document["artifacts"] = [a for a in document["artifacts"] if a["role"] not in tables]
    document["capabilities"]["return_series"] = "source_only"
    document["methods"] = []


def without_role(role: str) -> Change:
    def change(document: Document) -> None:
        document["artifacts"] = [a for a in document["artifacts"] if a["role"] != role]

    return change


def artifact_of(role: str, change: Change) -> Change:
    def changed_artifact(document: Document) -> None:
        (artifact,) = (a for a in document["artifacts"] if a["role"] == role)
        change(artifact)

    return changed_artifact


def test_run_manifest_1_2_0_accepts_a_run_with_its_four_tables() -> None:
    for base in (
        "runs/synthetic-run-1.1.0/manifest.json",
        "runs/synthetic-run-1.0.0/manifest.json",
    ):
        document = run_manifest_1_2(base)

        manifest = RunManifestV1_2.model_validate_json(json.dumps(document))

        assert manifest.model_dump(mode="json") == document
        fields = list(RunManifestV1_1.model_fields)
        assert list(RunManifestV1_2.model_fields) == [
            *fields[: fields.index("parsers") + 1],
            "methods",
            *fields[fields.index("parsers") + 1 :],
        ]


def test_run_manifest_1_2_0_accepts_a_run_without_tables() -> None:
    accepts(RunManifestV1_2, changed(run_manifest_1_2, without_tables))
    accepts(
        RunManifestV1_2,
        changed(
            run_manifest_1_2,
            lambda d: (without_tables(d), d["capabilities"].update(return_series="absent")),
        ),
    )


RESPONSE_SOURCE: Document = next(
    artifact["source"]
    for artifact in fixture("runs/synthetic-run-1.1.0/manifest.json")["artifacts"]
    if artifact["role"] == "provider_response"
)
"""The committed run's response's source record."""

INVALID_RUN_MANIFESTS: dict[str, Change] = {
    "three of the four tables": without_role("analysis"),
    "a table at another path": artifact_of("series", lambda a: a.update(path="series.csv")),
    "a table without its schema version": artifact_of(
        "analysis", lambda a: a.update(schema_version=None)
    ),
    "tables and return_series source_only": lambda d: d["capabilities"].update(
        return_series="source_only"
    ),
    "normalized without tables": lambda d: (
        without_tables(d),
        d["capabilities"].update(return_series="normalized"),
    ),
    "tables without methods": lambda d: d.update(methods=[]),
    "the analysis set without tables": lambda d: (without_tables(d), d.update(methods=[METHOD])),
    "baseline-comparison": lambda d: d.update(methods=[METHOD, COMPARISON]),
    "two analysis sets": lambda d: d.update(methods=[METHOD, {**METHOD, "version": "1.1.0"}]),
    "the analysis set's version not a version": lambda d: d.update(
        methods=[{**METHOD, "version": "1.0"}]
    ),
    "methods missing": lambda d: d.pop("methods"),
    "a comparison": lambda d: d["artifacts"].append(
        table("normalized/comparison.csv", "comparison")
    ),
    "a response without its source record": artifact_of(
        "provider_response", lambda a: a.update(source=None)
    ),
    "a table with a source record": artifact_of(
        "series", lambda a: a.update(source=RESPONSE_SOURCE)
    ),
    "a log": lambda d: d["artifacts"].append(table("logs/trialfolio.log", "plan", None)),
}


@pytest.mark.parametrize("case", INVALID_RUN_MANIFESTS)
def test_run_manifest_1_2_0_rejects_tables_and_methods_that_disagree(case: str) -> None:
    rejects(RunManifestV1_2, changed(run_manifest_1_2, INVALID_RUN_MANIFESTS[case]))


def test_run_manifest_1_1_0_keeps_its_shape() -> None:
    """A run manifest 0.4.0 wrote has no role for the new tables, and no `methods`."""
    document = fixture("runs/synthetic-run-1.1.0/manifest.json")
    document["artifacts"].append(table("normalized/series.csv", "series"))

    rejects(RunManifestV1_1, document)
    rejects(
        RunManifestV1_1,
        inserted(fixture("runs/synthetic-run-1.1.0/manifest.json"), "parsers", "methods", []),
    )


# Experiment manifest 1.2.0

SESSION_2 = "experiments/synthetic-experiment-1.1.0/sessions/2/manifest.json"


def experiment_manifest_1_2(base: str = SESSION_2) -> Document:
    """A committed session's manifest, as a session 0.5.0 runs writes it: each case's
    `series.csv` and `analysis.csv` after its `settings.csv`, the session's `comparison.csv`
    before its report, `return_series` `normalized`, and `methods` after `parsers`."""
    document = inserted(fixture(base), "parsers", "methods", [METHOD, COMPARISON])
    document["schema_version"] = "1.2.0"
    artifacts: list[Document] = []
    for artifact in document["artifacts"]:
        if artifact["role"] == "report":
            session = artifact["path"].rsplit("/", 1)[0]
            artifacts.append(table(f"{session}/normalized/comparison.csv", "comparison"))
        artifacts.append(artifact)
        if artifact["role"] == "settings":
            case = artifact["path"].rsplit("/", 1)[0]
            artifacts.append(table(f"{case}/series.csv", "series"))
            artifacts.append(table(f"{case}/analysis.csv", "analysis"))
    document["artifacts"] = artifacts
    document["capabilities"]["return_series"] = "normalized"
    return document


def first_of(role: str, change: Change) -> Change:
    def changed_artifact(document: Document) -> None:
        artifact = next(a for a in document["artifacts"] if a["role"] == role)
        change(artifact)

    return changed_artifact


def without_first(role: str) -> Change:
    def change(document: Document) -> None:
        artifacts = document["artifacts"]
        artifacts.remove(next(a for a in artifacts if a["role"] == role))

    return change


def without_case_tables(document: Document) -> None:
    tables = ("metrics", "settings", "series", "analysis")
    document["artifacts"] = [a for a in document["artifacts"] if a["role"] not in tables]
    document["capabilities"]["return_series"] = "source_only"
    document["methods"] = [COMPARISON]


def test_experiment_manifest_1_2_0_accepts_a_session_with_its_tables() -> None:
    for base in (SESSION_2, "experiments/synthetic-experiment-1.0.0/sessions/2/manifest.json"):
        document = experiment_manifest_1_2(base)

        manifest = ExperimentManifestV1_2.model_validate_json(json.dumps(document))

        assert manifest.model_dump(mode="json") == document


def test_experiment_manifest_1_2_0_accepts_cases_of_two_analysis_sets_and_none() -> None:
    """A revision for a new Trial Folio version keeps the cases an earlier one calculated, so a
    session can show two analysis sets; and a session whose cases have no tables still writes
    its comparison."""
    two = [METHOD, {**METHOD, "version": "1.1.0"}, COMPARISON]
    # Versions sort by their numbers, not as text: 1.9.0 comes before 1.10.0.
    numbers = [{**METHOD, "version": "1.9.0"}, {**METHOD, "version": "1.10.0"}, COMPARISON]

    for methods in (two, numbers):
        accepts(
            ExperimentManifestV1_2,
            changed(experiment_manifest_1_2, lambda d, m=methods: d.update(methods=m)),
        )
    accepts(ExperimentManifestV1_2, changed(experiment_manifest_1_2, without_case_tables))


INVALID_EXPERIMENT_MANIFESTS: dict[str, Change] = {
    "a case without its series.csv": without_first("series"),
    "no comparison.csv": without_role("comparison"),
    "another session's comparison.csv": artifact_of(
        "comparison", lambda a: a.update(path="sessions/1/normalized/comparison.csv")
    ),
    "a comparison.csv in a case's directory": artifact_of(
        "comparison",
        lambda a: a.update(path="cases/case-6f5dfa46755878ed/normalized/comparison.csv"),
    ),
    "a table without its schema version": first_of(
        "series", lambda a: a.update(schema_version=None)
    ),
    "tables and return_series source_only": lambda d: d["capabilities"].update(
        return_series="source_only"
    ),
    "normalized without tables": lambda d: (
        without_case_tables(d),
        d["capabilities"].update(return_series="normalized"),
    ),
    "no baseline-comparison": lambda d: d.update(methods=[METHOD]),
    "baseline-comparison first": lambda d: d.update(methods=[COMPARISON, METHOD]),
    "analysis sets out of order": lambda d: d.update(
        methods=[{**METHOD, "version": "1.1.0"}, METHOD, COMPARISON]
    ),
    "analysis sets in the order of their text": lambda d: d.update(
        methods=[{**METHOD, "version": "1.10.0"}, {**METHOD, "version": "1.9.0"}, COMPARISON]
    ),
    "an analysis set twice": lambda d: d.update(methods=[METHOD, METHOD, COMPARISON]),
    "the analysis set without tables": lambda d: (
        without_case_tables(d),
        d.update(methods=[METHOD, COMPARISON]),
    ),
    "baseline-comparison's version as text": lambda d: d.update(
        methods=[METHOD, {**COMPARISON, "version": "1"}]
    ),
    "baseline-comparison's version 0": lambda d: d.update(
        methods=[METHOD, {**COMPARISON, "version": 0}]
    ),
}


@pytest.mark.parametrize("case", INVALID_EXPERIMENT_MANIFESTS)
def test_experiment_manifest_1_2_0_rejects_tables_and_methods_that_disagree(case: str) -> None:
    rejects(
        ExperimentManifestV1_2, changed(experiment_manifest_1_2, INVALID_EXPERIMENT_MANIFESTS[case])
    )


def test_experiment_manifest_1_1_0_keeps_its_shape() -> None:
    document = fixture(SESSION_2)
    document["artifacts"].append(table("sessions/2/normalized/comparison.csv", "comparison"))

    rejects(ExperimentManifestV1_1, document)


# The report manifest

PARSER = {"layout": "p123api-screen-backtest", "layout_version": 1, "parser_version": 1}
CASES = ("case-e29404ddebf86363", "case-0492159b4461ceff")


def report(path: str = "report.html") -> Document:
    return {
        "path": path,
        "artifact_id": digest("4d"),
        "size": 2048,
        "role": "report",
        "schema_version": None,
    }


def report_table(path: str, role: str) -> Document:
    document = table(path, role)
    document.pop("source")
    return document


def run_report_manifest() -> Document:
    """The report manifest of `trialfolio report` of a run an earlier version wrote: the report,
    then the two tables it calculated."""
    return {
        "schema_version": "1.0.0",
        "artifact_type": "report",
        "trialfolio_version": "0.5.0",
        "synthetic": True,
        "input": {
            "artifact_type": "run",
            "manifest": digest("1a"),
            "plan_hash": digest("2b"),
            "experiment_id": None,
            "session": None,
        },
        "artifacts": [
            report(),
            report_table("normalized/series.csv", "series"),
            report_table("normalized/analysis.csv", "analysis"),
        ],
        "parsers": [PARSER],
        "methods": [METHOD],
        "license_id": "LicenseRef-NSPRL-1.1",
        "notice_version": "1.0",
        "capabilities": {
            "return_series": "normalized",
            "statistical_validation": "not_assessed",
            "trading_readiness": "not_assessed",
        },
    }


def experiment_report_manifest() -> Document:
    """The report manifest of `trialfolio report` of an experiment an earlier version wrote: the
    report, each planned case's two tables, then the comparison."""
    document = run_report_manifest()
    document["input"].update(
        artifact_type="experiment", experiment_id="synthetic-earnyield", session=2
    )
    document["artifacts"] = [
        report(),
        *(
            report_table(f"cases/{case}/normalized/{name}.csv", name)
            for case in CASES
            for name in ("series", "analysis")
        ),
        report_table("normalized/comparison.csv", "comparison"),
    ]
    document["methods"] = [METHOD, COMPARISON]
    return document


def report_only(document: Document) -> None:
    """The output of a run or an experiment with its own tables: the report alone."""
    document["artifacts"] = [report()]
    document["parsers"] = []
    document["capabilities"]["return_series"] = "absent"


def test_the_report_manifest_accepts_a_run_s_and_an_experiment_s_output() -> None:
    for build in (run_report_manifest, experiment_report_manifest):
        document = build()

        manifest = ReportManifest.model_validate_json(json.dumps(document))

        assert manifest.model_dump(mode="json") == document
        accepts(ReportManifest, changed(build, report_only))
    # A run whose result has no tables shows no analysis set.
    accepts(
        ReportManifest,
        changed(run_report_manifest, lambda d: (report_only(d), d.update(methods=[]))),
    )
    # An experiment's output with the comparison alone: its cases had their own tables.
    accepts(
        ReportManifest,
        changed(
            experiment_report_manifest,
            lambda d: (
                report_only(d),
                d["artifacts"].append(report_table("normalized/comparison.csv", "comparison")),
            ),
        ),
    )


INVALID_REPORT_MANIFESTS: dict[str, tuple[Any, Change]] = {
    "no report": (run_report_manifest, lambda d: d["artifacts"].pop(0)),
    "the report after a table": (
        run_report_manifest,
        lambda d: d["artifacts"].append(d["artifacts"].pop(0)),
    ),
    "the report with a schema version": (
        run_report_manifest,
        lambda d: d["artifacts"][0].update(schema_version="1.0.0"),
    ),
    "the report elsewhere": (
        run_report_manifest,
        lambda d: d["artifacts"][0].update(path="normalized/report.html"),
    ),
    "a table without its schema version": (
        run_report_manifest,
        lambda d: d["artifacts"][1].update(schema_version=None),
    ),
    "a run's tables in a case's directory": (
        run_report_manifest,
        lambda d: [
            artifact.update(path=f"cases/{CASES[0]}/{artifact['path']}")
            for artifact in d["artifacts"][1:]
        ],
    ),
    "an experiment's case's tables in normalized/": (
        experiment_report_manifest,
        lambda d: [
            artifact.update(path=artifact["path"].removeprefix(f"cases/{CASES[0]}/"))
            for artifact in d["artifacts"][1:3]
        ],
    ),
    "a run's comparison": (
        run_report_manifest,
        lambda d: d["artifacts"].append(report_table("normalized/comparison.csv", "comparison")),
    ),
    "a series without its analysis": (run_report_manifest, lambda d: d["artifacts"].pop(2)),
    "a parser without a series": (
        run_report_manifest,
        lambda d: (report_only(d), d.update(parsers=[PARSER])),
    ),
    "a series without its parser": (run_report_manifest, lambda d: d.update(parsers=[])),
    "normalized without a series": (
        run_report_manifest,
        lambda d: (report_only(d), d["capabilities"].update(return_series="normalized")),
    ),
    "a series and return_series absent": (
        run_report_manifest,
        lambda d: d["capabilities"].update(return_series="absent"),
    ),
    "an analysis.csv without the analysis set": (
        run_report_manifest,
        lambda d: d.update(methods=[]),
    ),
    "a run's baseline-comparison": (
        run_report_manifest,
        lambda d: d.update(methods=[METHOD, COMPARISON]),
    ),
    "an experiment without baseline-comparison": (
        experiment_report_manifest,
        lambda d: d.update(methods=[METHOD]),
    ),
    "a run's two analysis sets": (
        run_report_manifest,
        lambda d: d.update(methods=[METHOD, {**METHOD, "version": "1.1.0"}]),
    ),
    "a run with an experiment_id": (
        run_report_manifest,
        lambda d: d["input"].update(experiment_id="synthetic-earnyield"),
    ),
    "an experiment without its session": (
        experiment_report_manifest,
        lambda d: d["input"].update(session=None),
    ),
    "a time": (run_report_manifest, lambda d: d.update(created_at="2026-11-05T00:00:00Z")),
    "a path to the input": (
        run_report_manifest,
        lambda d: d["input"].update(path="runs/synthetic-run-1.0.0"),
    ),
    "the input's files": (
        run_report_manifest,
        lambda d: d["artifacts"].append(report_table("normalized/metrics.csv", "metrics")),
    ),
}


@pytest.mark.parametrize("case", INVALID_REPORT_MANIFESTS)
def test_the_report_manifest_rejects_what_its_output_doesn_t_hold(case: str) -> None:
    build, change = INVALID_REPORT_MANIFESTS[case]

    rejects(ReportManifest, changed(build, change))


# series.csv

CASE = "case-e29404ddebf86363"
RESPONSE = digest("3c")


def daily(**fields: object) -> Document:
    """The strategy's level on 2024-01-02, the example's second `chart` entry."""
    row: Document = {
        "label": CASE,
        "series": "daily",
        "subject": "strategy",
        "date": "2024-01-02",
        "period_start": None,
        "value": "102",
        "unit": "index",
        "source_decimals": 0,
        "availability": "available",
        "unavailable_reason": None,
        "origin": "reported",
        "provenance": "verified",
        "source_label": "screenReturns",
        "source_artifact": RESPONSE,
        "source_location": "chart.screenReturns[1]",
    }
    return {**row, **fields}


def period(**fields: object) -> Document:
    """The example's first period's excess, the second of `results.rows`, which gives the
    newest first."""
    row = daily(
        series="period",
        subject="excess",
        date="2024-01-08",
        period_start="2024-01-01",
        value="-1",
        unit="percent",
        source_label="Excess%",
        source_location="results.rows[1][4]",
    )
    return {**row, **fields}


UNAVAILABLE_DAILY: Document = {
    "date": None,
    "value": None,
    "source_decimals": None,
    "availability": "unavailable",
    "source_location": None,
}

VALID_SERIES_ROWS: dict[str, Document] = {
    "a strategy level": daily(),
    "a benchmark level, with digits": daily(
        subject="benchmark",
        value="101.0432",
        source_decimals=4,
        source_label="benchReturns",
        source_location="chart.benchReturns[1]",
    ),
    "a daily series without a chart": daily(
        **UNAVAILABLE_DAILY, unavailable_reason="blank_in_source"
    ),
    "a daily series that can't be read": daily(
        **UNAVAILABLE_DAILY, unavailable_reason="unparseable_in_source"
    ),
    "a daily series that isn't daily": daily(**UNAVAILABLE_DAILY, unavailable_reason="not_daily"),
    "a period's excess": period(),
    "a period's strategy return": period(
        subject="strategy", value="10.0000", source_decimals=4, source_label="Ret%"
    ),
    "a null return, keeping its place": period(
        value=None,
        source_decimals=None,
        availability="unavailable",
        unavailable_reason="blank_in_source",
    ),
    "a missing column's return, keeping its dates": period(
        value=None,
        source_decimals=None,
        availability="unavailable",
        unavailable_reason="blank_in_source",
        source_location=None,
    ),
    "a period whose date can't be read": period(
        date=None,
        value=None,
        source_decimals=None,
        availability="unavailable",
        unavailable_reason="unparseable_in_source",
    ),
    "no period": period(
        date=None,
        period_start=None,
        value=None,
        source_decimals=None,
        availability="unavailable",
        unavailable_reason="blank_in_source",
        source_location=None,
    ),
}


@pytest.mark.parametrize("case", VALID_SERIES_ROWS)
def test_series_row_accepts_each_value_and_each_unavailable_one(case: str) -> None:
    accepts(SeriesRow, VALID_SERIES_ROWS[case])


INVALID_SERIES_ROWS: dict[str, Document] = {
    "digits other than source_decimals": daily(source_decimals=1),
    "a value in exponent notation": daily(value="1.02e2"),
    "an available value without its date": daily(date=None),
    "an available value without its location": daily(source_location=None),
    "a level of 0": daily(value="0"),
    "a negative level": daily(value="-1"),
    "a daily row's excess": daily(subject="excess"),
    "a daily row in percent": daily(unit="percent"),
    "a daily row with a period_start": daily(period_start="2024-01-01"),
    "the strategy's level from benchReturns": daily(source_label="benchReturns"),
    "the strategy's level at benchReturns": daily(source_location="chart.benchReturns[1]"),
    "a level at a period's cell": daily(source_location="results.rows[0][2]"),
    "an unavailable daily row with a date": daily(
        **{**UNAVAILABLE_DAILY, "date": "2024-01-02"}, unavailable_reason="not_daily"
    ),
    "an unavailable daily row with a location": daily(
        **{**UNAVAILABLE_DAILY, "source_location": "chart.screenReturns[1]"},
        unavailable_reason="blank_in_source",
    ),
    "an unavailable value with its digits": daily(
        **{**UNAVAILABLE_DAILY, "source_decimals": 0}, unavailable_reason="blank_in_source"
    ),
    "an unavailable value without its reason": daily(**UNAVAILABLE_DAILY),
    "an available value with a reason": daily(unavailable_reason="blank_in_source"),
    "an available value that's empty": daily(
        value=None, source_decimals=None, date=None, source_location=None
    ),
    "a period row in index": period(unit="index"),
    "a period row not_daily": period(
        value=None, source_decimals=None, availability="unavailable", unavailable_reason="not_daily"
    ),
    "the excess from Ret%": period(source_label="Ret%"),
    "a period's return at a chart entry": period(source_location="chart.screenReturns[0]"),
    "an available period without its period_start": period(period_start=None),
    "a location that isn't a JSON path": period(source_location="results.rows[1].4"),
    "a calculated value": daily(origin="calculated"),
    "an inferred value": daily(provenance="inferred"),
    "a calculated reason": daily(**UNAVAILABLE_DAILY, unavailable_reason="input_unavailable"),
}


@pytest.mark.parametrize("case", INVALID_SERIES_ROWS)
def test_series_row_rejects_what_series_csv_calls_invalid(case: str) -> None:
    rejects(SeriesRow, INVALID_SERIES_ROWS[case])


# analysis.csv


def analysis_row(**fields: object) -> Document:
    """The `full` segment's strategy's maximum drawdown in the example, −4.8077, from 01-04 to
    01-05, which Portfolio123 reported as −4.8078, which agrees."""
    row: Document = {
        "label": CASE,
        "analysis_set": "1.0.0",
        "segment": "full",
        "analysis": "max_drawdown",
        "subject": "strategy",
        "window_days": None,
        "value": "-4.8077",
        "unit": "percent",
        "decimals": 4,
        "availability": "available",
        "unavailable_reason": None,
        "observations": 10,
        "period_start": "2024-01-04",
        "period_end": "2024-01-05",
        "reported_value": "-4.8078",
        "reconciliation": "agrees",
        "flags": [],
        "inputs": ["daily/strategy"],
        "origin": "calculated",
        "provenance": "inferred",
        "trialfolio_version": "0.5.0",
        "source_artifact": RESPONSE,
    }
    return {**row, **fields}


NOT_RECONCILED: Document = {"reported_value": None, "reconciliation": None}
UNAVAILABLE: Document = {
    "value": None,
    "decimals": None,
    "availability": "unavailable",
    "period_start": None,
    "period_end": None,
}


def rolling(name: str = "rolling_mean", **fields: object) -> Document:
    """The strategy's 7-day rolling mean in the example: 2.8258, over 5 windows."""
    row = analysis_row(
        analysis=name,
        window_days=7,
        value="2.8258",
        observations=5,
        period_start="2024-01-01",
        period_end="2024-01-12",
        flags=["overlapping_windows"],
        **NOT_RECONCILED,
    )
    return {**row, **fields}


VALID_ANALYSIS_ROWS: dict[str, Document] = {
    "a reconciled value that agrees": analysis_row(),
    "a reconciled value that differs": analysis_row(
        reported_value="-4.8079", reconciliation="differs"
    ),
    "a reconciled value too short to annualize": analysis_row(
        **UNAVAILABLE,
        analysis="annualized_return",
        unavailable_reason="too_short",
        reported_value="10.0000",
        reconciliation="not_compared",
    ),
    "a reported metric that's unavailable": analysis_row(
        reported_value=None, reconciliation="not_compared"
    ),
    "a difference whose input is unavailable": analysis_row(
        **UNAVAILABLE,
        **NOT_RECONCILED,
        analysis="annualized_return_difference",
        subject="excess",
        unit="pp",
        unavailable_reason="input_unavailable",
        observations=None,
        inputs=["daily/strategy", "daily/benchmark"],
    ),
    "a split segment's drawdown, not reconciled": analysis_row(segment="split-0", **NOT_RECONCILED),
    "a descriptive value": analysis_row(
        **NOT_RECONCILED,
        analysis="tracking_error",
        subject="excess",
        value="7.7782",
        observations=2,
        period_start="2024-01-01",
        period_end="2024-01-12",
        flags=["descriptive"],
        inputs=["period/excess"],
    ),
    "a descriptive value that isn't applicable": analysis_row(
        **UNAVAILABLE,
        **NOT_RECONCILED,
        analysis="excess_t_value",
        subject="excess",
        unit="ratio",
        unavailable_reason="not_applicable",
        observations=2,
        flags=["descriptive"],
        inputs=["period/excess"],
    ),
    "a count of periods": analysis_row(
        **NOT_RECONCILED,
        analysis="period_count",
        subject=None,
        value="2",
        unit="count",
        decimals=0,
        observations=2,
        period_start="2024-01-01",
        period_end="2024-01-12",
        inputs=["period"],
    ),
    "a split segment's share of the coverage": analysis_row(
        **NOT_RECONCILED,
        segment="split-0",
        analysis="coverage_share",
        subject=None,
        value="36.3636",
        observations=None,
        period_start="2024-01-01",
        period_end="2024-01-05",
        inputs=[],
    ),
    "a recovery's date": analysis_row(
        **NOT_RECONCILED,
        analysis="max_drawdown_recovery",
        value="2024-01-10",
        unit="date",
        decimals=None,
        period_start=None,
        period_end=None,
    ),
    "a drawdown that doesn't recover": analysis_row(
        **UNAVAILABLE,
        **NOT_RECONCILED,
        segment="split-0",
        analysis="max_drawdown_recovery",
        unit="date",
        unavailable_reason="not_recovered",
        observations=5,
    ),
    "a recovery without a drawdown": analysis_row(
        **UNAVAILABLE,
        **NOT_RECONCILED,
        analysis="max_drawdown_recovery",
        unit="date",
        unavailable_reason="not_applicable",
    ),
    "a split segment outside the coverage": analysis_row(
        **UNAVAILABLE,
        **NOT_RECONCILED,
        segment="split-1",
        unavailable_reason="outside_coverage",
        observations=None,
    ),
    "a time below a peak to the segment's end": analysis_row(
        **NOT_RECONCILED,
        segment="split-0",
        analysis="longest_drawdown_days",
        subject="benchmark",
        value="1",
        unit="days",
        decimals=0,
        observations=5,
        period_start="2024-01-04",
        period_end="2024-01-05",
        flags=["not_recovered"],
        inputs=["daily/benchmark"],
    ),
    "a maximum drawdown of 0, without dates": analysis_row(
        value="0.0000", period_start=None, period_end=None, reported_value="0"
    ),
    "a rolling mean": rolling(),
    "a rolling count": rolling(
        "rolling_window_count",
        subject=None,
        value="5",
        unit="count",
        decimals=0,
        flags=[],
        inputs=["daily"],
    ),
    "a rolling share beating": rolling(
        "rolling_share_beating",
        subject="excess",
        value="40.0000",
        inputs=["daily/strategy", "daily/benchmark"],
    ),
    "a window too long for the series": rolling(
        **UNAVAILABLE, window_days=30, unavailable_reason="too_few_observations", observations=0
    ),
    "a year's window": rolling(window_days=365),
}


@pytest.mark.parametrize("case", VALID_ANALYSIS_ROWS)
def test_analysis_row_accepts_each_kind_of_value(case: str) -> None:
    accepts(AnalysisRow, VALID_ANALYSIS_ROWS[case])


INVALID_ANALYSIS_ROWS: dict[str, Document] = {
    "an analysis set this version doesn't know": analysis_row(analysis_set="1.1.0"),
    "an analysis the set doesn't have": analysis_row(analysis="sharpe_ratio"),
    "a subject the analysis doesn't have": analysis_row(subject="excess", inputs=["period/excess"]),
    "a value about the segment with a subject": analysis_row(
        **NOT_RECONCILED,
        analysis="period_count",
        value="2",
        unit="count",
        decimals=0,
        inputs=["period/strategy"],
    ),
    "the share of the coverage in the full segment": VALID_ANALYSIS_ROWS[
        "a split segment's share of the coverage"
    ]
    | {"segment": "full"},
    "a rolling return in a split segment": rolling(segment="split-1"),
    "a segment past the tenth split": analysis_row(segment="split-11", **NOT_RECONCILED),
    "a rolling return without its window": rolling(window_days=None),
    "a window the set doesn't have": rolling(window_days=14),
    "a window on a value that isn't rolling": analysis_row(window_days=7),
    "another unit": analysis_row(unit="pp"),
    "other inputs": analysis_row(inputs=["daily/benchmark"]),
    "a descriptive value without its flag": VALID_ANALYSIS_ROWS["a descriptive value"]
    | {"flags": []},
    "a flag on a value that isn't descriptive": analysis_row(flags=["descriptive"]),
    "a rolling summary without its flag": rolling(flags=[]),
    "not_recovered on a drawdown": analysis_row(flags=["not_recovered"]),
    "not_recovered on a time below a peak without a value": VALID_ANALYSIS_ROWS[
        "a time below a peak to the segment's end"
    ]
    | UNAVAILABLE
    | {"unavailable_reason": "too_few_observations"},
    "a flag twice": rolling(flags=["overlapping_windows", "overlapping_windows"]),
    "digits other than decimals": analysis_row(decimals=3),
    "a zero with a sign": analysis_row(value="-0.0000", period_start=None, period_end=None),
    "a count with decimals": VALID_ANALYSIS_ROWS["a count of periods"] | {"decimals": 4},
    "a count with digits": VALID_ANALYSIS_ROWS["a count of periods"] | {"value": "2.0"},
    "a date with decimals": VALID_ANALYSIS_ROWS["a recovery's date"] | {"decimals": 0},
    "a date that isn't a date": VALID_ANALYSIS_ROWS["a recovery's date"] | {"value": "2024-01-32"},
    "a percent without its decimals": analysis_row(decimals=None),
    "an unavailable value with its decimals": VALID_ANALYSIS_ROWS[
        "a window too long for the series"
    ]
    | {"decimals": 4},
    "an unavailable value without its reason": VALID_ANALYSIS_ROWS[
        "a window too long for the series"
    ]
    | {"unavailable_reason": None},
    "an available value with a reason": analysis_row(unavailable_reason="too_short"),
    "an available value that's empty": analysis_row(
        value=None, decimals=None, period_start=None, period_end=None, reconciliation="not_compared"
    ),
    "a source's reason": VALID_ANALYSIS_ROWS["a window too long for the series"]
    | {"unavailable_reason": "not_daily"},
    # A reason the analysis set gives some analyses or segments alone, on another's row.
    "a drawdown too short": analysis_row(
        **UNAVAILABLE, unavailable_reason="too_short", reconciliation="not_compared"
    ),
    "a difference too short": VALID_ANALYSIS_ROWS["a difference whose input is unavailable"]
    | {"unavailable_reason": "too_short"},
    "a drawdown that isn't applicable": analysis_row(
        **UNAVAILABLE, unavailable_reason="not_applicable", reconciliation="not_compared"
    ),
    "a drawdown that doesn't recover": analysis_row(
        **UNAVAILABLE, unavailable_reason="not_recovered", reconciliation="not_compared"
    ),
    "the full segment outside the coverage": analysis_row(
        **UNAVAILABLE, unavailable_reason="outside_coverage", reconciliation="not_compared"
    ),
    "a value without its observations": analysis_row(observations=None),
    "too few without how many": VALID_ANALYSIS_ROWS["a window too long for the series"]
    | {"observations": None},
    "the share of the coverage with observations": VALID_ANALYSIS_ROWS[
        "a split segment's share of the coverage"
    ]
    | {"observations": 4},
    "an unavailable input with observations": VALID_ANALYSIS_ROWS[
        "a difference whose input is unavailable"
    ]
    | {"observations": 10},
    "a first date without a last": analysis_row(period_end=None),
    "an unavailable value with dates": VALID_ANALYSIS_ROWS["a window too long for the series"]
    | {"period_start": "2024-01-01", "period_end": "2024-01-12"},
    "dates out of order": analysis_row(period_start="2024-01-05", period_end="2024-01-04"),
    "a reconciled value without its reconciliation": analysis_row(reconciliation=None),
    "a reconciliation on a split segment": VALID_ANALYSIS_ROWS[
        "a split segment's drawdown, not reconciled"
    ]
    | {"reconciliation": "agrees", "reported_value": "-4.8078"},
    "a reported value on a value not reconciled": rolling(reported_value="2.8258"),
    "agrees without the reported value": analysis_row(reported_value=None),
    "not_compared with both values": analysis_row(reconciliation="not_compared"),
    "a reported value that isn't a decimal": analysis_row(reported_value="−4.8078"),
    "a reported origin": analysis_row(origin="reported"),
    "verified provenance": analysis_row(provenance="verified"),
    "a version that isn't a version": analysis_row(trialfolio_version="0.5"),
}


@pytest.mark.parametrize("case", INVALID_ANALYSIS_ROWS)
def test_analysis_row_rejects_what_analysis_csv_calls_invalid(case: str) -> None:
    rejects(AnalysisRow, INVALID_ANALYSIS_ROWS[case])


def test_analysis_set_1_0_0_has_94_rows_for_the_full_segment_and_31_for_a_split() -> None:
    """Its 26 analyses, each with a row for each subject, and the rolling returns' for each of
    the five window lengths (analysis.csv, rows)."""
    full = split = 0
    for definition in ANALYSIS_SET_1_0_0.values():
        rows = len(definition.subjects) * (len(ROLLING_WINDOWS_1_0_0) if definition.windows else 1)
        full += rows if definition.segments != "split" else 0
        split += rows if definition.segments != "full" else 0

    assert (len(ANALYSIS_SET_1_0_0), full, split) == (26, 94, 31)
    assert ANALYSIS_SETS["1.0.0"].windows == (7, 30, 90, 180, 365)


def methodology_analyses() -> list[str]:
    """Each analysis methodology.md's analysis set 1.0.0 defines, in its order: its two tables'
    first column, then the rolling returns' counts and summaries, as `analysis.csv` orders them."""
    text = (ROOT / "docs" / "methodology.md").read_text(encoding="utf-8")
    section = text[text.index("## Analysis set 1.0.0") : text.index("### Charts")]
    tables = re.findall(r"^\| `([a-z_]+)` \|", section, re.MULTILINE)
    contracts = (ROOT / "docs" / "contracts.md").read_text(encoding="utf-8")
    rows = contracts[contracts.index("**Rows.** For each result: the `full` segment's rows") :]
    rows = rows[: rows.index("\n")]
    rolling_part = rows[rows.index("shortest first:") : rows.index("Every row is written")]
    return tables + re.findall(r"`(rolling_[a-z0-9_]+)`", rolling_part)


def test_analysis_set_1_0_0_is_methodology_s_in_its_order() -> None:
    assert list(ANALYSIS_SET_1_0_0) == methodology_analyses()


ROLLING_UNITS: dict[str, tuple[str, str]] = {
    "rolling_window_count": ("None", "count"),
    "rolling_non_overlapping_count": ("None", "count"),
    **{
        name: ("strategy, benchmark", "percent")
        for name in (
            "rolling_mean",
            "rolling_median",
            "rolling_p10",
            "rolling_p90",
            "rolling_worst",
        )
    },
    "rolling_share_beating": ("excess", "percent"),
}
"""The rolling returns' subjects and units, which methodology.md gives in words, not in a table:
the counts of windows, the strategy's and the benchmark's summaries of returns in percent, and the
share of windows beaten, in percent."""


def test_analysis_set_1_0_0_has_methodology_s_subjects_and_units() -> None:
    text = (ROOT / "docs" / "methodology.md").read_text(encoding="utf-8")
    section = text[text.index("## Analysis set 1.0.0") : text.index("### Rolling returns")]
    documented = {
        name: (subjects, unit)
        for name, subjects, unit in re.findall(
            r"^\| `([a-z_]+)` \| ([a-z, A-Z]+) \| ([a-z]+) \|", section, re.MULTILINE
        )
    } | ROLLING_UNITS

    for name, definition in ANALYSIS_SET_1_0_0.items():
        subjects = ", ".join(subject or "None" for subject in definition.subjects)
        assert (subjects, definition.unit) == documented[name], name


def test_analysis_set_1_0_0_flags_and_reconciles_what_the_documents_give() -> None:
    contracts = (ROOT / "docs" / "contracts.md").read_text(encoding="utf-8")
    descriptive = re.search(r"^\| `descriptive` \| ([^|]+) \|", contracts, re.MULTILINE)
    assert descriptive is not None
    methodology = (ROOT / "docs" / "methodology.md").read_text(encoding="utf-8")
    reconciliation = methodology[methodology.index("### Reconciliation with Portfolio123's") :]
    reconciled = reconciliation[
        reconciliation.index("segment, ") : reconciliation.index(", for the strategy and")
    ]

    flagged = {
        flag: {name for name, definition in ANALYSIS_SET_1_0_0.items() if definition.flag == flag}
        for flag in ("descriptive", "overlapping_windows")
    }

    assert flagged["descriptive"] == set(re.findall(r"`([a-z_]+)`", descriptive.group(1)))
    assert flagged["overlapping_windows"] == set(ROLLING_UNITS) - {
        "rolling_window_count",
        "rolling_non_overlapping_count",
    }
    assert ANALYSIS_SETS["1.0.0"].reconciled == set(re.findall(r"`([a-z_]+)`", reconciled))


def methodology_rows() -> dict[str, tuple[str, list[str]]]:
    """Each analysis of methodology.md's two tables, by identifier: the series its section's
    analyses read, `period` or `daily`, and its row's cells, the analysis, its subjects, its
    unit, its definition, and what it needs."""
    text = (ROOT / "docs" / "methodology.md").read_text(encoding="utf-8")
    rows: dict[str, tuple[str, list[str]]] = {}
    for heading, series in (
        ("### Period-return analyses", "period"),
        ("### Daily-level analyses", "daily"),
    ):
        section = text[text.index(heading) :]
        section = section[: section.index("\n### ")]
        for line in re.findall(r"^\| `[a-z_]+` \|.*\|$", section, re.MULTILINE):
            cells = [cell.strip() for cell in line.strip("|").split(" | ")]
            assert len(cells) == 5, line
            rows[cells[0].strip("`")] = (series, cells)
    return rows


def test_analysis_set_1_0_0_gives_each_analysis_the_reasons_methodology_names_for_it() -> None:
    """The reasons a row is refused on another analysis's: those its row's "Needs" names, or
    the row's it needs as, such as `excess_t_value`'s "As `information_ratio`". The rolling
    returns name none."""
    needs = {name: cells[4] for name, (_, cells) in methodology_rows().items()}
    codes = set(get_args(AnalysisUnavailableReason))
    named: dict[str, set[str]] = {}
    for name, text in needs.items():
        same = re.fullmatch(r"As `([a-z_]+)`", text)
        named[name] = set(re.findall(r"`([a-z_]+)`", needs[same.group(1)] if same else text))
        named[name] &= codes

    for name, definition in ANALYSIS_SET_1_0_0.items():
        assert set(definition.reasons) == named.get(name, set()), name
    assert {"not_applicable", "too_short", "not_recovered"} == set().union(*named.values())


# comparison.csv

BASELINE = "case-0492159b4461ceff"


def metric_row(**fields: object) -> Document:
    """`holdings-50`'s strategy total return against the baseline's: 12.5000 against 10.0000."""
    row: Document = {
        "label": CASE,
        "baseline_label": BASELINE,
        "kind": "metric",
        "segment": None,
        "name": "total_return",
        "subject": "strategy",
        "window_days": None,
        "baseline_value": "10.0000",
        "value": "12.5000",
        "unit": "percent",
        "classification": "differenced",
        "difference": "2.5000",
        "difference_unit": "pp",
        "difference_decimals": 4,
        "reason": None,
    }
    return {**row, **fields}


NOT_DIFFERENCED: Document = {
    "difference": None,
    "difference_unit": None,
    "difference_decimals": None,
}


def analysis_pair(**fields: object) -> Document:
    """The two cases' `full` segment's maximum drawdown recovery, 2024-01-09 against
    2024-01-10: a day earlier."""
    row = metric_row(
        kind="analysis",
        segment="full",
        name="max_drawdown_recovery",
        baseline_value="2024-01-10",
        value="2024-01-09",
        unit="date",
        difference="-1",
        difference_unit="days",
        difference_decimals=0,
    )
    return {**row, **fields}


def not_comparable(reason: str, **fields: object) -> Document:
    """An analysis pair that isn't differenced, for `reason`: by default, the recoveries'."""
    return analysis_pair(
        **NOT_DIFFERENCED, classification="not_comparable", reason=reason, **fields
    )


MEAN_PERIOD_RETURNS: Document = {
    "name": "mean_period_return",
    "baseline_value": "5.0000",
    "value": "10.0000",
    "unit": "percent",
}
"""The strategy's mean period returns, a value from period returns."""
TOTAL_RETURNS: Document = {
    "name": "total_return",
    "baseline_value": "10.0000",
    "value": "12.5000",
    "unit": "percent",
}
"""The strategy's total returns, a value from its daily levels alone."""
PERIOD_COUNTS: Document = {
    "name": "period_count",
    "subject": None,
    "baseline_value": "2",
    "value": "1",
    "unit": "count",
}
"""The counts of periods, which read the periods' dates and none of their values."""


VALID_COMPARISON_ROWS: dict[str, Document] = {
    "a metric differenced": metric_row(),
    "a metric over another benchmark": metric_row(
        **NOT_DIFFERENCED, classification="not_comparable", reason="different_benchmark"
    ),
    "a metric unavailable": metric_row(
        **NOT_DIFFERENCED, value=None, classification="unavailable", reason="input_unavailable"
    ),
    "a date differenced in days": analysis_pair(),
    "a count differenced": analysis_pair(
        name="period_count",
        subject=None,
        baseline_value="2",
        value="1",
        unit="count",
        difference="-1",
        difference_unit="count",
    ),
    "days differenced": analysis_pair(
        name="longest_drawdown_days",
        baseline_value="6",
        value="4",
        unit="days",
        difference="-2",
    ),
    "a percent's difference in pp": analysis_pair(
        name="mean_period_return",
        subject="excess",
        baseline_value="4.5000",
        value="4.5000",
        unit="percent",
        difference="0.0000",
        difference_unit="pp",
        difference_decimals=4,
    ),
    "a pp value's difference in pp": analysis_pair(
        segment="split-1",
        name="total_return_difference",
        subject="excess",
        baseline_value="10.1111",
        value="9.1111",
        unit="pp",
        difference="-1.0000",
        difference_unit="pp",
        difference_decimals=4,
    ),
    "a value of another rebalance": not_comparable("different_rebalance", **MEAN_PERIOD_RETURNS),
    "a value from periods of an unknown period": not_comparable(
        "unknown_period", **MEAN_PERIOD_RETURNS
    ),
    "a count of periods of an unknown period": not_comparable("unknown_period", **PERIOD_COUNTS),
    "a value from daily levels of another period": not_comparable(
        "different_period", segment="split-1"
    ),
    "the benchmark's value over another benchmark": not_comparable(
        "different_benchmark", subject="benchmark"
    ),
    "an excess of the daily levels over another benchmark": not_comparable(
        "different_benchmark",
        name="total_return_difference",
        subject="excess",
        baseline_value="10.1111",
        value="9.1111",
        unit="pp",
    ),
    "a rolling value": analysis_pair(
        name="rolling_mean",
        window_days=7,
        baseline_value="2.8258",
        value="3.0000",
        unit="percent",
        difference="0.1742",
        difference_unit="pp",
        difference_decimals=4,
    ),
}


@pytest.mark.parametrize("case", VALID_COMPARISON_ROWS)
def test_comparison_row_accepts_each_kind_of_pair(case: str) -> None:
    accepts(ComparisonRow, VALID_COMPARISON_ROWS[case])


INVALID_COMPARISON_ROWS: dict[str, Document] = {
    "the baseline against itself": metric_row(label=BASELINE),
    "a label that isn't a case_id": metric_row(label="holdings-50"),
    "a metric with a segment": metric_row(segment="full"),
    "a metric with a window": metric_row(window_days=7),
    "a metric of the excess": metric_row(subject="excess"),
    "a metric in pp": metric_row(unit="pp"),
    "a metric of another rebalance": metric_row(
        **NOT_DIFFERENCED, classification="not_comparable", reason="different_rebalance"
    ),
    "an analysis without its segment": analysis_pair(segment=None),
    "an analysis the set doesn't have": analysis_pair(name="sharpe_ratio"),
    "an analysis of a subject it doesn't have": analysis_pair(subject="excess"),
    "an analysis in another unit": analysis_pair(
        unit="days", baseline_value="6", value="5", difference="-1"
    ),
    "an analysis with a window it doesn't have": analysis_pair(window_days=7),
    # A reason that doesn't apply to the pair's analysis (comparing a case with the baseline).
    "a rolling value of another rebalance": VALID_COMPARISON_ROWS["a rolling value"]
    | NOT_DIFFERENCED
    | {"classification": "not_comparable", "reason": "different_rebalance"},
    "a value from daily levels of another rebalance": not_comparable("different_rebalance"),
    "a value from daily levels of an unknown period": not_comparable(
        "unknown_period", **TOTAL_RETURNS
    ),
    "the strategy's value from daily levels over another benchmark": not_comparable(
        "different_benchmark", **TOTAL_RETURNS
    ),
    "the strategy's value from periods over another benchmark": not_comparable(
        "different_benchmark", **MEAN_PERIOD_RETURNS
    ),
    "a count of periods over another benchmark": not_comparable(
        "different_benchmark", **PERIOD_COUNTS
    ),
    "an analysis in two units": not_comparable("different_unit"),
    "a difference with other decimals": metric_row(difference="2.50", difference_decimals=2),
    "a difference in another unit": metric_row(difference_unit="percent"),
    "a zero with a sign": VALID_COMPARISON_ROWS["a percent's difference in pp"]
    | {"difference": "-0.0000"},
    "a difference with a reason": metric_row(reason="different_period"),
    "a difference without its value": metric_row(value=None),
    "not comparable without a value": metric_row(
        **NOT_DIFFERENCED, value=None, classification="not_comparable", reason="different_period"
    ),
    "not comparable without why": metric_row(**NOT_DIFFERENCED, classification="not_comparable"),
    "not comparable with a difference": metric_row(
        classification="not_comparable", reason="different_period"
    ),
    "unavailable with both values": metric_row(
        **NOT_DIFFERENCED, classification="unavailable", reason="input_unavailable"
    ),
    "unavailable for another reason": metric_row(
        **NOT_DIFFERENCED, value=None, classification="unavailable", reason="different_period"
    ),
    "a number of days with digits": VALID_COMPARISON_ROWS["days differenced"] | {"value": "4.0"},
    "a date that isn't a date": analysis_pair(value="2024-02-30"),
}


@pytest.mark.parametrize("case", INVALID_COMPARISON_ROWS)
def test_comparison_row_rejects_what_comparison_csv_calls_invalid(case: str) -> None:
    rejects(ComparisonRow, INVALID_COMPARISON_ROWS[case])


# The tables' columns


def documented_columns(heading: str) -> list[str]:
    """The columns docs/contracts.md's table under `heading` gives, in order, each cell of its
    first column that names several, such as `period_start`, `period_end`, read as each."""
    contracts = (ROOT / "docs" / "contracts.md").read_text(encoding="utf-8")
    section = contracts[contracts.index(heading) :]
    table = section[section.index("| Column | Meaning |") :]
    table = table[: table.index("\n\n")]
    columns: list[str] = []
    for line in table.splitlines()[2:]:
        columns += re.findall(r"`([a-z_]+)`", line.split("|")[1])
    return columns


@pytest.mark.parametrize(
    ("heading", "columns"),
    [
        ("### `series.csv`", SERIES_COLUMNS),
        ("### `analysis.csv`", ANALYSIS_COLUMNS),
        ("### `comparison.csv`", COMPARISON_COLUMNS),
    ],
    ids=["series", "analysis", "comparison"],
)
def test_each_table_has_contracts_md_s_columns_in_order(
    heading: str, columns: tuple[str, ...]
) -> None:
    assert list(columns) == documented_columns(heading)
