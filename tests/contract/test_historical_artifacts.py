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

Release 0.4.0's, which the synthetic writer wrote through the core with the demo's client, read
the same way (R04-T13): `runs/synthetic-run-1.1.0/` reads as a complete run, synthetic, its run
manifest 1.1.0 with the approval `not_required` and `command` null; `experiments/
synthetic-experiment-1.1.0/` passes the records check a resume makes of an experiment with a
ranking definition; `reviews/synthetic-ranking-review-1.0.0/`, which `trialfolio review` wrote
of two synthetic runs with a definition, gives each of its results `synthetic` true, and reads
with `differences.csv` 1.1.0 and `screen-run-differences` version 2; and
`snapshots/synthetic-snapshot-1.0.0/` reads as reading a snapshot checks it, complete, with its
manifest's `synthetic` true, so a configuration that names it fails with `config.invalid`.

Traces to docs/contracts.md, artifact compatibility, and to the test pairings' "other checks" in
releases 0.1.0, 0.2.0, 0.3.0, and 0.4.0, `tests/contract/test_historical_artifacts.py`. Each
fixture changes only with a stated reason, so a reader that stops reading it fails here, not in a
user's saved run, review, experiment, or snapshot. Each is read from a copy, so a reader that
wrote anything couldn't change the committed files. Every expected value is written by hand.
"""

import hashlib
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.support.paths import FIXTURES, SCREEN_CONFIGS
from tests.support.snapshot_builder import naming
from trialfolio.configuration import (
    read_experiment_configuration,
    read_experiment_configuration_v1_1,
    read_review_configuration,
    read_screen_configuration_v1_1,
)
from trialfolio.contracts.attempt import (
    AttemptRecordV1_1,
    AttemptRecordV1_2,
    AttemptRecordV1_3,
    AuthenticationRecord,
    StartRecordV1_1,
    StartRecordV1_2,
    StartRecordV1_3,
)
from trialfolio.contracts.experiment_manifest import ExperimentManifest, ExperimentManifestV1_1
from trialfolio.contracts.experiment_plan import PlanV1_1, PlanV1_3
from trialfolio.contracts.experiment_record import (
    ExperimentRecord,
    ExperimentRecordV1_1,
    SessionRecord,
)
from trialfolio.contracts.manifest import RunManifest, RunManifestV1_1
from trialfolio.contracts.plan import Plan, PlanV1_2
from trialfolio.contracts.ranking_snapshot import (
    RankingSnapshotManifest,
    RankingSnapshotPlan,
    RankingSnapshotRecord,
)
from trialfolio.contracts.review_manifest import ReviewManifest
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_records import read_experiment
from trialfolio.planning import plan_hash
from trialfolio.runs import SavedRun, read_run
from trialfolio.snapshots import SYNTHETIC_PROBLEM, NotARanking, SnapshotName, read_snapshot
from trialfolio.storage import LocalArtifactStore
from trialfolio.tables import (
    read_differences_csv,
    read_differences_csv_v1_1,
    read_metrics_csv,
    read_settings_csv,
    read_settings_csv_v1_1,
)

FIXTURE = FIXTURES / "runs" / "synthetic-run-1.0.0"
REVIEW_FIXTURE = FIXTURES / "reviews" / "synthetic-review-1.0.0"
EXPERIMENT_FIXTURE = FIXTURES / "experiments" / "synthetic-experiment-1.0.0"
RANKING_RUN_FIXTURE = FIXTURES / "runs" / "synthetic-run-1.1.0"
RANKING_EXPERIMENT_FIXTURE = FIXTURES / "experiments" / "synthetic-experiment-1.1.0"
RANKING_REVIEW_FIXTURE = FIXTURES / "reviews" / "synthetic-ranking-review-1.0.0"
SNAPSHOT_FIXTURE = FIXTURES / "snapshots" / "synthetic-snapshot-1.0.0"

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


# Release 0.4.0's fixtures, with a ranking definition.

RANKING_RUN_SCHEMA_VERSIONS = {
    "plan": "1.2.0",
    "configuration": "1.1.0",
    "ranking_definition": None,
    "rank_update_request": None,
    "update_record": "1.2.0",
    "rank_update_response": None,
    "provider_request": None,
    "start_record": "1.2.0",
    "provider_response": None,
    "attempt_record": "1.2.0",
    "metrics": "1.0.0",
    "settings": "1.1.0",
    "report": None,
}
"""The schema version the run with a definition's manifest gives each role: plan 1.2.0, start,
update, and attempt records 1.2.0, the screen configuration and `settings.csv` 1.1.0, and none for
the definition's copy, the provider's requests and responses, or the report."""

WEIGHT_NODES = (
    "Value",
    "Value/Earnings Yield",
    "Value/Sales Yield",
    "Momentum",
    "Momentum/Six-Month Return",
    "Momentum/Year Return",
    "Quality",
    "Quality/Return on Equity",
    "Quality/Gross Margin",
)
"""`synthetic.xml`'s nodes, by canonical path, in its order."""


def test_the_run_with_a_definition_reads_as_a_complete_synthetic_run(tmp_path: Path) -> None:
    copy = tmp_path / "synthetic-run-1.1.0"
    shutil.copytree(RANKING_RUN_FIXTURE, copy)

    run = read_run(LocalArtifactStore(copy))

    assert isinstance(run.manifest, RunManifestV1_1)
    assert (run.manifest.schema_version, run.manifest.outcome) == ("1.1.0", "completed")
    assert (run.manifest.synthetic, run.manifest.approval, run.manifest.command) == (
        True,
        "not_required",
        None,
    )
    assert isinstance(run.plan, PlanV1_2)
    assert run.plan.ranking_source.form == "definition"
    assert run.plan.ranking_source.definition == artifact_id(copy / "definition.xml")
    (attempt,) = run.attempts
    assert isinstance(attempt.update, StartRecordV1_2)
    assert isinstance(attempt.start, StartRecordV1_2)
    assert isinstance(attempt.record, AttemptRecordV1_2)
    assert (attempt.update.operation, attempt.start.operation) == ("rank_update", "screen_backtest")
    assert [exchange.request for exchange in attempt.record.exchanges] == [
        "POST /auth",
        "POST /rank",
        "POST /screen/backtest",
    ]
    assert attempt.status.outcome == "succeeded"
    assert run.settings is not None and run.metrics is not None
    assert {artifact.role: artifact.schema_version for artifact in run.manifest.artifacts} == (
        RANKING_RUN_SCHEMA_VERSIONS
    )
    settings = read_settings_csv_v1_1(
        (copy / "normalized" / "settings.csv").read_bytes(), "settings.csv"
    )
    assert tuple(row.node for row in settings if row.node is not None) == WEIGHT_NODES
    assert len(settings) == len(run.settings) == 23 + len(WEIGHT_NODES)


RANKING_EXPERIMENT_SCHEMA_VERSIONS = {
    "configuration": "1.1.0",
    "ranking_definition": None,
    "plan": "1.3.0",
    "experiment_record": "1.1.0",
    "authentication_record": "1.0.0",
    "rank_update_request": None,
    "update_record": "1.3.0",
    "rank_update_response": None,
    "provider_request": None,
    "start_record": "1.3.0",
    "provider_response": None,
    "attempt_record": "1.3.0",
    "metrics": "1.0.0",
    "settings": "1.1.0",
    "session_record": "1.0.0",
    "report": None,
}
"""The schema version release 0.4.0 defines for each role the experiment with a definition's
latest manifest lists: plan 1.3.0, `experiment.json` 1.1.0, start, update, and attempt records
1.3.0, and `settings.csv` and the configuration 1.1.0."""


@pytest.fixture
def ranking_experiment(tmp_path: Path) -> Path:
    copy = tmp_path / "synthetic-experiment-1.1.0"
    shutil.copytree(RANKING_EXPERIMENT_FIXTURE, copy)
    return copy


def test_the_experiment_with_a_definition_passes_the_records_check_a_resume_makes(
    ranking_experiment: Path,
) -> None:
    saved = read_experiment(LocalArtifactStore(ranking_experiment), ranking=True)

    assert [(p.number, p.plan.schema_version, p.record.schema_version) for p in saved.plans] == [
        (1, "1.3.0", "1.1.0"),
        (2, "1.3.0", "1.1.0"),
    ]
    assert [(s.session, s.schema_version) for s in saved.sessions] == [(1, "1.0.0"), (2, "1.0.0")]
    assert saved.synthetic
    for saved_plan in saved.plans:
        assert {entry.approval for entry in saved_plan.record.plans} == {"not_required"}
    manifest = saved.manifest
    assert isinstance(manifest, ExperimentManifestV1_1)
    assert (manifest.session, manifest.plan) == (2, 2)
    assert manifest.plan_hash == saved.current.plan.plan_hash
    assert (manifest.synthetic, manifest.approval, manifest.command) == (True, "not_required", None)
    current = saved.current.plan
    assert isinstance(current, PlanV1_3)
    cases = saved.cases(current)
    assert [(case.case.case_key, case.outcome, len(case.attempts)) for case in cases] == [
        ("baseline", "succeeded", 1),
        ("value-heavy", "succeeded", 1),
        ("no-sales-yield", "succeeded", 1),
    ]
    # Each attempt wrote its definition, then backtested: its update record, its start record,
    # and its attempt record are 1.3.0, and each session authenticated once.
    for attempt in saved.attempts:
        assert isinstance(attempt.update, StartRecordV1_3)
        assert isinstance(attempt.start, StartRecordV1_3)
        assert isinstance(attempt.record, AttemptRecordV1_3)
        assert attempt.record.outcome == "succeeded"
        assert attempt.rank_response is not None
    assert [
        attempt.session for attempt in saved.attempts if attempt.authentication is not None
    ] == [1, 2]
    assert manifest.counts.provider_requests == 6
    assert (manifest.counts.cases.planned, manifest.counts.cases.succeeded) == (3, 3)


def test_each_file_the_experiment_with_a_definition_lists_has_its_artifact_id_and_version(
    ranking_experiment: Path,
) -> None:
    manifest = ExperimentManifestV1_1.model_validate_json(
        (ranking_experiment / "sessions" / "2" / "manifest.json").read_bytes()
    )
    records: dict[str, Callable[[bytes], str]] = {
        "plan": lambda data: PlanV1_3.model_validate_json(data).schema_version,
        "experiment_record": lambda data: (
            ExperimentRecordV1_1.model_validate_json(data).schema_version
        ),
        "update_record": lambda data: StartRecordV1_3.model_validate_json(data).schema_version,
        "start_record": lambda data: StartRecordV1_3.model_validate_json(data).schema_version,
        "attempt_record": lambda data: AttemptRecordV1_3.model_validate_json(data).schema_version,
    }

    assert {(a.role, a.schema_version) for a in manifest.artifacts} == set(
        RANKING_EXPERIMENT_SCHEMA_VERSIONS.items()
    )
    for artifact in manifest.artifacts:
        data = (ranking_experiment / artifact.path).read_bytes()
        assert artifact.artifact_id == "sha256:" + hashlib.sha256(data).hexdigest(), artifact.path
        if artifact.role in records:
            assert records[artifact.role](data) == artifact.schema_version, artifact.path
        if artifact.role == "settings":
            read_settings_csv_v1_1(data, "settings.csv")
        if artifact.role == "configuration":
            # Read with its plan's copy of the definition, as a resume reads it.
            path = ranking_experiment / artifact.path
            definition = (path.parent / "definition.xml").read_bytes()
            read = read_experiment_configuration_v1_1(
                data, "configuration.yaml", path, definition=definition
            )
            assert read.configuration.schema_version == artifact.schema_version, artifact.path


def test_the_ranking_review_reads_with_the_current_readers(tmp_path: Path) -> None:
    review = tmp_path / "synthetic-ranking-review-1.0.0"
    shutil.copytree(RANKING_REVIEW_FIXTURE, review)
    manifest = ReviewManifest.model_validate_json((review / "manifest.json").read_bytes())
    rows = read_differences_csv_v1_1(
        (review / "normalized" / "differences.csv").read_bytes(), "differences.csv"
    )

    assert manifest.synthetic
    assert [(result.label, result.synthetic) for result in manifest.results] == [
        ("synthetic", True),
        ("synthetic-heavy", True),
    ]
    assert [(method.name, method.version) for method in manifest.methods] == [
        ("screen-run-differences", 2)
    ]
    weights = {row.node: row.classification for row in rows if row.node is not None}
    assert weights == {
        node: "intended_change" if node in ("Value", "Momentum", "Quality") else "same"
        for node in WEIGHT_NODES
    }
    readers = {
        "run_manifest": lambda data: RunManifestV1_1.model_validate_json(data),
        "plan": lambda data: PlanV1_2.model_validate_json(data),
        "metrics": lambda data: read_metrics_csv(data, "metrics.csv"),
        "settings": lambda data: read_settings_csv_v1_1(data, "settings.csv"),
    }
    assert {artifact.role: artifact.schema_version for artifact in manifest.artifacts} == {
        "configuration": "1.0.0",
        "run_manifest": "1.1.0",
        "plan": "1.2.0",
        "metrics": "1.0.0",
        "settings": "1.1.0",
        "differences": "1.1.0",
        "report": None,
    }
    for artifact in manifest.artifacts:
        data = (review / artifact.path).read_bytes()
        assert artifact.artifact_id == "sha256:" + hashlib.sha256(data).hexdigest(), artifact.path
        if artifact.role in readers:
            readers[artifact.role](data)
    for result in manifest.results:
        copied = RunManifestV1_1.model_validate_json(
            (review / "inputs" / result.label / "manifest.json").read_bytes()
        )
        assert (copied.synthetic, copied.command, copied.approval) == (True, None, "not_required")


def test_the_synthetic_snapshot_is_complete_and_cant_be_named_as_a_ranking(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "synthetic-snapshot-1.0.0"
    shutil.copytree(SNAPSHOT_FIXTURE, snapshot)
    manifest = RankingSnapshotManifest.model_validate_json(
        (snapshot / "manifest.json").read_bytes()
    )
    record = RankingSnapshotRecord.model_validate_json((snapshot / "snapshot.json").read_bytes())
    plan = RankingSnapshotPlan.model_validate_json((snapshot / "plan.json").read_bytes())
    (attempt,) = (snapshot / "attempts").iterdir()

    assert (manifest.outcome, manifest.synthetic, manifest.approval, manifest.command) == (
        "completed",
        True,
        "not_required",
        None,
    )
    assert manifest.plan_hash == plan.plan_hash == plan_hash(plan)
    assert record.definition == artifact_id(snapshot / "definition.xml")
    start = StartRecordV1_2.model_validate_json((attempt / "started.json").read_bytes())
    finished = AttemptRecordV1_2.model_validate_json((attempt / "attempt.json").read_bytes())
    assert (start.operation, finished.operation, finished.case_id) == ("rank_get", "rank_get", None)
    for artifact in manifest.artifacts:
        data = (snapshot / artifact.path).read_bytes()
        assert artifact.artifact_id == "sha256:" + hashlib.sha256(data).hexdigest(), artifact.path
    # Complete, so reading it finds only that it's synthetic, which no ranking may be.
    with pytest.raises(NotARanking) as refused:
        read_snapshot(LocalArtifactStore(snapshot), SnapshotName(shown="it", logged="it"))
    assert refused.value.problems == (SYNTHETIC_PROBLEM,)
    named = naming(SCREEN_CONFIGS / "definition.yaml", snapshot, tmp_path / "configs")
    with pytest.raises(TrialFolioError) as invalid:
        read_screen_configuration_v1_1(named.read_bytes(), named.name, named)
    assert invalid.value.code == "config.invalid"
    assert "synthetic" in invalid.value.message
