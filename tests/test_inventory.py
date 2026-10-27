"""The inventory, `tests/support/inventory.py`, the first half of the check of the tests, which
TS-AC04 runs on a task's base and on its branch (docs/test-refactoring.md).

Traces to TS-AC04: the inventory lists the IDs each suite collects, the default suite and those
`-m packaging`, `-m reference`, and `-m live` select, by collecting only, as pyproject.toml selects
them, into a new file; and the comparison finds each test that's dropped, unless the task's map
gives what it became, a split test's every part included, each that's added, and each name the map
gives that isn't there. The map is the task's rows
of docs/test-refactoring.md's "Where the tests moved", which stays readable. TS-T01 wrote the
inventory, and these tests, with it.
"""

import json
import tomllib
from pathlib import Path

import pytest

from tests.support.inventory import (
    MAP,
    ROOT,
    SUITES,
    CollectionFailed,
    Inventory,
    Move,
    collected,
    covers,
    differences,
    inventory,
    main,
    moves_of,
    read,
)

_SAMPLE_CONFIGURATION = """\
[tool.pytest.ini_options]
addopts = ["-m", "not packaging and not reference and not live"]
markers = ["packaging: p", "reference: r", "live: l"]
"""

_SAMPLE_TESTS = """\
from pathlib import Path

import pytest


def test_runs_nothing_while_collected():
    Path("ran").write_text("ran")


@pytest.mark.parametrize("value", ["a - b", "c"])
def test_a_parameter(value):
    pass


@pytest.mark.packaging
def test_packaging():
    pass


@pytest.mark.reference
def test_reference():
    pass


@pytest.mark.live
def test_live():
    pass


@pytest.mark.live
def test_live_too():
    pass
"""


@pytest.fixture(scope="module")
def sample(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A project with a test of each suite, whose test writes a file when it runs."""
    root = tmp_path_factory.mktemp("sample")
    (root / "pyproject.toml").write_text(_SAMPLE_CONFIGURATION, encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_sample.py").write_text(_SAMPLE_TESTS, encoding="utf-8")
    return root


def _ids(*names: str) -> list[str]:
    return [f"tests/test_sample.py::{name}" for name in names]


def test_the_suites_are_the_default_and_each_marker_pyproject_toml_gives() -> None:
    options = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pytest_options = options["tool"]["pytest"]["ini_options"]
    markers = [marker.split(":")[0] for marker in pytest_options["markers"]]
    assert list(SUITES) == ["default", *markers]
    default = pytest_options["addopts"][pytest_options["addopts"].index("-m") + 1]
    assert default == " and ".join(f"not {marker}" for marker in markers)
    assert all(SUITES[marker] == ("-m", marker) for marker in markers)


def test_each_suite_lists_what_it_collects_in_order_and_runs_nothing(sample: Path) -> None:
    assert inventory(sample) == {
        "default": _ids(
            "test_runs_nothing_while_collected", "test_a_parameter[a - b]", "test_a_parameter[c]"
        ),
        "packaging": _ids("test_packaging"),
        "reference": _ids("test_reference"),
        "live": _ids("test_live", "test_live_too"),
    }
    assert not (sample / "ran").exists()


def test_the_pytest_variables_add_no_options(sample: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k packaging")
    assert collected(sample) == _ids(
        "test_runs_nothing_while_collected", "test_a_parameter[a - b]", "test_a_parameter[c]"
    )


def test_a_selection_of_no_test_lists_none(sample: Path) -> None:
    assert collected(sample, "-m", "packaging and live") == []


def test_a_module_that_doesnt_import_fails_the_listing(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    (tmp_path / "test_broken.py").write_text("import no_such_module\n", encoding="utf-8")
    with pytest.raises(CollectionFailed, match="no_such_module"):
        collected(tmp_path)


@pytest.mark.parametrize(
    ("name", "test_id", "expected"),
    [
        ("tests/a.py", "tests/a.py::test_x", True),
        ("tests/a.py::test_x", "tests/a.py::test_x", True),
        ("tests/a.py::test_x", "tests/a.py::test_x[p]", True),
        ("tests/a.py::Tests", "tests/a.py::Tests::test_x", True),
        ("tests/a.py::test_x", "tests/a.py::test_xy", False),
        ("tests/a.py", "tests/a.pyc::test_x", False),
        ("tests/a.py::test_x[p]", "tests/a.py::test_x", False),
    ],
)
def test_a_name_covers_the_ids_it_starts_up_to_a_separator(
    name: str, test_id: str, expected: bool
) -> None:
    assert covers(name, test_id) is expected


def _one_suite(*ids: str) -> Inventory:
    return {suite: list(ids) if suite == "default" else [] for suite in SUITES}


def test_a_test_neither_kept_nor_moved_is_dropped_and_a_new_one_added() -> None:
    comparison = differences(
        _one_suite("tests/a.py::test_kept", "tests/a.py::test_gone"),
        _one_suite("tests/a.py::test_kept", "tests/a.py::test_new"),
    )
    assert comparison.dropped == ["dropped from default: tests/a.py::test_gone"]
    assert comparison.added == ["added to default: tests/a.py::test_new"]
    assert comparison.unmatched == []
    assert comparison.failed
    assert comparison.counts[0] == (
        "default: 2 at the base, 2 on the branch; 1 kept, 0 moved, 1 dropped, 1 added."
    )


def test_an_added_test_alone_doesnt_fail_the_comparison() -> None:
    comparison = differences(_one_suite("tests/a.py::t"), _one_suite("tests/a.py::t", "t2"))
    assert comparison.added and not comparison.failed


def test_a_test_moved_to_another_suite_is_dropped_from_its_own() -> None:
    before = _one_suite("tests/a.py::test_x")
    after = {suite: ["tests/a.py::test_x"] if suite == "live" else [] for suite in SUITES}
    comparison = differences(before, after)
    assert comparison.dropped == ["dropped from default: tests/a.py::test_x"]
    assert comparison.added == ["added to live: tests/a.py::test_x"]


def test_a_renamed_module_moves_each_test_with_the_rest_of_its_id() -> None:
    comparison = differences(
        _one_suite("tests/old.py::test_x", "tests/old.py::test_y[p]"),
        _one_suite("tests/new.py::test_x", "tests/new.py::test_y[p]"),
        [Move("tests/old.py", ("tests/new.py",))],
    )
    assert (comparison.dropped, comparison.added, comparison.unmatched) == ([], [], [])
    assert comparison.counts[0] == (
        "default: 2 at the base, 2 on the branch; 0 kept, 2 moved, 0 dropped, 0 added."
    )


def test_the_most_specific_row_moves_a_test() -> None:
    moves = [
        Move("tests/old.py", ("tests/new.py",)),
        Move("tests/old.py::test_x", ("tests/new.py::test_renamed",)),
    ]
    comparison = differences(
        _one_suite("tests/old.py::test_x[p]", "tests/old.py::test_y"),
        _one_suite("tests/new.py::test_renamed[p]", "tests/new.py::test_y"),
        moves,
    )
    assert not comparison.failed and comparison.added == []


def test_a_separated_module_s_tests_may_go_to_any_module_its_row_gives() -> None:
    comparison = differences(
        _one_suite("tests/big.py::test_x", "tests/big.py::test_y"),
        _one_suite("tests/big.py::test_x", "tests/part.py::test_y"),
        [Move("tests/big.py", ("tests/big.py", "tests/part.py"))],
    )
    assert not comparison.failed and comparison.added == []


def test_a_split_test_moves_only_when_each_of_its_parameters_is_in_each_test_it_became() -> None:
    comparison = differences(
        _one_suite("tests/a.py::test_whole[p1]", "tests/a.py::test_whole[p2]"),
        _one_suite(
            "tests/a.py::test_first[p1]",
            "tests/a.py::test_second[p1]",
            "tests/a.py::test_first[p2]",
        ),
        [Move("tests/a.py::test_whole", ("tests/a.py::test_first", "tests/a.py::test_second"))],
    )
    assert comparison.dropped == ["dropped from default: tests/a.py::test_whole[p2]"]
    assert comparison.added == ["added to default: tests/a.py::test_first[p2]"]
    assert comparison.failed


def test_a_test_split_in_two_without_one_of_them_on_the_branch_is_dropped() -> None:
    comparison = differences(
        _one_suite("tests/a.py::test_split"),
        _one_suite("tests/a.py::test_first"),
        [Move("tests/a.py::test_split", ("tests/a.py::test_first", "tests/a.py::test_second"))],
    )
    assert comparison.dropped == ["dropped from default: tests/a.py::test_split"]
    assert comparison.unmatched == ["the map's tests/a.py::test_second isn't on the branch"]


def test_a_test_split_into_parametrized_tests_moves_to_each_of_their_parameters() -> None:
    comparison = differences(
        _one_suite("tests/c.py::test_doc"),
        _one_suite("tests/c.py::test_a[x]", "tests/c.py::test_a[y]", "tests/c.py::test_b[z]"),
        [Move("tests/c.py::test_doc", ("tests/c.py::test_a", "tests/c.py::test_b"))],
    )
    assert (comparison.dropped, comparison.added, comparison.unmatched) == ([], [], [])
    assert comparison.counts[0] == (
        "default: 1 at the base, 3 on the branch; 0 kept, 1 moved, 0 dropped, 0 added."
    )


def test_two_tests_that_become_one_parametrized_test_each_move() -> None:
    comparison = differences(
        _one_suite("tests/a.py::test_x", "tests/b.py::test_x"),
        _one_suite("tests/a.py::test_x[first]", "tests/a.py::test_x[second]"),
        [
            Move("tests/a.py::test_x", ("tests/a.py::test_x[first]",)),
            Move("tests/b.py::test_x", ("tests/a.py::test_x[second]",)),
        ],
    )
    assert not comparison.failed and comparison.added == []


def test_each_name_the_map_gives_that_isn_t_there_fails_the_comparison() -> None:
    comparison = differences(
        _one_suite("tests/a.py::test_x"),
        _one_suite("tests/b.py::test_x"),
        [
            Move("tests/a.py", ("tests/b.py", "tests/c.py")),
            Move("tests/a.py::test_never", ("tests/b.py::test_x",)),
        ],
    )
    assert comparison.dropped == []
    assert comparison.unmatched == [
        "the map's tests/c.py isn't on the branch",
        "the map's tests/a.py::test_never isn't at the base",
    ]
    assert comparison.failed


_MAP = """\
# Plan

## Where the tests moved

Each entry gives the task, the name it had, and the name it has.

| Task | Had | Has |
|---|---|---|
| TS-T07 | `tests/core/test_report.py` | `tests/core/test_run_report.py` |
| TS-T08 | `tests/a.py::test_x` | `tests/a.py::test_y`, and `tests/a.py::test_z` |
| TS-T07 | `tests/b.py` | `tests/b.py` and `tests/c.py` |

## Open questions

| Task | Had | Has |
"""


def test_a_task_s_moves_are_its_rows_of_the_map() -> None:
    assert moves_of(_MAP, "TS-T07") == [
        Move("tests/core/test_report.py", ("tests/core/test_run_report.py",)),
        Move("tests/b.py", ("tests/b.py", "tests/c.py")),
    ]
    assert moves_of(_MAP, "TS-T08") == [
        Move("tests/a.py::test_x", ("tests/a.py::test_y", "tests/a.py::test_z"))
    ]
    assert moves_of(_MAP, "TS-T09") == []


@pytest.mark.parametrize(
    "row",
    [
        "| TS-T09 | `tests/a.py` `tests/b.py` | `tests/c.py` |",
        "| TS-T09 | tests/a.py | `tests/c.py` |",
        "| TS-T09 | `tests/a.py` | tests/c.py |",
        "| TS-T09 | `tests/a.py` |",
    ],
)
def test_a_row_of_another_task_that_can_t_be_read_fails_the_map(row: str) -> None:
    text = _MAP.replace("\n\n## Open questions", f"\n{row}\n\n## Open questions")
    with pytest.raises(ValueError, match="the map's row"):
        moves_of(text, "TS-T07")


@pytest.mark.parametrize(
    "table",
    ["| Task | Had | Has |\n| TS-T07 | `a` | `b` |", "| Task | Was | Is |\n|---|---|---|"],
    ids=["without its separator", "with other columns"],
)
def test_a_table_without_its_columns_fails_the_map(table: str) -> None:
    with pytest.raises(ValueError, match="columns"):
        moves_of(f"## Where the tests moved\n\n{table}\n", "TS-T07")


def test_a_text_without_the_section_fails_the_map() -> None:
    with pytest.raises(ValueError, match="Where the tests moved"):
        moves_of("# Plan\n\n## Tasks\n", "TS-T07")


def test_the_plan_s_map_reads() -> None:
    moves_of(MAP.read_text(encoding="utf-8"), "TS-T01")


def test_the_listing_writes_a_new_inventory_that_reads_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    listed = _one_suite("tests/a.py::test_x", "tests/a.py::test_y")
    monkeypatch.setattr("tests.support.inventory.inventory", lambda: listed)
    out = tmp_path / "inventory.json"
    assert main(["list", str(out)]) == 0
    assert read(out) == listed
    assert capsys.readouterr().out == (
        f"Listed 2 default, 0 packaging, 0 reference, 0 live tests into {out}.\n"
    )
    written = out.read_bytes()
    monkeypatch.setattr("tests.support.inventory.inventory", lambda: _one_suite("tests/a.py::t"))
    assert main(["list", str(out)]) == 2
    assert capsys.readouterr().err.startswith("Can't list the tests: ")
    assert out.read_bytes() == written


def _written(path: Path, found: Inventory) -> Path:
    path.write_text(json.dumps(found), encoding="utf-8")
    return path


def test_the_comparison_prints_what_it_finds_and_fails_for_a_dropped_test(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = _written(tmp_path / "before.json", _one_suite("tests/a.py::t", "tests/a.py::u"))
    after = _written(tmp_path / "after.json", _one_suite("tests/a.py::t", "tests/a.py::v"))
    assert main(["compare", str(before), str(before)]) == 0
    assert len(capsys.readouterr().out.splitlines()) == len(SUITES)
    assert main(["compare", str(before), str(after)]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[:3] == [
        "dropped from default: tests/a.py::u",
        "added to default: tests/a.py::v",
        "default: 2 at the base, 2 on the branch; 1 kept, 0 moved, 1 dropped, 1 added.",
    ]
    assert len(out) == 2 + len(SUITES)


@pytest.mark.parametrize(
    "content",
    [
        None,
        "not json",
        json.dumps({"default": ["a"]}),
        json.dumps({suite: "a" for suite in SUITES}),
    ],
)
def test_the_comparison_fails_when_it_can_t_read_an_inventory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str | None
) -> None:
    good = _written(tmp_path / "good.json", _one_suite())
    bad = tmp_path / "bad.json"
    if content is not None:
        bad.write_text(content, encoding="utf-8")
    assert main(["compare", str(good), str(bad)]) == 2
    out, err = capsys.readouterr()
    assert out == ""
    assert err.startswith("Can't compare: ")


def test_a_wrong_usage_exits_with_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["compare", "one"]) == 2
    assert capsys.readouterr().err.startswith("usage: ")
