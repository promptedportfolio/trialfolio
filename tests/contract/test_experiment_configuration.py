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
"""

import json
import re
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from trialfolio.configuration import read_experiment_configuration, read_screen_configuration
from trialfolio.contracts.common import WINDOWS_DEVICE_NAMES
from trialfolio.contracts.experiment_configuration import (
    ExperimentConfiguration,
    configured_variants,
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


def rejection(content: bytes | str, source_name: str = "experiment.yaml") -> str:
    """Reads `content`, expects `config.invalid`, and returns the message."""
    if isinstance(content, str):
        content = content.encode()
    with pytest.raises(TrialFolioError) as caught:
        read_experiment_configuration(content, source_name)
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

    message = rejection(path.read_bytes(), path.name)

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
    listed = set(re.findall(r"^\| `([a-z0-9-]+)\.yaml` \|", readme, re.MULTILINE))

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
