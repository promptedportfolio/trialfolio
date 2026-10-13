"""The check of the reports, `tests/support/rewritten_fixtures.py`, which RF-AC04 runs on a
refactoring task's base and on its branch (docs/refactoring.md).

Traces to RF-AC04: each committed fixture is written again through the real code, with the fixed
clock and a fixed sequence of IDs, so the same code writes the same bytes, apart from `logs/`, and
a difference between the base and the branch is the change's. RF-T01 wrote the check, and these
tests, with it.
"""

import re
import shutil
from pathlib import Path

import pytest

from tests.support.rewritten_fixtures import FIXTURES, differences, write

_ATTEMPT_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")


@pytest.fixture(scope="module")
def written(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("written")
    write(out)
    return out


def _layout(directory: Path) -> set[str]:
    """The files under `directory`, apart from `logs/`, with each attempt's ID left out."""
    return {
        _ATTEMPT_ID.sub("<id>", path.relative_to(directory).as_posix())
        for path in directory.rglob("*")
        if path.is_file() and "logs" not in path.relative_to(directory).parts
    }


def test_the_same_code_writes_the_same_bytes(written: Path, tmp_path: Path) -> None:
    again = tmp_path / "again"
    write(again)
    assert differences(written, again) == []


@pytest.mark.parametrize(
    ("name", "fixture"),
    [
        ("run", "runs/synthetic-run-1.0.0"),
        ("review", "reviews/synthetic-review-1.0.0"),
        ("experiment", "experiments/synthetic-experiment-1.0.0"),
    ],
)
def test_each_fixture_is_written_again_with_its_files(
    written: Path, name: str, fixture: str
) -> None:
    assert _layout(written / name) == _layout(FIXTURES / fixture)


def test_the_committed_run_s_report_is_rendered_again(written: Path) -> None:
    assert _layout(written / "report") == {"report.html"}


def test_the_comparison_finds_each_changed_file_but_those_in_logs(
    written: Path, tmp_path: Path
) -> None:
    changed = tmp_path / "changed"
    shutil.copytree(written, changed)
    (changed / "run" / "report.html").write_bytes(b"changed")
    (changed / "review" / "logs" / "trialfolio.log").write_bytes(b"changed")
    (changed / "experiment" / "experiment.lock").unlink()
    (changed / "report" / "extra.html").write_bytes(b"")
    assert differences(written, changed) == [
        "only before: experiment/experiment.lock",
        "only after: report/extra.html",
        "differs: run/report.html",
    ]
