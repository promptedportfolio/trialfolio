"""The plan compiler builds plans 1.2.0 and 1.3.0 from a ranking definition, as docs/contracts.md
specifies them, and revises an experiment's plan when its definition or its ranking method
changes.

Traces to release 0.4.0's test pairing, R04-AC01's core check, which R04-T07 wrote:
`ranking-example.yaml` compiles to plan 1.3.0 with its four cases, in the documented order, each
with its `rank_update`, whose `nodes` is the case's whole definition, the baseline's or the
baseline's with exactly its variant's change, byte for byte, with `rankingMethod` 2, `type`
`stock`, `currency` `USD`, and no `id`, then its backtest, ranked by `ApiRankingSystem`; each
case's settings hold the `ranking` row, with the definition's hash, and a weight row for each
node of its definition, by canonical path, 9, or 8 for `no-sales-yield`; each ranking variant's
`variant` holds `set` and `remove` by canonical paths; `ranking_source` is the file's; and the
budget is 8 requests, 8 authentication calls, the documented `costs`, and 24 credits. A byte
changed in the definition changes the baseline's `case_id` and the plan hash, while a copy with
Windows line endings gives the same plan; `ranking-written-differently.yaml` gives the same plan
and hash; `ranking-positions.yaml` names each node by its canonical path; `ranking-mixed.yaml`'s
`holdings-50` and `rebalance-weeks-1` send the baseline's definition; `definition.yaml` gives
plan 1.2.0, with 2 requests and 6 credits, whose case is `ranking-example.yaml`'s baseline; and
`example.yaml`'s `case_id`s, held by hand, are those 0.3.0 gave.

Also to R04-T07's row, the revisions a changed definition or ranking method gives, with
`experiment.json` 1.1.0 (plans with a ranking definition, revisions; `experiment.json`), with the
`revisions/ranking-*.yaml` fixtures: `ranking-definition-changed.yaml` keeps the cases whose
definitions don't change, and retires the others; `ranking-method-changed.yaml` retires every
case; `ranking-budget-raised.yaml` keeps them all; and `ranking-from-formula.yaml` revises
`example.yaml`'s plan 1.1.0 into a plan 1.3.0, whose `experiment.json` is 1.1.0, with the 1.0.0
record's entries written with `set` and `remove` null. A change of the definition's source alone
is a change of `ranking_source`. The configuration that gives the current plan resumes it, as
docs/contracts.md's running an experiment says, a plan that revises another included.

Also to R01-AC05: a version no release verified fails with `environment.unsupported` in both of
0.4.0's planners.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trialfolio.configuration import (
    read_experiment_configuration,
    read_experiment_configuration_v1_1,
    read_screen_configuration,
    read_screen_configuration_v1_1,
)
from trialfolio.contracts.experiment_plan import ExperimentPlanCaseV1_3, PlanV1_1, PlanV1_3
from trialfolio.contracts.experiment_record import ExperimentRecord, ExperimentRecordV1_1
from trialfolio.contracts.plan import PlanSettingV1_2, PlanV1_2
from trialfolio.errors import TrialFolioError
from trialfolio.planning import (
    VERIFIED_VERSIONS,
    PlanRevisionV1_1,
    Versions,
    build_experiment_plan,
    build_experiment_plan_v1_1,
    build_plan,
    build_plan_v1_1,
    case_id,
    first_experiment_record_v1_1,
    plan_changes_v1_1,
    plan_hash,
    plan_revision_v1_1,
    revised_experiment_record_v1_1,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENTS = REPO_ROOT / "tests" / "fixtures" / "experiment-configs"
DEFINITIONS = EXPERIMENTS / "ranking"
REVISIONS = EXPERIMENTS / "revisions"
SCREENS = REPO_ROOT / "tests" / "fixtures" / "screen-configs"

VERSIONS = Versions(
    trialfolio="0.4.0",
    p123api=VERIFIED_VERSIONS["p123api"][0],
    requests=VERIFIED_VERSIONS["requests"][0],
    urllib3=VERIFIED_VERSIONS["urllib3"][0],
)

CREATED_AT = datetime(2026, 10, 15, 12, 0, 0, tzinfo=UTC)

EXAMPLE_KEYS = ["baseline", "value-heavy", "tilt-earnings-yield", "no-sales-yield"]

COSTS = [
    {
        "operation": "rank_update",
        "credits_per_request": 1,
        "source": {
            "title": "API functions: Rank",
            "url": "https://portfolio123.customerly.help/en/articles/43323-api-rank",
            "checked": "2026-10-12",
        },
    },
    {
        "operation": "screen_backtest",
        "credits_per_request": 5,
        "source": {
            "title": "API: Screen",
            "url": "https://portfolio123.customerly.help/en/articles/43324-api-screen",
            "checked": "2026-10-01",
        },
    },
]
"""`costs`, exactly as docs/contracts.md's plans with a ranking definition gives it."""

EXAMPLE_CASE_IDS_IN_0_3_0 = {
    "baseline": "case-e29404ddebf86363",
    "liquidity-100m": "case-b5d8a262354ab93d",
    "holdings-50": "case-edb681850dd8e058",
    "rebalance-weeks-1": "case-0492159b4461ceff",
    "slippage-050": "case-5dd6bf5d608d3956",
}
"""`example.yaml`'s `case_id`s as Trial Folio 0.3.0's planner gave them, at the tag `v0.3.0`."""


def digest(number: int) -> str:
    """A well-formed `artifact_id`, distinct for each number."""
    return f"sha256:{number:064x}"


def hash_of(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def plan_of(path: Path, revises: str | None = None) -> PlanV1_1 | PlanV1_3:
    read = read_experiment_configuration_v1_1(path.read_bytes(), path.name, path)
    return build_experiment_plan_v1_1(read, VERSIONS, revises)


def ranking_plan(path: Path) -> PlanV1_3:
    plan = plan_of(path)
    assert isinstance(plan, PlanV1_3)
    return plan


def by_key(plan: PlanV1_3) -> dict[str, ExperimentPlanCaseV1_3]:
    return {case.case_key: case for case in plan.cases}


def weights(case: ExperimentPlanCaseV1_3) -> list[tuple[str | None, object]]:
    return [(row.node, row.value) for row in case.settings if row.setting == "ranking_weight"]


def ranking_row(case: ExperimentPlanCaseV1_3) -> PlanSettingV1_2:
    (row,) = (row for row in case.settings if row.setting == "ranking")
    return row


def reweighted(text: str, *changes: tuple[str, str, str]) -> str:
    """`text` with each named node's weight changed, as written by hand."""
    for name, old, new in changes:
        written = f'Name="{name}" Weight="{old}"'
        assert text.count(written) == 1
        text = text.replace(written, f'Name="{name}" Weight="{new}"')
    return text


BASELINE = (DEFINITIONS / "value-momentum.xml").read_text(encoding="utf-8")
LINES = BASELINE.split("\n")
assert LINES[5].startswith('\t\t<StockFormula Name="Sales Yield"')
DEFINITIONS_BY_KEY = {
    "baseline": BASELINE,
    "value-heavy": (DEFINITIONS / "value-heavy.xml").read_text(encoding="utf-8"),
    "tilt-earnings-yield": reweighted(
        BASELINE, ("Earnings Yield", "50", "70"), ("Sales Yield", "50", "30")
    ),
    "no-sales-yield": reweighted("\n".join(LINES[:5] + LINES[8:]), ("Earnings Yield", "50", "100")),
}
"""Each case's definition, as the ranking example describes it: the baseline's, its top-level
weights at 60, 20, and 20, its Value factors at 70 and 30, and its Sales Yield removed, with its
line, and Earnings Yield at 100."""

BASELINE_WEIGHTS = [
    ("Value", "40"),
    ("Value/Earnings Yield", "50"),
    ("Value/Sales Yield", "50"),
    ("Momentum", "30"),
    ("Momentum/Six-Month Return", "50"),
    ("Momentum/Year Return", "50"),
    ("Quality", "30"),
    ("Quality/Return on Equity", "50"),
    ("Quality/Gross Margin", "50"),
]


def with_weights(changed: dict[str, str | None]) -> list[tuple[str, str]]:
    """The baseline's weight rows, with each named node's weight changed, or the node removed."""
    rows: list[tuple[str, str]] = []
    for node, weight in BASELINE_WEIGHTS:
        new = changed.get(node, weight)
        if new is not None:
            rows.append((node, new))
    return rows


WEIGHTS_BY_KEY = {
    "baseline": BASELINE_WEIGHTS,
    "value-heavy": with_weights({"Value": "60", "Momentum": "20", "Quality": "20"}),
    "tilt-earnings-yield": with_weights({"Value/Earnings Yield": "70", "Value/Sales Yield": "30"}),
    "no-sales-yield": with_weights({"Value/Earnings Yield": "100", "Value/Sales Yield": None}),
}


# The plan of the ranking example


def test_the_ranking_example_compiles_to_plan_1_3_with_its_four_cases() -> None:
    plan = ranking_plan(EXPERIMENTS / "ranking-example.yaml")

    assert plan.schema_version == "1.3.0"
    assert [case.case_key for case in plan.cases] == EXAMPLE_KEYS
    assert [case.description for case in plan.cases] == [
        None,
        "More weight on value, taken equally from momentum and quality.",
        None,
        None,
    ]
    assert plan.revises is None


@pytest.mark.parametrize("key", EXAMPLE_KEYS)
def test_each_case_writes_its_whole_definition_then_backtests_ranked_by_api_ranking_system(
    key: str,
) -> None:
    case = by_key(ranking_plan(EXPERIMENTS / "ranking-example.yaml"))[key]

    update, backtest = (request.model_dump(mode="json") for request in case.requests)
    assert update == {
        "operation": "rank_update",
        "params": {
            "type": "stock",
            "nodes": DEFINITIONS_BY_KEY[key],
            "rankingMethod": 2,
            "currency": "USD",
        },
    }
    assert list(update["params"]) == ["type", "nodes", "rankingMethod", "currency"]
    assert backtest["operation"] == "screen_backtest"
    assert backtest["params"]["screen"]["ranking"] == "ApiRankingSystem"
    assert backtest["params"]["screen"]["maxNumHoldings"] == 25
    assert backtest["params"]["rebalFreq"] == "Every 4 Weeks"


@pytest.mark.parametrize("key", EXAMPLE_KEYS)
def test_each_case_holds_its_definition_s_hash_and_a_weight_row_for_each_of_its_nodes(
    key: str,
) -> None:
    case = by_key(ranking_plan(EXPERIMENTS / "ranking-example.yaml"))[key]

    assert ranking_row(case).model_dump(mode="json") == {
        "setting": "ranking",
        "node": None,
        "category": "strategy",
        "critical": True,
        "value": {
            "definition": hash_of(DEFINITIONS_BY_KEY[key]),
            "ranking_method": "percentile_nas_negative",
        },
        "unit": None,
        "interpretation": "interpreted",
        "expected_provenance": "verified",
        "inference_rule": None,
        "flags": [],
    }
    assert weights(case) == WEIGHTS_BY_KEY[key]
    assert len(weights(case)) == (8 if key == "no-sales-yield" else 9)
    names = [row.setting for row in case.settings]
    first = names.index("ranking_weight")
    assert names[first - 1] == "ranking"
    assert names[first + len(weights(case))] == "max_holdings"
    row = next(row for row in case.settings if row.setting == "ranking_weight")
    assert row.model_dump(mode="json", exclude={"node", "value"}) == {
        "setting": "ranking_weight",
        "category": "strategy",
        "critical": True,
        "unit": None,
        "interpretation": "interpreted",
        "expected_provenance": "verified",
        "inference_rule": None,
        "flags": [],
    }
    assert case.case_id == case_id(case.settings)


def test_a_case_id_covers_each_weight_row_by_its_node() -> None:
    """Plan hashing: a weight row is reduced to its `setting`, `node`, `value`, and `unit`, and
    every other row to its `setting`, `value`, and `unit`, computed here from the rule."""
    case = by_key(ranking_plan(EXPERIMENTS / "ranking-example.yaml"))["no-sales-yield"]
    rows = []
    for row in case.settings:
        kept = {"setting", "value", "unit"} | (
            {"node"} if row.setting == "ranking_weight" else set()
        )
        rows.append(
            {key: value for key, value in row.model_dump(mode="json").items() if key in kept}
        )
    # RFC 8785 writes these values, text, whole numbers, null, and mappings of them, as json does
    # with its keys sorted and no white space.
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    assert case.case_id == "case-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    assert any("node" in row for row in rows)


def test_each_ranking_variant_gives_set_and_remove_by_canonical_paths() -> None:
    plan = ranking_plan(EXPERIMENTS / "ranking-example.yaml")

    unchanged = {"value": None, "add": None, "replace": None, "with": None, "default": False}
    assert [
        None if case.variant is None else case.variant.model_dump(mode="json")
        for case in plan.cases
    ] == [
        None,
        unchanged
        | {
            "setting": "ranking",
            "set": [
                {"node": "Value", "weight": "60"},
                {"node": "Momentum", "weight": "20"},
                {"node": "Quality", "weight": "20"},
            ],
            "remove": None,
        },
        unchanged
        | {
            "setting": "ranking",
            "set": [
                {"node": "Value/Earnings Yield", "weight": "70"},
                {"node": "Value/Sales Yield", "weight": "30"},
            ],
            "remove": None,
        },
        unchanged
        | {
            "setting": "ranking",
            "set": [{"node": "Value/Earnings Yield", "weight": "100"}],
            "remove": "Value/Sales Yield",
        },
    ]


def test_the_plan_records_the_file_s_source_and_a_budget_with_each_operation_s_cost() -> None:
    built = ranking_plan(EXPERIMENTS / "ranking-example.yaml")
    saved = PlanV1_3.model_validate_json(built.model_dump_json(indent=2))
    plan = saved.model_dump(mode="json")

    assert plan["ranking_source"] == {
        "form": "definition",
        "definition": hash_of(BASELINE),
        "system": None,
        "snapshot_record": None,
        "snapshot_definition": None,
    }
    assert plan["budget"] == {
        "provider_requests": 8,
        "costs": COSTS,
        "credits": 24,
        "authentication_calls": 8,
    }
    assert [entry["settings"] for entry in plan["data_sent"]][1] == [
        "universe",
        "rules",
        "ranking",
        "ranking_weight",
    ]
    assert list(plan) == [
        "schema_version",
        "trialfolio_version",
        "canonicalization_version",
        "provider_wrapper",
        "transport",
        "experiment_id",
        "title",
        "purpose",
        "prior_research",
        "ranking_source",
        "revises",
        "cases",
        "budget",
        "retry_policy",
        "data_sent",
        "plan_hash",
    ]
    assert plan_hash(saved) == saved.plan_hash == built.plan_hash


def copy_example(directory: Path, definition: bytes | None = None) -> Path:
    """`ranking-example.yaml` and its definition, copied into `directory`, the definition
    replaced by `definition` when given."""
    (directory / "ranking").mkdir()
    (directory / "ranking" / "value-momentum.xml").write_bytes(
        definition or BASELINE.encode("utf-8")
    )
    path = directory / "ranking-example.yaml"
    path.write_bytes((EXPERIMENTS / "ranking-example.yaml").read_bytes())
    return path


def test_a_byte_changed_in_the_definition_changes_the_baseline_s_case_and_the_plan_hash(
    tmp_path: Path,
) -> None:
    example = ranking_plan(EXPERIMENTS / "ranking-example.yaml")
    changed = BASELINE.replace("<Formula>…</Formula>", "<Formula>…!</Formula>", 1)

    plan = ranking_plan(copy_example(tmp_path, changed.encode("utf-8")))

    assert by_key(plan)["baseline"].case_id != by_key(example)["baseline"].case_id
    assert plan.plan_hash != example.plan_hash
    assert plan.ranking_source.definition == hash_of(changed)


def test_a_definition_with_windows_line_endings_gives_the_same_plan(tmp_path: Path) -> None:
    windows = BASELINE.replace("\n", "\r\n").encode("utf-8")

    plan = ranking_plan(copy_example(tmp_path, windows))

    assert plan == ranking_plan(EXPERIMENTS / "ranking-example.yaml")


def test_a_file_written_differently_gives_the_same_plan_and_hash() -> None:
    example = ranking_plan(EXPERIMENTS / "ranking-example.yaml")

    written_differently = ranking_plan(EXPERIMENTS / "ranking-written-differently.yaml")

    assert written_differently == example
    assert written_differently.plan_hash == example.plan_hash


def test_ranking_positions_names_each_node_by_its_canonical_path() -> None:
    plan = ranking_plan(EXPERIMENTS / "ranking-positions.yaml")

    baseline, heavy, removal = plan.cases
    assert weights(baseline) == [
        ("Value P\\/E", "25"),
        ("Value P\\/E/#1", "40"),
        ("Value P\\/E/#2", "40"),
        ("Value P\\/E/Cash Flow", "20"),
        ("#2", "10"),
        ("#3", "10"),
        ("Price\\\\Book", "20"),
        ("Price\\\\Book/Book Yield", "100"),
        ("\\#Momentum", "15"),
        ("\\#Momentum/Short Return", "50"),
        ("\\#Momentum/Long Return", "50"),
        ("Secret Sauce", "20"),
        ("Secret Sauce/Margin", "60"),
        ("Secret Sauce/Turnover", "40"),
    ]
    assert heavy.variant is not None and removal.variant is not None
    assert [(entry.node, entry.weight) for entry in heavy.variant.set or ()] == [
        ("Value P\\/E", "30"),
        ("#2", "5"),
        ("#3", "5"),
        ("Price\\\\Book", "25"),
        ("\\#Momentum", "15"),
        ("Secret Sauce", "20"),
    ]
    assert removal.variant.remove == "Value P\\/E/#1"
    assert [(entry.node, entry.weight) for entry in removal.variant.set or ()] == [
        ("Value P\\/E/#2", "60"),
        ("Value P\\/E/Cash Flow", "40"),
    ]
    # The factor left of the two that shared a name has it alone now, so its path is the name.
    assert weights(removal)[:3] == [
        ("Value P\\/E", "25"),
        ("Value P\\/E/Yield", "60"),
        ("Value P\\/E/Cash Flow", "40"),
    ]
    assert plan.budget.model_dump(mode="json")["credits"] == 18


def test_ranking_mixed_s_variants_of_other_settings_send_the_baseline_s_definition() -> None:
    plan = ranking_plan(EXPERIMENTS / "ranking-mixed.yaml")

    cases = by_key(plan)
    assert list(cases) == ["baseline", "value-heavy", "holdings-50", "rebalance-weeks-1"]
    baseline = cases["baseline"]
    for key, setting, value in (
        ("holdings-50", "max_holdings", 50),
        ("rebalance-weeks-1", "rebalance_weeks", 1),
    ):
        case = cases[key]
        assert case.requests[0] == baseline.requests[0], key
        assert case.requests[0].params.nodes == BASELINE
        changed = [
            (own.setting, own.value)
            for own, base in zip(case.settings, baseline.settings, strict=True)
            if own != base
        ]
        assert changed == [(setting, value)], key
        assert case.variant is not None
        assert (case.variant.setting, case.variant.set, case.variant.remove) == (
            setting,
            None,
            None,
        )
    assert cases["rebalance-weeks-1"].variant is not None
    assert cases["rebalance-weeks-1"].variant.default is True
    assert cases["value-heavy"].requests[0].params.nodes == DEFINITIONS_BY_KEY["value-heavy"]
    assert plan.budget.credits == 24


def test_definition_yaml_gives_plan_1_2_whose_case_is_the_example_s_baseline() -> None:
    path = SCREENS / "definition.yaml"
    read = read_screen_configuration_v1_1(path.read_bytes(), path.name, path)

    plan = build_plan_v1_1(read, VERSIONS)

    assert isinstance(plan, PlanV1_2)
    (case,) = plan.cases
    baseline = by_key(ranking_plan(EXPERIMENTS / "ranking-example.yaml"))["baseline"]
    assert (case.case_id, case.requests, case.settings) == (
        baseline.case_id,
        baseline.requests,
        baseline.settings,
    )
    assert plan.model_dump(mode="json")["budget"] == {
        "provider_requests": 2,
        "costs": COSTS,
        "credits": 6,
        "authentication_calls": 1,
    }
    assert plan.ranking_source.model_dump(mode="json") == {
        "form": "definition",
        "definition": hash_of(BASELINE),
        "system": None,
        "snapshot_record": None,
        "snapshot_definition": None,
    }
    assert (plan.title, plan.purpose) == (
        "Value, momentum, and quality with a liquidity floor",
        "The ranking example's baseline, as a screen run.",
    )
    assert list(plan.model_dump()) == [
        "schema_version",
        "trialfolio_version",
        "canonicalization_version",
        "provider_wrapper",
        "transport",
        "title",
        "purpose",
        "ranking_source",
        "cases",
        "budget",
        "retry_policy",
        "data_sent",
        "plan_hash",
    ]
    assert plan.plan_hash == plan_hash(plan)


def test_a_case_without_a_definition_keeps_the_case_id_0_3_0_gave() -> None:
    """A screen or an experiment ranked another way gives plan 1.0.0 or 1.1.0, as 0.3.0's planner
    does, whichever version its file is."""
    path = EXPERIMENTS / "example.yaml"
    text = path.read_text(encoding="utf-8")
    as_1_1_0 = text.replace("schema_version: 1.0.0\n", "schema_version: 1.1.0\n")
    assert as_1_1_0 != text

    plan = plan_of(path)
    plan_1_1_0 = build_experiment_plan_v1_1(
        read_experiment_configuration_v1_1(as_1_1_0.encode(), path.name, path), VERSIONS
    )

    assert isinstance(plan, PlanV1_1)
    assert {case.case_key: case.case_id for case in plan.cases} == EXAMPLE_CASE_IDS_IN_0_3_0
    assert plan == plan_1_1_0
    assert plan == build_experiment_plan(
        read_experiment_configuration(path.read_bytes(), path.name), VERSIONS
    )
    screen = SCREENS / "formula.yaml"
    screen_text = screen.read_text(encoding="utf-8")
    screen_1_1_0 = screen_text.replace("schema_version: 1.0.0\n", "schema_version: 1.1.0\n")
    assert screen_1_1_0 != screen_text
    screen_plan = build_plan(read_screen_configuration(screen.read_bytes(), screen.name), VERSIONS)
    for text in (screen_text, screen_1_1_0):
        read = read_screen_configuration_v1_1(text.encode(), screen.name, screen)
        assert build_plan_v1_1(read, VERSIONS) == screen_plan


def test_a_baseline_named_by_a_snapshot_isn_t_planned_until_its_definition_is_read(
    tmp_path: Path,
) -> None:
    """Release 0.4.0's R04-T10 reads a snapshot, and its definition, which the plan holds."""
    path = tmp_path / "ranking-example.yaml"
    path.write_text(
        (EXPERIMENTS / "ranking-example.yaml")
        .read_text(encoding="utf-8")
        .replace(
            "    definition: 'ranking/value-momentum.xml'\n"
            "    ranking_method: percentile_nas_negative\n",
            "    snapshot: 'ranking/value-momentum/'\n",
        ),
        encoding="utf-8",
    )
    read = read_experiment_configuration_v1_1(path.read_bytes(), path.name, path)

    with pytest.raises(TypeError, match="snapshot"):
        build_experiment_plan_v1_1(read, VERSIONS)


@pytest.mark.parametrize("kind", ["screen", "experiment"])
def test_a_version_no_release_verified_isn_t_planned(kind: str) -> None:
    unverified = Versions("0.4.0", "3.1.0", "2.34.3", "2.8.0")

    with pytest.raises(TrialFolioError) as raised:
        if kind == "screen":
            path = SCREENS / "definition.yaml"
            build_plan_v1_1(
                read_screen_configuration_v1_1(path.read_bytes(), path.name, path), unverified
            )
        else:
            path = EXPERIMENTS / "ranking-example.yaml"
            build_experiment_plan_v1_1(
                read_experiment_configuration_v1_1(path.read_bytes(), path.name, path), unverified
            )

    assert raised.value.code == "environment.unsupported"
    assert "The installed requests is 2.34.3." in raised.value.message


# Revisions


def revision_of(path: Path, current: PlanV1_1 | PlanV1_3) -> PlanRevisionV1_1:
    read = read_experiment_configuration_v1_1(path.read_bytes(), path.name, path)
    revision = plan_revision_v1_1(read, VERSIONS, current)
    assert revision is not None
    return revision


def first_record(plan: PlanV1_1 | PlanV1_3) -> ExperimentRecord | ExperimentRecordV1_1:
    return first_experiment_record_v1_1(
        plan,
        plan_artifact_id=digest(1),
        configuration_artifact_id=digest(2),
        approval="option",
        created_at=CREATED_AT,
    )


def revised_record(
    previous: ExperimentRecord | ExperimentRecordV1_1, revision: PlanRevisionV1_1, number: int
) -> ExperimentRecord | ExperimentRecordV1_1:
    return revised_experiment_record_v1_1(
        previous,
        revision,
        number=number,
        reason="The ranking changed.",
        plan_artifact_id=digest(2 * number + 1),
        configuration_artifact_id=digest(2 * number + 2),
        approval="option",
        created_at=CREATED_AT,
    )


@pytest.mark.parametrize("name", ["ranking-example.yaml", "ranking-written-differently.yaml"])
def test_the_configuration_that_gives_the_current_plan_resumes_it(name: str) -> None:
    current = ranking_plan(EXPERIMENTS / "ranking-example.yaml")
    path = EXPERIMENTS / name
    read = read_experiment_configuration_v1_1(path.read_bytes(), path.name, path)

    assert plan_revision_v1_1(read, VERSIONS, current) is None


@pytest.mark.parametrize(
    ("first", "revised"),
    [
        (EXPERIMENTS / "ranking-example.yaml", REVISIONS / "ranking-definition-changed.yaml"),
        (EXPERIMENTS / "example.yaml", REVISIONS / "ranking-from-formula.yaml"),
    ],
    ids=["definition-changed", "from-formula"],
)
def test_the_configuration_that_gave_a_revision_resumes_it(first: Path, revised: Path) -> None:
    """The revision's plan is built again with its own `revises`, the hash of the plan it revised,
    so the configuration that gave it gives it again, and the experiment resumes."""
    current = revision_of(revised, plan_of(first)).plan
    assert isinstance(current, PlanV1_3)
    assert current.revises is not None
    read = read_experiment_configuration_v1_1(revised.read_bytes(), revised.name, revised)

    assert plan_revision_v1_1(read, VERSIONS, current) is None


def test_a_changed_definition_keeps_the_cases_whose_definition_doesn_t_change() -> None:
    current = ranking_plan(EXPERIMENTS / "ranking-example.yaml")

    revision = revision_of(REVISIONS / "ranking-definition-changed.yaml", current)

    plan = revision.plan
    assert isinstance(plan, PlanV1_3)
    assert plan.revises == current.plan_hash
    before, after = by_key(current), by_key(plan)
    for key in ("tilt-earnings-yield", "no-sales-yield"):
        assert after[key].case_id == before[key].case_id
        assert after[key].requests[0] == before[key].requests[0]
    changes = revision.changes.model_dump(mode="json")
    assert changes == {
        "versions": [],
        "cases_added": [
            {"case_id": after["baseline"].case_id, "case_key": "baseline"},
            {"case_id": after["value-heavy"].case_id, "case_key": "value-heavy"},
        ],
        "cases_retired": [
            {"case_id": before["baseline"].case_id, "case_key": "baseline"},
            {"case_id": before["value-heavy"].case_id, "case_key": "value-heavy"},
        ],
        "parts": ["budget"],
    }
    assert plan.ranking_source.definition == hash_of(
        (DEFINITIONS / "value-momentum-revised.xml").read_text(encoding="utf-8")
    )
    record = revised_record(first_record(current), revision, 2)
    assert isinstance(record, ExperimentRecordV1_1)
    assert [(case.case_key, case.plan) for case in record.retired_cases] == [
        ("baseline", 1),
        ("value-heavy", 1),
    ]
    assert record.retired_cases[1].variant == before["value-heavy"].variant
    assert record.plans[-1].changes == revision.changes
    # A later revision keeps them, with the last plan that included them.
    path = REVISIONS / "ranking-definition-changed.yaml"
    raised = path.read_bytes().replace(b"provider_requests: 12\n", b"provider_requests: 14\n")
    third = plan_revision_v1_1(
        read_experiment_configuration_v1_1(raised, path.name, path), VERSIONS, plan
    )
    assert third is not None and third.changes.parts == ("budget",)
    later = revised_record(record, third, 3)
    assert [(case.case_key, case.plan) for case in later.retired_cases] == [
        ("baseline", 1),
        ("value-heavy", 1),
    ]


def test_a_changed_ranking_method_retires_every_case() -> None:
    current = ranking_plan(EXPERIMENTS / "ranking-example.yaml")

    revision = revision_of(REVISIONS / "ranking-method-changed.yaml", current)

    plan = revision.plan
    assert isinstance(plan, PlanV1_3)
    assert [case.requests[0].params.rankingMethod for case in plan.cases] == [4, 4, 4, 4]
    assert [change.case_key for change in revision.changes.cases_added] == EXAMPLE_KEYS
    assert [change.case_key for change in revision.changes.cases_retired] == EXAMPLE_KEYS
    assert revision.changes.parts == ()


def test_a_raised_budget_keeps_every_case() -> None:
    current = ranking_plan(EXPERIMENTS / "ranking-example.yaml")

    revision = revision_of(REVISIONS / "ranking-budget-raised.yaml", current)

    assert [case.case_id for case in revision.plan.cases] == [
        case.case_id for case in current.cases
    ]
    assert revision.changes.model_dump(mode="json") == {
        "versions": [],
        "cases_added": [],
        "cases_retired": [],
        "parts": ["budget"],
    }
    assert revision.plan.budget.model_dump(mode="json")["credits"] == 30


def test_a_plan_1_1_0_from_a_formula_is_revised_into_a_plan_1_3_0() -> None:
    current = plan_of(EXPERIMENTS / "example.yaml")
    assert isinstance(current, PlanV1_1)
    previous = first_record(current)
    assert isinstance(previous, ExperimentRecord)

    revision = revision_of(REVISIONS / "ranking-from-formula.yaml", current)

    plan = revision.plan
    assert isinstance(plan, PlanV1_3)
    assert plan.revises == current.plan_hash
    keys = list(EXAMPLE_CASE_IDS_IN_0_3_0)
    assert [case.case_key for case in plan.cases] == keys
    assert [change.case_key for change in revision.changes.cases_retired] == keys
    assert [change.case_key for change in revision.changes.cases_added] == keys
    assert revision.changes.parts == ("budget",)
    assert plan.budget.model_dump(mode="json") == {
        "provider_requests": 15,
        "costs": COSTS,
        "credits": 43,
        "authentication_calls": 15,
    }
    record = revised_record(previous, revision, 2)
    assert isinstance(record, ExperimentRecordV1_1)
    written = record.model_dump(mode="json")
    held = previous.model_dump(mode="json")
    assert written["plans"][0] == held["plans"][0]
    assert written["retired_cases"] == [
        case | {"variant": with_set_and_remove(case["variant"]), "plan": 1}
        for case in held["planned_cases"]
    ]


def with_set_and_remove(variant: dict[str, object] | None) -> dict[str, object] | None:
    """A 1.0.0 `experiment.json`'s variant as 1.1.0 writes it: with `set` and `remove` null,
    after `with`, and otherwise unchanged."""
    if variant is None:
        return None
    keys = ["setting", "value", "add", "replace", "with", "set", "remove", "default"]
    return {key: variant.get(key) for key in keys}


def test_a_revision_between_versions_changes_the_budget_with_the_same_requests() -> None:
    """Plan 1.1.0's budget and plan 1.3.0's differ in form and credits, so a revision from one to
    the other changes `budget`, even when `budget.provider_requests` is the same."""
    example = EXPERIMENTS / "example.yaml"
    ten = example.read_bytes().replace(b"provider_requests: 6\n", b"provider_requests: 10\n")
    current = build_experiment_plan_v1_1(
        read_experiment_configuration_v1_1(ten, example.name, example), VERSIONS
    )
    path = REVISIONS / "ranking-from-formula.yaml"
    ranked = path.read_bytes().replace(b"provider_requests: 15\n", b"provider_requests: 10\n")

    revision = plan_revision_v1_1(
        read_experiment_configuration_v1_1(ranked, path.name, path), VERSIONS, current
    )

    assert revision is not None
    assert current.budget.provider_requests == revision.plan.budget.provider_requests == 10
    assert revision.changes.parts == ("budget",)


def test_a_plan_1_3_0_revised_back_to_a_formula_keeps_experiment_json_1_1_0() -> None:
    first = plan_of(EXPERIMENTS / "example.yaml")
    ranked = revision_of(REVISIONS / "ranking-from-formula.yaml", first)
    second = revised_record(first_record(first), ranked, 2)

    revision = revision_of(EXPERIMENTS / "example.yaml", ranked.plan)

    assert isinstance(revision.plan, PlanV1_1)
    assert [case.case_id for case in revision.plan.cases] == list(
        EXAMPLE_CASE_IDS_IN_0_3_0.values()
    )
    record = revised_record(second, revision, 3)
    assert isinstance(record, ExperimentRecordV1_1)
    assert [(case.case_key, case.plan) for case in record.retired_cases] == [
        (key, 2) for key in EXAMPLE_CASE_IDS_IN_0_3_0
    ]
    assert [entry.plan for entry in record.plans] == [1, 2, 3]


def test_a_revision_of_plans_1_1_0_alone_keeps_experiment_json_1_0_0() -> None:
    current = plan_of(EXPERIMENTS / "example.yaml")

    revision = revision_of(REVISIONS / "holdings-40.yaml", current)

    record = revised_record(first_record(current), revision, 2)
    assert isinstance(record, ExperimentRecord)
    assert record.plans[-1].changes is not None
    assert record.plans[-1].changes.model_dump() == revision.changes.model_dump()


def test_the_first_record_of_a_plan_1_3_0_is_experiment_json_1_1_0() -> None:
    plan = ranking_plan(EXPERIMENTS / "ranking-example.yaml")

    record = first_record(plan)

    assert isinstance(record, ExperimentRecordV1_1)
    assert [case.variant for case in record.planned_cases] == [case.variant for case in plan.cases]
    assert record.plans[0].plan_hash == plan.plan_hash


def test_a_change_of_the_definition_s_source_alone_is_a_change_of_ranking_source() -> None:
    """A snapshot of the definition the file held keeps every case, and `experiment.json`
    records the change as `ranking_source`."""
    current = ranking_plan(EXPERIMENTS / "ranking-example.yaml")
    snapshot = current.ranking_source.model_copy(
        update={
            "form": "snapshot",
            "system": "Value and momentum",
            "snapshot_record": digest(7),
            "snapshot_definition": digest(8),
        }
    )
    draft = current.model_copy(update={"ranking_source": snapshot, "revises": current.plan_hash})
    revision = PlanV1_3.model_validate_json(
        draft.model_copy(update={"plan_hash": plan_hash(draft)}).model_dump_json()
    )

    changes = plan_changes_v1_1(current, revision)

    assert changes.model_dump(mode="json") == {
        "versions": [],
        "cases_added": [],
        "cases_retired": [],
        "parts": ["ranking_source"],
    }


def test_another_experiment_isn_t_a_revision() -> None:
    current = ranking_plan(EXPERIMENTS / "ranking-example.yaml")
    path = EXPERIMENTS / "ranking-mixed.yaml"
    read = read_experiment_configuration_v1_1(path.read_bytes(), path.name, path)

    with pytest.raises(TrialFolioError) as raised:
        plan_revision_v1_1(read, VERSIONS, current)

    assert raised.value.code == "output.not_empty"
    assert "another experiment" in raised.value.message
