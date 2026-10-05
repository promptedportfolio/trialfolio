"""Reading a review configuration enforces docs/contracts.md's review configuration rules.

Traces to R02-AC11 in release 0.2.0's test pairing: each file in
tests/fixtures/review-configs/invalid/ fails with `config.invalid`, and the message names the
offending key, never its value; an unknown or undeclarable setting's message lists the 12
declarable settings; and a label is none of the 22 device names Windows reserves.
`test_documented_example_is_valid` traces to the example in docs/contracts.md, which
`review-configs/example.yaml` copies. The other tests trace to the review configuration's keys and
rules, and to the rules for every configuration file.
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from trialfolio.configuration import read_review_configuration
from trialfolio.contracts.common import WINDOWS_DEVICE_NAMES
from trialfolio.contracts.review_configuration import (
    IntendedChange,
    ReviewConfiguration,
    ReviewResult,
)
from trialfolio.contracts.screen_settings import DECLARABLE_SETTINGS
from trialfolio.errors import TrialFolioError

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "review-configs"
INVALID = FIXTURES / "invalid"
SCHEMA = REPO_ROOT / "schemas" / "review-configuration-1.0.0.schema.json"

DECLARABLE = (
    "universe",
    "rules",
    "ranking",
    "max_holdings",
    "benchmark",
    "start_date",
    "end_date",
    "rebalance_weeks",
    "transaction_price",
    "slippage_percent",
    "pit_method",
    "precision",
)
"""The 12 settings marked declarable in docs/contracts.md's screen settings, written by hand."""

DEVICE_NAMES = (
    "con",
    "prn",
    "aux",
    "nul",
    "com1",
    "com2",
    "com3",
    "com4",
    "com5",
    "com6",
    "com7",
    "com8",
    "com9",
    "lpt1",
    "lpt2",
    "lpt3",
    "lpt4",
    "lpt5",
    "lpt6",
    "lpt7",
    "lpt8",
    "lpt9",
)
"""The device names docs/contracts.md's review configuration lists, written by hand."""


def documented_example() -> str:
    contracts = (REPO_ROOT / "docs" / "contracts.md").read_text(encoding="utf-8")
    section = contracts[contracts.index("### Review configuration") :]
    found = re.search(r"Example:\n\n```yaml\n(.*?)```", section, re.DOTALL)
    assert found, "docs/contracts.md has no review configuration example"
    return found.group(1)


def rejection(content: bytes | str, source_name: str = "review.yaml") -> str:
    """Reads `content`, expects `config.invalid`, and returns the message."""
    if isinstance(content, str):
        content = content.encode()
    with pytest.raises(TrialFolioError) as caught:
        read_review_configuration(content, source_name)
    assert caught.value.code == "config.invalid"
    assert caught.value.log_message == caught.value.message
    return caught.value.message


def with_line(old: str, new: str) -> str:
    """The documented example, with one line replaced."""
    example = documented_example()
    assert example.count(old) == 1, old
    return example.replace(old, new)


def contains_value(message: str, value: str) -> bool:
    """Whether `message` holds `value` as a whole, not inside a longer name: `max_holding` is
    in `max_holding.` but not in `max_holdings`."""
    word = r"[A-Za-z0-9_.-]"
    return re.search(rf"(?<!{word}){re.escape(value)}(?!{word})", message) is not None


def test_documented_example_is_valid() -> None:
    configuration = read_review_configuration(documented_example().encode(), "comparison.yaml")

    assert configuration == ReviewConfiguration(
        kind="review",
        schema_version="1.0.0",
        title="Holdings 25 versus 50",
        purpose="Check whether doubling holdings changes risk as expected.",
        baseline="hold25",
        results=(
            ReviewResult(label="hold25", run="runs/hold25"),
            ReviewResult(
                label="hold50",
                run="runs/hold50",
                intended_changes=(
                    IntendedChange(
                        setting="max_holdings",
                        reason="Doubling holdings is the change under review.",
                    ),
                ),
            ),
        ),
    )
    assert configuration.results[0].intended_changes is None
    assert configuration.results[0].description is None
    assert (FIXTURES / "example.yaml").read_text(encoding="utf-8") == documented_example()


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
    body = "\n".join(line for line in content.splitlines() if not line.startswith("#"))
    for long_value in re.findall(r":[ \t]+'?([^'\n]{20,}?)'?$", body, re.MULTILINE):
        assert long_value not in message


def test_every_invalid_case_is_in_its_readme() -> None:
    readme = (INVALID / "README.md").read_text(encoding="utf-8")
    listed = set(re.findall(r"^\| `([a-z0-9-]+)\.yaml` \|", readme, re.MULTILINE))

    assert listed == {path.stem for path in INVALID.glob("*.yaml")}


def test_the_declarable_settings_are_the_documented_twelve() -> None:
    schema = json.loads(SCHEMA.read_bytes())

    assert DECLARABLE_SETTINGS == DECLARABLE
    assert schema["$defs"]["IntendedChange"]["properties"]["setting"]["enum"] == list(DECLARABLE)


@pytest.mark.parametrize("name", ["unknown-setting", "undeclarable-setting"])
def test_a_setting_that_cant_be_declared_lists_those_that_can(name: str) -> None:
    path = INVALID / f"{name}.yaml"

    message = rejection(path.read_bytes(), path.name)

    assert (
        "`results[1].intended_changes[0].setting` isn't a setting a review can declare. The "
        "declarable settings are universe, rules, ranking, max_holdings, benchmark, start_date, "
        "end_date, rebalance_weeks, transaction_price, slippage_percent, pit_method, and "
        "precision." in message
    )


LABEL = "  - label: hold25\n"


def test_the_device_names_are_the_documented_twenty_two() -> None:
    schema = json.loads(SCHEMA.read_bytes())

    assert WINDOWS_DEVICE_NAMES == DEVICE_NAMES
    assert schema["$defs"]["ReviewResult"]["properties"]["label"]["not"] == {
        "enum": list(DEVICE_NAMES)
    }


@pytest.mark.parametrize("name", [name for name in DEVICE_NAMES if name != "nul"])
def test_each_other_device_name_is_rejected_as_a_label(name: str) -> None:
    """`invalid/label-device-name.yaml` checks `nul`; these are the other 21."""
    message = rejection(with_line(LABEL, f"  - label: {name}\n"))

    assert "`results[0].label` is a name Windows reserves for a device" in message
    assert not contains_value(message, name)


@pytest.mark.parametrize("name", ["com0", "lpt0", "com10", "console", "nul-1", "aux_2"])
def test_a_label_that_only_starts_like_a_device_name_is_accepted(name: str) -> None:
    content = with_line(LABEL, f"  - label: {name}\n").replace(
        "baseline: hold25", f"baseline: {name}"
    )

    assert read_review_configuration(content.encode(), "review.yaml").baseline == name


def test_a_label_device_name_in_uppercase_fails_the_pattern_first() -> None:
    assert "`results[0].label` must be a label of 1 to 64 characters" in rejection(
        with_line(LABEL, "  - label: NUL\n")
    )


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("title: Holdings 25 versus 50", "title: '" + "t" * 200 + "'"),
        (
            "purpose: Check whether doubling holdings changes risk as expected.",
            "purpose: '" + "p" * 2000 + "'",
        ),
        ("    run: runs/hold50\n", "    run: runs/hold50\n    description: '" + "d" * 500 + "'\n"),
        (
            "        reason: Doubling holdings is the change under review.",
            "        reason: '" + "r" * 500 + "'",
        ),
        ("  - label: hold50", "  - label: " + "h" * 64),
    ],
    ids=["title-200", "purpose-2000", "description-500", "reason-500", "label-64"],
)
def test_text_at_its_limit_is_accepted(old: str, new: str) -> None:
    read_review_configuration(with_line(old, new).encode(), "review.yaml")


def test_the_baseline_may_be_any_result() -> None:
    """The baseline is named, not the first result: a change declared on the first result is
    valid when another is the baseline."""
    content = """\
kind: review
schema_version: 1.0.0
title: Holdings 50 versus 25
baseline: hold50
results:
  - label: hold25
    run: runs/hold25
    intended_changes:
      - setting: max_holdings
        reason: Halving holdings is the change under review.
  - label: hold50
    run: runs/hold50
"""

    configuration = read_review_configuration(content.encode(), "review.yaml")

    assert configuration.baseline == "hold50"
    assert configuration.results[0].intended_changes is not None
    assert configuration.results[1].intended_changes is None


def test_a_result_may_declare_several_settings() -> None:
    content = with_line(
        "        reason: Doubling holdings is the change under review.",
        "        reason: Doubling holdings is the change under review.\n"
        "      - setting: precision\n"
        "        reason: A precision this release can't vary yet.",
    )

    (_, result) = read_review_configuration(content.encode(), "review.yaml").results

    assert result.intended_changes is not None
    assert [change.setting for change in result.intended_changes] == ["max_holdings", "precision"]


def test_an_empty_list_of_changes_says_to_leave_the_key_out() -> None:
    path = INVALID / "empty-intended-changes.yaml"

    assert (
        "`results[1].intended_changes` is empty. A result that declares no change leaves the key "
        "out." in rejection(path.read_bytes(), path.name)
    )


def test_a_third_result_repeating_a_label_names_both() -> None:
    content = documented_example() + "  - label: hold25\n    run: runs/hold25-again\n"

    assert "`results[2].label` repeats the label of `results[0]`." in rejection(content)


def test_text_written_without_quotes_is_accepted() -> None:
    """A review sends nothing to Portfolio123, so its text needs no quotes, unlike a screen
    configuration's."""
    content = with_line(
        "    run: runs/hold50\n", "    run: runs/hold50\n    description: Twice the holdings.\n"
    )

    (_, result) = read_review_configuration(content.encode(), "review.yaml").results

    assert result.description == "Twice the holdings."


def test_a_screen_configuration_is_not_a_review() -> None:
    path = REPO_ROOT / "tests" / "fixtures" / "screen-configs" / "formula.yaml"

    assert "`kind` must be review." in rejection(path.read_bytes(), path.name)


def test_each_problem_is_listed() -> None:
    content = (
        with_line("  - label: hold50\n", "  - label: Hold50\n")
        .replace("title: Holdings 25 versus 50", "title: ''")
        .replace("      - setting: max_holdings", "      - setting: commission")
    )

    message = rejection(content)

    assert message.count("\n- ") == 3
    for key in ("title", "results[1].label", "results[1].intended_changes[0].setting"):
        assert f"`{key}`" in message


def test_messages_never_include_values() -> None:
    """Errors are logged without input values (Pydantic conventions; REQ-06)."""
    canary = "canary-5d21c9e7"
    content = f"""\
kind: review
schema_version: 1.0.0
title: '{canary * 20}'
purpose: ['{canary}']
baseline: {canary}-baseline
results:
  - label: {canary}-UPPER
    run: ['{canary}']
    description: '{canary * 40}'
  - label: {canary}
    run: runs/{canary}
    intended_changes:
      - setting: {canary}
        reason: '{canary * 40}'
      - setting: '{canary}-setting'
        reason: ['{canary}']
"""

    message = rejection(content)

    for key in (
        "title",
        "purpose",
        "results[0].label",
        "results[0].run",
        "results[0].description",
        "results[1].intended_changes[0].setting",
        "results[1].intended_changes[0].reason",
        "results[1].intended_changes[1].setting",
        "results[1].intended_changes[1].reason",
    ):
        assert f"`{key}`" in message
    assert canary not in message


VALID: dict[str, Any] = {
    "kind": "review",
    "schema_version": "1.0.0",
    "title": "A title",
    "baseline": "hold25",
    "results": [
        {"label": "hold25", "run": "runs/hold25"},
        {
            "label": "hold50",
            "run": "runs/hold50",
            "intended_changes": [{"setting": "max_holdings", "reason": "Doubling."}],
        },
    ],
}


def with_result(index: int, **changes: object) -> dict[str, Any]:
    document = json.loads(json.dumps(VALID))
    document["results"][index].update(changes)
    return document


@pytest.mark.parametrize(
    "document",
    [
        VALID | {"purpose": None},
        VALID | {"results": {"hold25", "hold50"}},
        VALID | {"results": VALID["results"][:1]},
        VALID | {"baseline": "hold100"},
        with_result(1, description=None),
        with_result(1, intended_changes=None),
        with_result(1, intended_changes=[]),
        with_result(1, intended_changes=({"setting": "max_holdings", "reason": "x"},) * 2),
        with_result(1, intended_changes=[{"setting": "commission", "reason": "x"}]),
        with_result(1, intended_changes=[{"setting": "max_holdings", "reason": " "}]),
        with_result(0, intended_changes=[{"setting": "max_holdings", "reason": "x"}]),
        with_result(1, label="hold25"),
        with_result(1, label="lpt3"),
        with_result(1, label=50),
        with_result(1, run=""),
        with_result(1, run=None),
    ],
    ids=[
        "null-purpose",
        "results-as-a-set",
        "one-result",
        "baseline-not-a-label",
        "null-description",
        "null-intended-changes",
        "empty-intended-changes",
        "setting-twice",
        "undeclarable-setting",
        "blank-reason",
        "change-on-baseline",
        "duplicate-label",
        "device-name",
        "label-number",
        "empty-run",
        "null-run",
    ],
)
def test_model_rejects_what_the_contract_calls_invalid(document: dict[str, Any]) -> None:
    """A model that accepts something docs/contracts.md calls invalid has a defect, whatever
    the reader does first."""
    ReviewConfiguration.model_validate(VALID)
    with pytest.raises(ValidationError):
        ReviewConfiguration.model_validate(document)
