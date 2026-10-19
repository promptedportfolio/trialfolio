"""Reading an experiment configuration enforces docs/contracts.md's experiment configuration rules.

Traces to release 0.3.0's test pairing, "other checks in the default suite":
`test_documented_examples_resolve_to_reference_requests` repeats the documented examples'
validation, which R03-T02 left for R03-T05: each example is valid, equals its fixture, and each
of its cases resolves to the request Portfolio123 accepted, and the `case_id` of the screen
configuration its validation names; and each file in tests/fixtures/experiment-configs/invalid/
fails with `config.invalid`, and the message names the offending key, or a variant by its place,
never by its key or its value. The other tests trace to the experiment configuration's keys and
rules, its default variant, and the order of its cases, and to the rules for every configuration
file. R03-T06 wrote them.

Experiment configuration 1.1.0's tests, at the end, trace to R04-AC02's ranking variants and
baseline, as release 0.4.0's test pairing gives them for `test_experiment_configuration.py`: each
invalid configuration fails with `config.invalid`, and the message names a ranking variant's
`set` entry by its place, never by its path; a 1.0.0 file with a ranking variant, or a baseline
ranked by a definition, says they need 1.1.0; and a budget is at least two requests a case. Also
to the ranking example's structure, which the configuration's reader accepts. R04-T05 wrote
them, with the reader of both versions, which the invalid files' test uses. The 1.0.0 reader's
messages for such a file stay 0.3.0's, as the R04-T05 details in release 0.4.0's changes after
sign-off give them; since R04-T12, `trialfolio run` reads with the reader of both versions, so its
messages are that reader's. What a path names in the definition, and the example's cases, are R04-T06's: since then,
the reader of both versions reads the baseline's definition file, from the configuration's
directory, so it's given the configuration's path, and applies each ranking variant, and the
invalid files' test reads the ranking variants' cases that depend on the definition too.
`test_documented_ranking_example_compiles_to_its_cases` repeats the ranking example's
validation, which R04-T02 left for R04-T04's test pairing to give R04-T06. What the reader reads
in the definition, and each variant's case, are tested in
tests/contract/test_ranking_definitions.py.
"""

import json
import re
from collections.abc import Callable
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from tests.support.snapshot_builder import SnapshotBuilder
from trialfolio.configuration import (
    read_experiment_configuration,
    read_experiment_configuration_v1_1,
    read_run_configuration,
    read_screen_configuration,
)
from trialfolio.contracts.common import WINDOWS_DEVICE_NAMES
from trialfolio.contracts.experiment_configuration import (
    ExperimentConfiguration,
    ExperimentConfigurationV1_1,
    RankingVariant,
    configured_variants,
    configured_variants_v1_1,
)
from trialfolio.contracts.plan import screen_backtest_params
from trialfolio.contracts.screen_configuration import ScreenFields
from trialfolio.errors import TrialFolioError
from trialfolio.planning import case_id, resolve_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "experiment-configs"
INVALID = FIXTURES / "invalid"
REFERENCE = REPO_ROOT / "reference"
SCHEMA = REPO_ROOT / "schemas" / "experiment-configuration-1.0.0.schema.json"


def documented_examples() -> tuple[str, str]:
    """The experiment example in docs/contracts.md, and the second example as a whole file: the
    first, with the universe `'Easy to Trade US'` and the second's `variants`."""
    contracts = (REPO_ROOT / "docs" / "contracts.md").read_text(encoding="utf-8")
    section = contracts[contracts.index("#### Experiment example") :]
    first, second = re.findall(r"```yaml\n(.*?)```", section, re.DOTALL)[:2]
    whole = first.replace("  universe: 'SP500'\n", "  universe: 'Easy to Trade US'\n")
    whole = whole[: whole.index("variants:\n")] + second + whole[whole.index("budget:\n") :]
    return first, whole


def example() -> str:
    return documented_examples()[0]


def rejection(
    content: bytes | str,
    source_name: str = "experiment.yaml",
    reader: Callable[[bytes, str], object] = read_experiment_configuration,
) -> str:
    """Reads `content`, expects `config.invalid`, and returns the message."""
    if isinstance(content, str):
        content = content.encode()
    with pytest.raises(TrialFolioError) as caught:
        reader(content, source_name)
    assert caught.value.code == "config.invalid"
    assert caught.value.log_message == caught.value.message
    return caught.value.message


def with_line(old: str, new: str, text: str | None = None) -> str:
    """The documented example, or `text`, with one line replaced."""
    text = example() if text is None else text
    assert text.count(old) == 1, old
    return text.replace(old, new)


def read(content: str) -> ExperimentConfiguration:
    return read_experiment_configuration(content.encode(), "experiment.yaml")


def contains_value(message: str, value: str) -> bool:
    """Whether `message` holds `value` as a whole, not inside a longer name."""
    word = r"[A-Za-z0-9_.-]"
    return re.search(rf"(?<!{word}){re.escape(value)}(?!{word})", message) is not None


def resolved(screen: ScreenFields) -> tuple[str, str]:
    """A screen's request, as JSON text, so a float and an integer can't pass for each other, and
    its `case_id`."""
    settings = resolve_settings(screen)
    params = {row.setting: row.value for row in settings}
    request = screen_backtest_params(params).model_dump(mode="json")
    return json.dumps(request, sort_keys=True), case_id(settings)


def cases_of(configuration: ExperimentConfiguration) -> dict[str, tuple[str, str]]:
    """Each case's request and `case_id`, by its key, in the order of cases."""
    cases = {"baseline": resolved(configuration.baseline)}
    for variant in configured_variants(configuration):
        cases[variant.key] = resolved(variant.screen)
    return cases


def reference_request(path: str) -> str:
    return json.dumps(json.loads((REFERENCE / path).read_text(encoding="utf-8")), sort_keys=True)


def reference_screen(path: str) -> tuple[str, str]:
    """The request and `case_id` of a committed screen configuration, read with the screen
    configuration's reader."""
    return resolved(read_screen_configuration((REFERENCE / path).read_bytes(), path))


def test_documented_examples_resolve_to_reference_requests() -> None:
    first, second = documented_examples()
    assert (FIXTURES / "example.yaml").read_text(encoding="utf-8") == first
    assert (FIXTURES / "no-microcaps.yaml").read_text(encoding="utf-8") == second

    cases = cases_of(read_experiment_configuration(first.encode(), "example.yaml"))
    microcaps = cases_of(read_experiment_configuration(second.encode(), "no-microcaps.yaml"))

    assert list(cases) == [
        "baseline",
        "liquidity-100m",
        "holdings-50",
        "rebalance-weeks-1",
        "slippage-050",
    ]
    assert cases["baseline"][0] == reference_request("p123api-screen-backtest/request.json")
    assert cases["rebalance-weeks-1"][0] == reference_request(
        "p123api-screen-backtest-values/request-weekly.json"
    )
    assert cases["liquidity-100m"] == reference_screen("variant-capabilities/liquidity-100m.yaml")
    assert cases["holdings-50"] == reference_screen("review-live-exercise/holdings-50.yaml")
    assert cases["slippage-050"] == reference_screen("variant-capabilities/slippage-050.yaml")
    assert list(microcaps) == ["baseline", "no-microcaps"]
    assert microcaps["baseline"] == reference_screen("variant-capabilities/easy-to-trade.yaml")
    assert microcaps["no-microcaps"] == reference_screen("variant-capabilities/no-microcaps.yaml")


def test_the_documented_example_reads_as_documented() -> None:
    configuration = read(example())

    assert configuration.experiment_id == "earnyield-sensitivity"
    assert configuration.purpose.startswith("How do holdings, slippage,")
    assert configuration.prior_research.status == "partial"
    assert configuration.baseline.slippage_percent == Decimal("0.25")
    assert configuration.budget.provider_requests == 6
    variants = configured_variants(configuration)
    assert [(v.place, v.setting, v.key, v.default) for v in variants] == [
        ("variants.rules[0]", "rules", "liquidity-100m", False),
        ("variants.max_holdings[0]", "max_holdings", "holdings-50", False),
        (None, "rebalance_weeks", "rebalance-weeks-1", True),
        ("variants.slippage_percent[0]", "slippage_percent", "slippage-050", False),
    ]
    assert variants[0].description == "A stricter liquidity floor, 100 million dollars a day."
    assert variants[2].description is None
    assert variants[0].screen.rules == ("AvgDailyTot(30) > 100000000",)
    assert variants[3].screen.slippage_percent == Decimal("0.5")


def header(content: str, name: str) -> str:
    found = re.search(rf"^# {name}: (.+)$", content, re.MULTILINE)
    assert found, f"no '# {name}:' line"
    return found.group(1)


@pytest.mark.parametrize("path", sorted(INVALID.glob("*.yaml")), ids=lambda path: path.stem)
def test_invalid_configuration_is_rejected_naming_its_key_never_its_value(path: Path) -> None:
    content = path.read_text(encoding="utf-8")
    key, value = header(content, "Key"), header(content, "Value")

    message = rejection(
        path.read_bytes(),
        path.name,
        lambda content, name: read_experiment_configuration_v1_1(content, name, path),
    )

    assert message.startswith(f"{path.name} isn't a valid configuration:")
    if key != "-":
        assert f"`{key}`" in message
    if value != "-":
        assert not contains_value(message, value)
    # A variant is named by its place, never by its key, which is the user's text.
    for variant_key in re.findall(r"^ *- key: (\S+)$", content, re.MULTILINE):
        assert not contains_value(message, variant_key)
    body = "\n".join(line for line in content.splitlines() if not line.startswith("#"))
    for long_value in re.findall(r":[ \t]+'?([^'\n]{20,}?)'?$", body, re.MULTILINE):
        assert long_value not in message


def test_every_invalid_case_is_in_its_readme() -> None:
    readme = (INVALID / "README.md").read_text(encoding="utf-8")
    listed = set(re.findall(r"^\| `([a-z0-9.-]+)\.yaml` \|", readme, re.MULTILINE))

    assert listed == {path.stem for path in INVALID.glob("*.yaml")}


def test_a_setting_a_variant_cant_change_lists_those_it_can() -> None:
    path = INVALID / "variant-universe.yaml"

    assert (
        "`variants.universe` isn't a setting a variant may change. A variant may change rules, "
        "max_holdings, rebalance_weeks, or slippage_percent." in rejection(path.read_bytes())
    )


@pytest.mark.parametrize("name", ["kind", "title"])
def test_a_screens_header_key_in_the_baseline_says_where_it_belongs(name: str) -> None:
    """Not that its spelling is wrong: it's a key of the experiment, at the top level."""
    path = INVALID / f"baseline-with-{name}.yaml"

    assert (
        f"`baseline.{name}` isn't a key of the baseline: an experiment's kind, schema_version, "
        "title, and purpose are written at the top level." in rejection(path.read_bytes())
    )


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("experiment-id-uppercase", "experiment_id"),
        ("key-uppercase", "variants.max_holdings[0].key"),
    ],
)
def test_an_experiment_key_isnt_called_a_label(name: str, key: str) -> None:
    """A review's results have labels; an experiment's ID and its variants' keys share their
    pattern, and aren't labels."""
    message = rejection((INVALID / f"{name}.yaml").read_bytes())

    assert (
        f"`{key}` must be 1 to 64 characters: lowercase letters, digits, _, and -, starting with a "
        "letter or a digit." in message
    )
    assert "label" not in message


def test_a_budget_below_the_cases_gives_their_number() -> None:
    path = INVALID / "budget-below-cases.yaml"

    assert "less than the experiment's 5 cases" in rejection(path.read_bytes())


def test_a_budget_of_exactly_the_cases_is_accepted() -> None:
    content = with_line("  provider_requests: 6\n", "  provider_requests: 5\n")

    assert read(content).budget.provider_requests == 5


def test_a_budget_whose_credits_a_plan_cant_hash_is_rejected() -> None:
    """At 5 credits a request, 1801439850948199 requests cost more than 2^53 - 1 credits, which
    canonical hashing can't keep exactly. tests/core/test_experiment_plan.py plans the largest
    budget accepted."""
    content = with_line("  provider_requests: 6\n", "  provider_requests: 1801439850948199\n")

    assert (
        "`budget.provider_requests` input should be less than or equal to 1801439850948198."
        in rejection(content)
    )


# The default variant, and the order of cases

NO_VARIANTS = example()[: example().index("variants:\n")] + "budget:\n  provider_requests: 2\n"


@pytest.mark.parametrize(("weeks", "default"), [(4, 1), (1, 4)])
def test_without_variants_the_default_is_the_other_rebalance_frequency(
    weeks: int, default: int
) -> None:
    content = with_line("  rebalance_weeks: 4\n", f"  rebalance_weeks: {weeks}\n", NO_VARIANTS)

    (variant,) = configured_variants(read(content))

    assert (variant.key, variant.default, variant.place) == (
        f"rebalance-weeks-{default}",
        True,
        None,
    )
    assert variant.screen.rebalance_weeks == default
    assert variant.description is None


def test_a_budget_must_cover_the_default_variant() -> None:
    content = with_line("  provider_requests: 2\n", "  provider_requests: 1\n", NO_VARIANTS)

    assert "less than the experiment's 2 cases" in rejection(content)


def test_a_rebalance_list_replaces_the_default() -> None:
    """A key that would name the default is free once a list replaces it."""
    content = with_line(
        "  slippage_percent:\n",
        "  rebalance_weeks:\n    - key: rebalance-weeks-1\n      value: 1\n  slippage_percent:\n",
    )

    variants = configured_variants(read(content))

    assert [(v.key, v.default) for v in variants if v.setting == "rebalance_weeks"] == [
        ("rebalance-weeks-1", False)
    ]


def test_an_empty_rebalance_list_turns_the_default_off() -> None:
    configuration = read_experiment_configuration(
        (FIXTURES / "no-microcaps.yaml").read_bytes(), "no-microcaps.yaml"
    )

    (variant,) = configured_variants(configuration)

    assert (variant.key, variant.setting) == ("no-microcaps", "rules")
    assert variant.screen.rules == ("AvgDailyTot(30) > 1000000", "MktCap > 300")


def test_the_order_of_keys_in_variants_leaves_no_trace() -> None:
    start, end = example().index("variants:\n"), example().index("budget:\n")
    reordered = (
        example()[:start]
        + "variants:\n"
        + "  slippage_percent:\n    - key: slippage-050\n      value: 0.5\n"
        + "  max_holdings:\n    - key: holdings-50\n      value: 50\n"
        + "  rules:\n"
        + "    - with: 'AvgDailyTot(30) > 100000000'\n"
        + "      replace: 'AvgDailyTot(30) > 1000000'\n"
        + "      description: A stricter liquidity floor, 100 million dollars a day.\n"
        + "      key: liquidity-100m\n"
        + example()[end:]
    )

    assert configured_variants(read(reordered)) == configured_variants(read(example()))


def test_each_list_keeps_its_order() -> None:
    content = with_line(
        "      value: 50\n", "      value: 50\n    - key: holdings-10\n      value: 10\n"
    )

    keys = [v.key for v in configured_variants(read(content)) if v.setting == "max_holdings"]

    assert keys == ["holdings-50", "holdings-10"]


def test_a_replaced_rule_keeps_its_place() -> None:
    content = with_line(
        "    - 'AvgDailyTot(30) > 1000000'\n",
        "    - 'AvgDailyTot(30) > 1000000'\n    - 'Price > 5'\n",
    )

    (rules,) = (v for v in configured_variants(read(content)) if v.setting == "rules")

    assert rules.screen.rules == ("AvgDailyTot(30) > 100000000", "Price > 5")


def test_a_rule_variant_written_as_block_scalars_is_accepted() -> None:
    content = with_line(
        "      with: 'AvgDailyTot(30) > 100000000'\n",
        "      with: >-\n        AvgDailyTot(30) > 100000000\n",
    )

    (rules, *_) = configured_variants(read(content))

    assert rules.screen.rules == ("AvgDailyTot(30) > 100000000",)


def test_a_variant_value_is_normalized() -> None:
    content = with_line("      value: 0.5\n", "      value: 0.500\n")

    (*_, slippage) = configured_variants(read(content))

    assert str(slippage.screen.slippage_percent) == "0.5"


def test_replace_must_name_exactly_one_rule() -> None:
    """A baseline that holds the replaced rule twice makes `replace` ambiguous."""
    content = with_line(
        "    - 'AvgDailyTot(30) > 1000000'\n",
        "    - 'AvgDailyTot(30) > 1000000'\n    - 'AvgDailyTot(30) > 1000000'\n",
    )

    assert "`variants.rules[0].replace` isn't one of the baseline's rules." in rejection(content)


def test_two_variants_of_one_rule_with_one_change_are_one_case() -> None:
    content = with_line(
        "  max_holdings:\n",
        "    - key: liquidity-again\n      replace: 'AvgDailyTot(30) > 1000000'\n"
        "      with: 'AvgDailyTot(30) > 100000000'\n  max_holdings:\n",
    )

    assert "`variants.rules[1]` gives the same settings as `variants.rules[0]`" in rejection(
        content
    )


def test_two_variants_that_add_one_rule_are_one_case() -> None:
    content = with_line(
        "    - key: liquidity-100m\n"
        "      description: A stricter liquidity floor, 100 million dollars a day.\n"
        "      replace: 'AvgDailyTot(30) > 1000000'\n"
        "      with: 'AvgDailyTot(30) > 100000000'\n",
        "    - key: no-microcaps\n      add: 'MktCap > 300'\n"
        "    - key: no-microcaps-again\n      add: 'MktCap > 300'\n",
    )

    assert "`variants.rules[1]` gives the same settings as `variants.rules[0]`" in rejection(
        content
    )


def test_a_key_repeated_within_a_list_names_both_places() -> None:
    content = with_line(
        "      value: 50\n", "      value: 50\n    - key: holdings-50\n      value: 10\n"
    )

    assert "`variants.max_holdings[1].key` repeats the key of `variants.max_holdings[0]`." in (
        rejection(content)
    )


def test_a_key_before_the_default_is_named_too() -> None:
    """The rules come before the default in the order of cases."""
    content = with_line("    - key: liquidity-100m\n", "    - key: rebalance-weeks-1\n")

    assert "`variants.rules[0].key` is the key of the default rebalance variant" in rejection(
        content
    )


# Text, keys, and quoting

DEVICE_NAMES = (
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{digit}" for digit in "123456789"),
    *(f"lpt{digit}" for digit in "123456789"),
)
"""The device names docs/contracts.md's review configuration lists, which an experiment's ID
and case keys exclude too."""


def test_the_device_names_are_the_review_labels_twenty_two() -> None:
    schema = json.loads(SCHEMA.read_bytes())

    assert WINDOWS_DEVICE_NAMES == DEVICE_NAMES
    assert schema["properties"]["experiment_id"]["not"] == {"enum": list(DEVICE_NAMES)}
    assert schema["$defs"]["HoldingsVariant"]["properties"]["key"]["not"] == {
        "enum": list(DEVICE_NAMES)
    }


@pytest.mark.parametrize("name", DEVICE_NAMES)
def test_a_device_name_is_neither_an_experiment_id_nor_a_case_key(name: str) -> None:
    for content, key in (
        (
            with_line("experiment_id: earnyield-sensitivity\n", f"experiment_id: {name}\n"),
            "experiment_id",
        ),
        (
            with_line("    - key: holdings-50\n", f"    - key: {name}\n"),
            "variants.max_holdings[0].key",
        ),
    ):
        message = rejection(content)

        assert f"`{key}` is a name Windows reserves for a device." in message
        assert not contains_value(message, name)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("title: Earnings yield sensitivity", "title: '" + "t" * 200 + "'"),
        ("experiment_id: earnyield-sensitivity", "experiment_id: " + "e" * 64),
        ("    - key: holdings-50", "    - key: " + "h" * 64),
        (
            "      description: A stricter liquidity floor, 100 million dollars a day.",
            "      description: '" + "d" * 500 + "'",
        ),
    ],
    ids=["title-200", "experiment-id-64", "key-64", "description-500"],
)
def test_text_at_its_limit_is_accepted(old: str, new: str) -> None:
    read(with_line(f"{old}\n", f"{new}\n"))


@pytest.mark.parametrize(
    ("pattern", "replacement"),
    [
        (r"^purpose: .*$", "purpose: '" + "p" * 2000 + "'"),
        (r"^  description: Earlier.*$", "  description: '" + "d" * 5000 + "'"),
    ],
    ids=["purpose-2000", "prior-research-5000"],
)
def test_long_text_at_its_limit_is_accepted(pattern: str, replacement: str) -> None:
    read(re.sub(pattern, replacement, example(), count=1, flags=re.MULTILINE))


def test_unknown_prior_research_needs_no_description() -> None:
    description = re.search(r"^  description: Earlier.*\n", example(), re.MULTILINE)
    assert description
    content = with_line("  status: partial\n", "  status: unknown\n").replace(
        description.group(0), ""
    )

    research = read(content).prior_research

    assert (research.status, research.description) == ("unknown", None)


def test_unknown_prior_research_may_have_a_description() -> None:
    research = read(with_line("  status: partial\n", "  status: unknown\n")).prior_research

    assert research.description is not None


@pytest.mark.parametrize(
    ("old", "new", "key"),
    [
        ("  universe: 'SP500'\n", "  universe: SP500\n", "baseline.universe"),
        ("  benchmark: 'SPY'\n", "  benchmark: SPY\n", "baseline.benchmark"),
        ("    formula: 'EarnYield'\n", "    formula: EarnYield\n", "baseline.ranking.formula"),
    ],
)
def test_the_baselines_text_portfolio123_receives_is_quoted(old: str, new: str, key: str) -> None:
    assert f"`{key}` is text Portfolio123 receives, written without quotes." in rejection(
        with_line(old, new)
    )


def test_text_never_sent_may_be_written_without_quotes() -> None:
    """The ID, title, purpose, prior research, keys, and descriptions describe the experiment."""
    configuration = read(example())

    assert configuration.title == "Earnings yield sensitivity"


def test_a_screen_configuration_is_not_an_experiment() -> None:
    path = REPO_ROOT / "tests" / "fixtures" / "screen-configs" / "formula.yaml"

    assert "`kind` must be experiment." in rejection(path.read_bytes(), path.name)


def test_a_missing_kind_names_the_experiment_kind() -> None:
    content = with_line("kind: experiment\n", "")

    assert "`kind` is required. An experiment configuration has `kind: experiment`." in (
        rejection(content)
    )


def test_each_problem_is_listed() -> None:
    content = (
        with_line("    - key: holdings-50\n", "    - key: Holdings-50\n")
        .replace("title: Earnings yield sensitivity", "title: ''")
        .replace("  rebalance_weeks: 4\n", "  rebalance_weeks: 2\n")
    )

    message = rejection(content)

    assert message.count("\n- ") == 3
    for key in ("title", "variants.max_holdings[0].key", "baseline.rebalance_weeks"):
        assert f"`{key}`" in message


def test_messages_never_include_values() -> None:
    """Errors are logged without input values (Pydantic conventions; REQ-06)."""
    canary = "canary-7c41e0b9"
    content = f"""\
kind: experiment
schema_version: 1.0.0
experiment_id: {canary}-UPPER
title: '{canary * 20}'
purpose: ['{canary}']
prior_research:
  status: {canary}
  description: ['{canary}']
baseline:
  universe: ['{canary}']
  rules: '{canary}'
  ranking:
    formula: ['{canary}']
    lower_is_better: '{canary}'
  max_holdings: '{canary}'
  benchmark: ['{canary}']
  start_date: '{canary}'
  end_date: '{canary}'
  rebalance_weeks: '{canary}'
  transaction_price: {canary}
  slippage_percent: '{canary}'
  pit_method: {canary}
  precision: '{canary}'
variants:
  max_holdings:
    - key: {canary}-UPPER
      description: '{canary * 40}'
      value: '{canary}'
  rules:
    - key: {canary}
      add: ['{canary}']
budget:
  provider_requests: '{canary}'
"""

    message = rejection(content)

    for key in (
        "experiment_id",
        "title",
        "purpose",
        "prior_research.status",
        "prior_research.description",
        "baseline.universe",
        "baseline.max_holdings",
        "variants.max_holdings[0].key",
        "variants.max_holdings[0].description",
        "variants.max_holdings[0].value",
        "variants.rules[0].add",
        "budget.provider_requests",
    ):
        assert f"`{key}`" in message
    assert canary not in message


# The model, given values as the reader gives them

BASELINE: dict[str, Any] = {
    "universe": "SP500",
    "rules": ["AvgDailyTot(30) > 1000000"],
    "ranking": {"formula": "EarnYield", "lower_is_better": False},
    "max_holdings": 25,
    "benchmark": "SPY",
    "start_date": date(2016, 1, 1),
    "end_date": date(2025, 12, 31),
    "rebalance_weeks": 4,
    "transaction_price": "open",
    "slippage_percent": Decimal("0.25"),
    "pit_method": "complete",
    "precision": 4,
}

VALID: dict[str, Any] = {
    "kind": "experiment",
    "schema_version": "1.0.0",
    "experiment_id": "earnyield-sensitivity",
    "title": "A title",
    "purpose": "A purpose.",
    "prior_research": {"status": "partial", "description": "Earlier work."},
    "baseline": BASELINE,
    "variants": {
        "rules": [
            {
                "key": "liquidity-100m",
                "replace": "AvgDailyTot(30) > 1000000",
                "with": "AvgDailyTot(30) > 100000000",
            }
        ],
        "max_holdings": [{"key": "holdings-50", "value": 50}],
    },
    "budget": {"provider_requests": 4},
}


REMOVE = object()


def changed(path: str, value: object) -> dict[str, Any]:
    """`VALID`, with the value at a dotted path, such as `variants.rules.0.with`, replaced; or
    removed, when `value` is `REMOVE`."""
    document = deepcopy(VALID)
    *parents, last = path.split(".")
    target: Any = document
    for part in parents:
        target = target[int(part)] if isinstance(target, list) else target[part]
    if value is REMOVE:
        del target[int(last) if isinstance(target, list) else last]
    elif isinstance(target, list):
        target[int(last)] = value
    else:
        target[last] = value
    return document


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("purpose", None),
        ("purpose", REMOVE),
        ("experiment_id", "nul"),
        ("prior_research.description", REMOVE),
        ("prior_research.description", None),
        ("prior_research.status", "incomplete"),
        ("baseline.title", "A title"),
        ("baseline.rebalance_weeks", 2),
        ("variants", None),
        ("variants", {}),
        ("variants.max_holdings", []),
        ("variants.max_holdings", {"key": "holdings-50", "value": 50}),
        ("variants.max_holdings.0.value", 25),
        ("variants.max_holdings.0.value", True),
        ("variants.max_holdings.0.key", "baseline"),
        ("variants.max_holdings.0.key", "liquidity-100m"),
        ("variants.max_holdings.0.description", None),
        ("variants.universe", [{"key": "russell", "value": "Russell 1000"}]),
        ("variants.rules.0.with", REMOVE),
        ("variants.rules.0.add", "MktCap > 300"),
        ("variants.rules.0.with_", "AvgDailyTot(30) > 100000000"),
        ("variants.rules.0.replace", "AvgDailyTot(20) > 1000000"),
        ("variants.rules.0.with", "AvgDailyTot(30) > 1000000"),
        ("variants.rebalance_weeks", [{"key": "weekly", "value": Decimal("1.0")}]),
        ("variants.slippage_percent", [{"key": "slippage", "value": 0.5}]),
        ("variants.slippage_percent", [{"key": "slippage", "value": "0.5"}]),
        ("budget.provider_requests", 3),
        ("budget.provider_requests", Decimal("6.0")),
    ],
    ids=[
        "null-purpose",
        "no-purpose",
        "device-name-id",
        "partial-without-description",
        "null-description",
        "status-incomplete",
        "baseline-title",
        "baseline-rebalance-2",
        "null-variants",
        "empty-variants",
        "empty-holdings-list",
        "holdings-not-a-list",
        "value-equals-baseline",
        "value-true",
        "key-baseline",
        "key-repeated",
        "null-variant-description",
        "universe-variant",
        "replace-without-with",
        "add-and-replace",
        "with-by-its-field-name",
        "replace-not-a-rule",
        "with-a-baseline-rule",
        "rebalance-decimal",
        "slippage-float",
        "slippage-text",
        "budget-below-cases",
        "budget-decimal",
    ],
)
def test_model_rejects_what_the_contract_calls_invalid(path: str, value: object) -> None:
    """A model that accepts something docs/contracts.md calls invalid has a defect, whatever
    the reader does first."""
    ExperimentConfiguration.model_validate(VALID)
    with pytest.raises(ValidationError):
        ExperimentConfiguration.model_validate(changed(path, value))


# Experiment configuration 1.1.0, from 0.4.0: a baseline ranked by a definition or a snapshot,
# and ranking variants.


def ranking_example() -> str:
    """docs/contracts.md's ranking example: the experiment on `ranking/value-momentum.xml`."""
    contracts = (REPO_ROOT / "docs" / "contracts.md").read_text(encoding="utf-8")
    section = contracts[contracts.index("#### Ranking example") :]
    return re.findall(r"```yaml\n(.*?)```", section, re.DOTALL)[0]


def read_v1_1(
    content: str | bytes, source_name: str = "experiment.yaml"
) -> ExperimentConfiguration | ExperimentConfigurationV1_1:
    """Reads with the reader of both versions, as if the file were in the fixtures' directory,
    from which the baseline's definition path is read."""
    if isinstance(content, str):
        content = content.encode()
    return read_experiment_configuration_v1_1(
        content, source_name, FIXTURES / source_name
    ).configuration


def read_ranked(content: str) -> ExperimentConfigurationV1_1:
    configuration = read_v1_1(content)
    assert isinstance(configuration, ExperimentConfigurationV1_1)
    return configuration


def ranking_rejection(content: str) -> str:
    return rejection(content, reader=read_v1_1)


def ranking_line(old: str, new: str) -> str:
    return with_line(old, new, ranking_example())


VALUE_HEAVY = "      set: {'Value': 60, 'Momentum': 20, 'Quality': 20}"


def ranking_example_xml() -> str:
    """docs/contracts.md's ranking example's definition: the XML of `ranking/value-momentum.xml`."""
    contracts = (REPO_ROOT / "docs" / "contracts.md").read_text(encoding="utf-8")
    section = contracts[contracts.index("#### Ranking example") :]
    return re.findall(r"```xml\n(.*?)```", section, re.DOTALL)[0]


def snapshot_example() -> str:
    """docs/contracts.md's ranking snapshot configuration example."""
    contracts = (REPO_ROOT / "docs" / "contracts.md").read_text(encoding="utf-8")
    section = contracts[contracts.index("### Ranking snapshot configuration") :]
    return re.findall(r"```yaml\n(.*?)```", section, re.DOTALL)[0]


def ranking_problems(tmp_path: Path, content: str, definition: bytes) -> list[str]:
    """The problems of the experiment `content`, read with `definition` as the file its baseline
    names, `ranking/value-momentum.xml`, beside it."""
    path = tmp_path / "experiment.yaml"
    path.write_text(content, encoding="utf-8")
    (tmp_path / "ranking").mkdir(exist_ok=True)
    (tmp_path / "ranking" / "value-momentum.xml").write_bytes(definition)
    with pytest.raises(TrialFolioError) as caught:
        read_experiment_configuration_v1_1(path.read_bytes(), path.name, path)
    assert caught.value.code == "config.invalid"
    return caught.value.message.split("\n")[1:]


ALTERED_DEFINITIONS = {
    "weight-zero": "a node's Weight is 0",
    "weight-percent": "a node's Weight isn't a decimal in plain notation",
    "xml-declaration": "it holds an XML declaration",
    "doctype": "it holds a document type declaration",
    "comment": "it holds a comment",
    "conditional-node": "an element where a node goes isn't a Composite",
    "root-not-ranking-system": "its root element isn't RankingSystem",
    "not-well-formed": "it isn't well-formed XML 1.0",
    "byte-order-mark": "the file starts with a byte-order mark",
    "empty-composite": "a Composite holds no node",
}
"""The alterations of the example's definition that its validation lists, each one of the
invalid definitions in `ranking/invalid/`, with the rule its message gives."""

VALUE_HEAVY_SET = "{'Value': 60, 'Momentum': 20, 'Quality': 20}"

ALTERED_VARIANTS = [
    (
        "{'Value': 60, 'Momentum': 20, 'Qualty': 20}",
        "set[2]` is a node path whose segment 1 names none",
    ),
    ("{'Value': 50, 'Momentum': 20}", "set` leaves out its parent's node at position 3."),
    ("{'Value': 60, 'Momentum/Year Return': 20, 'Quality': 20}", "set[1]` names a node of another"),
    ("{'Value': 60, '#1': 60, 'Momentum': 20, 'Quality': 20}", "set[1]` names the same node as"),
    ("{'Value': 60, 'Momentum': 20, 'Quality': 30}", "set` gives weights that don't sum to"),
    ("{'Value': 40, 'Momentum': 30, 'Quality': 30}", "set` gives every node the weight it has"),
]
"""The alterations of the example's `value-heavy` variant that its validation lists, with the
start of the problem its message gives, after `variants.ranking[0].`."""


def test_documented_ranking_example_compiles_to_its_cases(tmp_path: Path) -> None:
    """Repeats the ranking example's validation, which R04-T02 left for R04-T04 (release 0.4.0's
    other checks in the default suite). Its XML and YAML are the fixtures, byte for byte, and so
    is the snapshot example; the experiment gives the four cases the example describes, each with
    the definition it describes; each alteration the validation lists fails; and a path with `\\/`
    in single quotes names the node a path with `\\\\/` in double quotes names. The plan these
    cases compile to is checked in `tests/core/test_ranking_plan.py` (release 0.4.0's R04-T07)."""
    xml = ranking_example_xml()
    assert (FIXTURES / "ranking" / "value-momentum.xml").read_bytes() == xml.encode()
    assert (FIXTURES / "ranking-example.yaml").read_bytes() == ranking_example().encode()
    snapshot = REPO_ROOT / "tests" / "fixtures" / "ranking-snapshot-configs" / "example.yaml"
    assert snapshot.read_bytes() == snapshot_example().encode()

    path = FIXTURES / "ranking-example.yaml"
    read = read_experiment_configuration_v1_1(path.read_bytes(), path.name, path)

    assert read.definition is not None and read.definition.text == xml
    keys = [
        "baseline",
        *(variant.key for variant in configured_variants_v1_1(read_ranked(ranking_example()))),
    ]
    assert keys == ["baseline", "value-heavy", "tilt-earnings-yield", "no-sales-yield"]
    heavy, tilt, no_sales = (case.definition.text for case in read.ranking_cases)

    def weights(text: str, *changes: tuple[str, str, str]) -> str:
        for name, old, new in changes:
            written = f'Name="{name}" Weight="{old}"'
            assert text.count(written) == 1
            text = text.replace(written, f'Name="{name}" Weight="{new}"')
        return text

    assert heavy == weights(
        xml, ("Value", "40", "60"), ("Momentum", "30", "20"), ("Quality", "30", "20")
    )
    assert tilt == weights(xml, ("Earnings Yield", "50", "70"), ("Sales Yield", "50", "30"))
    lines = xml.split("\n")
    assert lines[5:8] == [
        (
            '\t\t<StockFormula Name="Sales Yield" Weight="50" RankType="Higher" Scope="Universe" '
            'Description="">'
        ),
        "\t\t\t<Formula>…</Formula>",
        "\t\t</StockFormula>",
    ]
    removed = "\n".join(lines[:5] + lines[8:])
    assert no_sales == weights(removed, ("Earnings Yield", "50", "100"))
    assert len({xml, heavy, tilt, no_sales}) == 4

    content = ranking_example()
    for name, rule in ALTERED_DEFINITIONS.items():
        definition = (FIXTURES / "ranking" / "invalid" / f"{name}.xml").read_bytes()
        (problem,) = ranking_problems(tmp_path, content, definition)
        assert problem.startswith("- `baseline.ranking.definition` names a definition"), name
        assert rule in problem, name
    for altered, problem in ALTERED_VARIANTS:
        found = ranking_problems(
            tmp_path, with_line(VALUE_HEAVY_SET, altered, content), xml.encode()
        )
        assert found == [found[0]] and found[0].startswith(f"- `variants.ranking[0].{problem}")
    # Two nodes that share a name, which the path names.
    shared = xml.replace('Name="Sales Yield"', 'Name="Earnings Yield"').encode()
    assert any(
        "`variants.ranking[1].set[0]` is a node path whose segment 2 names more than one" in found
        for found in ranking_problems(tmp_path, content, shared)
    )
    # The removal of a composite, and of a composite's only factor.
    composite = with_line("      remove: 'Value/Sales Yield'", "      remove: 'Value'", content)
    composite = with_line(
        "      set: {'Value/Earnings Yield': 100}",
        "      set: {'Momentum': 50, 'Quality': 50}",
        composite,
    )
    assert ranking_problems(tmp_path, composite, xml.encode())[0].startswith(
        "- `variants.ranking[2].remove` names a composite."
    )
    only = xml.encode().replace("\n".join(lines[5:8]).encode() + b"\n", b"")
    only = only.replace(b'Name="Earnings Yield" Weight="50"', b'Name="Earnings Yield" Weight="100"')
    alone = with_line(
        "      remove: 'Value/Sales Yield'", "      remove: 'Value/Earnings Yield'", content
    )
    assert any(
        problem.startswith("- `variants.ranking[2].remove` names its parent's only node")
        for problem in ranking_problems(tmp_path, alone, only)
    )
    # An escaped / in single quotes, and in double quotes, where YAML reads its own escapes first.
    slashed = xml.replace('Name="Sales Yield"', 'Name="P/E"').encode()
    single = with_line(
        "      set: {'Value/Earnings Yield': 70, 'Value/Sales Yield': 30}",
        "      set: {'Value/Earnings Yield': 70, 'Value/P\\/E': 30}",
        content,
    )
    single = with_line("      remove: 'Value/Sales Yield'", "      remove: 'Value/P\\/E'", single)
    double = single.replace("'Value/P\\/E'", '"Value/P\\\\/E"')
    cases = []
    for written in (single, double):
        path = tmp_path / "experiment.yaml"
        path.write_text(written, encoding="utf-8")
        (tmp_path / "ranking" / "value-momentum.xml").write_bytes(slashed)
        cases.append(
            [
                (case.definition.text, case.remove and case.remove.path)
                for case in read_experiment_configuration_v1_1(
                    path.read_bytes(), path.name, path
                ).ranking_cases
            ]
        )
    assert cases[0] == cases[1]
    assert cases[0][2][1] == "Value/P\\/E"


def test_the_ranking_example_reads_as_documented() -> None:
    """Its structure: the baseline ranked by a definition file, with its ranking method, three
    ranking variants, no default, and a budget of two requests a case. The definition, and the
    cases it gives, are read with it (release 0.4.0's R04-T06)."""
    configuration = read_v1_1(ranking_example())

    assert isinstance(configuration, ExperimentConfigurationV1_1)
    assert configuration.baseline.ranking.model_dump() == {
        "definition": "ranking/value-momentum.xml",
        "ranking_method": "percentile_nas_negative",
    }
    variants = configured_variants_v1_1(configuration)
    assert [(variant.key, variant.setting, variant.place) for variant in variants] == [
        ("value-heavy", "ranking", "variants.ranking[0]"),
        ("tilt-earnings-yield", "ranking", "variants.ranking[1]"),
        ("no-sales-yield", "ranking", "variants.ranking[2]"),
    ]
    changes = [variant.variant for variant in variants]
    assert all(isinstance(change, RankingVariant) for change in changes)
    assert [
        (change.set, change.remove) for change in changes if isinstance(change, RankingVariant)
    ] == [
        ({"Value": Decimal(60), "Momentum": Decimal(20), "Quality": Decimal(20)}, None),
        ({"Value/Earnings Yield": Decimal(70), "Value/Sales Yield": Decimal(30)}, None),
        ({"Value/Earnings Yield": Decimal(100)}, "Value/Sales Yield"),
    ]
    assert all(variant.screen is None for variant in variants)
    assert configuration.budget.provider_requests == 8


def test_a_baseline_may_name_a_snapshot_instead(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The example's second form: the snapshot's directory, and no `ranking_method`, which the
    snapshot records. Release 0.4.0's R04-T10 reads the snapshot, so the test takes one, over the
    fake server, beside the configuration, where R04-T05's test named a directory that didn't
    exist, which no reader read then."""
    SnapshotBuilder(monkeypatch, tmp_path / "home").snapshot(
        tmp_path / "ranking" / "value-momentum"
    )
    content = ranking_line(
        "    definition: 'ranking/value-momentum.xml'\n    ranking_method: percentile_nas_negative",
        "    snapshot: 'ranking/value-momentum/'",
    )
    path = tmp_path / "experiment.yaml"

    configuration = read_experiment_configuration_v1_1(content.encode(), path.name, path)

    assert configuration.configuration.baseline.ranking.model_dump() == {
        "snapshot": "ranking/value-momentum/"
    }
    assert configuration.snapshot is not None


def test_a_weight_is_read_as_a_normalized_decimal() -> None:
    content = ranking_line(
        VALUE_HEAVY, "      set: {'Value': 60.0, 'Momentum': 20.000, 'Quality': 20}"
    )

    variant = configured_variants_v1_1(read_ranked(content))[0].variant

    assert isinstance(variant, RankingVariant)
    assert [str(weight) for weight in variant.set.values()] == ["60", "20", "20"]


def test_ranking_variants_come_after_rules_and_before_holdings() -> None:
    """The order of cases: the variants of rules, ranking, max_holdings, rebalance_weeks, and
    slippage_percent, the default in rebalance_weeks' place."""
    content = ranking_line(
        "  rebalance_weeks: []\n",
        "  slippage_percent:\n    - key: slippage-050\n      value: 0.5\n"
        "  max_holdings:\n    - key: holdings-50\n      value: 50\n"
        "  rules:\n    - key: no-microcaps\n      add: 'MktCap > 300'\n",
    )
    content = with_line("provider_requests: 8", "provider_requests: 16", content)

    variants = configured_variants_v1_1(read_ranked(content))

    assert [variant.key for variant in variants] == [
        "no-microcaps",
        "value-heavy",
        "tilt-earnings-yield",
        "no-sales-yield",
        "holdings-50",
        "rebalance-weeks-1",
        "slippage-050",
    ]
    assert [variant.default for variant in variants] == [False] * 5 + [True, False]
    # A variant of another setting keeps the baseline's definition: its case's ranking is the
    # baseline's.
    holdings = variants[4].screen
    assert holdings is not None and holdings.max_holdings == 50
    assert holdings.ranking == read_v1_1(content).baseline.ranking


def test_the_default_variant_counts_two_requests_with_a_definition() -> None:
    """Without `rebalance_weeks`, the default is a fifth case, so the budget needs 10."""
    content = ranking_line("  rebalance_weeks: []\n", "")

    assert "less than the 10 requests the experiment's 5 cases need" in ranking_rejection(content)
    assert read_v1_1(with_line("provider_requests: 8", "provider_requests: 10", content))


def test_a_budget_of_two_requests_a_case_is_accepted() -> None:
    assert read_v1_1(ranking_example()).budget.provider_requests == 8


def test_a_1_1_0_baseline_ranked_by_a_formula_needs_one_request_a_case() -> None:
    """Version 1.1.0 changes nothing for a baseline that isn't ranked by a definition."""
    content = example().replace("schema_version: 1.0.0", "schema_version: 1.1.0", 1)

    configuration = read_v1_1(content)

    assert isinstance(configuration, ExperimentConfigurationV1_1)
    assert [variant.key for variant in configured_variants_v1_1(configuration)] == [
        variant.key for variant in configured_variants(read(example()))
    ]
    assert read_v1_1(with_line("provider_requests: 6", "provider_requests: 5", content))
    budget = with_line("provider_requests: 6", "provider_requests: 4", content)
    assert ranking_rejection(budget).endswith(
        "`budget.provider_requests` is less than the experiment's 5 cases. It must be at least "
        "the number of cases, so that each can be sent once."
    )


def test_a_ranking_variant_s_key_is_unique_among_the_cases() -> None:
    content = ranking_line(
        "  rebalance_weeks: []\n",
        "  max_holdings:\n    - key: value-heavy\n      value: 50\n  rebalance_weeks: []\n",
    )
    content = with_line("provider_requests: 8", "provider_requests: 10", content)

    assert "`variants.max_holdings[0].key` repeats the key of `variants.ranking[0]`" in (
        ranking_rejection(content)
    )


def test_a_set_entry_is_named_by_its_place_never_by_its_path() -> None:
    """A node path holds node names, the user's strategy definition, so no message holds one,
    whatever rule the entry breaks (node paths)."""
    paths = ["Momentum/Secret Price", "Value #2", "Quality"]
    content = ranking_line(
        VALUE_HEAVY,
        f"      set: {{'{paths[0]}': 60, '{paths[1]}': '20', '{paths[2]}': 0, '{paths[1]}': 1}}",
    )

    message = ranking_rejection(content)

    assert "`variants.ranking[0].set[0]`" in message
    for path in paths:
        assert path not in message
    for path in ("Momentum", "Secret Price", "Value #2"):
        assert path not in message


def test_each_weight_problem_names_its_entry() -> None:
    content = ranking_line(VALUE_HEAVY, "      set: {'Value': '60', 'Momentum': 0, 'Quality': 20}")

    message = ranking_rejection(content)

    assert "`variants.ranking[0].set[0]` must be a number written without quotes" in message
    assert "`variants.ranking[0].set[1]` must be greater than 0" in message
    assert "Value" not in message and "Momentum" not in message


@pytest.mark.parametrize("weight", ["sixty", "60%"])
def test_a_weight_written_as_plain_text_is_reported_as_a_weight(weight: str) -> None:
    """A weight is never text, so a plain one is a weight written wrongly, not a node path
    written without quotes: the entry's key, `'Value'`, is quoted."""
    content = ranking_line(
        VALUE_HEAVY, f"      set: {{'Value': {weight}, 'Momentum': 20, 'Quality': 20}}"
    )

    message = ranking_rejection(content)

    assert message == (
        "experiment.yaml isn't a valid configuration:\n"
        "- `variants.ranking[0].set[0]` must be a number written without quotes, such as 0.25."
    )


def test_a_plain_path_with_a_plain_weight_is_reported_once_for_each() -> None:
    content = ranking_line(VALUE_HEAVY, "      set: {Value: sixty, 'Momentum': 20, 'Quality': 20}")

    message = ranking_rejection(content)

    assert message.count("`variants.ranking[0].set[0]` is a node path written without quotes") == 1
    assert (
        message.count("`variants.ranking[0].set[0]` must be a number written without quotes") == 1
    )


def test_an_empty_set_names_its_variant() -> None:
    message = ranking_rejection(ranking_line(VALUE_HEAVY, "      set: {}"))

    assert "`variants.ranking[0].set` must hold at least 1 item." in message


def test_a_set_s_paths_and_remove_may_be_in_double_quotes() -> None:
    content = ranking_line(VALUE_HEAVY, '      set: {"Value": 60, "Momentum": 20, "Quality": 20}')
    content = with_line(
        "      remove: 'Value/Sales Yield'", '      remove: "Value/Sales Yield"', content
    )

    variants = configured_variants_v1_1(read_ranked(content))

    assert [variant.key for variant in variants][-1] == "no-sales-yield"


def test_a_1_0_0_file_can_t_vary_the_ranking() -> None:
    path = INVALID / "variant-ranking.yaml"

    message = rejection(path.read_bytes(), path.name, read_v1_1)

    assert (
        "`variants.ranking` needs schema_version 1.1.0, with a baseline ranked by a definition "
        "or a snapshot. In 1.0.0, a variant may change rules, max_holdings, rebalance_weeks, or "
        "slippage_percent." in message
    )


@pytest.mark.parametrize(
    ("name", "problem"),
    [
        (
            "variant-ranking.yaml",
            (
                "`variants.ranking` isn't a setting a variant may change. A variant may change "
                "rules, max_holdings, rebalance_weeks, or slippage_percent."
            ),
        ),
        (
            "baseline-definition-in-1.0.0.yaml",
            (
                "`baseline.ranking` must hold exactly one of formula, name, or id. The supported "
                "forms are {formula, lower_is_better}, {name}, and {id}."
            ),
        ),
    ],
    ids=["ranking-variant", "baseline-definition"],
)
def test_the_1_0_0_reader_gives_a_1_0_0_file_0_3_0_s_message(name: str, problem: str) -> None:
    """0.3.0's reader, which reads 1.0.0 only, keeps 0.3.0's message for such a file."""
    path = INVALID / name

    message = rejection(path.read_bytes(), path.name)

    assert message == f"{name} isn't a valid configuration:\n- {problem}"


def run_reader(directory: Path) -> Callable[[bytes, str], object]:
    """`trialfolio run`'s reader, as if the file were in `directory`."""
    return lambda content, name: read_run_configuration(content, name, directory / name)


@pytest.mark.parametrize(
    ("name", "later"),
    [
        ("variant-ranking.yaml", "`variants.ranking` needs schema_version 1.1.0"),
        ("baseline-definition-in-1.0.0.yaml", "a form that needs schema_version 1.1.0"),
    ],
    ids=["ranking-variant", "baseline-definition"],
)
def test_run_s_reader_tells_a_1_0_0_file_its_key_needs_1_1_0(name: str, later: str) -> None:
    """Since R04-T12, `trialfolio run` reads 1.1.0, with the reader of both versions, so it tells
    a 1.0.0 file that gives a key of 1.1.0 that the key needs that version, as the release's
    changes after sign-off give it (R04-T05's review)."""
    path = INVALID / name

    message = rejection(path.read_bytes(), path.name, run_reader(INVALID))

    assert later in message
    assert message == rejection(path.read_bytes(), path.name, read_v1_1)


RANKED_BY_SALES = (
    "  ranking:\n"
    "    - key: ranked-by-sales\n"
    "      value:\n"
    "        formula: 'SalesGr%TTM'\n"
    "        lower_is_better: false\n"
)

NOT_A_VARIANT_SETTING = (
    "`variants.ranking` isn't a setting a variant may change. A variant may change rules, "
    "max_holdings, rebalance_weeks, or slippage_percent."
)


@pytest.mark.parametrize(
    ("variant", "problem"),
    [
        ("      set:\n        Value: 100\n", NOT_A_VARIANT_SETTING),
        ("      remove: Value\n", NOT_A_VARIANT_SETTING),
        (
            "      set:\n        'Value': 1\n        'Value': 2\n",
            "`variants.ranking[0].set.Value` appears more than once.",
        ),
        (
            "      set:\n        'api_key': 1\n",
            (
                "`variants.ranking[0].set.api_key` looks like a credential. A configuration never "
                "holds credentials: the CLI reads them from TRIALFOLIO_P123_API_ID and "
                "TRIALFOLIO_P123_API_KEY."
            ),
        ),
    ],
    ids=["unquoted-path", "unquoted-remove", "path-twice", "credential-word"],
)
def test_the_1_0_0_reader_reads_a_1_0_0_ranking_variant_s_keys_as_0_3_0_did(
    variant: str, problem: str
) -> None:
    """0.3.0's reader has no node paths: it reads a ranking variant's keys as any other, as 0.3.0
    did, and asks for no quotes a 1.0.0 file can't use. Its message is the one 0.3.0 gave."""
    path = INVALID / "variant-ranking.yaml"
    content = path.read_text(encoding="utf-8")
    assert content.count(RANKED_BY_SALES) == 1
    content = content.replace(RANKED_BY_SALES, f"  ranking:\n    - key: weights\n{variant}")

    message = rejection(content, path.name)

    assert message == f"{path.name} isn't a valid configuration:\n- {problem}"


@pytest.mark.parametrize(
    "variant",
    [
        "      set:\n        Value: 100\n",
        "      set:\n        'Value': 1\n        'Value': 2\n",
        "      set:\n        'api_key': 1\n",
    ],
    ids=["unquoted-path", "path-twice", "credential-word"],
)
def test_run_s_reader_reads_a_1_0_0_ranking_variant_s_keys_as_node_paths(variant: str) -> None:
    """Since R04-T12, `trialfolio run` reads with the reader of both versions, which reads a
    ranking variant's keys as node paths in either version, and names a `set` entry by its
    place, never by its path."""
    path = INVALID / "variant-ranking.yaml"
    content = path.read_text(encoding="utf-8")
    content = content.replace(RANKED_BY_SALES, f"  ranking:\n    - key: weights\n{variant}")

    message = rejection(content, path.name, run_reader(INVALID))

    assert message == rejection(content, path.name, read_v1_1)
    assert "variants.ranking[0].set." not in message
    assert "api_key" not in message


def test_a_1_1_0_variant_of_another_setting_names_the_ranking_among_those_it_can() -> None:
    content = ranking_line(
        "  rebalance_weeks: []\n",
        "  universe:\n    - key: russell\n      value: 'Russell 1000'\n  rebalance_weeks: []\n",
    )

    assert (
        "`variants.universe` isn't a setting a variant may change. A variant may change rules, "
        "ranking, max_holdings, rebalance_weeks, or slippage_percent."
    ) in ranking_rejection(content)


def test_without_files_the_reader_reads_no_file_the_baselines_ranking_names() -> None:
    """The core reads the configuration of a plan without a ranking definition with `files`
    false: a baseline's definition named, without its bytes, is a `ValueError`, though the file
    exists, while a baseline ranked another way reads (R04-T12)."""
    assert read_v1_1(ranking_example()) is not None

    with pytest.raises(ValueError, match="names a file"):
        read_experiment_configuration_v1_1(
            ranking_example().encode(), "experiment.yaml", FIXTURES / "experiment.yaml", files=False
        )
    formula = with_line("schema_version: 1.0.0", "schema_version: 1.1.0")
    read = read_experiment_configuration_v1_1(
        formula.encode(), "experiment.yaml", "experiment.yaml", files=False
    )
    assert (read.definition, read.configuration.schema_version) == (None, "1.1.0")


def test_the_readers_name_the_versions_they_read() -> None:
    """0.3.0's reader reads 1.0.0 only, so a 1.1.0 file is a version it doesn't read; the reader
    of both versions, which `trialfolio run` reads with since R04-T12, names both."""
    assert "Supported versions: 1.0.0." in rejection(ranking_example())
    unsupported = with_line("schema_version: 1.0.0", "schema_version: 2.0.0")
    assert "Supported versions: 1.0.0, 1.1.0." in ranking_rejection(unsupported)
    assert "Supported versions: 1.0.0, 1.1.0." in rejection(
        unsupported, "experiment.yaml", run_reader(FIXTURES)
    )


def test_the_reader_of_both_versions_reads_1_0_0_as_before() -> None:
    configuration = read_v1_1(example())

    assert type(configuration) is ExperimentConfiguration
    assert configuration == read(example())
