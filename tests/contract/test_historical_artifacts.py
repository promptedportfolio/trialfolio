"""Each documented historical schema version has a reader and a committed fixture, and the current
readers read that fixture: `runs/synthetic-run-1.0.0/`, which `trialfolio demo` wrote with the
1.0.0 schemas, reads as a complete run, with every artifact it lists in its 1.0.0 schema;
`reviews/synthetic-review-1.0.0/`, which `trialfolio review` wrote with the 1.0.0 schemas of the
review configuration, the review manifest, and `differences.csv`, reads with the current readers,
and each file its manifest lists has its `artifact_id`; and
`experiments/synthetic-experiment-1.0.0/`, which the core wrote with release 0.3.0's schemas,
passes the records check a resume makes, and each plan, each attempt, and each file its latest
manifest lists has its `artifact_id`, with every listed file in the schema version 0.3.0 defines
for its role.

Traces to docs/contracts.md, artifact compatibility, and to the test pairings' "other checks" in
releases 0.1.0, 0.2.0, and 0.3.0, `tests/contract/test_historical_artifacts.py`. Each fixture
changes only with a stated reason, so a reader that stops reading it fails here, not in a user's
saved run, review, or experiment. Each is read from a copy, so a reader that wrote anything
couldn't change the committed files.
"""

import hashlib
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from trialfolio.configuration import read_experiment_configuration, read_review_configuration
from trialfolio.contracts.attempt import AttemptRecordV1_1, AuthenticationRecord, StartRecordV1_1
from trialfolio.contracts.experiment_manifest import ExperimentManifest
from trialfolio.contracts.experiment_plan import PlanV1_1
from trialfolio.contracts.experiment_record import ExperimentRecord, SessionRecord
from trialfolio.contracts.manifest import RunManifest
from trialfolio.contracts.plan import Plan
from trialfolio.contracts.review_manifest import ReviewManifest
from trialfolio.experiment_records import read_experiment
from trialfolio.planning import plan_hash
from trialfolio.runs import SavedRun, read_run
from trialfolio.storage import LocalArtifactStore
from trialfolio.tables import read_differences_csv, read_metrics_csv, read_settings_csv

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FIXTURE = FIXTURES / "runs" / "synthetic-run-1.0.0"
REVIEW_FIXTURE = FIXTURES / "reviews" / "synthetic-review-1.0.0"
EXPERIMENT_FIXTURE = FIXTURES / "experiments" / "synthetic-experiment-1.0.0"

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


EXPERIMENT_SCHEMA_VERSIONS = {
    "configuration": "1.0.0",
    "plan": "1.1.0",
    "experiment_record": "1.0.0",
    "authentication_record": "1.0.0",
    "start_record": "1.1.0",
    "attempt_record": "1.1.0",
    "metrics": "1.0.0",
    "settings": "1.0.0",
    "session_record": "1.0.0",
    "provider_request": None,
    "provider_response": None,
    "report": None,
}
"""The schema version release 0.3.0 defines for each role the experiment fixture's latest manifest
lists: plan 1.1.0, start and attempt records 1.1.0, and 1.0.0 for every other file Trial Folio
defines a schema for; none for the provider's request and response, or the report."""


def artifact_id(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def experiment(tmp_path: Path) -> Path:
    copy = tmp_path / "synthetic-experiment-1.0.0"
    shutil.copytree(EXPERIMENT_FIXTURE, copy)
    return copy


def test_the_1_0_0_experiment_passes_the_records_check_a_resume_makes(experiment: Path) -> None:
    saved = read_experiment(LocalArtifactStore(experiment))

    assert [(p.number, p.plan.schema_version, p.record.schema_version) for p in saved.plans] == [
        (1, "1.1.0", "1.0.0"),
        (2, "1.1.0", "1.0.0"),
    ]
    assert [(s.session, s.schema_version) for s in saved.sessions] == [(1, "1.0.0"), (2, "1.0.0")]
    # Synthetic, with the approval not_required in each entry of each plan's experiment.json.
    assert saved.synthetic
    for saved_plan in saved.plans:
        assert {entry.approval for entry in saved_plan.record.plans} == {"not_required"}
    manifest = saved.manifest
    assert manifest is not None
    assert (manifest.schema_version, manifest.session, manifest.plan) == ("1.0.0", 2, 2)
    assert manifest.plan_hash == saved.plan.plan_hash
    assert (manifest.synthetic, manifest.approval, manifest.command) == (True, "not_required", None)
    # Every case succeeded, each with one attempt and its tables, and each session authenticated
    # once.
    cases = saved.cases(saved.plan)
    assert [(case.case.case_key, case.outcome, len(case.attempts)) for case in cases] == [
        ("baseline", "succeeded", 1),
        ("holdings-50", "succeeded", 1),
        ("rebalance-weeks-1", "succeeded", 1),
    ]
    assert sorted(saved.tables) == sorted(case.case.case_id for case in cases)
    assert not saved.missing
    for attempt in saved.attempts:
        assert attempt.start is not None
        assert attempt.start.schema_version == "1.1.0"
        assert attempt.record is not None
        assert (attempt.record.schema_version, attempt.record.outcome) == ("1.1.0", "succeeded")
    assert [
        (attempt.session, attempt.authentication.schema_version)
        for attempt in saved.attempts
        if attempt.authentication is not None
    ] == [(1, "1.0.0"), (2, "1.0.0")]
    assert manifest.outcome == "completed"
    assert manifest.counts.cases.planned == manifest.counts.cases.succeeded == 3
    assert (manifest.counts.retired_cases, manifest.counts.attempts.succeeded) == (0, 3)


def test_each_file_the_experiments_latest_manifest_lists_has_its_artifact_id_and_schema_version(
    experiment: Path,
) -> None:
    manifest = ExperimentManifest.model_validate_json(
        (experiment / "sessions" / "2" / "manifest.json").read_bytes()
    )
    # Each record's reader gives the schema version the file holds. A table holds none, and the
    # manifest gives its layout's.
    records: dict[str, Callable[[bytes], str]] = {
        "configuration": lambda data: (
            read_experiment_configuration(data, "configuration.yaml").schema_version
        ),
        "plan": lambda data: PlanV1_1.model_validate_json(data).schema_version,
        "experiment_record": lambda data: ExperimentRecord.model_validate_json(data).schema_version,
        "authentication_record": lambda data: (
            AuthenticationRecord.model_validate_json(data).schema_version
        ),
        "start_record": lambda data: StartRecordV1_1.model_validate_json(data).schema_version,
        "attempt_record": lambda data: AttemptRecordV1_1.model_validate_json(data).schema_version,
        "session_record": lambda data: SessionRecord.model_validate_json(data).schema_version,
    }
    tables: dict[str, Callable[[bytes], object]] = {
        "metrics": lambda data: read_metrics_csv(data, "metrics.csv"),
        "settings": lambda data: read_settings_csv(data, "settings.csv"),
    }

    assert {(a.role, a.schema_version) for a in manifest.artifacts} == set(
        EXPERIMENT_SCHEMA_VERSIONS.items()
    )
    for artifact in manifest.artifacts:
        data = (experiment / artifact.path).read_bytes()
        assert artifact.artifact_id == "sha256:" + hashlib.sha256(data).hexdigest(), artifact.path
        assert artifact.size == len(data)
        if artifact.role in records:
            assert records[artifact.role](data) == artifact.schema_version, artifact.path
        if artifact.role in tables:
            tables[artifact.role](data)
    # It lists every file of the experiment's records: all but the lock, the first session's
    # files, and itself.
    files = {
        path.relative_to(experiment).as_posix() for path in experiment.rglob("*") if path.is_file()
    }
    unlisted = {"experiment.lock", "sessions/2/manifest.json"} | {
        f"sessions/1/{name}" for name in ("session.json", "report.html", "manifest.json")
    }
    assert {artifact.path for artifact in manifest.artifacts} == files - unlisted


def test_each_plan_and_each_attempt_of_the_experiment_names_its_files_by_their_artifact_ids(
    experiment: Path,
) -> None:
    previous: ExperimentRecord | None = None
    for number in (1, 2):
        directory = experiment / "plans" / str(number)
        record = ExperimentRecord.model_validate_json((directory / "experiment.json").read_bytes())
        plan = PlanV1_1.model_validate_json((directory / "plan.json").read_bytes())
        # Its last entry is its directory's plan, which recomputes to the entry's hash, and its
        # entries before the last are the previous plan's, unchanged.
        entry = record.plans[-1]
        assert (entry.plan, entry.plan_hash) == (number, plan_hash(plan))
        assert entry.plan_hash == plan.plan_hash
        assert entry.plan_artifact_id == artifact_id(directory / "plan.json")
        assert entry.configuration_artifact_id == artifact_id(directory / "configuration.yaml")
        assert record.plans[:-1] == (() if previous is None else previous.plans)
        revised = None if previous is None else previous.plans[-1].plan_hash
        assert plan.revises == entry.revises == revised
        previous = record
    paths = sorted(experiment.glob("cases/*/attempts/*/attempt.json"))
    assert len(paths) == 3
    for path in paths:
        attempt = AttemptRecordV1_1.model_validate_json(path.read_bytes())
        assert (path.parent.name, path.parents[2].name) == (
            str(attempt.attempt_id),
            attempt.case_id,
        )
        for reference in (attempt.request, attempt.response):
            assert reference is not None
            assert reference.artifact_id == artifact_id(experiment / reference.path)
