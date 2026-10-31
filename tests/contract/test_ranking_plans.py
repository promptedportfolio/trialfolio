"""The plans of a ranking definition, and of a ranking snapshot, accept what docs/contracts.md
describes, and reject what it calls invalid.

Traces to release 0.4.0's test pairing, which names tests/contract/test_ranking_artifact_models.py
for the records' contract tests (R04-T05), here for plans 1.2.0 and 1.3.0 (plans with a ranking
definition) and the snapshot plan (ranking snapshot output); and to the 0.3.0 contracts, which a
definition doesn't reach: plan 1.0.0 refuses a definition and weight rows.

The models give each plan's shapes, and the rules one plan can show. Release 0.4.0's R04-T07 added
the plans' consistency rules (plans with a ranking definition), and a rejected plan for each,
`plan_1_2()` or `plan_1_3()` changed one way, to R04-AC01's row: a `rank_update` whose `nodes` isn't
the definition its case's `ranking` row names by hash, or whose `rankingMethod` isn't that row's
method; weight rows that aren't the definition's weights, in its order, by canonical path; a
backtest ranked by a name other than `ApiRankingSystem`; a `ranking_source` whose `definition` isn't
the baseline's, or whose other fields don't follow its `form`; a variant whose definition isn't the
baseline's with exactly its change, and a ranking variant that changes a row besides `ranking` and
the weight rows; and `credits` other than its `costs` give, and, in 1.3.0, `provider_requests` below
twice the cases. So the plans tests/support/ranking_documents.py builds are consistent: each
definition's hash is its text's, and each case's weight rows are its definition's. Each document is
synthetic, and read as a reader reads it: from JSON text, with `model_validate_json`. TS-T07
separated these tests from tests/contract/test_ranking_artifact_models.py (docs/test-refactoring.md,
modules to separate).
"""

import json

import pytest
from pydantic import BaseModel, ValidationError

from tests.support.contract_checks import Change, Document, accepts, changed, digest, rejects
from tests.support.ranking_documents import (
    COSTS,
    DEFINITION,
    DEFINITION_ID,
    EARLIER_PLAN,
    HEAVY,
    HEAVY_CASE,
    HEAVY_ID,
    HEAVY_SET,
    NO_SALES,
    PLAN_HASH,
    SCREEN_SOURCE,
    WEIGHTS,
    backtest,
    baseline_case,
    data_sent,
    experiment_case,
    hash_of,
    heavy_case,
    holdings_case,
    plan_1_2,
    plan_1_3,
    rank_update,
    settings_rows,
    snapshot_plan,
    variant,
)
from trialfolio.contracts.experiment_plan import ExperimentPlanCaseV1_3, PlanV1_3
from trialfolio.contracts.plan import Plan, PlanV1_2
from trialfolio.contracts.plan_parts import read_nodes
from trialfolio.contracts.ranking_snapshot import RankingSnapshotPlan

# Plan 1.2.0


def case_of(document: Document, index: int = 0) -> Document:
    case: Document = document["cases"][index]
    return case


def setting_of(document: Document, name: str, case: int = 0) -> Document:
    (row,) = (row for row in case_of(document, case)["settings"] if row["setting"] == name)
    return row


def weight_of(document: Document, index: int, case: int = 0) -> Document:
    rows = [
        row for row in case_of(document, case)["settings"] if row["setting"] == "ranking_weight"
    ]
    return rows[index]


def rank_params(document: Document, case: int = 0) -> Document:
    params: Document = case_of(document, case)["requests"][0]["params"]
    return params


def move_weights(document: Document, after: str) -> None:
    rows: list[Document] = case_of(document)["settings"]
    weights = [row for row in rows if row["setting"] == "ranking_weight"]
    others = [row for row in rows if row["setting"] != "ranking_weight"]
    index = next(i for i, row in enumerate(others) if row["setting"] == after)
    case_of(document)["settings"] = [*others[: index + 1], *weights, *others[index + 1 :]]


def snapshot_source(document: Document) -> None:
    document["ranking_source"] = {
        "form": "snapshot",
        "definition": DEFINITION_ID,
        "system": "Value and momentum",
        "snapshot_record": digest("f3"),
        "snapshot_definition": digest("f1"),
    }


ONE_NODE = (
    '<RankingSystem RankType="Higher">\n'
    '\t<StockFormula Name="Earnings Yield" Weight="100" RankType="Higher">\n'
    "\t\t<Formula>EarnYield</Formula>\n"
    "\t</StockFormula>\n"
    "</RankingSystem>\n"
)
UNNAMED = (
    '<RankingSystem RankType="Higher">\n'
    '\t<StockFactor Weight="12.5" RankType="Higher">\n'
    "\t\t<Factor>…</Factor>\n"
    "\t</StockFactor>\n"
    '\t<StockFactor Weight="87.50" RankType="Lower">\n'
    "\t\t<Factor>…</Factor>\n"
    "\t</StockFactor>\n"
    "</RankingSystem>\n"
)
"""Two factors without a name, so each is named by its position, whose weights are written as
decimals, one not normalized."""
THREE_NODES = DEFINITION.replace(
    "</RankingSystem>",
    '\t<StockFormula Name="Quality" Weight="10" RankType="Higher">\n'
    "\t\t<Formula>ROE%TTM</Formula>\n\t</StockFormula>\n</RankingSystem>",
)


def use_definition(
    document: Document,
    nodes: str,
    weights: tuple[tuple[str, str], ...],
    case: int = 0,
    method: str = "percentile_nas_negative",
    values: dict[str, object] | None = None,
) -> None:
    """Gives a case another definition, consistently: its `rank_update`, its `ranking` row's hash
    and method, and its weight rows; and, for the baseline, the plan's `ranking_source`."""
    found = case_of(document, case)
    ranking = {"ranking": {"definition": hash_of(nodes), "ranking_method": method}}
    found["settings"] = settings_rows(ranking | (values or {}), weights)
    found["requests"][0] = rank_update(nodes, 2 if method == "percentile_nas_negative" else 4)
    if case == 0:
        document["ranking_source"]["definition"] = hash_of(nodes)


PLAN_1_2_ACCEPTS: dict[str, Change] = {
    "a snapshot's source": snapshot_source,
    "ranking method 4": lambda d: (
        rank_params(d).update(rankingMethod=4),
        setting_of(d, "ranking")["value"].update(ranking_method="percentile_nas_neutral"),
    ),
    "a purpose": lambda d: d.update(purpose="A reference run of the ranking."),
    "a weight of one node": lambda d: use_definition(d, ONE_NODE, (("Earnings Yield", "100"),)),
    "nodes by position, and with a decimal weight": lambda d: use_definition(
        d, UNNAMED, (("#1", "12.5"), ("#2", "87.5"))
    ),
    "another documented cost": lambda d: (
        d["budget"]["costs"][0].update(credits_per_request=2),
        d["budget"].update(credits=7),
    ),
}


@pytest.mark.parametrize("change", PLAN_1_2_ACCEPTS.values(), ids=PLAN_1_2_ACCEPTS.keys())
def test_plan_1_2_accepts(change: Change) -> None:
    accepts(PlanV1_2, changed(plan_1_2, change))


PLAN_1_2_REJECTS: dict[str, Change] = {
    "version 1.0.0": lambda d: d.update(schema_version="1.0.0"),
    "no ranking_source": lambda d: d.pop("ranking_source"),
    "a ranking_source of another form": lambda d: d["ranking_source"].update(form="file"),
    "a ranking_source without the definition's hash": lambda d: d["ranking_source"].update(
        definition=None
    ),
    "a ranking_source that leaves a field out": lambda d: d["ranking_source"].pop("system"),
    "two cases": lambda d: d.update(cases=[case_of(d), case_of(d)]),
    "one request": lambda d: case_of(d).update(requests=[backtest()]),
    "the backtest first": lambda d: case_of(d).update(requests=[backtest(), rank_update()]),
    "a third request": lambda d: case_of(d)["requests"].append(backtest()),
    "a rank_update with an id": lambda d: rank_params(d).update(id=42),
    "a rank_update with ranking method 1": lambda d: rank_params(d).update(rankingMethod=1),
    "a rank_update with ranking method true": lambda d: rank_params(d).update(rankingMethod=True),
    "a rank_update in another currency": lambda d: rank_params(d).update(currency="EUR"),
    "a rank_update of another type": lambda d: rank_params(d).update(type="etf"),
    "a rank_update with no definition": lambda d: rank_params(d).update(nodes=""),
    "no weight rows": lambda d: case_of(d).update(settings=settings_rows(weights=())),
    "the weight rows before ranking": lambda d: move_weights(d, "rules"),
    "the weight rows after max_holdings": lambda d: move_weights(d, "max_holdings"),
    "a weight row without its node": lambda d: weight_of(d, 0).update(node=None),
    "a node on another row": lambda d: setting_of(d, "universe").update(node="Earnings Yield"),
    "a weight of 0": lambda d: weight_of(d, 0).update(value="0"),
    "a weight not normalized": lambda d: weight_of(d, 0).update(value="60.0"),
    "a weight as a number": lambda d: weight_of(d, 0).update(value=60),
    "a weight row with a unit": lambda d: weight_of(d, 0).update(unit="count"),
    "a weight row that's inferred": lambda d: weight_of(d, 0).update(
        expected_provenance="inferred", inference_rule="A rule"
    ),
    "a weight row with a flag": lambda d: weight_of(d, 0).update(flags=["not_snapshotted"]),
    "a ranking by formula": lambda d: setting_of(d, "ranking").update(
        value={"formula": "EarnYield", "lower_is_better": False}
    ),
    "a ranking by name": lambda d: setting_of(d, "ranking").update(
        value={"name": "Value and momentum"}, flags=["not_snapshotted"]
    ),
    "a definition flagged not_snapshotted": lambda d: setting_of(d, "ranking").update(
        flags=["not_snapshotted"]
    ),
    "a definition's ranking method that isn't documented": lambda d: setting_of(d, "ranking")[
        "value"
    ].update(ranking_method="normal_distribution"),
    "a definition by its path": lambda d: setting_of(d, "ranking")["value"].update(
        definition="ranking/value-momentum.xml"
    ),
    "one provider request": lambda d: d["budget"].update(provider_requests=1),
    "two authentication calls": lambda d: d["budget"].update(authentication_calls=2),
    "the costs in another order": lambda d: d["budget"].update(costs=COSTS[::-1]),
    "one cost": lambda d: d["budget"].update(costs=COSTS[:1]),
    "a cost of another operation": lambda d: d["budget"]["costs"][0].update(operation="rank_get"),
    "1.0.0's budget": lambda d: d.update(
        budget={
            "provider_requests": 2,
            "credits_per_request": 5,
            "credits_per_request_source": SCREEN_SOURCE,
            "credits": 10,
            "authentication_calls": 1,
        }
    ),
    "the weights not among the data sent": lambda d: d.update(
        data_sent=data_sent(["universe", "rules", "ranking"])
    ),
}


@pytest.mark.parametrize("change", PLAN_1_2_REJECTS.values(), ids=PLAN_1_2_REJECTS.keys())
def test_plan_1_2_rejects(change: Change) -> None:
    rejects(PlanV1_2, changed(plan_1_2, change))


def backtest_of(document: Document, case: int = 0) -> Document:
    params: Document = case_of(document, case)["requests"][1]["params"]
    return params


def swap_weights(document: Document) -> None:
    rows: list[Document] = case_of(document)["settings"]
    first = next(i for i, row in enumerate(rows) if row["setting"] == "ranking_weight")
    rows[first], rows[first + 1] = rows[first + 1], rows[first]


def snapshot_without(field: str) -> Change:
    return lambda d: (snapshot_source(d), d["ranking_source"].update({field: None}))


INCONSISTENT_CASE: dict[str, tuple[Change, str]] = {
    "a rank_update whose nodes is another definition": (
        lambda d: rank_params(d).update(nodes=HEAVY),
        "a rank_update's nodes is the definition whose hash its case's ranking setting holds",
    ),
    "a rank_update whose nodes isn't a definition": (
        lambda d: rank_params(d).update(nodes="<Ranking/>\n"),
        "a rank_update's nodes is a ranking definition that Trial Folio reads",
    ),
    "a rank_update whose nodes ends its lines with carriage returns": (
        lambda d: rank_params(d).update(nodes=DEFINITION.replace("\n", "\r\n")),
        "a rank_update's nodes ends each line with a line feed alone",
    ),
    "a rank_update with another ranking method": (
        lambda d: rank_params(d).update(rankingMethod=4),
        "a rank_update's rankingMethod is the number of its case's ranking method",
    ),
    "a weight row with another weight": (
        lambda d: weight_of(d, 0).update(value="70"),
        "a case's weight rows are the weights its definition gives its nodes",
    ),
    "the weight rows in another order": (
        swap_weights,
        "a case's weight rows are the weights its definition gives its nodes",
    ),
    "a weight row by a path that isn't canonical": (
        lambda d: weight_of(d, 0).update(node="#1"),
        "a case's weight rows are the weights its definition gives its nodes",
    ),
    "a weight row for each node but one": (
        lambda d: case_of(d).update(settings=settings_rows(weights=WEIGHTS[:1])),
        "a case's weight rows are the weights its definition gives its nodes",
    ),
    "a backtest ranked by another name": (
        lambda d: backtest_of(d)["screen"].update(ranking="Value and momentum"),
        "a backtest with a ranking definition ranks by ApiRankingSystem",
    ),
    "a backtest ranked by a formula": (
        lambda d: backtest_of(d)["screen"].update(
            ranking={"formula": "EarnYield", "lowerIsBetter": False}
        ),
        "a backtest with a ranking definition ranks by ApiRankingSystem",
    ),
    "a backtest that isn't what the settings send": (
        lambda d: backtest_of(d)["screen"].update(maxNumHoldings=50),
        "the backtest's params must be what the settings send",
    ),
}
"""A case changed one way, each breaking one consistency rule of a case with a ranking
definition, with the start of its rule's message; in plan 1.2.0, and in plan 1.3.0's baseline."""

INCONSISTENT_PLAN_1_2: dict[str, tuple[Change, str]] = {
    "a ranking_source of another definition": (
        lambda d: d["ranking_source"].update(definition=HEAVY_ID),
        "ranking_source's definition is the hash of the baseline's definition",
    ),
    "a file's ranking_source with a system": (
        lambda d: d["ranking_source"].update(system="Value and momentum"),
        "a file's ranking_source gives no system or snapshot files",
    ),
    "a file's ranking_source with a snapshot's record": (
        lambda d: d["ranking_source"].update(snapshot_record=digest("f3")),
        "a file's ranking_source gives no system or snapshot files",
    ),
    "a snapshot's ranking_source without its system": (
        snapshot_without("system"),
        "a snapshot's ranking_source gives its system's name and its files' artifact_ids",
    ),
    "a snapshot's ranking_source without its record": (
        snapshot_without("snapshot_record"),
        "a snapshot's ranking_source gives its system's name and its files' artifact_ids",
    ),
    "a snapshot's ranking_source without its definition's copy": (
        snapshot_without("snapshot_definition"),
        "a snapshot's ranking_source gives its system's name and its files' artifact_ids",
    ),
    "credits other than its costs give": (
        lambda d: d["budget"].update(credits=10),
        "credits is the most the provider requests can cost at the costs given",
    ),
    "credits at one cost for every request": (
        lambda d: d["budget"].update(credits=2),
        "credits is the most the provider requests can cost at the costs given",
    ),
}
"""Plan 1.2.0 changed one way, each breaking one of its consistency rules, with the start of its
rule's message."""


def test_a_rank_update_s_nodes_with_a_lone_surrogate_isn_t_a_definition() -> None:
    """No JSON reader gives a lone surrogate, which UTF-8 can't encode, so this is checked where
    the models read `nodes`: as a definition Trial Folio doesn't read, without quoting it."""
    with pytest.raises(ValueError, match="^a rank_update's nodes is a ranking definition that"):
        read_nodes(DEFINITION.replace("EarnYield", "\ud800"))


def rejected_by(model: type[BaseModel], document: Document) -> str:
    """The message of the one error `model` gives the document."""
    with pytest.raises(ValidationError) as caught:
        model.model_validate_json(json.dumps(document))
    (error,) = caught.value.errors(include_input=False)
    return str(error["msg"])


@pytest.mark.parametrize(
    ("change", "rule"),
    [*INCONSISTENT_CASE.values(), *INCONSISTENT_PLAN_1_2.values()],
    ids=[*INCONSISTENT_CASE, *INCONSISTENT_PLAN_1_2],
)
def test_plan_1_2_rejects_an_inconsistent_plan_by_its_own_rule(change: Change, rule: str) -> None:
    """R04-T07's consistency rules: each plan breaks one, and is rejected by it alone."""
    assert rejected_by(PlanV1_2, changed(plan_1_2, change)).startswith(f"Value error, {rule}")


def test_plan_1_0_0_refuses_a_definition_and_weight_rows() -> None:
    """A screen whose ranking is a definition writes plan 1.2.0, so plan 1.0.0 stays as 0.3.0
    reads it."""
    document = plan_1_2()
    document.update(schema_version="1.0.0")
    document.pop("ranking_source")
    for row in case_of(document)["settings"]:
        row.pop("node")
    document["budget"] = {
        "provider_requests": 1,
        "credits_per_request": 5,
        "credits_per_request_source": SCREEN_SOURCE,
        "credits": 5,
        "authentication_calls": 1,
    }
    document["data_sent"] = data_sent(["universe", "rules", "ranking"])
    case_of(document)["requests"] = [backtest()]

    with pytest.raises(ValidationError) as caught:
        Plan.model_validate_json(json.dumps(document))

    located = {error["loc"][:4] for error in caught.value.errors(include_input=False)}
    assert ("cases", 0, "settings", 3) in located  # the definition, in place of a form's keys
    assert ("cases", 0, "settings", 4) in located  # a weight row


# Plan 1.3.0


def removal_case() -> Document:
    """A removal variant: `Sales Yield` removed, and `Earnings Yield` at 100."""
    case = experiment_case(
        "no-sales-yield",
        "case-0000000000000005",
        variant("ranking", set=[{"node": "Earnings Yield", "weight": "100"}], remove="Sales Yield"),
        settings_rows(
            {
                "ranking": {
                    "definition": hash_of(NO_SALES),
                    "ranking_method": "percentile_nas_negative",
                }
            },
            (("Earnings Yield", "100"),),
        ),
        [rank_update(NO_SALES), backtest()],
    )
    return case


def five_cases(document: Document, case: Document) -> None:
    """Adds `case` after the ranking variant, with a budget of two requests for each of the five
    cases."""
    document["cases"].insert(2, case)
    document["budget"].update(provider_requests=10, authentication_calls=10, credits=30)


def holdings_on_heavy() -> Document:
    """A holdings variant built on the ranking variant's settings, instead of the baseline's."""
    case = holdings_case()
    case["settings"] = settings_rows(
        {
            "max_holdings": 50,
            "ranking": {"definition": HEAVY_ID, "ranking_method": "percentile_nas_negative"},
        },
        (("Earnings Yield", "70"), ("Sales Yield", "30")),
    )
    case["requests"][0] = rank_update(HEAVY)
    return case


def heavy_variant(document: Document) -> Document:
    found: Document = case_of(document, 1)["variant"]
    return found


PLAN_1_3_ACCEPTS: dict[str, Change] = {
    "a removal variant": lambda d: five_cases(d, removal_case()),
    "a revision": lambda d: d.update(revises=EARLIER_PLAN),
    "no default": lambda d: d["cases"].pop(),
    "a snapshot's source": snapshot_source,
    "a larger budget": lambda d: d["budget"].update(
        provider_requests=10, authentication_calls=10, credits=30
    ),
    "a ranking variant with a description": lambda d: case_of(d, 1).update(
        description="More weight on earnings yield."
    ),
}


@pytest.mark.parametrize("change", PLAN_1_3_ACCEPTS.values(), ids=PLAN_1_3_ACCEPTS.keys())
def test_plan_1_3_accepts(change: Change) -> None:
    accepts(PlanV1_3, changed(plan_1_3, change))


PLAN_1_3_REJECTS: dict[str, Change] = {
    "version 1.1.0": lambda d: d.update(schema_version="1.1.0"),
    "no ranking_source": lambda d: d.pop("ranking_source"),
    "a case with one request": lambda d: case_of(d, 2).update(requests=[backtest()]),
    "no case with weight rows": lambda d: [
        case.update(settings=[row for row in case["settings"] if row["node"] is None])
        for case in d["cases"]
    ],
    "a holdings variant with set": lambda d: case_of(d, 2)["variant"].update(set=HEAVY_SET),
    "a holdings variant with remove": lambda d: case_of(d, 2)["variant"].update(
        remove="Sales Yield"
    ),
    "a ranking variant with a value": lambda d: heavy_variant(d).update(value=70),
    "a ranking variant with an add": lambda d: heavy_variant(d).update(add="MktCap > 300"),
    "a ranking variant without set": lambda d: heavy_variant(d).update(set=None),
    "a ranking variant with an empty set": lambda d: heavy_variant(d).update(set=[]),
    "a ranking variant that names a node twice": lambda d: heavy_variant(d).update(
        set=[{"node": "Earnings Yield", "weight": "70"}, {"node": "Earnings Yield", "weight": "30"}]
    ),
    "a ranking variant that gives the removed factor a weight": lambda d: heavy_variant(d).update(
        remove="Sales Yield"
    ),
    "a ranking variant's weight of 0": lambda d: heavy_variant(d)["set"][0].update(weight="0"),
    "a ranking variant's weight not normalized": lambda d: heavy_variant(d)["set"][0].update(
        weight="70.0"
    ),
    "a ranking variant's weight as a number": lambda d: heavy_variant(d)["set"][0].update(
        weight=70
    ),
    "a ranking variant's empty node": lambda d: heavy_variant(d)["set"][0].update(node=""),
    "the default a ranking variant": lambda d: heavy_variant(d).update(default=True),
    "the ranking variant after the holdings variant": lambda d: d["cases"].insert(
        2, d["cases"].pop(1)
    ),
    "a variant keyed baseline": lambda d: case_of(d, 1).update(case_key="baseline"),
    "a baseline with a description": lambda d: case_of(d, 0).update(description="The baseline."),
    "a variant first, the other built on it": lambda d: d.update(
        cases=[heavy_case(), holdings_on_heavy()]
    ),
    "a holdings variant with a weight row the baseline doesn't have": lambda d: use_definition(
        d, THREE_NODES, (*WEIGHTS, ("Quality", "10")), case=2, values={"max_holdings": 50}
    ),
    "a repeated case key": lambda d: case_of(d, 2).update(case_key="earnings-heavy"),
    "a repeated case ID": lambda d: case_of(d, 2).update(case_id=HEAVY_CASE),
    "two holdings variants of 50": lambda d: d["cases"].insert(
        3, holdings_case() | {"case_key": "holdings-again", "case_id": "case-0000000000000009"}
    ),
    "a budget below the cases": lambda d: d["budget"].update(
        provider_requests=3, authentication_calls=3, credits=7
    ),
    "authentication calls other than the requests": lambda d: d["budget"].update(
        authentication_calls=7
    ),
    "1.1.0's budget": lambda d: d.update(
        budget={
            "provider_requests": 8,
            "credits_per_request": 5,
            "credits_per_request_source": SCREEN_SOURCE,
            "credits": 40,
            "authentication_calls": 8,
        }
    ),
    "the weights not among the data sent": lambda d: d.update(
        data_sent=data_sent(["universe", "rules", "ranking"])
    ),
    "a plan that revises itself": lambda d: d.update(revises=PLAN_HASH),
}


@pytest.mark.parametrize("change", PLAN_1_3_REJECTS.values(), ids=PLAN_1_3_REJECTS.keys())
def test_plan_1_3_rejects(change: Change) -> None:
    rejects(PlanV1_3, changed(plan_1_3, change))


@pytest.mark.parametrize(
    ("nodes", "weights"),
    [(THREE_NODES, (*WEIGHTS, ("Quality", "10"))), (ONE_NODE, (("Earnings Yield", "100"),))],
    ids=["one more", "one fewer"],
)
def test_a_variant_of_another_setting_with_other_weight_rows_says_so(
    nodes: str, weights: tuple[tuple[str, str], ...]
) -> None:
    """Its rows are the baseline's with exactly its change, so it has the baseline's weight
    rows: the error names them. Its definition is consistent with its own rows, so only that rule
    rejects it."""
    document = changed(
        plan_1_3,
        lambda d: use_definition(d, nodes, weights, case=2, values={"max_holdings": 50}),
    )

    with pytest.raises(ValidationError) as caught:
        PlanV1_3.model_validate_json(json.dumps(document))

    assert caught.value.errors(include_input=False)[0]["msg"] == (
        "Value error, a variant of max_holdings keeps the baseline's weight rows"
    )


def heavy_with(
    nodes: str,
    weights: tuple[tuple[str, str], ...],
    method: str = "percentile_nas_negative",
    holdings: int = 25,
) -> Change:
    """Gives the ranking variant another definition, ranking method, or holdings, its case
    consistent with them."""

    def change(document: Document) -> None:
        values: dict[str, object] | None = {"max_holdings": holdings} if holdings != 25 else None
        use_definition(document, nodes, weights, case=1, method=method, values=values)
        backtest_of(document, 1)["screen"].update(maxNumHoldings=holdings)

    return change


BY_THE_RULES = "a ranking variant's change follows the rules of ranking variants, and "
"""The start of the message for a ranking variant that breaks one of their rules, which then
gives the rule, by the entry at fault."""

EIGHTY = DEFINITION.replace('Weight="60.0"', 'Weight="80"').replace('Weight="40"', 'Weight="20"')
HEAVY_WEIGHTS = (("Earnings Yield", "70"), ("Sales Yield", "30"))

INCONSISTENT_PLAN_1_3: dict[str, tuple[Change, str]] = {
    "a ranking variant whose definition isn't its change's": (
        heavy_with(EIGHTY, (("Earnings Yield", "80"), ("Sales Yield", "20"))),
        "a ranking variant's definition is the baseline's with exactly its change",
    ),
    "a ranking variant whose weights don't keep their sum": (
        lambda d: (
            heavy_with(
                HEAVY.replace('Weight="30"', 'Weight="40"'),
                (("Earnings Yield", "70"), ("Sales Yield", "40")),
            )(d),
            heavy_variant(d)["set"][1].update(weight="40"),
        ),
        f"{BY_THE_RULES}`cases[1].variant.set` gives weights that don't sum",
    ),
    "a ranking variant that changes nothing": (
        lambda d: (
            heavy_with(DEFINITION, WEIGHTS)(d),
            heavy_variant(d).update(
                set=[
                    {"node": "Earnings Yield", "weight": "60"},
                    {"node": "Sales Yield", "weight": "40"},
                ]
            ),
        ),
        f"{BY_THE_RULES}`cases[1].variant.set` gives every node the weight it has",
    ),
    "a ranking variant that leaves a node out": (
        lambda d: heavy_variant(d).update(set=HEAVY_SET[:1]),
        f"{BY_THE_RULES}`cases[1].variant.set` leaves out its parent's node at position 2",
    ),
    "a ranking variant that names no node": (
        lambda d: heavy_variant(d)["set"][1].update(node="Quality"),
        f"{BY_THE_RULES}`cases[1].variant.set[1]` is a node path whose segment 1 names none",
    ),
    "a ranking variant's set by position": (
        lambda d: heavy_variant(d).update(
            set=[{"node": "#1", "weight": "70"}, {"node": "#2", "weight": "30"}]
        ),
        "a ranking variant's set names each node by its canonical path",
    ),
    "a ranking variant's set in another order": (
        lambda d: heavy_variant(d).update(set=HEAVY_SET[::-1]),
        "a ranking variant's set names each node by its canonical path",
    ),
    "a removal by a path that isn't canonical": (
        lambda d: (five_cases(d, removal_case()), case_of(d, 2)["variant"].update(remove="#2")),
        "a ranking variant's remove names the factor by its canonical path",
    ),
    "a ranking variant that changes the holdings too": (
        heavy_with(HEAVY, HEAVY_WEIGHTS, holdings=50),
        "a ranking variant keeps the baseline's max_holdings",
    ),
    "a ranking variant with another ranking method": (
        heavy_with(HEAVY, HEAVY_WEIGHTS, method="percentile_nas_neutral"),
        "a ranking variant keeps the baseline's ranking method",
    ),
    "two ranking variants with one definition": (
        lambda d: five_cases(
            d, heavy_case() | {"case_key": "heavy-again", "case_id": "case-0000000000000009"}
        ),
        "the cases' settings must not repeat",
    ),
    "a holdings variant on another definition": (
        lambda d: d["cases"].__setitem__(2, holdings_on_heavy()),
        "a variant of max_holdings keeps the baseline's ranking",
    ),
    "a holdings variant whose rank_update isn't its definition's": (
        lambda d: rank_params(d, 2).update(nodes=HEAVY),
        "a rank_update's nodes is the definition whose hash its case's ranking setting holds",
    ),
    "a ranking_source of another definition": (
        lambda d: d["ranking_source"].update(definition=HEAVY_ID),
        "ranking_source's definition is the hash of the baseline's definition",
    ),
    "provider requests below twice the cases": (
        lambda d: d["budget"].update(provider_requests=7, authentication_calls=7, credits=19),
        "the budget's provider_requests is at least twice the number of cases",
    ),
    "credits other than its costs give": (
        lambda d: d["budget"].update(credits=40),
        "credits is the most the provider requests can cost at the costs given",
    ),
}
"""Plan 1.3.0 changed one way, each breaking one of its consistency rules, with the start of its
rule's message."""


@pytest.mark.parametrize(
    ("change", "rule"),
    [*INCONSISTENT_CASE.values(), *INCONSISTENT_PLAN_1_3.values()],
    ids=[*INCONSISTENT_CASE, *INCONSISTENT_PLAN_1_3],
)
def test_plan_1_3_rejects_an_inconsistent_plan_by_its_own_rule(change: Change, rule: str) -> None:
    """R04-T07's consistency rules: each plan breaks one, and is rejected by it alone. A case's
    rules apply to the baseline, here, as to each case."""
    assert rejected_by(PlanV1_3, changed(plan_1_3, change)).startswith(f"Value error, {rule}")


@pytest.mark.parametrize(
    "case",
    [
        baseline_case() | {"variant": variant("ranking", set=HEAVY_SET)},
        heavy_case() | {"variant": None},
    ],
    ids=["a baseline with a variant", "a variant without one"],
)
def test_a_plan_1_3_case_is_the_baseline_exactly_when_it_has_no_variant(case: Document) -> None:
    """A case read alone, as the plan reads each of its cases."""
    accepts(ExperimentPlanCaseV1_3, baseline_case())
    rejects(ExperimentPlanCaseV1_3, case)


# The snapshot plan


def snapshot_entry(document: Document, index: int) -> Document:
    entry: Document = document["data_sent"][index]
    return entry


SNAPSHOT_PLAN_REJECTS: dict[str, Change] = {
    "a rank_get of another name": lambda d: d["requests"][0]["params"].update(name="Other"),
    "two requests": lambda d: d["requests"].append(d["requests"][0]),
    "a rank_update": lambda d: d["requests"][0].update(operation="rank_update"),
    "a rank_get with an id": lambda d: d["requests"][0]["params"].update(id=424242),
    "a blank system": lambda d: (
        d.update(system=" "),
        d["requests"][0]["params"].update(name=" "),
    ),
    "two provider requests": lambda d: d["budget"].update(provider_requests=2, credits=2),
    "a backtest's cost": lambda d: d["budget"].update(
        credits_per_request=5, credits=5, credits_per_request_source=SCREEN_SOURCE
    ),
    "a cost of 2": lambda d: d["budget"].update(credits_per_request=2, credits=2),
    "a source checked on another day": lambda d: d["budget"]["credits_per_request_source"].update(
        checked="2026-10-13"
    ),
    "backtest settings sent": lambda d: snapshot_entry(d, 1).update(category="backtest_settings"),
    "the system's name not sent": lambda d: snapshot_entry(d, 1).update(settings=[]),
    "the data sent in another order": lambda d: d["data_sent"].reverse(),
    "a third category": lambda d: d["data_sent"].append(snapshot_entry(d, 1)),
    "a title": lambda d: d.update(title="A snapshot"),
    "cases": lambda d: d.update(cases=[]),
}


@pytest.mark.parametrize("change", SNAPSHOT_PLAN_REJECTS.values(), ids=SNAPSHOT_PLAN_REJECTS.keys())
def test_snapshot_plan_rejects(change: Change) -> None:
    rejects(RankingSnapshotPlan, changed(snapshot_plan, change))
