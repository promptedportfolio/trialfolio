"""The mutations, `tests/support/mutations.py`, the second half of the check of the tests, which
TS-AC05 runs on a task's base and on its branch (docs/test-refactoring.md).

Traces to TS-AC05: each mutation is applied alone, in a linked worktree whose `src/` has no
changes, and its tests record which of them fail, by their IDs, an ID that holds " - " included;
bytecode left from before, beside the module or under a prefix, can't hide a mutation; each module
takes back its saved bytes, and no bytecode is left, whatever stops the run, a SIGTERM included; a
list that can't run, or tests that don't pass unchanged, or skip, refuse before any mutation is
applied; and the comparison fails for a mutation caught at the base and missed on the branch, and
for a test in `caught_by` that didn't fail, or can't be shown to have. TS-T01 wrote the mutations,
and these tests, with them.
"""

import importlib.util
import json
import py_compile
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from tests.support.git import outside_any_repository
from tests.support.inventory import ROOT, environment
from tests.support.mutations import (
    Mutation,
    MutationList,
    Outcome,
    Refused,
    Results,
    applied,
    compared,
    failed_tests,
    main,
    read_list,
    run,
)

_CORE = """\
def total(values):
    return sum(values)


def label(count):
    return "one" if count == 1 else "many"


def unused():
    return 1
"""

_TESTS = """\
import pytest

from sample.core import label, total


def test_total():
    assert total([1, 2]) == 3


@pytest.mark.parametrize(("count", "expected"), [(1, "one"), (2, "many")], ids=["one - a", "two"])
def test_label(count, expected):
    assert label(count) == expected


def test_elsewhere():
    pytest.skip("runs elsewhere")


@pytest.mark.broken
def test_broken():
    assert False


@pytest.mark.data
def test_with_data():
    pass


@pytest.mark.data
def test_without_data():
    pytest.skip("no data")
"""

_FILES = {
    ".gitignore": "__pycache__/\n",
    "pyproject.toml": (
        "[tool.pytest.ini_options]\n"
        'addopts = ["-m", "not broken and not data"]\n'
        'markers = ["broken: b", "data: d"]\n'
    ),
    "src/sample/__init__.py": "",
    "src/sample/core.py": _CORE,
    "tests/test_core.py": _TESTS,
}

_TOTAL = "tests/test_core.py::test_total"
_LABELS = ["tests/test_core.py::test_label[one - a]", "tests/test_core.py::test_label[two]"]


@dataclass(frozen=True)
class Sample:
    """A repository, its main checkout, and a linked worktree of it, whose tests import the
    worktree's `src/`."""

    main: Path
    worktree: Path

    @property
    def env(self) -> dict[str, str]:
        return environment() | {"PYTHONPATH": str(self.worktree / "src")}

    @property
    def core(self) -> Path:
        return self.worktree / "src" / "sample" / "core.py"


def _git(root: Path, *argv: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *argv],
        cwd=root,
        env=outside_any_repository(),
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _sample(main: Path) -> Sample:
    """A repository of `_FILES` in `main`, and a linked worktree of it beside `main`."""
    for name, text in _FILES.items():
        (main / name).parent.mkdir(parents=True, exist_ok=True)
        (main / name).write_text(text, encoding="utf-8")
    _git(main, "init", "--quiet")
    _git(main, "add", ".")
    _git(main, "commit", "--quiet", "-m", "sample")
    worktree = main.parent / "worktree"
    _git(main, "worktree", "add", "--quiet", "--detach", str(worktree))
    return Sample(main, worktree)


@pytest.fixture(scope="module")
def sample(tmp_path_factory: pytest.TempPathFactory) -> Sample:
    return _sample(tmp_path_factory.mktemp("sample"))


def _mutation(name: str, old: str, new: str, **fields: Any) -> Mutation:
    return Mutation(name=name, file="src/sample/core.py", old=old, new=new, **fields)


_TOTAL_PLUS_ONE = _mutation("a total one more", "sum(values)", "sum(values) + 1")
_LABEL_OF_TWO = _mutation("one is two", "count == 1", "count == 2")
_UNUSED = _mutation("unused gives 2", "return 1", "return 2")


@pytest.fixture(scope="module")
def results(sample: Sample) -> Results:
    """A run of three mutations, with bytecode of the unchanged module left from before, which
    Python would take without reading the module."""
    py_compile.compile(
        str(sample.core),
        cfile=importlib.util.cache_from_source(str(sample.core)),
        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
    )
    listed = MutationList(
        tests=["tests/test_core.py"], mutation=[_TOTAL_PLUS_ONE, _LABEL_OF_TWO, _UNUSED]
    )
    return run(listed, base=False, root=sample.worktree, env=sample.env)


def test_each_mutation_records_the_tests_that_failed_with_it(results: Results) -> None:
    outcomes = [(m.name, m.exit_code, m.failed) for m in results.mutations]
    assert outcomes == [
        ("a total one more", 1, [_TOTAL]),
        ("one is two", 1, _LABELS),
        ("unused gives 2", 0, []),
    ]
    assert [m.caught for m in results.mutations] == [True, True, False]
    assert results.side == "branch"


def test_each_module_takes_back_its_bytes_and_no_bytecode_is_left(
    sample: Sample, results: Results
) -> None:
    assert sample.core.read_text(encoding="utf-8") == _CORE
    assert _git(sample.worktree, "status", "--porcelain", "--ignored", "--", "src") == ""


def test_a_mutation_restores_its_module_whatever_stops_the_run(tmp_path: Path) -> None:
    module = tmp_path / "module.py"
    module.write_bytes(b"value = 1\n")
    with pytest.raises(KeyboardInterrupt), applied(module, _mutation("m", "1", "2")):
        assert module.read_bytes() == b"value = 2\n"
        raise KeyboardInterrupt
    assert module.read_bytes() == b"value = 1\n"


def test_a_mutation_stopped_while_it_s_written_restores_its_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = tmp_path / "module.py"
    module.write_bytes(b"value = 1\n")
    write_bytes = Path.write_bytes
    stopped: list[bytes] = []

    def stopped_once(path: Path, data: bytes) -> int:
        """The first write is stopped by a Ctrl-C, after a part of it is written."""
        if stopped:
            return write_bytes(path, data)
        stopped.append(data)
        write_bytes(path, data[:3])
        raise KeyboardInterrupt

    monkeypatch.setattr(Path, "write_bytes", stopped_once)
    with pytest.raises(KeyboardInterrupt), applied(module, _mutation("m", "1", "2")):
        pytest.fail("the block ran, though the change was stopped")
    monkeypatch.undo()
    assert stopped == [b"value = 2\n"]
    assert module.read_bytes() == b"value = 1\n"


_STOPPED_RUN = """\
import json, sys
from pathlib import Path
from tests.support.mutations import MutationList, run
run(MutationList.model_validate_json(sys.argv[1]), base=False, root=Path(sys.argv[2]),
    env=json.loads(sys.argv[3]))
"""


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no SIGTERM to handle")
def test_a_sigterm_during_a_mutation_s_tests_restores_its_module_and_leaves_no_bytecode(
    tmp_path: Path,
) -> None:
    sample = _sample(tmp_path / "main")
    started = tmp_path / "started"
    waiting = _mutation(
        "a total that waits",
        "sum(values)",
        f"__import__('pathlib').Path({str(started)!r}).touch() or "
        "__import__('time').sleep(30) or sum(values)",
    )
    listed = MutationList(tests=[_TOTAL], mutation=[waiting])
    bytecode = {"PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX"}
    env = {name: value for name, value in sample.env.items() if name not in bytecode}
    command = [sys.executable, "-c", _STOPPED_RUN, listed.model_dump_json(), str(sample.worktree)]
    runner = subprocess.Popen(
        [*command, json.dumps(env)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 60
        while not started.exists():
            assert runner.poll() is None, runner.communicate()[0]
            assert time.monotonic() < deadline, "the mutation's tests didn't start"
            time.sleep(0.05)
        assert list((sample.core.parent / "__pycache__").glob("core.*.pyc"))
        runner.send_signal(signal.SIGTERM)
        output, _ = runner.communicate(timeout=60)
    finally:
        if runner.poll() is None:
            runner.kill()
            runner.wait()
    assert runner.returncode == 128 + signal.SIGTERM, output
    assert sample.core.read_text(encoding="utf-8") == _CORE
    assert _git(sample.worktree, "status", "--porcelain", "--ignored", "--", "src") == ""


def test_bytecode_under_a_prefix_can_t_hide_a_mutation(
    sample: Sample, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bytecode of the unchanged module, under the prefix `PYTHONPYCACHEPREFIX` names, which
    Python would take without reading the module."""
    prefix = tmp_path / "bytecode"
    with monkeypatch.context() as prefixed:
        prefixed.setattr(sys, "pycache_prefix", str(prefix))
        cached = importlib.util.cache_from_source(str(sample.core))
    py_compile.compile(
        str(sample.core),
        cfile=cached,
        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
    )
    listed = MutationList(tests=[_TOTAL], mutation=[_TOTAL_PLUS_ONE])
    env = sample.env | {"PYTHONPYCACHEPREFIX": str(prefix)}
    (outcome,) = run(listed, base=False, root=sample.worktree, env=env).mutations
    assert (outcome.exit_code, outcome.failed) == (1, [_TOTAL])


def test_a_mutation_caught_at_the_base_and_missed_on_the_branch_is_lost(sample: Sample) -> None:
    listed = MutationList(
        tests=["tests/test_core.py::test_label"],
        base_tests=[_TOTAL],
        mutation=[_TOTAL_PLUS_ONE],
    )
    at_the_base = run(listed, base=True, root=sample.worktree, env=sample.env)
    on_the_branch = run(listed, base=False, root=sample.worktree, env=sample.env)
    assert [m.tests for m in at_the_base.mutations] == [[_TOTAL]]
    assert [m.tests for m in on_the_branch.mutations] == [["tests/test_core.py::test_label"]]
    lines, failed = compared(at_the_base, on_the_branch)
    assert lines[0] == ("lost: a total one more (base: caught, exit 1, 1 failed; branch: missed)")
    assert failed


def test_a_mutation_whose_tests_time_out_is_caught(sample: Sample) -> None:
    looping = _mutation(
        "a total that never ends", "return sum(values)", "while True:\n        pass"
    )
    listed = MutationList(tests=[_TOTAL], mutation=[looping])
    timed = run(listed, base=False, root=sample.worktree, env=sample.env, shortest_timeout=0)
    # Each is rounded to a tenth, so they differ by 0.3 at most, and by 0.4 at least without the
    # factor of 5.
    assert timed.timeout_seconds == pytest.approx(5 * timed.unchanged_seconds, abs=0.35)
    (outcome,) = timed.mutations
    assert outcome.exit_code is None
    assert outcome.caught
    assert sample.core.read_text(encoding="utf-8") == _CORE


def test_a_run_in_the_main_checkout_is_refused(sample: Sample) -> None:
    listed = MutationList(tests=[_TOTAL], mutation=[_TOTAL_PLUS_ONE])
    with pytest.raises(Refused, match="main checkout"):
        run(listed, base=False, root=sample.main, env=sample.env)


def test_a_run_with_changes_in_src_is_refused(sample: Sample) -> None:
    added = sample.worktree / "src" / "sample" / "added.py"
    added.write_text("", encoding="utf-8")
    try:
        with pytest.raises(Refused, match="src/ has changes"):
            run(MutationList(tests=[_TOTAL], mutation=[_UNUSED]), base=False, root=sample.worktree)
    finally:
        added.unlink()


def test_a_run_whose_tests_import_another_checkout_s_module_is_refused(sample: Sample) -> None:
    elsewhere = environment() | {"PYTHONPATH": str(sample.main / "src")}
    listed = MutationList(tests=[_TOTAL], mutation=[_TOTAL_PLUS_ONE])
    with pytest.raises(Refused, match="from this checkout's src/"):
        run(listed, base=False, root=sample.worktree, env=elsewhere)


@pytest.mark.parametrize(
    ("listed", "refusal"),
    [
        (
            MutationList(tests=[_TOTAL], mutation=[_mutation("twice", "return", "yield")]),
            "occurs 3 times",
        ),
        (
            MutationList(tests=[_TOTAL], mutation=[_mutation("never", "product", "sum")]),
            "occurs 0 times",
        ),
        (MutationList(tests=["tests/test_missing.py"], mutation=[_UNUSED]), "test_missing.py"),
        (
            MutationList(tests=["tests/test_core.py::test_broken"], mutation=[_UNUSED]),
            "collect nothing",
        ),
        (
            MutationList(
                tests=[_TOTAL],
                mutation=[
                    _TOTAL_PLUS_ONE,
                    _mutation(
                        "m", "return 1", "return 2", tests=["tests/test_core.py::test_broken"]
                    ),
                ],
            ),
            "collect nothing",
        ),
        (
            MutationList(tests=["tests/test_core.py"], marker="broken", mutation=[_UNUSED]),
            "don't pass unchanged",
        ),
        (
            MutationList(tests=["tests/test_core.py::test_elsewhere"], mutation=[_UNUSED]),
            "(?s)no test passes unchanged.*runs elsewhere",
        ),
        (
            MutationList(tests=["tests/test_core.py"], marker="data", mutation=[_UNUSED]),
            "(?s)1 of the tests skip unchanged, and a list with a marker.*no data",
        ),
    ],
    ids=[
        "old text twice",
        "old text missing",
        "a test that isn't there",
        "tests the default deselects",
        "a mutation's own tests that select none",
        "tests that fail unchanged",
        "tests that all skip",
        "a marker's tests of which one skips",
    ],
)
def test_a_list_that_can_t_run_is_refused_before_any_mutation(
    sample: Sample, listed: MutationList, refusal: str
) -> None:
    with pytest.raises(Refused, match=refusal):
        run(listed, base=False, root=sample.worktree, env=sample.env)
    assert sample.core.read_text(encoding="utf-8") == _CORE


_MUTATION = """
[[mutation]]
name = "m"
file = "src/sample/core.py"
old = '''return 1'''
new = '''return 2'''
"""


_NOT_A_LIST = "isn't a list of mutations"
_NOT_IN_SRC = "isn't a module of src/"


@pytest.mark.parametrize(
    ("text", "refusal"),
    [
        ('tests = ["t"]\n' + _MUTATION + "caughtby = []\n", _NOT_A_LIST),
        (
            'tests = ["t"]\n' + _MUTATION.replace("src/sample/core.py", "tests/test_core.py"),
            _NOT_IN_SRC,
        ),
        (
            'tests = ["t"]\n' + _MUTATION.replace("src/sample/core.py", "src/../sample/core.py"),
            _NOT_IN_SRC,
        ),
        ('tests = ["t"]\n' + _MUTATION.replace("core.py", "core.txt"), _NOT_IN_SRC),
        ('tests = ["t"]\n' + _MUTATION.replace("return 2", "return 1"), "'m' changes nothing"),
        ('tests = ["t"]\n' + _MUTATION + _MUTATION, "two mutations have the same name"),
        (_MUTATION, "a mutation names no tests, and the list gives none"),
        (
            'base_tests = ["t"]\n' + _MUTATION + 'tests = ["u"]\n',
            "the list gives base_tests without its tests",
        ),
        (
            'tests = ["t"]\n' + _MUTATION + 'base_tests = ["u"]\n',
            "'m' gives base_tests without its tests",
        ),
        ('tests = ["t"]\n', _NOT_A_LIST),
        ("tests = []\n" + _MUTATION, _NOT_A_LIST),
        ("tests = [", _NOT_A_LIST),
    ],
    ids=[
        "an unknown key",
        "a module outside src",
        "a path out of src",
        "a file that isn't a module",
        "a change of nothing",
        "two mutations of one name",
        "no tests",
        "the list's base_tests without its tests",
        "a mutation's base_tests without its tests",
        "no mutation",
        "an empty list of tests",
        "not TOML",
    ],
)
def test_a_file_that_isn_t_a_list_is_refused(tmp_path: Path, text: str, refusal: str) -> None:
    path = tmp_path / "list.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(Refused, match=_NOT_A_LIST) as refused:
        read_list(path)
    assert refusal in str(refused.value)


def test_a_list_reads_as_the_module_gives_it(tmp_path: Path) -> None:
    path = tmp_path / "list.toml"
    path.write_text('tests = ["t"]\nmarker = "broken"\n' + _MUTATION, encoding="utf-8")
    listed = read_list(path)
    assert listed.marker == "broken"
    assert listed.tests_of(listed.mutation[0], base=True) == ["t"]
    assert listed.mutation[0].old == "return 1"


def test_a_summary_line_gives_the_test_s_id_though_it_holds_the_separator() -> None:
    output = (
        ".F\n"
        "FAILED tests/a.py::test_x[1 - 2] - AssertionError: assert 1 - 2 == 0\n"
        "FAILED tests/a.py::test_y\n"
        "ERROR tests/b.py - ImportError: no module\n"
        "1 failed in 0.1s\n"
    )
    known = {"tests/a.py::test_x[1 - 2]", "tests/a.py::test_x[1]", "tests/a.py::test_y"}
    assert failed_tests(output, known) == [
        "tests/a.py::test_x[1 - 2]",
        "tests/a.py::test_y",
        "tests/b.py",
    ]


def _outcome(
    name: str,
    *,
    caught: bool,
    failed: tuple[str, ...] = (),
    caught_by: tuple[str, ...] = (),
    timed_out: bool = False,
) -> Outcome:
    return Outcome(
        name=name,
        file="src/sample/core.py",
        old="a",
        new="b",
        tests=["t"],
        caught_by=list(caught_by),
        exit_code=None if timed_out else 1 if caught else 0,
        failed=list(failed),
        seconds=0.1,
    )


def _results(side: str, *outcomes: Outcome) -> Results:
    return Results.model_validate(
        {"side": side, "unchanged_seconds": 1, "timeout_seconds": 60, "mutations": outcomes}
    )


def test_the_comparison_names_each_mutation_s_status_and_fails_only_for_a_lost_one() -> None:
    before = _results(
        "base",
        _outcome("kept", caught=True),
        _outcome("gained", caught=False),
        _outcome("missed", caught=False),
    )
    after = _results(
        "branch",
        _outcome("kept", caught=True),
        _outcome("gained", caught=True),
        _outcome("missed", caught=False),
    )
    lines, failed = compared(before, after)
    assert [line.split(" (")[0] for line in lines[:3]] == [
        "kept: kept",
        "gained: gained",
        "missed: missed",
    ]
    assert lines[-1] == (
        "3 mutations: 1 kept, 0 lost, 1 gained, 1 missed; 0 tests in caught_by didn't fail, "
        "and 0 mutations with caught_by timed out."
    )
    assert not failed


def test_the_comparison_fails_for_a_test_in_caught_by_that_didn_t_fail() -> None:
    names = ("tests/a.py::test_x", "tests/a.py::test_y")
    before = _results("base", _outcome("m", caught=False))
    after = _results(
        "branch", _outcome("m", caught=True, failed=("tests/a.py::test_x[p]",), caught_by=names)
    )
    lines, failed = compared(before, after)
    assert lines[1:-1] == ["not caught by tests/a.py::test_y: m"]
    assert failed


def test_a_module_that_doesn_t_import_fails_each_of_its_tests_in_caught_by() -> None:
    before = _results("base", _outcome("m", caught=False))
    after = _results(
        "branch",
        _outcome("m", caught=True, failed=("tests/a.py",), caught_by=("tests/a.py::test_x",)),
    )
    lines, failed = compared(before, after)
    assert lines[1:-1] == []
    assert not failed


def test_a_mutation_whose_tests_time_out_can_t_show_its_tests_in_caught_by_failed() -> None:
    before = _results("base", _outcome("m", caught=True, timed_out=True))
    after = _results(
        "branch", _outcome("m", caught=True, timed_out=True, caught_by=("tests/a.py::test_x",))
    )
    lines, failed = compared(before, after)
    assert lines[1:] == [
        "timed out, so it can't show its tests in caught_by failed: m",
        (
            "1 mutations: 1 kept, 0 lost, 0 gained, 0 missed; 0 tests in caught_by didn't fail, "
            "and 1 mutations with caught_by timed out."
        ),
    ]
    assert failed


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (
            _results("branch", _outcome("m", caught=True)),
            _results("base", _outcome("m", caught=True)),
        ),
        (
            _results("base", _outcome("m", caught=True)),
            _results("branch", _outcome("n", caught=True)),
        ),
        (_results("base", _outcome("m", caught=True)), _results("branch")),
    ],
    ids=["the branch's first", "other mutations", "fewer mutations"],
)
def test_the_comparison_refuses_results_that_aren_t_the_base_s_and_the_branch_s_of_one_list(
    before: Results, after: Results
) -> None:
    with pytest.raises(ValueError, match="the results are|the same mutations"):
        compared(before, after)


def test_the_comparison_s_exit_code_says_whether_it_passed_failed_or_couldn_t_compare(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {name: tmp_path / f"{name}.json" for name in ("base", "kept", "lost", "unreadable")}
    written = {
        "base": _results("base", _outcome("m", caught=True)).model_dump_json(),
        "kept": _results("branch", _outcome("m", caught=True)).model_dump_json(),
        "lost": _results("branch", _outcome("m", caught=False)).model_dump_json(),
        "unreadable": json.dumps({"side": "branch"}),
    }
    for name, text in written.items():
        files[name].write_text(text, encoding="utf-8")
    assert main(["compare", str(files["base"]), str(files["kept"])]) == 0
    assert main(["compare", str(files["base"]), str(files["lost"])]) == 1
    capsys.readouterr()
    assert main(["compare", str(files["base"]), str(files["unreadable"])]) == 2
    out, err = capsys.readouterr()
    assert out == ""
    assert err.startswith("Can't compare: ")


def test_a_wrong_usage_exits_with_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", "list.toml"]) == 2
    assert capsys.readouterr().err.startswith("usage: ")


def test_a_run_into_results_that_exist_is_refused_before_it_starts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "results.json"
    out.write_text("{}", encoding="utf-8")
    assert main(["run", str(tmp_path / "no-list.toml"), str(out)]) == 2
    assert "exists" in capsys.readouterr().err
    assert out.read_text(encoding="utf-8") == "{}"
