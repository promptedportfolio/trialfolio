"""The records of a ranking definition, and of a ranking snapshot, each read a valid document and
write it back as the same JSON, and reject an unknown field.

Traces to release 0.4.0's test pairing, which names this module for the records' contract tests
(R04-T05): plans 1.2.0 and 1.3.0 (plans with a ranking definition), the snapshot plan, start and
attempt records 1.2.0 and 1.3.0 (sending a definition), `experiment.json` 1.1.0, run manifest 1.1.0
and experiment manifest 1.1.0, the snapshot manifest and record (ranking snapshot output), and the
rows of `settings.csv` 1.1.0 and `differences.csv` 1.1.0 (weight rows). Each valid document is
tests/support/ranking_documents.py's, synthetic, and read as a reader reads it: from JSON text, with
`model_validate_json`.

TS-T07 separated this module's other tests by family, each with what its records accept and reject,
and moved the documents they change to tests/support/ranking_documents.py (docs/test-refactoring.md,
modules to separate): the plans, in tests/contract/test_ranking_plans.py; the start and attempt
records, in `test_ranking_attempt_records.py`; `experiment.json`, in
`test_ranking_experiment_record.py`; the manifests and the snapshot's record, in
`test_ranking_manifests.py`; and the rows, in `test_ranking_rows.py`.
"""

import json
from collections.abc import Callable

import pytest
from pydantic import BaseModel

from tests.support.contract_checks import Document, rejects
from tests.support.ranking_documents import (
    attempt_record_1_2,
    differences_row,
    experiment_attempt_record,
    experiment_manifest,
    experiment_record,
    experiment_start_record,
    experiment_update_record,
    plan_1_2,
    plan_1_3,
    run_manifest,
    settings_row,
    snapshot_attempt_record,
    snapshot_manifest,
    snapshot_plan,
    snapshot_record,
    snapshot_start_record,
    source_revision,
    start_record_1_2,
    update_record,
)
from trialfolio.contracts.attempt import (
    AttemptRecordV1_2,
    AttemptRecordV1_3,
    StartRecordV1_2,
    StartRecordV1_3,
)
from trialfolio.contracts.experiment_manifest import ExperimentManifestV1_1
from trialfolio.contracts.experiment_plan import PlanV1_3
from trialfolio.contracts.experiment_record import ExperimentRecordV1_1
from trialfolio.contracts.manifest import RunManifestV1_1
from trialfolio.contracts.plan import PlanV1_2
from trialfolio.contracts.ranking_snapshot import (
    RankingSnapshotManifest,
    RankingSnapshotPlan,
    RankingSnapshotRecord,
)
from trialfolio.contracts.tables import DifferencesRowV1_1, SettingsRowV1_1

VALID: list[tuple[type[BaseModel], Callable[[], Document]]] = [
    (PlanV1_2, plan_1_2),
    (PlanV1_3, plan_1_3),
    (RankingSnapshotPlan, snapshot_plan),
    (StartRecordV1_2, update_record),
    (StartRecordV1_2, start_record_1_2),
    (StartRecordV1_2, snapshot_start_record),
    (AttemptRecordV1_2, attempt_record_1_2),
    (AttemptRecordV1_2, snapshot_attempt_record),
    (StartRecordV1_3, experiment_update_record),
    (StartRecordV1_3, experiment_start_record),
    (AttemptRecordV1_3, experiment_attempt_record),
    (ExperimentRecordV1_1, experiment_record),
    (ExperimentRecordV1_1, source_revision),
    (RunManifestV1_1, run_manifest),
    (ExperimentManifestV1_1, experiment_manifest),
    (RankingSnapshotManifest, snapshot_manifest),
    (RankingSnapshotRecord, snapshot_record),
    (SettingsRowV1_1, settings_row),
    (DifferencesRowV1_1, differences_row),
]
IDS = [
    "plan-1.2.0",
    "plan-1.3.0",
    "snapshot-plan",
    "update-record-1.2.0",
    "start-record-1.2.0",
    "snapshot-start-record",
    "attempt-record-1.2.0",
    "snapshot-attempt-record",
    "update-record-1.3.0",
    "start-record-1.3.0",
    "attempt-record-1.3.0",
    "experiment-record-1.1.0",
    "source-revision",
    "run-manifest-1.1.0",
    "experiment-manifest-1.1.0",
    "snapshot-manifest",
    "snapshot-record",
    "settings-row-1.1.0",
    "differences-row-1.1.0",
]


@pytest.mark.parametrize(("model", "build"), VALID, ids=IDS)
def test_documents_round_trip(model: type[BaseModel], build: Callable[[], Document]) -> None:
    """A valid document reads, and writes back as the same JSON."""
    document = build()

    written = model.model_validate_json(json.dumps(document)).model_dump_json()

    assert json.loads(written) == document


@pytest.mark.parametrize(("model", "build"), VALID, ids=IDS)
def test_unknown_fields_are_rejected(model: type[BaseModel], build: Callable[[], Document]) -> None:
    rejects(model, build() | {"unexpected": 1})
