"""A storage failure during `trialfolio run` exits with `storage.write_failed` and 4, even after
the backtest request was sent, and leaves no manifest, so the output is visibly incomplete. The
attempt's records still give its outcome: a 200 whose response wasn't saved is `unknown` and
possibly charged, and without an attempt record the start record reads as `running`.

Traces to R01-AC29, and to docs/contracts.md, endings that decide the error code and artifact
storage (completion), through the CLI's entry function in the test process, with storage faults
wrapping the real store. R01-T15 adds the failed `os.link` of a file system without hard links,
for R01-AC29's case at `configuration.yaml`; here the same write fails with `ENOSPC`. A failure
after the store published the manifest, such as its directory's sync, discards it (R01-T14).
"""

import uuid
from pathlib import Path

import pytest

from tests.interface.conftest import (
    Cli,
    FaultyStores,
    Outcome,
    config,
    plan_hash_for,
    serve_success,
)
from tests.support.storage_faults import StorageFaults
from trialfolio.attempts import read_attempt
from trialfolio.contracts.attempt import AttemptRecord
from trialfolio.errors import TrialFolioError
from trialfolio.storage import ArtifactStore, LocalArtifactStore

FORMULA = config("formula.yaml")


def approved_run(cli: Cli, out: Path, faults: FaultyStores) -> Outcome:
    return cli(
        "run",
        FORMULA,
        "--out",
        out,
        "--approve",
        plan_hash_for(FORMULA),
        "--json",
        store_factory=faults,
    )


def write_failed(outcome: Outcome) -> None:
    assert outcome.exit_code == 4, outcome.stderr
    error = outcome.summary["error"]
    assert isinstance(error, dict)
    assert error["code"] == "storage.write_failed"


def attempt_directory(out: Path) -> Path:
    (directory,) = (out / "cases").glob("*/attempts/*")
    return directory


def test_a_failure_saving_the_response_after_a_200_is_unknown_and_possibly_charged(
    cli: Cli, faults: FaultyStores
) -> None:
    cli.ready()
    out = cli.tmp / "out"
    serve_success(cli.server)
    faults.fail_os("response.json")

    outcome = approved_run(cli, out, faults)

    write_failed(outcome)
    directory = attempt_directory(out)
    record = AttemptRecord.model_validate_json((directory / "attempt.json").read_bytes())
    assert record.outcome == "unknown"
    assert record.possibly_charged is True
    assert record.response is None
    assert record.error is not None
    assert record.error.code == "storage.write_failed"
    assert not (directory / "response.json").exists()
    assert not (out / "manifest.json").exists()
    assert not (out / "normalized").exists()
    assert cli.server.requests() == ["POST /auth", "POST /screen/backtest"]
    summary = outcome.summary
    assert summary["ids"]["attempt_id"] == directory.name  # pyright: ignore[reportIndexIssue]
    assert summary["counts"]["attempts"] == 1  # pyright: ignore[reportIndexIssue]
    assert summary["counts"]["provider_requests"] == 1  # pyright: ignore[reportIndexIssue]
    assert "manifest" not in summary["outputs"]  # pyright: ignore[reportOperatorIssue]


def test_without_an_attempt_record_the_start_record_reads_as_running(
    cli: Cli, faults: FaultyStores
) -> None:
    cli.ready()
    out = cli.tmp / "out"
    serve_success(cli.server)
    faults.fail_os("response.json")
    faults.fail_os("attempt.json")

    outcome = approved_run(cli, out, faults)

    write_failed(outcome)
    directory = attempt_directory(out)
    assert (directory / "started.json").exists()
    assert not (directory / "attempt.json").exists()
    status = read_attempt(
        LocalArtifactStore(out), directory.parent.parent.name, uuid.UUID(directory.name)
    )
    assert status is not None
    assert status.outcome == "running"
    assert status.possibly_charged is True
    assert status.provider_requests == 1
    summary = outcome.summary
    assert summary["ids"]["attempt_id"] == directory.name  # pyright: ignore[reportIndexIssue]
    assert summary["counts"]["attempts"] == 1  # pyright: ignore[reportIndexIssue]
    assert summary["counts"]["provider_requests"] == 1  # pyright: ignore[reportIndexIssue]
    assert summary["counts"]["cost"] is None  # pyright: ignore[reportIndexIssue]
    assert not (out / "manifest.json").exists()


def test_a_failure_writing_the_configuration_fails_before_any_request(
    cli: Cli, faults: FaultyStores
) -> None:
    cli.ready()
    out = cli.tmp / "out"
    serve_success(cli.server)
    faults.fail_os("configuration.yaml")

    outcome = approved_run(cli, out, faults)

    write_failed(outcome)
    assert cli.server.received == ()
    assert not (out / "configuration.yaml").exists()
    record = AttemptRecord.model_validate_json(
        (attempt_directory(out) / "attempt.json").read_bytes()
    )
    assert record.outcome == "failed"
    assert record.possibly_charged is False
    assert record.exchanges == ()
    assert not (out / "manifest.json").exists()
    assert outcome.summary["counts"]["provider_requests"] == 0  # pyright: ignore[reportIndexIssue]


def test_a_failure_writing_the_report_leaves_no_manifest(cli: Cli, faults: FaultyStores) -> None:
    cli.ready()
    out = cli.tmp / "out"
    serve_success(cli.server)
    faults.fail_os("report.html")

    outcome = approved_run(cli, out, faults)

    write_failed(outcome)
    record = AttemptRecord.model_validate_json(
        (attempt_directory(out) / "attempt.json").read_bytes()
    )
    assert record.outcome == "succeeded"
    assert (out / "normalized" / "metrics.csv").exists()
    assert not (out / "report.html").exists()
    assert not (out / "manifest.json").exists()
    message = outcome.summary["error"]["message"]  # pyright: ignore[reportIndexIssue]
    assert "The run has no manifest, so its output is incomplete." in message


def test_a_failure_writing_the_manifest_leaves_the_run_incomplete(
    cli: Cli, faults: FaultyStores
) -> None:
    cli.ready()
    out = cli.tmp / "out"
    serve_success(cli.server)
    faults.fail_os("manifest.json")

    outcome = approved_run(cli, out, faults)

    write_failed(outcome)
    assert (out / "report.html").exists()
    assert not (out / "manifest.json").exists()
    assert "manifest" not in outcome.summary["outputs"]  # pyright: ignore[reportOperatorIssue]
    assert len(faults.published) == len(set(faults.published))


SYNC_FAILED = TrialFolioError(
    "storage.write_failed",
    "Couldn't write manifest.json durably: Input/output error. Check the output directory's free"
    " space and permissions.",
)
"""What the store raises when the sync after publishing a file fails."""


def test_a_failure_after_the_manifest_is_published_discards_it(
    cli: Cli, faults: FaultyStores
) -> None:
    cli.ready()
    out = cli.tmp / "out"
    serve_success(cli.server)
    faults.fail_after("manifest.json", SYNC_FAILED)

    outcome = approved_run(cli, out, faults)

    write_failed(outcome)
    assert faults.published[-1] == "manifest.json"
    assert not (out / "manifest.json").exists()
    assert "manifest" not in outcome.summary["outputs"]  # pyright: ignore[reportOperatorIssue]
    message = outcome.summary["error"]["message"]  # pyright: ignore[reportIndexIssue]
    assert "The screen backtest request succeeded, and its response was saved." in message
    assert "The run has no manifest, so its output is incomplete." in message


class _Undiscardable(StorageFaults):
    """Storage faults whose store can't remove a file."""

    def discard(self, path: str, data: bytes) -> None:
        raise TrialFolioError("storage.write_failed", f"Couldn't remove {path}.")


def test_a_published_manifest_that_cant_be_discarded_is_named(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli.ready()
    out = cli.tmp / "out"
    serve_success(cli.server)

    def undiscardable(root: str) -> ArtifactStore:
        store = _Undiscardable(LocalArtifactStore(root), monkeypatch)
        store.fail_after("manifest.json", SYNC_FAILED)
        return store

    outcome = cli(
        "run",
        FORMULA,
        "--out",
        out,
        "--approve",
        plan_hash_for(FORMULA),
        "--json",
        store_factory=undiscardable,
    )

    write_failed(outcome)
    assert (out / "manifest.json").exists()
    assert "manifest" not in outcome.summary["outputs"]  # pyright: ignore[reportOperatorIssue]
    message = outcome.summary["error"]["message"]  # pyright: ignore[reportIndexIssue]
    assert (
        "The run's manifest.json was published before the failure, and couldn't be removed, so"
        " the run reads as complete although the command failed."
    ) in message
