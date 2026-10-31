"""The manifests of a ranking definition, and the ranking snapshot's manifest and record, accept
what docs/contracts.md describes, and reject what it calls invalid.

Traces to release 0.4.0's test pairing, which names tests/contract/test_ranking_artifact_models.py
for the records' contract tests (R04-T05), here for run manifest 1.1.0 and experiment manifest
1.1.0, and the snapshot manifest and record (ranking snapshot output). To R04-AC08's row: the
snapshot manifest's model rejects `synthetic` true with an approval other than `not_required` or
with a command, and `synthetic` false with `not_required` or without a command; and to the changes
after 0.4.0's sign-off: run manifest 1.1.0's model accepts `synthetic` true with `command` null and
the approval `not_required`, and rejects `synthetic` true with another approval or with the command
`run`, and `synthetic` false with `not_required`, without a command, or with the command `demo`.
Each document is tests/support/ranking_documents.py's, synthetic, changed one way, and read as a
reader reads it: from JSON text, with `model_validate_json`. TS-T07 separated these tests from
tests/contract/test_ranking_artifact_models.py (docs/test-refactoring.md, modules to separate).
"""

import pytest

from tests.support.contract_checks import Change, Document, accepts, changed, rejects
from tests.support.ranking_documents import (
    ATTEMPT_ID,
    BASELINE_ID,
    DIRECTORY,
    EXPERIMENT_ATTEMPT,
    SNAPSHOT_DIRECTORY,
    SNAPSHOT_SOURCES,
    SOURCES,
    artifact,
    core_synthetic,
    experiment_manifest,
    listed,
    run_manifest,
    snapshot_failed,
    snapshot_manifest,
    snapshot_record,
    source,
)
from trialfolio.contracts.experiment_manifest import ExperimentManifestV1_1
from trialfolio.contracts.manifest import RunManifestV1_1
from trialfolio.contracts.ranking_snapshot import RankingSnapshotManifest, RankingSnapshotRecord

# Run manifest 1.1.0


def demo_synthetic(document: Document) -> None:
    document.update(
        synthetic=True,
        approval="not_required",
        command={"name": "demo", "options": {"json": False}, "started_at": "2026-10-14T12:00:00Z"},
    )


def snapshot_ranking(document: Document) -> None:
    """A run ranked by a snapshot: its definition's copy is `rank_get`'s, beside the record."""
    artifact(document, "ranking_definition")["source"] = source(
        "ranking-definition", operation="rank_get"
    )
    document["artifacts"].insert(3, listed("snapshot.json", "ranking_snapshot_record", "1.0.0"))


RUN_MANIFEST_ACCEPTS: dict[str, Change] = {
    "a synthetic run the core wrote, with no command": core_synthetic,
    "a synthetic run trialfolio demo wrote": demo_synthetic,
    "a run ranked by a snapshot": snapshot_ranking,
    "a rank_update's 200 the wrapper couldn't decode": lambda d: artifact(
        d, "rank_update_response"
    ).update(
        path=f"{DIRECTORY}/rank-update-response.raw",
        role="rank_update_response_undecoded",
        source=SOURCES["rank_update_response_undecoded"],
    ),
}


@pytest.mark.parametrize("change", RUN_MANIFEST_ACCEPTS.values(), ids=RUN_MANIFEST_ACCEPTS.keys())
def test_run_manifest_1_1_accepts(change: Change) -> None:
    accepts(RunManifestV1_1, changed(run_manifest, change))


def definition_source(document: Document) -> Document:
    found: Document = artifact(document, "ranking_definition")["source"]
    return found


RUN_MANIFEST_REJECTS: dict[str, Change] = {
    "synthetic, approved with --approve": lambda d: (
        core_synthetic(d),
        d.update(approval="option"),
    ),
    "synthetic, approved interactively": lambda d: (
        core_synthetic(d),
        d.update(approval="interactive"),
    ),
    "synthetic, with the command run": lambda d: (
        core_synthetic(d),
        d.update(command=run_manifest()["command"]),
    ),
    "not synthetic, with the approval not_required": lambda d: d.update(approval="not_required"),
    "not synthetic, without a command": lambda d: d.update(command=None),
    "not synthetic, with the command demo": lambda d: (
        demo_synthetic(d),
        d.update(synthetic=False, approval="option"),
    ),
    "version 1.0.0": lambda d: d.update(schema_version="1.0.0"),
    "a log listed": lambda d: d["artifacts"].append(listed("logs/trialfolio.log", "report")),
    "a definition's copy with a parser": lambda d: definition_source(d).update(parser_version=1),
    "a definition's copy of another format": lambda d: definition_source(d).update(
        format="p123api-rank-get"
    ),
    "a definition's copy of another version": lambda d: definition_source(d).update(
        format_version="1.0.0"
    ),
    "a definition's copy from a file, verified": lambda d: definition_source(d).update(
        provenance="verified"
    ),
    "a definition's copy from a snapshot, user_supplied": lambda d: definition_source(d).update(
        operation="rank_get"
    ),
    "a definition's copy without its source record": lambda d: artifact(
        d, "ranking_definition"
    ).update(source=None),
    "a definition's copy under another name": lambda d: artifact(d, "ranking_definition").update(
        path="ranking.xml"
    ),
    "a rank_update's request of the backtest's format": lambda d: artifact(
        d, "rank_update_request"
    )["source"].update(format="p123api-screen-backtest-request"),
    "a rank_update's response from the backtest": lambda d: artifact(d, "rank_update_response")[
        "source"
    ].update(operation="screen_backtest"),
    "a rank_update's response parsed": lambda d: artifact(d, "rank_update_response")[
        "source"
    ].update(parser_version=1),
    "a rank_update's response the user supplied": lambda d: artifact(d, "rank_update_response")[
        "source"
    ].update(provenance="user_supplied"),
    "an undecoded rank_update response as the decoded one": lambda d: artifact(
        d, "rank_update_response"
    ).update(path=f"{DIRECTORY}/rank-update-response.raw"),
    "an update record without its schema version": lambda d: artifact(d, "update_record").update(
        schema_version=None
    ),
    "an update record with a source record": lambda d: artifact(d, "update_record").update(
        source=SOURCES["rank_update_request"]
    ),
    "an update record under another name": lambda d: artifact(d, "update_record").update(
        path=f"{DIRECTORY}/update.json"
    ),
    "a snapshot's record without its schema version": lambda d: (
        snapshot_ranking(d),
        artifact(d, "ranking_snapshot_record").update(schema_version=None),
    ),
    "a backtest's source of an operation 1.0.0 doesn't name": lambda d: artifact(
        d, "provider_response"
    )["source"].update(operation="rank_create"),
}


@pytest.mark.parametrize("change", RUN_MANIFEST_REJECTS.values(), ids=RUN_MANIFEST_REJECTS.keys())
def test_run_manifest_1_1_rejects(change: Change) -> None:
    rejects(RunManifestV1_1, changed(run_manifest, change))


# Experiment manifest 1.1.0


def experiment_artifact(document: Document, role: str) -> Document:
    return artifact(document, role)


EXPERIMENT_MANIFEST_ACCEPTS: dict[str, Change] = {
    "a plan ranked by a snapshot": lambda d: (
        experiment_artifact(d, "ranking_definition").update(
            source=source("ranking-definition", operation="rank_get")
        ),
        d["artifacts"].insert(
            2, listed("plans/1/snapshot.json", "ranking_snapshot_record", "1.0.0")
        ),
    ),
    "a synthetic experiment": lambda d: d.update(
        synthetic=True, approval="not_required", command=None
    ),
    "an undecoded rank_update response": lambda d: experiment_artifact(
        d, "rank_update_response"
    ).update(
        path=f"{EXPERIMENT_ATTEMPT}/rank-update-response.raw",
        role="rank_update_response_undecoded",
        source=SOURCES["rank_update_response_undecoded"],
    ),
}


@pytest.mark.parametrize(
    "change", EXPERIMENT_MANIFEST_ACCEPTS.values(), ids=EXPERIMENT_MANIFEST_ACCEPTS.keys()
)
def test_experiment_manifest_1_1_accepts(change: Change) -> None:
    accepts(ExperimentManifestV1_1, changed(experiment_manifest, change))


EXPERIMENT_MANIFEST_REJECTS: dict[str, Change] = {
    "version 1.0.0": lambda d: d.update(schema_version="1.0.0"),
    "a definition's copy in an attempt's directory": lambda d: experiment_artifact(
        d, "ranking_definition"
    ).update(path=f"{EXPERIMENT_ATTEMPT}/definition.xml"),
    "an update record in a plan's directory": lambda d: experiment_artifact(
        d, "update_record"
    ).update(path="plans/1/updating.json"),
    "a rank_update's request at the output's root": lambda d: experiment_artifact(
        d, "rank_update_request"
    ).update(path="rank-update-request.json"),
    "a snapshot's record without the definition's copy": lambda d: (
        d["artifacts"].remove(experiment_artifact(d, "ranking_definition")),
        d["artifacts"].insert(
            1, listed("plans/1/snapshot.json", "ranking_snapshot_record", "1.0.0")
        ),
    ),
    "a definition's copy without its source record": lambda d: experiment_artifact(
        d, "ranking_definition"
    ).update(source=None),
    "a rank_update's response of another format": lambda d: experiment_artifact(
        d, "rank_update_response"
    )["source"].update(format="p123api-screen-backtest"),
    "synthetic, with a command": lambda d: d.update(synthetic=True, approval="not_required"),
    "a configuration of another format": lambda d: experiment_artifact(d, "configuration")[
        "source"
    ].update(format="screen-configuration"),
}


@pytest.mark.parametrize(
    "change", EXPERIMENT_MANIFEST_REJECTS.values(), ids=EXPERIMENT_MANIFEST_REJECTS.keys()
)
def test_experiment_manifest_1_1_rejects(change: Change) -> None:
    rejects(ExperimentManifestV1_1, changed(experiment_manifest, change))


# The snapshot manifest


def snapshot_synthetic(document: Document) -> None:
    """The synthetic snapshot the core takes with the demo's client."""
    document.update(synthetic=True, approval="not_required", command=None)


SNAPSHOT_MANIFEST_ACCEPTS: dict[str, Change] = {
    "a synthetic snapshot the core took": snapshot_synthetic,
    "a snapshot whose rank_get failed": snapshot_failed,
    "a response the wrapper couldn't decode": lambda d: (
        snapshot_failed(d),
        d["artifacts"].insert(
            4,
            listed(
                f"{SNAPSHOT_DIRECTORY}/response.raw",
                "provider_response_undecoded",
                None,
                SNAPSHOT_SOURCES,
            ),
        ),
    ),
    "approved interactively": lambda d: d.update(approval="interactive"),
}


@pytest.mark.parametrize(
    "change", SNAPSHOT_MANIFEST_ACCEPTS.values(), ids=SNAPSHOT_MANIFEST_ACCEPTS.keys()
)
def test_snapshot_manifest_accepts(change: Change) -> None:
    accepts(RankingSnapshotManifest, changed(snapshot_manifest, change))


def snapshot_artifact(document: Document, role: str) -> Document:
    return artifact(document, role)


SNAPSHOT_MANIFEST_REJECTS: dict[str, Change] = {
    "synthetic, approved with --approve": lambda d: (
        snapshot_synthetic(d),
        d.update(approval="option"),
    ),
    "synthetic, with a command": lambda d: d.update(synthetic=True, approval="not_required"),
    "not synthetic, with the approval not_required": lambda d: d.update(approval="not_required"),
    "not synthetic, without a command": lambda d: d.update(command=None),
    "completed without its record": lambda d: d["artifacts"].remove(
        snapshot_artifact(d, "ranking_snapshot_record")
    ),
    "completed without its definition": lambda d: d["artifacts"].remove(
        snapshot_artifact(d, "ranking_definition")
    ),
    "failed, with its definition alone": lambda d: (
        snapshot_failed(d),
        d["artifacts"].append(
            listed("definition.xml", "ranking_definition", None, SNAPSHOT_SOURCES)
        ),
    ),
    "failed, with its definition and record": lambda d: d.update(
        outcome="failed",
        error={"code": "provider.unsupported_capability", "message": "Portfolio123 refused it."},
    ),
    "partial": lambda d: d.update(
        outcome="partial",
        error={"code": "execution.partial", "message": "Some planned cases didn't succeed."},
    ),
    "without its plan": lambda d: d["artifacts"].remove(snapshot_artifact(d, "plan")),
    "without its configuration": lambda d: d["artifacts"].remove(
        snapshot_artifact(d, "configuration")
    ),
    "a start record with a source record": lambda d: snapshot_artifact(d, "start_record").update(
        source=SNAPSHOT_SOURCES["provider_request"]
    ),
    "a configuration without its source record": lambda d: snapshot_artifact(
        d, "configuration"
    ).update(source=None),
    "a definition from a file": lambda d: snapshot_artifact(d, "ranking_definition").update(
        source=source("ranking-definition", "user_supplied", None)
    ),
    "a response of the backtest's format": lambda d: snapshot_artifact(d, "provider_response")[
        "source"
    ].update(format="p123api-screen-backtest"),
    "a response no parser read": lambda d: snapshot_artifact(d, "provider_response")[
        "source"
    ].update(parser_version=None),
    "a request from another operation": lambda d: snapshot_artifact(d, "provider_request")[
        "source"
    ].update(operation="screen_backtest"),
    "a configuration of the screen's format": lambda d: snapshot_artifact(d, "configuration")[
        "source"
    ].update(format="screen-configuration"),
    "a configuration the provider returned": lambda d: snapshot_artifact(d, "configuration")[
        "source"
    ].update(provenance="verified"),
    "a response of another version of its format": lambda d: snapshot_artifact(
        d, "provider_response"
    )["source"].update(format_version="2"),
    "an undecoded response of another version of its format": lambda d: (
        snapshot_failed(d),
        d["artifacts"].insert(
            4,
            listed(f"{SNAPSHOT_DIRECTORY}/response.raw", "provider_response_undecoded")
            | {
                "source": source(
                    "p123api-rank-get-response_undecoded", operation="rank_get", version="2"
                )
            },
        ),
    ),
    "a request of another version of its format": lambda d: snapshot_artifact(
        d, "provider_request"
    )["source"].update(format_version="2"),
    "a configuration of a version the snapshot configuration doesn't have": lambda d: (
        snapshot_artifact(d, "configuration")["source"].update(format_version="1.1.0")
    ),
    "a plan in an experiment's place": lambda d: snapshot_artifact(d, "plan").update(
        path="plans/1/plan.json"
    ),
    "an attempt in a case's directory": lambda d: snapshot_artifact(d, "attempt_record").update(
        path=f"cases/{BASELINE_ID}/attempts/{ATTEMPT_ID}/attempt.json"
    ),
    "a role a snapshot has no file of": lambda d: d["artifacts"].append(
        listed("report.html", "report", None, SNAPSHOT_SOURCES)
    ),
    "two provider requests": lambda d: d["counts"].update(provider_requests=2),
    "a retry": lambda d: d["counts"].update(retries=1),
    "capabilities": lambda d: d.update(capabilities=run_manifest()["capabilities"]),
    "a run's artifact type": lambda d: d.update(artifact_type="run"),
    "no parser": lambda d: d.update(parsers=[]),
    "a parser listed twice": lambda d: d.update(parsers=d["parsers"] * 2),
    "the backtest's parser in rank_get's place": lambda d: d["parsers"][0].update(
        layout="p123api-screen-backtest"
    ),
    "another version of rank_get's parser": lambda d: d["parsers"][0].update(parser_version=2),
    "another version of rank_get's layout": lambda d: d["parsers"][0].update(layout_version=2),
    "the backtest's parser beside rank_get's": lambda d: d["parsers"].append(
        {"layout": "p123api-screen-backtest", "layout_version": 1, "parser_version": 1}
    ),
}


@pytest.mark.parametrize(
    "change", SNAPSHOT_MANIFEST_REJECTS.values(), ids=SNAPSHOT_MANIFEST_REJECTS.keys()
)
def test_snapshot_manifest_rejects(change: Change) -> None:
    rejects(RankingSnapshotManifest, changed(snapshot_manifest, change))


# The snapshot record

SNAPSHOT_RECORD_ACCEPTS: dict[str, Change] = {
    "a name other than the one requested": lambda d: d["system"].update(name="Value and Momentum"),
    "a system that can't be a ranking, recorded as it is": lambda d: d["system"].update(
        ranking_method=1, currency="EUR", type="ETF"
    ),
}


@pytest.mark.parametrize(
    "change", SNAPSHOT_RECORD_ACCEPTS.values(), ids=SNAPSHOT_RECORD_ACCEPTS.keys()
)
def test_snapshot_record_accepts(change: Change) -> None:
    accepts(RankingSnapshotRecord, changed(snapshot_record, change))


SNAPSHOT_RECORD_REJECTS: dict[str, Change] = {
    "an ID that's a boolean": lambda d: d["system"].update(id=True),
    "an ID as text": lambda d: d["system"].update(id="424242"),
    "a ranking method as text": lambda d: d["system"].update(ranking_method="2"),
    "a system without its type": lambda d: d["system"].pop("type"),
    "a blank request": lambda d: d.update(requested=" "),
    "a time that isn't UTC": lambda d: d.update(taken_at="2026-10-14T14:01:30+02:00"),
    "an attempt ID not in canonical form": lambda d: d.update(attempt_id=ATTEMPT_ID.upper()),
    "a definition by its path": lambda d: d.update(definition="definition.xml"),
    "version 1.1.0": lambda d: d.update(schema_version="1.1.0"),
}


@pytest.mark.parametrize(
    "change", SNAPSHOT_RECORD_REJECTS.values(), ids=SNAPSHOT_RECORD_REJECTS.keys()
)
def test_snapshot_record_rejects(change: Change) -> None:
    rejects(RankingSnapshotRecord, changed(snapshot_record, change))
