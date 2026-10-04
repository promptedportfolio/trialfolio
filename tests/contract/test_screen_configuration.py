"""Reading a screen configuration enforces docs/contracts.md's screen configuration rules.

Traces to R01-AC02, R01-AC09, and R01-AC11 (Compustat) in release 0.1.0's test pairing, and to
the configuration file rules in docs/contracts.md. The fixtures are in
tests/fixtures/screen-configs/. `test_documented_example_resolves_to_reference_request` traces to
the example's validation against the request Portfolio123 accepted in R01-T01.
"""

import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from trialfolio.configuration import read_screen_configuration
from trialfolio.contracts.screen_configuration import (
    FormulaRanking,
    IdRanking,
    NameRanking,
    ScreenConfiguration,
)
from trialfolio.contracts.screen_settings import SCREEN_SETTINGS_BY_NAME, check_value
from trialfolio.errors import TrialFolioError
from trialfolio.planning import VERIFIED_VERSIONS, Versions, build_plan

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "screen-configs"
INVALID = FIXTURES / "invalid"


def documented_example() -> str:
    contracts = (REPO_ROOT / "docs" / "contracts.md").read_text(encoding="utf-8")
    found = re.search(r"#### Example\n\n```yaml\n(.*?)```", contracts, re.DOTALL)
    assert found, "docs/contracts.md has no screen configuration example"
    return found.group(1)


def read_fixture(name: str) -> ScreenConfiguration:
    path = FIXTURES / name
    return read_screen_configuration(path.read_bytes(), path.name)


def rejection(content: bytes, source_name: str = "screen.yaml") -> str:
    """Reads `content`, expects `config.invalid`, and returns the message."""
    with pytest.raises(TrialFolioError) as caught:
        read_screen_configuration(content, source_name)
    assert caught.value.code == "config.invalid"
    return caught.value.message


def with_line(old: str, new: str) -> bytes:
    """The documented example, with one line replaced."""
    example = documented_example()
    assert old in example
    return example.replace(old, new, 1).encode()


def test_documented_example_reads_as_documented() -> None:
    configuration = read_screen_configuration(documented_example().encode(), "example.yaml")

    assert configuration == ScreenConfiguration(
        kind="screen",
        schema_version="1.0.0",
        title="Earnings yield with a liquidity floor",
        purpose="Reference backtest for the 0.1.0 response layout.",
        universe="SP500",
        rules=("AvgDailyTot(30) > 1000000",),
        ranking=FormulaRanking(formula="EarnYield", lower_is_better=False),
        max_holdings=25,
        benchmark="SPY",
        start_date=date(2016, 1, 1),
        end_date=date(2025, 12, 31),
        rebalance_weeks=4,
        transaction_price="open",
        slippage_percent=Decimal("0.25"),
        pit_method="complete",
        precision=4,
    )
    assert configuration.data_vendor is None


def test_formula_fixture_is_the_documented_example() -> None:
    assert (FIXTURES / "formula.yaml").read_text(encoding="utf-8") == documented_example()


def test_documented_example_resolves_to_reference_request() -> None:
    configuration = read_screen_configuration(documented_example().encode(), "example.yaml")
    versions = Versions(
        trialfolio="0.1.0",
        p123api=VERIFIED_VERSIONS["p123api"][0],
        requests=VERIFIED_VERSIONS["requests"][0],
        urllib3=VERIFIED_VERSIONS["urllib3"][0],
    )
    reference = REPO_ROOT / "reference" / "p123api-screen-backtest" / "request.json"

    (request,) = build_plan(configuration, versions).cases[0].requests

    assert request.operation == "screen_backtest"
    # Compared as JSON text, so a float and an integer can't pass for each other.
    assert json.dumps(request.params.model_dump(mode="json"), sort_keys=True) == json.dumps(
        json.loads(reference.read_text(encoding="utf-8")), sort_keys=True
    )


@pytest.mark.parametrize("path", sorted(INVALID.glob("*.yaml")), ids=lambda path: path.stem)
def test_invalid_configuration_is_rejected_naming_its_key(path: Path) -> None:
    content = path.read_bytes()
    key = re.search(r"^# Key: (.+)$", content.decode(), re.MULTILINE)
    assert key, f"{path.name} has no '# Key:' line"

    message = rejection(content, path.name)

    assert message.startswith(f"{path.name} isn't a valid configuration:")
    if key.group(1) != "-":
        assert f"`{key.group(1)}`" in message


def test_every_invalid_case_is_in_its_readme() -> None:
    readme = (INVALID / "README.md").read_text(encoding="utf-8")
    listed = set(re.findall(r"^\| `([a-z0-9-]+)\.yaml` \|", readme, re.MULTILINE))

    assert listed == {path.stem for path in INVALID.glob("*.yaml")}


@pytest.mark.parametrize(
    "name", ["missing-start-date", "missing-end-date", "missing-slippage-percent"]
)
def test_dates_and_slippage_have_no_default(name: str) -> None:
    """R01-AC09: never today, and never zero."""
    path = INVALID / f"{name}.yaml"
    key = name.removeprefix("missing-").replace("-", "_")

    assert f"`{key}` is required." in rejection(path.read_bytes(), path.name)


def test_written_differently_reads_the_same() -> None:
    """Key order, `0.250`, and quoted dates don't change the configuration (R01-AC25's input)."""
    assert read_fixture("written-differently.yaml") == read_fixture("vendor-factset.yaml")


def test_factset_is_the_only_vendor() -> None:
    """R01-AC11: an explicit FactSet is accepted; Compustat is rejected."""
    assert read_fixture("vendor-factset.yaml").data_vendor == "FactSet"
    path = INVALID / "vendor-compustat.yaml"
    assert "`data_vendor` must be FactSet" in rejection(path.read_bytes())


@pytest.mark.parametrize(
    ("name", "ranking"),
    [
        ("formula.yaml", FormulaRanking(formula="EarnYield", lower_is_better=False)),
        ("ranking-name.yaml", NameRanking(name="Synthetic Value Composite")),
        ("ranking-id.yaml", IdRanking(id=424242)),
    ],
)
def test_each_ranking_form_reads(name: str, ranking: object) -> None:
    assert read_fixture(name).ranking == ranking


def test_non_ascii_title_is_kept() -> None:
    assert read_fixture("title-non-ascii.yaml").title.startswith("Café screen")


def test_canaries_fixture_is_valid() -> None:
    assert read_fixture("canaries.yaml").universe == "canary-universe-3c8b2d40"


@pytest.mark.parametrize(
    ("written", "normalized"),
    [
        ("0.25", "0.25"),
        ("0.250", "0.25"),
        ("1", "1"),
        ("1.0", "1"),
        ("100", "100"),
        ("0", "0"),
        ("0.0001", "0.0001"),
        ("123456789012345", "123456789012345"),
    ],
)
def test_slippage_is_normalized(written: str, normalized: str) -> None:
    """Decimals are read from their text and normalized: trailing zeros go, then the point."""
    content = with_line("slippage_percent: 0.25", f"slippage_percent: {written}")

    assert str(read_screen_configuration(content, "screen.yaml").slippage_percent) == normalized


@pytest.mark.parametrize(
    ("written", "normalized"),
    [("1000000000000000", "1000000000000000"), ("1000000000000000.0", "1000000000000000")],
)
def test_trailing_zeros_of_a_whole_number_are_not_significant(
    written: str, normalized: str
) -> None:
    """10^15 has one significant digit, and is below 10^16."""
    content = with_line("slippage_percent: 0.25", f"slippage_percent: {written}")

    assert str(read_screen_configuration(content, "screen.yaml").slippage_percent) == normalized


@pytest.mark.parametrize("written", ["9100000000000000", "9100000000000000.0"])
def test_whole_decimal_reads_the_same_with_or_without_a_point(written: str) -> None:
    """`1.0` and `1` are the same setting, up to the 10^16 limit."""
    content = with_line("slippage_percent: 0.25", f"slippage_percent: {written}")

    assert str(read_screen_configuration(content, "screen.yaml").slippage_percent) == (
        "9100000000000000"
    )


def test_integer_above_2_to_the_53_is_rejected() -> None:
    content = with_line("max_holdings: 25", "max_holdings: 9007199254740992")

    assert "`max_holdings` input should be less than or equal to 9007199254740991" in rejection(
        content
    )


def test_decimal_of_10_to_the_16_is_rejected() -> None:
    """The named fixture must reach the decimal magnitude rule, not the YAML integer limit."""
    content = (INVALID / "slippage-too-large.yaml").read_bytes()

    assert "`slippage_percent` must be less than 10^16." in rejection(content)


def test_integer_too_long_to_convert_is_rejected() -> None:
    """Python won't convert more than 4300 digits; the reader must still say config.invalid."""
    content = with_line("max_holdings: 25", "max_holdings: " + "9" * 5000)

    assert "`max_holdings` has more than 16 digits" in rejection(content)


def test_deep_nesting_is_rejected() -> None:
    content = with_line("universe: SP500", "universe: " + "[" * 3000 + "]" * 3000)

    assert "`universe` is nested more than 16 levels deep." in rejection(content)


@pytest.mark.parametrize(
    ("old", "new", "key"),
    [
        ("title: Earnings yield with a liquidity floor", "title: ' '", "title"),
        ("benchmark: SPY", "benchmark: '\t'", "benchmark"),
        ("  - 'AvgDailyTot(30) > 1000000'", "  - '  '", "rules[0]"),
        ("  formula: 'EarnYield'", "  formula: ' '", "ranking.formula"),
    ],
)
def test_blank_text_is_rejected(old: str, new: str, key: str) -> None:
    """Non-empty text has a character that isn't whitespace."""
    assert f"`{key}` is blank." in rejection(with_line(old, new))


def test_yaml_boolean_in_a_text_key_says_to_quote_it() -> None:
    message = rejection(with_line("benchmark: SPY", "benchmark: ON"))

    assert "`benchmark` is a YAML 1.1 boolean" in message
    assert "quote it if it's text" in message


@pytest.mark.parametrize(
    ("line", "fragment"),
    [
        ('universe: "SP\\q500"', "'q'"),
        ("slippage_percent: @x", "'@'"),
        ("end_date: '0000-01-01'", "year 0"),
    ],
)
def test_messages_quote_no_part_of_a_value(line: str, fragment: str) -> None:
    key = line.split(":", 1)[0]
    old = next(
        existing for existing in documented_example().splitlines() if existing.startswith(key)
    )

    assert fragment not in rejection(with_line(old, line))


def test_a_rule_of_the_wrong_type_is_one_error() -> None:
    message = rejection(with_line("  - 'AvgDailyTot(30) > 1000000'", "  - 5"))

    assert message.count("\n- ") == 1
    assert "`rules[0]` input should be a valid string." in message


def test_no_rules_needs_at_least_one() -> None:
    content = with_line("rules:\n  - 'AvgDailyTot(30) > 1000000'\n", "rules: []\n")

    assert "`rules` must hold at least 1 item." in rejection(content)


def test_an_empty_key_is_named() -> None:
    content = documented_example().encode() + b"'': 1\n"

    assert "`''` isn't a key this configuration accepts." in rejection(content)


# Formulas are written in quotes or as block scalars (R01-AC02)

RULE = "  - 'AvgDailyTot(30) > 1000000'"
HASH_FORMULA = 'FRank("EarnYield", #Industry) > 50'
"""A formula holding `#`, as Portfolio123's scopes do: without quotes, YAML would read
`FRank("EarnYield",` and take the rest for a comment."""


def test_a_formula_holding_a_hash_is_read_whole_in_quotes() -> None:
    configuration = read_screen_configuration(
        with_line(RULE, f"  - '{HASH_FORMULA}'"), "screen.yaml"
    )

    assert configuration.rules == (HASH_FORMULA,)


def test_a_formula_holding_a_hash_without_quotes_is_rejected_not_cut_short() -> None:
    message = rejection(with_line(RULE, f"  - {HASH_FORMULA}"))

    assert "`rules[0]` is a formula without quotes. Write it in single quotes" in message
    assert "FRank" not in message


@pytest.mark.parametrize(
    "written",
    [
        '  - "AvgDailyTot(30) > 1000000"',
        "  - |-\n    AvgDailyTot(30) > 1000000",
        "  - >-\n    AvgDailyTot(30) > 1000000",
    ],
    ids=["double-quoted", "literal-block", "folded-block"],
)
def test_a_formula_in_double_quotes_or_a_block_scalar_is_accepted(written: str) -> None:
    configuration = read_screen_configuration(with_line(RULE, written), "screen.yaml")

    assert configuration.rules == ("AvgDailyTot(30) > 1000000",)


def test_only_formulas_need_quotes() -> None:
    """The documented example writes its title, universe, and benchmark without quotes, and a
    ranking system's name isn't a formula."""
    configuration = read_screen_configuration(documented_example().encode(), "screen.yaml")
    named = read_screen_configuration(
        with_line("  formula: 'EarnYield'\n  lower_is_better: false", "  name: Value Composite"),
        "screen.yaml",
    )

    assert (configuration.universe, configuration.benchmark) == ("SP500", "SPY")
    assert named.ranking == NameRanking(name="Value Composite")


def test_each_unquoted_formula_is_listed_with_the_other_problems() -> None:
    content = (
        with_line(RULE, f"{RULE}\n  - Close(0) > 5")
        .replace(b"  formula: 'EarnYield'", b"  formula: EarnYield")
        .replace(b"max_holdings: 25\n", b"")
    )

    message = rejection(content)

    assert "`max_holdings` is required." in message
    assert "`rules[1]` is a formula without quotes." in message
    assert "`ranking.formula` is a formula without quotes." in message
    assert "`rules[0]`" not in message
    assert message.count("\n- ") == 3


@pytest.mark.parametrize(
    ("text", "blank"),
    [("\x1c", False), ("\ufeff", False), ("\u3000", True), ("\u0085", True), (" \t", True)],
    ids=["file-separator", "byte-order-mark", "ideographic-space", "next-line", "space-and-tab"],
)
def test_blank_means_unicode_white_space(text: str, blank: bool) -> None:
    """The reader and the plan's setting check agree on what's blank."""
    escaped = text.encode("unicode_escape").decode()
    content = with_line("universe: SP500", f'universe: "{escaped}"')

    if blank:
        assert "`universe` is blank." in rejection(content)
        with pytest.raises(ValueError):
            check_value(SCREEN_SETTINGS_BY_NAME["universe"], text)
    else:
        assert read_screen_configuration(content, "screen.yaml").universe == text
        check_value(SCREEN_SETTINGS_BY_NAME["universe"], text)


def test_byte_order_mark_is_ignored() -> None:
    content = b"\xef\xbb\xbf" + documented_example().encode()

    assert read_screen_configuration(content, "screen.yaml").title.startswith("Earnings")


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"", "The file is empty."),
        (b"\xff\xfekind: screen\n", "The file isn't UTF-8 text."),
        (b"kind: [screen\n", "The file isn't valid YAML at line"),
    ],
    ids=["empty", "not-utf-8", "not-yaml"],
)
def test_file_level_problems_are_rejected(content: bytes, expected: str) -> None:
    assert expected in rejection(content)


def test_alias_is_rejected() -> None:
    content = with_line("title: Earnings yield with a liquidity floor", "title: *name")

    assert "`title` is an alias." in rejection(content)


@pytest.mark.parametrize(
    ("old", "new", "key"),
    [
        ("benchmark: SPY", "benchmark: SPY\npassword: hunter2", "password"),
        ("benchmark: SPY", "benchmark: SPY\nAPI-Key: hunter2", "API-Key"),
        ("benchmark: SPY", "benchmark: SPY\np123_token: hunter2", "p123_token"),
        (
            "  lower_is_better: false",
            "  lower_is_better: false\n  secret: hunter2",
            "ranking.secret",
        ),
    ],
)
def test_credential_like_keys_are_rejected(old: str, new: str, key: str) -> None:
    message = rejection(with_line(old, new))

    assert f"`{key}` looks like a credential." in message
    assert "hunter2" not in message


def test_messages_never_include_values() -> None:
    """Errors are logged without input values (Pydantic conventions; REQ-06)."""
    canary = "canary-7e3f19ab"
    content = f"""\
kind: screen
schema_version: 1.0.0
title: '{canary * 20}'
purpose: '{canary}'
universe: ['{canary}']
rules: '{canary}'
ranking:
  formula: '{canary}'
  lower_is_better: '{canary}'
max_holdings: '{canary}'
benchmark: ['{canary}']
start_date: '{canary}'
end_date: 2015-01-01
rebalance_weeks: '{canary}'
transaction_price: '{canary}'
slippage_percent: '{canary}'
pit_method: '{canary}'
precision: '{canary}'
data_vendor: '{canary}'
""".encode()

    message = rejection(content)

    for key in (
        "title",
        "universe",
        "rules",
        "ranking.lower_is_better",
        "max_holdings",
        "benchmark",
        "start_date",
        "rebalance_weeks",
        "transaction_price",
        "slippage_percent",
        "pit_method",
        "precision",
        "data_vendor",
    ):
        assert f"`{key}`" in message
    assert canary not in message


VALID: dict[str, Any] = {
    "kind": "screen",
    "schema_version": "1.0.0",
    "title": "A title",
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


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("purpose", None),
        ("purpose", ""),
        ("purpose", "   "),
        ("rules", {"Price > 5", "MktCap > 1000"}),
        ("rules", frozenset({"Price > 5", "MktCap > 1000"})),
        ("data_vendor", None),
        ("slippage_percent", 0.25),
        ("slippage_percent", True),
        ("slippage_percent", Decimal("-0.25")),
        ("slippage_percent", Decimal("NaN")),
        ("rebalance_weeks", True),
        ("precision", Decimal(4)),
        ("start_date", "2016-1-1"),
        ("max_holdings", 2**53),
    ],
)
def test_model_rejects_what_the_contract_calls_invalid(key: str, value: object) -> None:
    """A model that accepts something docs/contracts.md calls invalid has a defect, whatever
    the reader does first."""
    ScreenConfiguration.model_validate(VALID)
    with pytest.raises(ValidationError):
        ScreenConfiguration.model_validate({**VALID, key: value})


@pytest.mark.parametrize("purpose", ["''", "'   '"])
def test_empty_purpose_must_be_omitted(purpose: str) -> None:
    """Configuration files: an optional purpose, when present, must be non-blank."""
    content = with_line(
        "purpose: Reference backtest for the 0.1.0 response layout.", f"purpose: {purpose}"
    )
    assert "`purpose`" in rejection(content)
