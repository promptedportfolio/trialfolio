"""The plan compiler builds an experiment's plan 1.1.0 as docs/contracts.md specifies it, and its
revision rules say what a changed configuration revises, and what `experiment.json` records of it.

Traces to release 0.3.0's test pairing: R03-AC01 (`example.yaml` compiles to its five cases, in
the documented order, each the baseline with exactly its variant's change, with the `case_id` and
request of the screen configuration with its settings; only the default is marked default; the
budget; `no-microcaps.yaml`'s two cases, with no default), R03-AC02 (`written-differently.yaml`
gives `example.yaml`'s plan and hash, and a case's `case_id` doesn't depend on its key, its
description, or its place), and R03-AC07's core check (each change docs/contracts.md's experiment
plans and revisions lists is a revision, with the cases kept, added, and retired, and the parts
changed, that `experiment.json` records; another `experiment_id` or universe isn't a revision;
and a plan built with other versions is a change of versions alone). Also to docs/contracts.md:
the experiment's budget, the default variant, the order of cases, plan hashing, and
`experiment.json`; and fixtures, whose README lists each revision. R03-T07 wrote them, and the
review of its pull request added the budget's bound and a budget whose documented cost changed.
"""

import os
import re
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from trialfolio.configuration import read_experiment_configuration, read_screen_configuration
from trialfolio.contracts.common import TransportVersions, WrapperVersions
from trialfolio.contracts.experiment_configuration import ExperimentConfiguration
from trialfolio.contracts.experiment_plan import ExperimentPlanCase, PlanV1_1
from trialfolio.contracts.experiment_record import CaseChange, ExperimentRecord
from trialfolio.contracts.plan import CREDITS_PER_REQUEST_SOURCE, PlanSetting
from trialfolio.errors import TrialFolioError
from trialfolio.planning import (
    VERIFIED_VERSIONS,
    PlanRevision,
    Versions,
    build_experiment_plan,
    build_plan,
    case_id,
    first_experiment_record,
    plan_hash,
    plan_revision,
    revised_experiment_record,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENTS = REPO_ROOT / "tests" / "fixtures" / "experiment-configs"
REVISIONS = EXPERIMENTS / "revisions"
SCREENS = REPO_ROOT / "tests" / "fixtures" / "screen-configs"

VERSIONS = Versions(
    trialfolio="0.3.0",
    p123api=VERIFIED_VERSIONS["p123api"][0],
    requests=VERIFIED_VERSIONS["requests"][0],
    urllib3=VERIFIED_VERSIONS["urllib3"][0],
)

EXAMPLE_KEYS = ["baseline", "liquidity-100m", "holdings-50", "rebalance-weeks-1", "slippage-050"]

CREATED_AT = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)


def digest(number: int) -> str:
    """A well-formed `artifact_id`, distinct for each number."""
    return f"sha256:{number:064x}"


def read(path: Path) -> ExperimentConfiguration:
    return read_experiment_configuration(path.read_bytes(), path.name)


def from_text(text: str) -> ExperimentConfiguration:
    return read_experiment_configuration(text.encode(), "experiment.yaml")


def plan_of(path: Path, versions: Versions = VERSIONS) -> PlanV1_1:
    return build_experiment_plan(read(path), versions)


def example_text() -> str:
    return (EXPERIMENTS / "example.yaml").read_text(encoding="utf-8")


def edited(old: str, new: str, text: str | None = None) -> str:
    """`example.yaml`'s text, or `text`, with `old`, which it holds once, replaced by `new`."""
    text = example_text() if text is None else text
    assert text.count(old) == 1, old
    return text.replace(old, new)


def by_key(plan: PlanV1_1) -> dict[str, ExperimentPlanCase]:
    return {case.case_key: case for case in plan.cases}


def settings_of(case: ExperimentPlanCase) -> dict[str, PlanSetting]:
    return {row.setting: row for row in case.settings}


def screen_case(text: str) -> tuple[str, object, object]:
    """The `case_id`, requests, and settings of the screen configuration `text`, planned as a
    screen run plans it."""
    (case,) = build_plan(read_screen_configuration(text.encode(), "screen.yaml"), VERSIONS).cases
    return case.case_id, case.requests, case.settings


def screen_text(*changes: tuple[str, str]) -> str:
    """`formula.yaml`, the example's baseline as a screen configuration, with each change made."""
    text = (SCREENS / "formula.yaml").read_text(encoding="utf-8")
    for old, new in changes:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return text


# Each case of the example, as the screen configuration with its settings: `formula.yaml`, with
# the case's one change.
EXAMPLE_SCREENS = {
    "baseline": screen_text(),
    "liquidity-100m": screen_text(("'AvgDailyTot(30) > 1000000'", "'AvgDailyTot(30) > 100000000'")),
    "holdings-50": screen_text(("max_holdings: 25", "max_holdings: 50")),
    "rebalance-weeks-1": screen_text(("rebalance_weeks: 4", "rebalance_weeks: 1")),
    "slippage-050": screen_text(("slippage_percent: 0.25", "slippage_percent: 0.5")),
}


def test_the_example_compiles_to_its_five_cases_in_the_order_of_cases() -> None:
    plan = plan_of(EXPERIMENTS / "example.yaml")

    assert [case.case_key for case in plan.cases] == EXAMPLE_KEYS
    variants = [
        None if case.variant is None else case.variant.model_dump(mode="json")
        for case in plan.cases
    ]
    unchanged = {"value": None, "add": None, "replace": None, "with": None, "default": False}
    assert variants == [
        None,
        unchanged
        | {
            "setting": "rules",
            "replace": "AvgDailyTot(30) > 1000000",
            "with": "AvgDailyTot(30) > 100000000",
        },
        unchanged | {"setting": "max_holdings", "value": 50},
        unchanged | {"setting": "rebalance_weeks", "value": 1, "default": True},
        unchanged | {"setting": "slippage_percent", "value": "0.5"},
    ]
    assert [case.description for case in plan.cases] == [
        None,
        "A stricter liquidity floor, 100 million dollars a day.",
        None,
        None,
        None,
    ]


@pytest.mark.parametrize("key", EXAMPLE_KEYS)
def test_each_case_is_the_screen_with_its_settings(key: str) -> None:
    case = by_key(plan_of(EXPERIMENTS / "example.yaml"))[key]

    assert (case.case_id, case.requests, case.settings) == screen_case(EXAMPLE_SCREENS[key])


@pytest.mark.parametrize(
    ("key", "setting"),
    [
        ("liquidity-100m", "rules"),
        ("holdings-50", "max_holdings"),
        ("rebalance-weeks-1", "rebalance_weeks"),
        ("slippage-050", "slippage_percent"),
    ],
)
def test_each_variant_is_the_baseline_with_exactly_its_change(key: str, setting: str) -> None:
    cases = by_key(plan_of(EXPERIMENTS / "example.yaml"))
    baseline, case = settings_of(cases["baseline"]), settings_of(cases[key])

    assert [name for name in case if case[name] != baseline[name]] == [setting]
    assert case[setting] == baseline[setting].model_copy(update={"value": case[setting].value})


def test_the_plan_records_the_research_context_and_the_budget_across_runs() -> None:
    plan = plan_of(EXPERIMENTS / "example.yaml").model_dump(mode="json")
    screen = build_plan(
        read_screen_configuration(EXAMPLE_SCREENS["baseline"].encode(), "screen.yaml"), VERSIONS
    ).model_dump(mode="json")

    assert plan["schema_version"] == "1.1.0"
    assert plan["experiment_id"] == "earnyield-sensitivity"
    assert plan["title"] == "Earnings yield sensitivity"
    assert plan["purpose"].startswith("How do holdings, slippage, and a stricter liquidity rule")
    assert plan["prior_research"] == {
        "status": "partial",
        "description": "Earlier backtests of this screen in the Portfolio123 website compared 25 "
        "and 50 holdings. Other variations tried there weren't recorded.",
    }
    assert plan["revises"] is None
    assert plan["budget"] == {
        "provider_requests": 6,
        "credits_per_request": 5,
        "credits_per_request_source": screen["budget"]["credits_per_request_source"],
        "credits": 30,
        "authentication_calls": 6,
    }
    for field in (
        "trialfolio_version",
        "canonicalization_version",
        "provider_wrapper",
        "transport",
        "retry_policy",
        "data_sent",
    ):
        assert plan[field] == screen[field], field


def test_the_largest_budget_gives_credits_the_plan_can_hash() -> None:
    """The budget's bound is the multiplication's: the largest budget the configuration accepts,
    1801439850948198 requests, costs 9007199254740990 credits at 5 a request, within 2^53 - 1.
    The contract tests check that one more is refused."""
    text = edited("  provider_requests: 6\n", "  provider_requests: 1801439850948198\n")

    plan = build_experiment_plan(from_text(text), VERSIONS)

    assert plan.budget.credits == 9007199254740990
    assert plan.plan_hash == plan_hash(plan)


def test_a_prior_research_declaration_without_a_description_is_planned_as_null() -> None:
    text = edited(
        "  status: partial\n  description: Earlier backtests of this screen in the Portfolio123 "
        "website compared 25 and 50 holdings. Other variations tried there weren't recorded.\n",
        "  status: unknown\n",
    )

    plan = build_experiment_plan(from_text(text), VERSIONS)

    assert plan.prior_research.model_dump() == {"status": "unknown", "description": None}


def test_no_microcaps_gives_its_two_cases_with_no_default() -> None:
    plan = plan_of(EXPERIMENTS / "no-microcaps.yaml")

    baseline, added = plan.cases
    assert [baseline.case_key, added.case_key] == ["baseline", "no-microcaps"]
    assert added.variant is not None
    assert (added.variant.setting, added.variant.add, added.variant.default) == (
        "rules",
        "MktCap > 300",
        False,
    )
    on_easy_to_trade = ("universe: 'SP500'", "universe: 'Easy to Trade US'")
    assert (baseline.case_id, baseline.requests, baseline.settings) == screen_case(
        screen_text(on_easy_to_trade)
    )
    assert (added.case_id, added.requests, added.settings) == screen_case(
        screen_text(
            on_easy_to_trade,
            (
                "  - 'AvgDailyTot(30) > 1000000'\n",
                "  - 'AvgDailyTot(30) > 1000000'\n  - 'MktCap > 300'\n",
            ),
        )
    )
    assert plan.budget.provider_requests == 6


@pytest.mark.parametrize(
    ("baseline_weeks", "default_key", "default_weeks"),
    [(4, "rebalance-weeks-1", 1), (1, "rebalance-weeks-4", 4)],
)
def test_without_variants_the_default_is_the_rebalance_frequency_the_baseline_doesnt_use(
    baseline_weeks: int, default_key: str, default_weeks: int
) -> None:
    text = (EXPERIMENTS / "default-only.yaml").read_text(encoding="utf-8")
    text = edited("rebalance_weeks: 4", f"rebalance_weeks: {baseline_weeks}", text)

    plan = build_experiment_plan(from_text(text), VERSIONS)

    baseline, default = plan.cases
    assert [baseline.case_key, default.case_key] == ["baseline", default_key]
    assert default.variant is not None
    assert (default.variant.setting, default.variant.value, default.variant.default) == (
        "rebalance_weeks",
        default_weeks,
        True,
    )
    assert default.description is None
    assert settings_of(default)["rebalance_weeks"].value == default_weeks
    assert plan.budget.provider_requests == plan.budget.authentication_calls == 2


def test_a_rebalance_list_replaces_the_default_and_an_empty_one_turns_it_off() -> None:
    listed = plan_of(REVISIONS / "default-explicit.yaml")
    off = build_experiment_plan(
        from_text(edited("  slippage_percent:\n", "  rebalance_weeks: []\n  slippage_percent:\n")),
        VERSIONS,
    )

    rebalance = by_key(listed)["rebalance-weeks-1"]
    assert rebalance.variant is not None
    assert rebalance.variant.default is False
    assert [case.case_key for case in off.cases] == [
        "baseline",
        "liquidity-100m",
        "holdings-50",
        "slippage-050",
    ]


def test_a_file_written_differently_gives_the_same_plan_and_hash() -> None:
    example = plan_of(EXPERIMENTS / "example.yaml")
    written_differently = plan_of(EXPERIMENTS / "written-differently.yaml")

    assert written_differently == example
    assert written_differently.plan_hash == example.plan_hash
    assert settings_of(by_key(written_differently)["baseline"])["slippage_percent"].value == "0.25"
    slippage = by_key(written_differently)["slippage-050"].variant
    assert slippage is not None
    assert slippage.value == "0.5"


def test_the_plan_hash_is_the_hash_of_the_canonical_plan_and_each_case_id_of_its_settings() -> None:
    plan = plan_of(EXPERIMENTS / "example.yaml")
    saved = PlanV1_1.model_validate_json(plan.model_dump_json(indent=2))

    assert plan_hash(saved) == saved.plan_hash == plan.plan_hash
    for case in saved.cases:
        assert case_id(case.settings) == case.case_id


def test_the_experiment_plan_hash_is_the_same_in_another_process() -> None:
    # Two hash seeds, so an order taken from a set would show.
    script = (
        "from tests.core.test_experiment_plan import EXPERIMENTS, plan_of\n"
        "print(plan_of(EXPERIMENTS / 'example.yaml').plan_hash)\n"
    )
    hashes = {
        subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
            env=os.environ | {"PYTHONHASHSEED": seed},
        ).stdout.strip()
        for seed in ("1", "2")
    }

    assert hashes == {plan_of(EXPERIMENTS / "example.yaml").plan_hash}


def test_a_version_no_release_verified_isnt_planned() -> None:
    with pytest.raises(TrialFolioError) as raised:
        build_experiment_plan(
            read(EXPERIMENTS / "example.yaml"), Versions("0.3.0", "3.1.0", "2.34.3", "2.8.0")
        )

    assert raised.value.code == "environment.unsupported"
    assert "The installed requests is 2.34.3." in raised.value.message


# Revisions


def revision_of(path: Path, current: PlanV1_1) -> PlanRevision:
    revision = plan_revision(read(path), VERSIONS, current)
    assert revision is not None
    return revision


def keyed(changes: tuple[CaseChange, ...]) -> list[str]:
    return [change.case_key for change in changes]


@pytest.mark.parametrize(
    "path", [EXPERIMENTS / "example.yaml", EXPERIMENTS / "written-differently.yaml"]
)
def test_the_configuration_that_gives_the_current_plan_resumes_it(path: Path) -> None:
    current = PlanV1_1.model_validate_json(plan_of(EXPERIMENTS / "example.yaml").model_dump_json())

    assert plan_revision(read(path), VERSIONS, current) is None


def test_a_revision_revises_the_current_plan_and_is_resumed_by_its_own_configuration() -> None:
    current = plan_of(EXPERIMENTS / "example.yaml")

    revision = revision_of(REVISIONS / "holdings-40.yaml", current)

    assert revision.plan.revises == current.plan_hash
    assert revision.plan.plan_hash == plan_hash(revision.plan) != current.plan_hash
    # The same configuration, versions, and revised plan give the same revision.
    assert revision_of(REVISIONS / "holdings-40.yaml", current).plan == revision.plan
    assert plan_revision(read(REVISIONS / "holdings-40.yaml"), VERSIONS, revision.plan) is None
    again = revision_of(EXPERIMENTS / "example.yaml", revision.plan)
    assert again.plan.revises == revision.plan.plan_hash
    assert again.plan.plan_hash != current.plan_hash


# Each revision of example.yaml, with the cases it adds and retires, by key, and the other parts
# it changes, as written by hand from docs/contracts.md's experiment plans and revisions.
REVISION_CHANGES = {
    "holdings-40": (["holdings-50"], ["holdings-50"], []),
    "key-renamed": ([], [], ["case_keys"]),
    "description-changed": ([], [], ["case_descriptions"]),
    "purpose-changed": ([], [], ["purpose"]),
    "prior-research-changed": ([], [], ["prior_research"]),
    "budget-raised": ([], [], ["budget"]),
    "budget-lowered": ([], [], ["budget"]),
    "variant-removed": ([], ["slippage-050"], []),
    "default-explicit": ([], [], ["case_variants"]),
    "two-holdings": (["holdings-40"], [], []),
}


@pytest.mark.parametrize("name", REVISION_CHANGES)
def test_each_change_is_a_revision_that_records_the_cases_and_parts_it_changed(name: str) -> None:
    added, retired, parts = REVISION_CHANGES[name]
    current = plan_of(EXPERIMENTS / "example.yaml")

    revision = revision_of(REVISIONS / f"{name}.yaml", current)

    changes = revision.changes
    assert (keyed(changes.cases_added), keyed(changes.cases_retired), list(changes.parts)) == (
        added,
        retired,
        parts,
    )
    assert changes.versions == ()
    before = {case.case_id for case in current.cases}
    after = {case.case_id for case in revision.plan.cases}
    assert {change.case_id for change in changes.cases_added} == after - before
    assert {change.case_id for change in changes.cases_retired} == before - after
    # Every other case keeps its case_id, and so its attempts, whatever its key or place.
    assert len(before & after) == len(current.cases) - len(retired)


def test_a_changed_variant_keeps_its_key_and_gets_a_new_case_id() -> None:
    current = plan_of(EXPERIMENTS / "example.yaml")

    revision = revision_of(REVISIONS / "holdings-40.yaml", current)

    old, new = by_key(current)["holdings-50"], by_key(revision.plan)["holdings-50"]
    assert new.case_id != old.case_id
    assert [change.case_id for change in revision.changes.cases_added] == [new.case_id]
    assert [change.case_id for change in revision.changes.cases_retired] == [old.case_id]


def test_a_renamed_key_keeps_every_case_id() -> None:
    current = plan_of(EXPERIMENTS / "example.yaml")

    revision = revision_of(REVISIONS / "key-renamed.yaml", current)

    assert [case.case_id for case in revision.plan.cases] == [
        case.case_id for case in current.cases
    ]
    assert (
        by_key(revision.plan)["max-holdings-50"].case_id == by_key(current)["holdings-50"].case_id
    )


def test_a_new_order_of_one_settings_variants_keeps_every_case_in_another_order() -> None:
    current = plan_of(REVISIONS / "two-holdings.yaml")

    revision = revision_of(REVISIONS / "two-holdings-reordered.yaml", current)

    assert revision.changes.parts == ("case_order",)
    assert (revision.changes.cases_added, revision.changes.cases_retired) == ((), ())
    assert [case.case_key for case in current.cases][2:4] == ["holdings-40", "holdings-50"]
    assert [case.case_key for case in revision.plan.cases][2:4] == ["holdings-50", "holdings-40"]
    assert sorted(case.case_id for case in revision.plan.cases) == sorted(
        case.case_id for case in current.cases
    )


@pytest.mark.parametrize(
    ("old", "new", "parts"),
    [
        ("title: Earnings yield sensitivity", "title: Earnings yield and holdings", ["title"]),
        (
            "    - key: holdings-50\n      value: 50\n",
            "    - key: holdings-50\n      description: Twice the holdings.\n      value: 50\n",
            ["case_descriptions"],
        ),
    ],
)
def test_a_changed_title_or_description_is_a_revision_of_that_part_alone(
    old: str, new: str, parts: list[str]
) -> None:
    current = plan_of(EXPERIMENTS / "example.yaml")

    revision = plan_revision(from_text(edited(old, new)), VERSIONS, current)

    assert revision is not None
    assert list(revision.changes.parts) == parts
    assert (revision.changes.cases_added, revision.changes.cases_retired) == ((), ())


def test_a_changed_baseline_setting_retires_every_case_and_adds_each_again() -> None:
    current = plan_of(EXPERIMENTS / "example.yaml")
    text = edited("  end_date: 2025-12-31\n", "  end_date: 2024-12-31\n")

    revision = plan_revision(from_text(text), VERSIONS, current)

    assert revision is not None
    assert keyed(revision.changes.cases_added) == EXAMPLE_KEYS
    assert keyed(revision.changes.cases_retired) == EXAMPLE_KEYS
    assert revision.changes.parts == ()
    assert not {case.case_id for case in current.cases} & {
        case.case_id for case in revision.plan.cases
    }


def test_an_added_variant_and_a_turned_off_default_are_revisions_of_the_cases() -> None:
    current = plan_of(EXPERIMENTS / "example.yaml")
    added = edited(
        "    - key: holdings-50\n      value: 50\n",
        "    - key: holdings-50\n      value: 50\n    - key: holdings-10\n      value: 10\n",
    )
    off = edited("  slippage_percent:\n", "  rebalance_weeks: []\n  slippage_percent:\n")

    with_added = plan_revision(from_text(added), VERSIONS, current)
    without_default = plan_revision(from_text(off), VERSIONS, current)

    assert with_added is not None
    assert without_default is not None
    assert (keyed(with_added.changes.cases_added), with_added.changes.parts) == (
        ["holdings-10"],
        (),
    )
    assert (keyed(without_default.changes.cases_retired), without_default.changes.parts) == (
        ["rebalance-weeks-1"],
        (),
    )


def test_a_case_that_becomes_the_baseline_is_kept_with_its_new_key_variant_and_place() -> None:
    # The baseline's holdings and the variant's trade places: the two cases keep their settings.
    current = plan_of(EXPERIMENTS / "example.yaml")
    text = edited("  max_holdings: 25\n", "  max_holdings: 50\n")
    text = edited(
        "    - key: holdings-50\n      value: 50\n",
        "    - key: holdings-25\n      value: 25\n",
        text,
    )

    revision = plan_revision(from_text(text), VERSIONS, current)

    assert revision is not None
    assert by_key(revision.plan)["holdings-25"].case_id == by_key(current)["baseline"].case_id
    assert by_key(revision.plan)["baseline"].case_id == by_key(current)["holdings-50"].case_id
    assert revision.changes.parts == ("case_keys", "case_variants", "case_order")


def recorded_with(plan: PlanV1_1, **fields: object) -> PlanV1_1:
    """`plan` as a plan.json that records other `fields`, such as another version, read back
    with its hash recomputed."""
    changed = plan.model_copy(update=fields)
    document = changed.model_copy(update={"plan_hash": plan_hash(changed)}).model_dump_json()
    return PlanV1_1.model_validate_json(document)


@pytest.mark.parametrize(
    ("package", "fields", "earlier"),
    [
        ("trialfolio", {"trialfolio_version": "0.2.1"}, "0.2.1"),
        ("p123api", {"provider_wrapper": WrapperVersions(p123api="3.0.9")}, "3.0.9"),
        (
            "requests",
            {"transport": TransportVersions(requests="2.34.1", urllib3=VERSIONS.urllib3)},
            "2.34.1",
        ),
        (
            "urllib3",
            {"transport": TransportVersions(requests=VERSIONS.requests, urllib3="2.7.0")},
            "2.7.0",
        ),
    ],
)
def test_a_plan_built_with_another_version_is_a_change_of_versions_alone(
    package: str, fields: dict[str, object], earlier: str
) -> None:
    current = recorded_with(plan_of(EXPERIMENTS / "example.yaml"), **fields)

    revision = revision_of(EXPERIMENTS / "example.yaml", current)

    changes = revision.changes.model_dump(mode="json")
    assert changes == {
        "versions": [
            {"package": package, "previous": earlier, "current": getattr(VERSIONS, package)}
        ],
        "cases_added": [],
        "cases_retired": [],
        "parts": [],
    }
    assert [case.case_id for case in revision.plan.cases] == [
        case.case_id for case in current.cases
    ]


@pytest.mark.parametrize(
    "budget",
    [
        {"credits_per_request": 4, "credits": 24},
        {
            "credits_per_request_source": CREDITS_PER_REQUEST_SOURCE.model_copy(
                update={"checked": date(2026, 9, 1)}
            )
        },
    ],
    ids=["credits_per_request", "credits_per_request_source"],
)
def test_a_plan_built_with_another_documented_cost_is_a_change_of_versions_and_of_the_budget(
    budget: dict[str, object],
) -> None:
    """`budget` is any change to the plan's budget, not only to `provider_requests`: an earlier
    Trial Folio may have recorded another documented cost, or another source for it, for the same
    configuration."""
    planned = plan_of(EXPERIMENTS / "example.yaml")
    current = recorded_with(
        planned, trialfolio_version="0.2.1", budget=planned.budget.model_copy(update=budget)
    )

    revision = revision_of(EXPERIMENTS / "example.yaml", current)

    assert current.budget.provider_requests == revision.plan.budget.provider_requests
    assert [change.package for change in revision.changes.versions] == ["trialfolio"]
    assert (revision.changes.cases_added, revision.changes.cases_retired) == ((), ())
    assert revision.changes.parts == ("budget",)
    assert revision.plan.budget == planned.budget


def test_another_trialfolio_version_given_as_installed_is_a_change_of_versions() -> None:
    current = plan_of(EXPERIMENTS / "example.yaml")
    upgraded = Versions("0.3.1", VERSIONS.p123api, VERSIONS.requests, VERSIONS.urllib3)

    revision = plan_revision(read(EXPERIMENTS / "example.yaml"), upgraded, current)

    assert revision is not None
    assert revision.plan.trialfolio_version == "0.3.1"
    assert [change.model_dump() for change in revision.changes.versions] == [
        {"package": "trialfolio", "previous": "0.3.0", "current": "0.3.1"}
    ]
    assert (revision.changes.cases_added, revision.changes.cases_retired) == ((), ())
    assert revision.changes.parts == ()


def test_every_version_changed_is_recorded_in_the_documented_order() -> None:
    current = recorded_with(
        plan_of(EXPERIMENTS / "example.yaml"),
        trialfolio_version="0.2.1",
        provider_wrapper=WrapperVersions(p123api="3.0.9"),
        transport=TransportVersions(requests="2.34.1", urllib3="2.7.0"),
    )

    revision = revision_of(REVISIONS / "budget-raised.yaml", current)

    assert [change.package for change in revision.changes.versions] == [
        "trialfolio",
        "p123api",
        "requests",
        "urllib3",
    ]
    assert revision.changes.parts == ("budget",)


@pytest.mark.parametrize(
    ("name", "hidden"),
    [("other-experiment-id", "earnyield-holdings"), ("other-universe", "Easy to Trade US")],
)
def test_another_experiment_id_or_universe_is_another_experiment_not_a_revision(
    name: str, hidden: str
) -> None:
    current = plan_of(EXPERIMENTS / "example.yaml")

    with pytest.raises(TrialFolioError) as raised:
        plan_revision(read(REVISIONS / f"{name}.yaml"), VERSIONS, current)

    assert raised.value.code == "output.not_empty"
    assert "another experiment" in raised.value.message
    assert "new output directory" in raised.value.message
    # The message names neither the configuration's value nor the experiment's.
    for value in (hidden, current.experiment_id, "SP500"):
        assert value not in raised.value.message


def test_another_experiment_is_found_before_the_versions_are_checked() -> None:
    current = plan_of(EXPERIMENTS / "example.yaml")
    unverified = Versions("0.3.0", "3.2.0", VERSIONS.requests, VERSIONS.urllib3)

    with pytest.raises(TrialFolioError) as raised:
        plan_revision(read(REVISIONS / "other-universe.yaml"), unverified, current)
    assert raised.value.code == "output.not_empty"

    with pytest.raises(TrialFolioError) as raised:
        plan_revision(read(EXPERIMENTS / "example.yaml"), unverified, current)
    assert raised.value.code == "environment.unsupported"


# experiment.json


def first_record(plan: PlanV1_1) -> ExperimentRecord:
    return first_experiment_record(
        plan,
        plan_artifact_id=digest(1),
        configuration_artifact_id=digest(2),
        approval="option",
        created_at=CREATED_AT,
    )


def revised_record(
    previous: ExperimentRecord, revision: PlanRevision, number: int, reason: str
) -> ExperimentRecord:
    return revised_experiment_record(
        previous,
        revision,
        number=number,
        reason=reason,
        plan_artifact_id=digest(2 * number + 1),
        configuration_artifact_id=digest(2 * number + 2),
        approval="interactive",
        created_at=CREATED_AT,
    )


def test_the_first_plans_record_declares_the_experiment_and_its_one_plan() -> None:
    plan = plan_of(EXPERIMENTS / "example.yaml")

    record = first_record(plan)

    document = ExperimentRecord.model_validate_json(record.model_dump_json()).model_dump(
        mode="json"
    )
    assert document["schema_version"] == "1.0.0"
    assert document["trialfolio_version"] == "0.3.0"
    assert document["created_at"] == "2026-10-09T12:00:00Z"
    assert (document["experiment_id"], document["title"], document["purpose"]) == (
        plan.experiment_id,
        plan.title,
        plan.purpose,
    )
    assert document["prior_research"] == plan.model_dump(mode="json")["prior_research"]
    assert document["planned_cases"] == [
        {
            "case_key": case.case_key,
            "case_id": case.case_id,
            "description": case.description,
            "variant": None if case.variant is None else case.variant.model_dump(mode="json"),
        }
        for case in plan.cases
    ]
    assert document["retired_cases"] == []
    assert document["plans"] == [
        {
            "plan": 1,
            "plan_hash": plan.plan_hash,
            "revises": None,
            "plan_artifact_id": digest(1),
            "configuration_artifact_id": digest(2),
            "approval": "option",
            "reason": None,
            "changes": None,
        }
    ]
    assert "outcome" not in record.model_dump_json()


def test_a_revisions_record_keeps_the_history_and_retires_the_changed_case() -> None:
    current = plan_of(EXPERIMENTS / "example.yaml")
    first = first_record(current)
    revision = revision_of(REVISIONS / "holdings-40.yaml", current)

    record = revised_record(first, revision, 2, "Forty holdings, not fifty.")

    assert record.plans[:-1] == first.plans
    entry = record.plans[-1]
    assert (entry.plan, entry.plan_hash, entry.revises) == (
        2,
        revision.plan.plan_hash,
        current.plan_hash,
    )
    assert (entry.reason, entry.changes, entry.approval) == (
        "Forty holdings, not fifty.",
        revision.changes,
        "interactive",
    )
    assert [case.case_key for case in record.planned_cases] == EXAMPLE_KEYS
    (retired,) = record.retired_cases
    old = by_key(current)["holdings-50"]
    assert retired.model_dump() == {
        "case_key": "holdings-50",
        "case_id": old.case_id,
        "description": None,
        "variant": old.variant.model_dump() if old.variant else None,
        "plan": 1,
    }
    assert retired.variant is not None
    assert retired.variant.value == 50


@pytest.mark.parametrize("name", REVISION_CHANGES)
def test_each_revisions_record_holds_its_planned_and_retired_cases(name: str) -> None:
    current = plan_of(EXPERIMENTS / "example.yaml")
    revision = revision_of(REVISIONS / f"{name}.yaml", current)

    record = revised_record(first_record(current), revision, 2, "A reason.")

    assert [(case.case_key, case.case_id) for case in record.planned_cases] == [
        (case.case_key, case.case_id) for case in revision.plan.cases
    ]
    assert [(case.case_id, case.plan) for case in record.retired_cases] == [
        (change.case_id, 1) for change in revision.changes.cases_retired
    ]
    assert record.plans[-1].changes == revision.changes
    assert (record.title, record.purpose, record.prior_research) == (
        revision.plan.title,
        revision.plan.purpose,
        revision.plan.prior_research,
    )


@pytest.mark.parametrize("key", ["slippage-050", "slippage-half"])
def test_a_retired_case_planned_again_under_any_key_is_the_same_case_again(key: str) -> None:
    first_plan = plan_of(EXPERIMENTS / "example.yaml")
    first = first_record(first_plan)
    removed = revision_of(REVISIONS / "variant-removed.yaml", first_plan)
    second = revised_record(first, removed, 2, "Without slippage.")
    text = edited("    - key: slippage-050\n", f"    - key: {key}\n")

    restored = plan_revision(from_text(text), VERSIONS, removed.plan)
    assert restored is not None
    third = revised_record(second, restored, 4, "With slippage again.")

    old = by_key(first_plan)["slippage-050"]
    assert by_key(restored.plan)[key].case_id == old.case_id
    assert [(change.case_id, change.case_key) for change in restored.changes.cases_added] == [
        (old.case_id, key)
    ]
    assert second.retired_cases[0].case_id == old.case_id
    assert third.retired_cases == ()
    assert [entry.plan for entry in third.plans] == [1, 2, 4]
    assert third.plans[:-1] == second.plans


def test_a_case_retired_earlier_keeps_the_last_plan_that_included_it() -> None:
    first_plan = plan_of(EXPERIMENTS / "example.yaml")
    removed = revision_of(REVISIONS / "variant-removed.yaml", first_plan)
    second = revised_record(first_record(first_plan), removed, 2, "Without slippage.")
    text = edited("  slippage_percent:\n    - key: slippage-050\n      value: 0.5\n", "")
    text = edited(
        "    - key: holdings-50\n      value: 50\n",
        "    - key: holdings-50\n      value: 40\n",
        text,
    )

    revision = plan_revision(from_text(text), VERSIONS, removed.plan)
    assert revision is not None
    third = revised_record(second, revision, 3, "Forty holdings.")

    assert [(case.case_key, case.plan) for case in third.retired_cases] == [
        ("slippage-050", 1),
        ("holdings-50", 2),
    ]
    assert third.retired_cases[0] == second.retired_cases[0]


def test_records_that_dont_fit_together_are_refused() -> None:
    current = plan_of(EXPERIMENTS / "example.yaml")
    first = first_record(current)
    revision = revision_of(REVISIONS / "holdings-40.yaml", current)
    second = revised_record(first, revision, 2, "Forty holdings.")

    with pytest.raises(ValueError, match="revises"):
        # A revision of the first plan, recorded after the second.
        revised_record(second, revision_of(REVISIONS / "purpose-changed.yaml", current), 3, "A.")
    with pytest.raises(ValueError, match="oldest first"):
        revised_record(first, revision, 1, "Forty holdings.")
    with pytest.raises(ValueError, match="revision"):
        first_record(revision.plan)
    with pytest.raises(ValueError, match="reason"):
        revised_record(first, revision, 2, " ")


def test_every_revision_is_in_its_readme() -> None:
    readme = (REVISIONS / "README.md").read_text(encoding="utf-8")
    listed = set(re.findall(r"^\| `([a-z0-9-]+)\.yaml` \|", readme, re.MULTILINE))

    assert listed == {path.stem for path in REVISIONS.glob("*.yaml")}
