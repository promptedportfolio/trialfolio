"""A review reads a real run: each run the live check wrote, which `trialfolio run` wrote from
Portfolio123's response, reviewed against itself, in a review of its own.

Traces to release 0.2.0's verification commands, `TRIALFOLIO_REFERENCE_DIR=reference uv run
pytest -m reference`. The runs are the owner's, in the git-ignored
`p123api-live-check/payloads/` (REQ-11), so the marker keeps this module out of the default
suite. A run there is a directory whose name starts with `run-`, as the live check names its
runs, and whose `manifest.json` is a run manifest. Other entries, such as the `report-`
directories the live check also writes, are left alone. Without the variable, or without such a
run, the test skips and says why.

Both of a review's results name the run, so every setting is `same`, and every metric row is
differenced, with a difference of zero, or `unavailable`. When the run has a saved response, the
two results share it, so every metric row is flagged `identical_source`. A run without one, such
as a run whose authentication failed, has only `unavailable` metric rows, with
`input_unavailable`, and none carries `identical_source`: two results with no saved response
don't share one.

The run's values are Portfolio123's, so no assertion here shows one: each names only the rows that
failed, by setting or metric. The review copies the run's tables, so it's written in a temporary
directory that's removed afterwards, never under the reference directory, and the run is left
unchanged.
"""

import hashlib
import json
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from tests.interface.conftest import Cli
from tests.support.fake_portfolio123 import FakePortfolio123
from trialfolio.contracts.review_manifest import ReviewManifest
from trialfolio.tables import read_differences_csv

pytestmark = pytest.mark.reference

LIVE_CHECK = Path("p123api-live-check") / "payloads"
"""Where the live check's runs are, under the reference directory."""

CONFIGURATION = """\
kind: review
schema_version: 1.0.0
title: A live check's run against itself
baseline: run
results:
  - label: run
    run: {run}
  - label: again
    run: {run}
"""


def live_check_runs(reference_dir: Path) -> list[Path]:
    """The runs the live check wrote: each directory whose name starts with `run-`, and whose
    manifest is a run manifest."""
    payloads = reference_dir / LIVE_CHECK
    if not payloads.is_dir():
        return []
    runs: list[Path] = []
    for entry in sorted(payloads.iterdir()):
        manifest = entry / "manifest.json"
        if not (entry.is_dir() and entry.name.startswith("run-") and manifest.is_file()):
            continue
        loaded: object = json.loads(manifest.read_bytes())
        if isinstance(loaded, dict) and loaded.get("artifact_type") == "run":  # pyright: ignore[reportUnknownMemberType]
            runs.append(entry)
    return runs


def digests(root: Path) -> dict[str, str]:
    """Each file under `root` by its SHA-256, so a comparison shows no content."""
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_each_live_check_run_reviewed_against_itself_is_the_same(
    reference_dir: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = live_check_runs(reference_dir)
    if not runs:
        pytest.skip(f"no run of the live check under {LIVE_CHECK} in the reference directory")
    server.close()  # A review sends nothing.

    for run in runs:
        before = digests(run)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            configuration = root / "review.yaml"
            # The run's absolute path, as JSON text, which YAML reads as a quoted scalar.
            configuration.write_text(
                CONFIGURATION.format(run=json.dumps(str(run))), encoding="utf-8"
            )
            out = root / "review"
            with monkeypatch.context() as patch:
                cli = Cli(patch, root, server)
                cli.accept_license()
                outcome = cli("review", configuration, "--out", out, "--json")

            # Only the error code: a message could hold a value.
            error = outcome.summary["error"]
            code = error["code"] if isinstance(error, dict) else None
            exit_code = outcome.exit_code
            assert exit_code == 0, (run.name, code)
            manifest = ReviewManifest.model_validate_json((out / "manifest.json").read_bytes())
            rows = read_differences_csv(
                (out / "normalized" / "differences.csv").read_bytes(), "differences.csv"
            )

        assert digests(run) == before, run.name
        first, second = manifest.results
        assert first.run_manifest == second.run_manifest
        assert first.response == second.response
        settings = [row for row in rows if row.kind == "setting"]
        metrics = [row for row in rows if row.kind == "metric"]
        assert (len(settings), len(metrics)) == (23, 20), run.name
        assert {row.label for row in rows} == {"again"}
        differing = [row.name for row in settings if row.classification != "same"]
        assert not differing, run.name
        flagged = [row.name for row in settings if row.flagged]
        assert not flagged, run.name
        if first.response is not None:
            not_zero = [
                f"{row.subject} {row.name}"
                for row in metrics
                if row.classification == "differenced"
                and (row.difference is None or Decimal(row.difference) != 0)
            ]
            assert not not_zero, run.name
            neither = [
                f"{row.subject} {row.name}"
                for row in metrics
                if row.classification not in ("differenced", "unavailable")
            ]
            assert not neither, run.name
            unflagged = [
                f"{row.subject} {row.name}"
                for row in metrics
                if "identical_source" not in row.flags or not row.flagged
            ]
            assert not unflagged, run.name
        else:
            available = [
                f"{row.subject} {row.name}"
                for row in metrics
                if (row.classification, row.reason) != ("unavailable", "input_unavailable")
            ]
            assert not available, run.name
            shared = [f"{row.subject} {row.name}" for row in metrics if row.flags]
            assert not shared, run.name
