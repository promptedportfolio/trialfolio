"""Each documented historical schema version has a reader and a committed fixture, and the current
readers read that fixture: `runs/synthetic-run-1.0.0/`, which `trialfolio demo` wrote with the
1.0.0 schemas, reads as a complete run, with every artifact it lists in its 1.0.0 schema.

Traces to docs/contracts.md, artifact compatibility, and to the test pairing's
`tests/contract/test_historical_artifacts.py`. The fixture changes only with a stated reason, so
a reader that stops reading it fails here, not in a user's saved run. The run is read from a copy,
so a reader that wrote anything couldn't change the committed files.
"""

import shutil
from pathlib import Path

import pytest

from trialfolio.runs import SavedRun, read_run
from trialfolio.storage import LocalArtifactStore

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "runs" / "synthetic-run-1.0.0"

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
