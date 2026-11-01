"""The rows of `settings.csv` 1.1.0 and `differences.csv` 1.1.0, with their weight rows, accept what
docs/contracts.md describes, and reject what it calls invalid.

Traces to release 0.4.0's test pairing, which names tests/contract/test_ranking_artifact_models.py
for the records' contract tests (R04-T05), here for the rows of `settings.csv` 1.1.0 and
`differences.csv` 1.1.0 (weight rows); and to the 0.3.0 contracts, which a definition doesn't reach:
`settings.csv` 1.0.0 and `differences.csv` 1.0.0 refuse a weight row and a definition. Each document
is tests/support/ranking_documents.py's, synthetic, changed one way, and read as a reader reads it:
from JSON text, with `model_validate_json`. TS-T07 separated these tests from
tests/contract/test_ranking_artifact_models.py (docs/test-refactoring.md, modules to separate).
"""

import pytest

from tests.support.contract_checks import Change, accepts, changed, rejects
from tests.support.ranking_documents import (
    DEFINITION_TEXT,
    differences_row,
    ranking_settings_row,
    settings_row,
    undeclared,
)
from trialfolio.contracts.tables import (
    DifferencesRow,
    DifferencesRowV1_1,
    SettingsRow,
    SettingsRowV1_1,
)

# The rows of settings.csv 1.1.0 and differences.csv 1.1.0

SETTINGS_ROW_ACCEPTS: dict[str, Change] = {
    "the ranking row of a definition": ranking_settings_row,
    "a weight a ranking variant sets": lambda d: d.update(
        value="70", original_key="variants.ranking[0].set[0]", original_value="70"
    ),
    "a row of another setting": lambda d: d.update(
        setting="max_holdings",
        value="25",
        unit="count",
        original_key="max_holdings",
        original_value="25",
        node=None,
    ),
}


@pytest.mark.parametrize("change", SETTINGS_ROW_ACCEPTS.values(), ids=SETTINGS_ROW_ACCEPTS.keys())
def test_settings_row_1_1_accepts(change: Change) -> None:
    accepts(SettingsRowV1_1, changed(settings_row, change))


SETTINGS_ROW_REJECTS: dict[str, Change] = {
    "a weight row without its node": lambda d: d.update(node=None),
    "a node on the ranking row": lambda d: (
        ranking_settings_row(d),
        d.update(node="Earnings Yield"),
    ),
    "a blank node": lambda d: d.update(node=""),
    "a weight of 0": lambda d: d.update(value="0"),
    "a weight not normalized": lambda d: d.update(value="60.0"),
    "a weight with a unit": lambda d: d.update(unit="percent"),
    "a weight that's inferred": lambda d: d.update(provenance="inferred", inference_rule="A rule"),
    "a weight with a flag": lambda d: d.update(flags=["not_snapshotted"]),
    "a weight in another category": lambda d: d.update(category="other", critical=False),
    "a ranking by formula": lambda d: (
        ranking_settings_row(d),
        d.update(value='{"formula": "EarnYield", "lower_is_better": false}'),
    ),
    "a definition flagged not_snapshotted": lambda d: (
        ranking_settings_row(d),
        d.update(flags=["not_snapshotted"]),
    ),
    "an original key without its value": lambda d: d.update(original_value=None),
}


@pytest.mark.parametrize("change", SETTINGS_ROW_REJECTS.values(), ids=SETTINGS_ROW_REJECTS.keys())
def test_settings_row_1_1_rejects(change: Change) -> None:
    rejects(SettingsRowV1_1, changed(settings_row, change))


def test_settings_row_1_0_0_refuses_a_weight_row_and_a_definition() -> None:
    """A run or case whose ranking is a definition writes `settings.csv` 1.1.0, so 1.0.0's rows
    stay as 0.3.0 reads them."""
    weight = settings_row()
    weight.pop("node")
    definition = changed(settings_row, ranking_settings_row)
    definition.pop("node")

    rejects(SettingsRow, weight)
    rejects(SettingsRow, definition)


DIFFERENCES_ROW_ACCEPTS: dict[str, Change] = {
    "a weight that differs, undeclared": undeclared,
    "the same weight": lambda d: d.update(value="60", classification="same", declared_reason=None),
    "a node the result's definition lacks": lambda d: (undeclared(d), d.update(value="absent")),
    "a node the baseline lacks, declared": lambda d: d.update(baseline_value="absent"),
    "a weight against a ranking by name": lambda d: d.update(
        value=None,
        classification="unknown",
        declared_reason=None,
        flagged=True,
        flags=["critical_unknown"],
    ),
    "a definition against a formula": lambda d: (
        undeclared(d),
        d.update(
            name="ranking",
            node=None,
            baseline_value=DEFINITION_TEXT,
            value='{"formula": "EarnYield", "lower_is_better": false}',
        ),
    ),
    "a definition against a ranking by name": lambda d: (
        undeclared(d),
        d.update(
            name="ranking",
            node=None,
            baseline_value=DEFINITION_TEXT,
            value='{"name": "Value and momentum"}',
            flags=["critical_unexplained_mismatch", "not_snapshotted"],
        ),
    ),
    "a metric row": lambda d: d.update(
        kind="metric",
        name="annualized_return",
        subject="strategy",
        category=None,
        critical=None,
        baseline_value="12.30",
        value="12.50",
        unit="percent",
        classification="differenced",
        difference="0.20",
        difference_unit="pp",
        difference_decimals=2,
        declared_reason=None,
        node=None,
    ),
}


@pytest.mark.parametrize(
    "change", DIFFERENCES_ROW_ACCEPTS.values(), ids=DIFFERENCES_ROW_ACCEPTS.keys()
)
def test_differences_row_1_1_accepts(change: Change) -> None:
    accepts(DifferencesRowV1_1, changed(differences_row, change))


DIFFERENCES_ROW_REJECTS: dict[str, Change] = {
    "a weight row without its node": lambda d: d.update(node=None),
    "a node on another setting's row": lambda d: d.update(
        name="max_holdings", baseline_value="25", value="50", unit="count"
    ),
    "the same weight, with a declared reason": lambda d: d.update(
        value="60", classification="same", flagged=True, flags=["intended_change_not_observed"]
    ),
    "a weight flagged intended_change_not_observed": lambda d: d.update(
        value="60",
        classification="same",
        declared_reason=None,
        flagged=True,
        flags=["intended_change_not_observed"],
    ),
    "a declared weight change without its reason": lambda d: d.update(declared_reason=None),
    "an undeclared weight change with a reason": lambda d: (
        undeclared(d),
        d.update(declared_reason="More weight on earnings yield."),
    ),
    "weights that differ, called the same": lambda d: d.update(
        classification="same", declared_reason=None
    ),
    "an unknown weight with both values": lambda d: d.update(
        classification="unknown",
        declared_reason=None,
        flagged=True,
        flags=["critical_unknown"],
    ),
    "an undeclared weight change not flagged": lambda d: (
        undeclared(d),
        d.update(flags=[], flagged=False),
    ),
    "a weight of 0": lambda d: d.update(value="0"),
    "a weight not normalized": lambda d: d.update(value="70.0"),
    "both nodes absent": lambda d: (
        undeclared(d),
        d.update(
            baseline_value="absent", value="absent", classification="same", flags=[], flagged=False
        ),
    ),
    "a definition flagged not_snapshotted": lambda d: (
        undeclared(d),
        d.update(
            name="ranking",
            node=None,
            baseline_value=DEFINITION_TEXT,
            value='{"formula": "EarnYield", "lower_is_better": false}',
            flags=["critical_unexplained_mismatch", "not_snapshotted"],
        ),
    ),
    "a metric row with a node": lambda d: d.update(
        kind="metric",
        name="annualized_return",
        subject="strategy",
        category=None,
        critical=None,
        baseline_value="12.30",
        value="12.50",
        unit="percent",
        classification="differenced",
        difference="0.20",
        difference_unit="pp",
        difference_decimals=2,
        declared_reason=None,
    ),
}


@pytest.mark.parametrize(
    "change", DIFFERENCES_ROW_REJECTS.values(), ids=DIFFERENCES_ROW_REJECTS.keys()
)
def test_differences_row_1_1_rejects(change: Change) -> None:
    rejects(DifferencesRowV1_1, changed(differences_row, change))


def test_differences_row_1_0_0_refuses_a_weight_row() -> None:
    document = differences_row()
    document.pop("node")

    rejects(DifferencesRow, document)
