"""The documented example: methodology.md's hand-checkable example, its table of levels and its two
periods, is what `responses/hand-checkable.json` holds, so the fixture the analysis set's tests
read is the example the documents give.

Traces to R05-AC03 (each value of analysis set 1.0.0 agrees with a hand-checkable fixture) and to
methodology.md, a hand-checkable example. The example is read from the document's text, never
copied into the test.
"""

import json
import re
from datetime import date
from typing import Final

from tests.support.paths import RESPONSES, ROOT

METHODOLOGY: Final = (ROOT / "docs" / "methodology.md").read_text(encoding="utf-8")
RESPONSE: Final = json.loads((RESPONSES / "hand-checkable.json").read_text(encoding="utf-8"))


def example() -> str:
    """The text of methodology.md's section on the example, up to its first table of values."""
    start = METHODOLOGY.index("### A hand-checkable example")
    return METHODOLOGY[start : METHODOLOGY.index("The `full` segment gives:", start)]


def table_row(text: str, name: str) -> list[str]:
    """A row of the example's table of levels, by its first cell, without that cell."""
    line = next(line for line in text.splitlines() if line.startswith(f"| {name} |"))
    return [cell.strip() for cell in line.strip("|").split("|")[1:]]


def test_the_fixtures_chart_is_the_examples_table_of_levels() -> None:
    text = example()
    dates = [
        date(2024, int(month), int(day))
        for month, day in (cell.split("-") for cell in table_row(text, "Date"))
    ]

    chart = RESPONSE["chart"]
    assert [date.fromisoformat(day) for day in chart["dates"]] == dates
    assert [str(level) for level in chart["screenReturns"]] == table_row(text, "Strategy")
    assert [str(level) for level in chart["benchReturns"]] == table_row(text, "Benchmark")
    assert "A response requested from 2024-01-01 to 2024-01-12, rebalanced every week" in text
    assert "at precision 4" in text


def test_the_fixtures_periods_are_the_examples_two_periods() -> None:
    """Its two periods are 2024-01-01 to 2024-01-08, with a `Ret%` of 0, a `Bench%` of 1, and an
    `Excess%` of −1, and 2024-01-08 to 2024-01-12, with 10, 0, and 10, as methodology.md writes
    them, its minus sign the Unicode one."""
    found = re.search(
        r"its two periods are (\S+) to (\S+), with a `Ret%` of (\S+), a `Bench%` of (\S+), and an"
        r" `Excess%` of (\S+), and (\S+) to (\S+), with (\S+), (\S+), and (\S+):",
        example().replace("\n", " "),
    )
    assert found is not None
    words = [word.replace("\N{MINUS SIGN}", "-") for word in found.groups()]
    documented = {
        (words[0], words[1]): tuple(words[2:5]),
        (words[5], words[6]): tuple(words[7:10]),
    }

    columns = RESPONSE["results"]["columns"]
    at = {name: columns.index(name) for name in ("Tran Dt", "End Dt", "Ret%", "Bench%", "Excess%")}
    held = {
        (row[at["Tran Dt"]], row[at["End Dt"]]): tuple(
            str(row[at[name]]) for name in ("Ret%", "Bench%", "Excess%")
        )
        for row in RESPONSE["results"]["rows"]
    }
    assert held == documented


def test_each_periods_value_of_100_invested_is_the_level_at_its_end() -> None:
    """Each `100 USD` column is the `chart` level at the period's `End Dt`, as the layout records
    it, so the fixture's periods reproduce from its levels."""
    chart = RESPONSE["chart"]
    level = {
        subject: dict(zip(chart["dates"], chart[key], strict=True))
        for subject, key in (("strategy", "screenReturns"), ("benchmark", "benchReturns"))
    }
    columns = RESPONSE["results"]["columns"]
    for row in RESPONSE["results"]["rows"]:
        end = row[columns.index("End Dt")]
        assert row[columns.index("100 USD Investment")] == level["strategy"][end]
        assert row[columns.index("100 USD in SPY:USA")] == level["benchmark"][end]
