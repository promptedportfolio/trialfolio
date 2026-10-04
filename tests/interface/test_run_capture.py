"""`trialfolio run` saves the complete response, and the provider's metadata, before anything is
normalized, and its manifest's hashes match the saved files; it makes one attempt, whose record
lists Trial Folio's authentication call and then the backtest request; and it ignores
`SSLKEYLOGFILE`.

Traces to R01-AC03, R01-AC07, and R01-AC32's interface part, through the CLI's entry function in
the test process, with the real client, `requests`, and `urllib3` over the fake server.
"""

import hashlib
import io
import json
import os
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tests.interface.conftest import (
    AUTHENTICATED,
    RESPONSES,
    STARTED,
    Cli,
    FaultyStores,
    Outcome,
    config,
    plan_hash_for,
    response,
    serve_success,
)
from tests.support.fake_portfolio123 import Received, Reply
from trialfolio.contracts.attempt import AttemptRecord
from trialfolio.contracts.manifest import RunManifest
from trialfolio.storage import ArtifactStore, LocalArtifactStore


def approved_run(
    cli: Cli,
    out: Path,
    *,
    name: str = "formula.yaml",
    store_factory: Callable[[str], ArtifactStore] = LocalArtifactStore,
) -> Outcome:
    """Runs `name`, approved with its plan's full hash."""
    path = config(name)
    return cli(
        "run",
        path,
        "--out",
        out,
        "--approve",
        plan_hash_for(path),
        "--json",
        store_factory=store_factory,
    )


def test_the_response_is_saved_whole_and_the_manifest_hashes_match(cli: Cli) -> None:
    cli.ready()
    serve_success(cli.server)
    out = cli.tmp / "out"

    outcome = approved_run(cli, out)

    assert outcome.exit_code == 0, outcome.stderr
    manifest = RunManifest.model_validate_json((out / "manifest.json").read_bytes())
    for artifact in manifest.artifacts:
        content = (out / artifact.path).read_bytes()
        assert artifact.artifact_id == "sha256:" + hashlib.sha256(content).hexdigest()
        assert artifact.size == len(content)
    (attempt_dir,) = (out / "cases").glob("*/attempts/*")
    served = json.loads((RESPONSES / "complete.json").read_bytes())
    assert json.loads((attempt_dir / "response.json").read_bytes()) == served
    record = AttemptRecord.model_validate_json((attempt_dir / "attempt.json").read_bytes())
    assert record.provider_metadata.cost == served["cost"]
    assert record.provider_metadata.quota_remaining == served["quotaRemaining"]
    assert manifest.approval == "option"
    assert manifest.outcome == "completed"


def test_the_manifest_records_the_options_without_a_path(cli: Cli) -> None:
    # A path can name the user, and manifests may be shared (D-14).
    cli.ready()
    serve_success(cli.server)
    out = cli.tmp / "out"

    outcome = approved_run(cli, out)

    assert outcome.exit_code == 0, outcome.stderr
    content = (out / "manifest.json").read_text()
    manifest = RunManifest.model_validate_json(content)
    assert manifest.command.options == {
        "approve": plan_hash_for(config("formula.yaml")),
        "json": True,
    }
    assert str(cli.tmp) not in content
    assert str(config("formula.yaml").parent) not in content


def test_the_manifest_gives_the_time_the_command_started(cli: Cli) -> None:
    # The clock reads an hour later once the plan is shown, as after a long wait for approval at
    # the prompt: the command started, and read its configuration, before that.
    cli.ready()
    serve_success(cli.server)
    out = cli.tmp / "out"
    shown = io.StringIO()

    def clock() -> datetime:
        return STARTED + timedelta(hours=1 if "Plan hash:" in shown.getvalue() else 0)

    path = config("formula.yaml")
    outcome = cli(
        "run", path, "--out", out, "--approve", plan_hash_for(path), stderr=shown, clock=clock
    )

    assert outcome.exit_code == 0, shown.getvalue()
    manifest = RunManifest.model_validate_json((out / "manifest.json").read_bytes())
    assert manifest.command.started_at == STARTED
    (configuration,) = (a for a in manifest.artifacts if a.role == "configuration")
    assert configuration.source is not None
    assert configuration.source.acquired_at == STARTED
    assert manifest.created_at == STARTED + timedelta(hours=1)


def test_one_attempt_lists_authentication_then_the_request(cli: Cli) -> None:
    cli.ready()
    serve_success(cli.server)

    outcome = approved_run(cli, cli.tmp / "out")

    (attempt_dir,) = (cli.tmp / "out" / "cases").glob("*/attempts/*")
    record = AttemptRecord.model_validate_json((attempt_dir / "attempt.json").read_bytes())
    assert [(e.request, e.status) for e in record.exchanges] == [
        ("POST /auth", 200),
        ("POST /screen/backtest", 200),
    ]
    assert cli.server.requests() == ["POST /auth", "POST /screen/backtest"]
    assert outcome.summary["counts"]["provider_requests"] == 1  # pyright: ignore[reportIndexIssue]
    assert outcome.summary["counts"]["attempts"] == 1  # pyright: ignore[reportIndexIssue]


def test_a_storage_failure_while_normalizing_leaves_the_saved_response(
    cli: Cli, faults: FaultyStores
) -> None:
    cli.ready()
    serve_success(cli.server)
    faults.fail_os("metrics.csv")

    outcome = approved_run(cli, cli.tmp / "out", store_factory=faults)

    assert outcome.exit_code == 4
    (attempt_dir,) = (cli.tmp / "out" / "cases").glob("*/attempts/*")
    assert (attempt_dir / "response.json").exists()
    assert (attempt_dir / "attempt.json").exists()
    assert not (cli.tmp / "out" / "manifest.json").exists()


def test_a_response_that_fails_validation_is_saved_and_flagged(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", response("invalid-structure.json"))

    outcome = approved_run(cli, cli.tmp / "out")

    assert outcome.exit_code == 5
    assert outcome.summary["error"]["code"] == "provider.response_invalid"  # pyright: ignore[reportIndexIssue]
    (attempt_dir,) = (cli.tmp / "out" / "cases").glob("*/attempts/*")
    assert (attempt_dir / "response.json").exists()
    manifest = RunManifest.model_validate_json((cli.tmp / "out" / "manifest.json").read_bytes())
    assert manifest.outcome == "failed"
    assert not (cli.tmp / "out" / "normalized").exists()


def test_sslkeylogfile_is_ignored_with_a_warning(cli: Cli, monkeypatch: pytest.MonkeyPatch) -> None:
    cli.ready()
    monkeypatch.setenv("SSLKEYLOGFILE", str(cli.tmp / "keys.log"))
    seen: list[str | None] = []
    serve_success(cli.server)
    real = cli.server._take  # pyright: ignore[reportPrivateUsage]

    def take(request: Received) -> Reply:
        seen.append(os.environ.get("SSLKEYLOGFILE"))
        return real(request)

    monkeypatch.setattr(cli.server, "_take", take)

    outcome = approved_run(cli, cli.tmp / "out")

    assert outcome.exit_code == 0
    assert "SSLKEYLOGFILE" in outcome.stderr
    assert seen == [None, None]
    assert not (cli.tmp / "keys.log").exists()
