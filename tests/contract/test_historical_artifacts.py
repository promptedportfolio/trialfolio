"""Each documented historical schema version has a reader and a committed fixture, and the current
readers read that fixture: `runs/synthetic-run-1.0.0/`, which `trialfolio demo` wrote with the
1.0.0 schemas, reads as a complete run, with every artifact it lists in its 1.0.0 schema; and
`reviews/synthetic-review-1.0.0/`, which `trialfolio review` wrote with the 1.0.0 schemas of the
review configuration, the review manifest, and `differences.csv`, reads with the current readers,
and each file its manifest lists has its `artifact_id`.

Traces to docs/contracts.md, artifact compatibility, and to the test pairings' "other checks" in
releases 0.1.0 and 0.2.0, `tests/contract/test_historical_artifacts.py`. Each fixture changes only
with a stated reason, so a reader that stops reading it fails here, not in a user's saved run or
review. Each is read from a copy, so a reader that wrote anything couldn't change the committed
files.
"""

import hashlib
import shutil
from pathlib import Path

import pytest

from trialfolio.configuration import read_review_configuration
from trialfolio.contracts.manifest import RunManifest
from trialfolio.contracts.plan import Plan
from trialfolio.contracts.review_manifest import ReviewManifest
from trialfolio.runs import SavedRun, read_run
from trialfolio.storage import LocalArtifactStore
from trialfolio.tables import read_differences_csv, read_metrics_csv, read_settings_csv

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FIXTURE = FIXTURES / "runs" / "synthetic-run-1.0.0"
REVIEW_FIXTURE = FIXTURES / "reviews" / "synthetic-review-1.0.0"

SCHEMA_VERSIONS = {
    "plan": "1.0.0",
    "configuration": "1.0.0",
    "start_record": "1.0.0",
    "attempt_record": "1.0.0",
    "metrics": "1.0.0",
    "settings": "1.0.0",
    "provider_request": None,
    "provider_response": None,
    "report": None,
}
"""The schema version the fixture's manifest gives each role: 1.0.0 for every file Trial Folio
defines a schema for, and none for the provider's request and response, or the report."""


@pytest.fixture
def run(tmp_path: Path) -> SavedRun:
    copy = tmp_path / "synthetic-run-1.0.0"
    shutil.copytree(FIXTURE, copy)
    return read_run(LocalArtifactStore(copy))


def test_the_1_0_0_run_reads_as_a_complete_run(run: SavedRun) -> None:
    assert run.manifest.schema_version == "1.0.0"
    assert run.manifest.synthetic
    assert run.manifest.approval == "not_required"
    assert run.manifest.outcome == "completed"
    assert run.manifest.plan_hash == run.plan.plan_hash
    assert run.plan.schema_version == "1.0.0"
    (attempt,) = run.attempts
    assert attempt.start is not None
    assert attempt.record is not None
    assert attempt.status.outcome == "succeeded"
    assert run.metrics is not None
    assert run.settings is not None
    assert len(run.metrics) == 20
    assert len(run.settings) == 23


def test_the_fixture_lists_each_artifact_in_its_1_0_0_schema(run: SavedRun) -> None:
    listed = {artifact.role: artifact.schema_version for artifact in run.manifest.artifacts}
    assert listed == SCHEMA_VERSIONS
    assert run.attempts[0].start is not None
    assert run.attempts[0].start.schema_version == "1.0.0"
    assert run.attempts[0].record is not None
    assert run.attempts[0].record.schema_version == "1.0.0"


REVIEW_SCHEMA_VERSIONS = {
    "configuration": "1.0.0",
    "run_manifest": "1.0.0",
    "plan": "1.0.0",
    "metrics": "1.0.0",
    "settings": "1.0.0",
    "differences": "1.0.0",
    "report": None,
}
"""The schema version the review fixture's manifest gives each role: each copy's is its run's,
1.0.0, and the report has none."""


@pytest.fixture
def review(tmp_path: Path) -> Path:
    copy = tmp_path / "synthetic-review-1.0.0"
    shutil.copytree(REVIEW_FIXTURE, copy)
    return copy


def test_the_1_0_0_review_reads_with_the_current_readers(review: Path) -> None:
    manifest = ReviewManifest.model_validate_json((review / "manifest.json").read_bytes())
    configuration = read_review_configuration(
        (review / "configuration.yaml").read_bytes(), "configuration.yaml"
    )
    rows = read_differences_csv(
        (review / "normalized" / "differences.csv").read_bytes(), "differences.csv"
    )

    assert manifest.schema_version == "1.0.0"
    assert manifest.artifact_type == "review"
    assert manifest.synthetic
    assert manifest.baseline == configuration.baseline == "demo"
    assert [result.label for result in manifest.results] == ["demo", "demo-again"]
    assert configuration.schema_version == "1.0.0"
    # demo-again against demo: its 23 settings, then its 20 metrics.
    assert len(rows) == 43
    assert {row.label for row in rows} == {"demo-again"}
    assert manifest.counts.results == 2


def test_each_file_the_review_lists_has_its_artifact_id_and_reads(review: Path) -> None:
    manifest = ReviewManifest.model_validate_json((review / "manifest.json").read_bytes())
    readers = {
        "run_manifest": lambda data: RunManifest.model_validate_json(data),
        "plan": lambda data: Plan.model_validate_json(data),
        "metrics": lambda data: read_metrics_csv(data, "metrics.csv"),
        "settings": lambda data: read_settings_csv(data, "settings.csv"),
    }

    listed = {artifact.role: artifact.schema_version for artifact in manifest.artifacts}
    assert listed == REVIEW_SCHEMA_VERSIONS
    for artifact in manifest.artifacts:
        data = (review / artifact.path).read_bytes()
        assert artifact.artifact_id == "sha256:" + hashlib.sha256(data).hexdigest(), artifact.path
        assert artifact.size == len(data)
        if artifact.role in readers:
            readers[artifact.role](data)
    for result in manifest.results:
        copied = review / "inputs" / result.label / "manifest.json"
        assert result.run_manifest == "sha256:" + hashlib.sha256(copied.read_bytes()).hexdigest()
        # The copied run manifest lists each copy beside it with its artifact_id.
        ids = {
            a.path: a.artifact_id
            for a in RunManifest.model_validate_json(copied.read_bytes()).artifacts
        }
        copies = [
            path.relative_to(copied.parent).as_posix()
            for path in sorted(copied.parent.rglob("*"))
            if path.is_file() and path != copied
        ]
        assert copies == ["normalized/metrics.csv", "normalized/settings.csv", "plan.json"]
        for path in copies:
            digest = hashlib.sha256((copied.parent / path).read_bytes()).hexdigest()
            assert ids[path] == "sha256:" + digest, path
