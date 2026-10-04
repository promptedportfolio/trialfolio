"""`trialfolio demo` writes a synthetic example run entirely offline, as `trialfolio run` writes a
run, from its packaged configuration and response: labeled synthetic, approved as `not_required`,
with records that read back as a complete run, and a report that says nothing was sent.

Traces to release 0.1.0's included scope (`trialfolio demo`) and required behavior 12 (`demo`
makes no network access), to docs/contracts.md, artifact storage (`synthetic` and the approval
`not_required`) and reports (a synthetic run's report), and to R01-AC16's checks of the demo's
labels, which R01-T16 repeats from a clean install. Through the CLI's entry function in the test
process.
"""

import json
import socket
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest

from tests.interface.conftest import Cli
from tests.support.html_report import parse
from trialfolio.contracts.attempt import AttemptRecord, StartRecord
from trialfolio.contracts.manifest import RunManifest
from trialfolio.runs import read_run
from trialfolio.storage import LocalArtifactStore

PACKAGED_RESPONSE = files("trialfolio").joinpath("demo_data", "response.json").read_bytes()
PACKAGED_CONFIGURATION = files("trialfolio").joinpath("demo_data", "screen.yaml").read_bytes()


@pytest.fixture
def connects(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Every address any socket in the process tries to connect to, in any thread."""
    attempted: list[object] = []
    real: Callable[..., Any] = socket.socket.connect

    def connect(sock: socket.socket, address: Any) -> None:
        attempted.append(address)
        real(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect)
    return attempted


def test_demo_runs_offline_and_labels_its_run_synthetic(cli: Cli, connects: list[object]) -> None:
    cli.accept_license()
    out = cli.tmp / "demo"

    outcome = cli("demo", "--out", out)

    assert outcome.exit_code == 0, outcome.stderr
    assert connects == []
    assert cli.server.received == ()
    manifest = RunManifest.model_validate_json((out / "manifest.json").read_bytes())
    assert manifest.synthetic is True
    assert manifest.approval == "not_required"
    assert manifest.command.name == "demo"
    assert manifest.command.options == {"json": False}
    assert str(out) not in (out / "manifest.json").read_text()
    assert manifest.outcome == "completed"
    assert manifest.error is None
    assert manifest.counts.cost is None
    assert "Nothing was sent to Portfolio123" in outcome.stdout
    # Its progress says the attempt's records are invented: before 2026-10-04, it said only that
    # the attempt was possibly charged.
    assert "possibly charged: yes, in its invented records, though nothing was sent;" in (
        outcome.stderr
    )


def test_the_demos_run_reads_back_as_a_complete_run(cli: Cli) -> None:
    cli.accept_license()
    out = cli.tmp / "demo"
    assert cli("demo", "--out", out).exit_code == 0

    saved = read_run(LocalArtifactStore(out))

    assert saved.manifest.synthetic is True
    assert saved.metrics is not None
    assert saved.settings is not None
    (attempt,) = saved.attempts
    assert attempt.status.outcome == "succeeded"
    (directory,) = (out / "cases").glob("*/attempts/*")
    StartRecord.model_validate_json((directory / "started.json").read_bytes())
    record = AttemptRecord.model_validate_json((directory / "attempt.json").read_bytes())
    assert record.outcome == "succeeded"
    assert record.provider_metadata.cost is None
    assert record.provider_metadata.quota_remaining is None
    assert json.loads((directory / "response.json").read_bytes()) == json.loads(PACKAGED_RESPONSE)
    assert (out / "configuration.yaml").read_bytes() == PACKAGED_CONFIGURATION


def test_the_demos_report_is_labeled_synthetic_and_says_nothing_was_sent(cli: Cli) -> None:
    cli.accept_license()
    out = cli.tmp / "demo"
    assert cli("demo", "--out", out).exit_code == 0

    document = parse((out / "report.html").read_text(encoding="utf-8"))

    assert document.dd("Results")[0].startswith("Synthetic:")
    (banner,) = (e for e in document.root.iter() if e.attrs.get("class") == "synthetic")
    assert banner.text.startswith("Synthetic example.")
    assert "nothing was sent to it" in banner.text
    assert document.dd("Approval") == ["Not required: the synthetic run sends nothing."]
    assert "Nothing was sent to Portfolio123, and nothing was charged." in (
        document.root.by_id("cases").text
    )


def test_report_rerenders_the_demos_run(cli: Cli) -> None:
    cli.accept_license()
    run = cli.tmp / "demo"
    assert cli("demo", "--out", run).exit_code == 0
    out = cli.tmp / "report"

    outcome = cli("report", run, "--out", out)

    assert outcome.exit_code == 0, outcome.stderr
    document = parse((out / "report.html").read_text(encoding="utf-8"))
    assert document.dd("Results")[0].startswith("Synthetic:")


def test_demo_json_summary_gives_its_ids_outputs_and_counts(cli: Cli) -> None:
    cli.accept_license()
    out = cli.tmp / "demo"

    outcome = cli("demo", "--out", out, "--json")

    assert outcome.exit_code == 0
    summary = outcome.summary
    manifest = RunManifest.model_validate_json((out / "manifest.json").read_bytes())
    (directory,) = (out / "cases").glob("*/attempts/*")
    assert summary["command"] == "demo"
    assert summary["outcome"] == "completed"
    assert summary["exit_code"] == 0
    assert summary["error"] is None
    assert summary["output_dir"] == str(out)
    assert summary["ids"] == {
        "plan_hash": manifest.plan_hash,
        "case_id": directory.parent.parent.name,
        "attempt_id": directory.name,
    }
    assert summary["outputs"] == {
        "manifest": "manifest.json",
        "report": "report.html",
        "metrics": "normalized/metrics.csv",
        "settings": "normalized/settings.csv",
    }
    assert summary["counts"] == {
        "attempts": 1,
        "provider_requests": 1,
        "metrics_unavailable": 0,
        "warnings": 0,
        "cost": None,
    }
    assert summary["statistical_validation"] == "not_assessed"
    assert summary["trading_readiness"] == "not_assessed"


def test_demo_needs_the_license_acknowledgment_and_writes_nothing_without_it(cli: Cli) -> None:
    out = cli.tmp / "demo"

    outcome = cli("demo", "--out", out, "--json")

    assert outcome.exit_code == 2
    assert outcome.summary["error"]["code"] == "license.not_acknowledged"  # pyright: ignore[reportIndexIssue]
    assert not out.exists()


def test_demo_refuses_an_output_directory_that_isnt_empty(cli: Cli) -> None:
    cli.accept_license()
    out = cli.tmp / "demo"
    out.mkdir()
    (out / "keep.txt").write_text("someone else's file")

    outcome = cli("demo", "--out", out, "--json")

    assert outcome.exit_code == 4
    assert outcome.summary["error"]["code"] == "output.not_empty"  # pyright: ignore[reportIndexIssue]
    assert sorted(path.name for path in out.iterdir()) == ["keep.txt"]


def test_the_demo_writes_no_acknowledgment_record_with_the_variable(cli: Cli) -> None:
    cli.accept_license()

    assert cli("demo", "--out", cli.tmp / "demo").exit_code == 0

    assert not list(Path(cli.home).rglob("acknowledgment.json"))
