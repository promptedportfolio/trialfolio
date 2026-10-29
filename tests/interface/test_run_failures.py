"""`trialfolio run` gives each provider failure its documented code, exit 5, and a message that
says what to do; a failure after the claim is accounted for, with the attempt record and a
manifest whose outcome is `failed`; and a read timeout records an `unknown` attempt that isn't
retried.

Traces to R01-AC05 (authentication, unavailable-provider, quota, unsupported-capability,
rejected-request, and response-validation errors) and R01-AC06 (a simulated read timeout), and to
release 0.1.0's failure table, through the CLI's entry function in the test process, with the real
client, `requests`, and `urllib3` over the fake server. An unexpected exception after the attempt,
injected by storage faults, says what the attempt's records say about the request (R01-T14), and
one while `configuration.yaml` is saved leaves no manifest, which would have to list it. One
after the store published an attempt's file still leaves a manifest that lists the file
(docs/contracts.md, execution outcomes and attempts; a corrected defect, 2026-10-10). Where stderr
says the run's records are, the output directory is escaped, as an error message escapes a path
(docs/contracts.md, CLI behavior; a corrected defect, 2026-10-11).
"""

import hashlib
from pathlib import Path

import pytest

from tests.support.cli import Cli, plan_hash_for
from tests.support.fake_portfolio123 import (
    AUTH,
    AUTHENTICATED,
    BACKTEST,
    Reply,
    response,
    serve_success,
)
from tests.support.paths import screen_config
from tests.support.saved_records import only_attempt_record
from tests.support.storage_faults import FaultyStores
from trialfolio.contracts.manifest import RunManifest

FORMULA = screen_config("formula.yaml")


def accounted_for(out: Path, code: str) -> RunManifest:
    """Checks the run's manifest records the failure, and returns it."""
    manifest = RunManifest.model_validate_json((out / "manifest.json").read_bytes())
    assert manifest.outcome == "failed"
    assert manifest.error is not None
    assert manifest.error.code == code
    assert (out / "report.html").exists()
    return manifest


# Before the claim


def test_a_p123api_that_cant_be_imported_fails_before_the_plan(cli: Cli) -> None:
    cli.ready()
    path = screen_config("formula.yaml")
    out = cli.tmp / "out"

    outcome = cli.without_module(
        "p123api", "run", path, "--out", out, "--approve", plan_hash_for(path), "--json"
    )

    assert outcome.exit_code == 3, outcome.stderr
    error = outcome.error
    assert error["code"] == "environment.unsupported"
    assert "p123api is installed, but it can't be imported" in error["message"]
    assert "Plan hash" not in outcome.stderr
    assert not out.exists()


def test_missing_credentials_fail_before_anything_is_written_or_sent(cli: Cli) -> None:
    cli.accept_license()
    out = cli.tmp / "out"

    outcome = cli.run_approved(FORMULA, out, "--json")

    assert outcome.exit_code == 5
    error = outcome.error
    assert error["code"] == "provider.auth_failed"
    assert (
        "set TRIALFOLIO_P123_API_ID and TRIALFOLIO_P123_API_KEY to your API ID and API key."
        in error["message"]
    )
    assert not out.exists()
    assert cli.server.requests() == []
    assert outcome.summary["output_dir"] is None


@pytest.mark.parametrize(
    ("blank", "named", "other", "other_name"),
    [
        ("TRIALFOLIO_P123_API_KEY", "your API key.", "TRIALFOLIO_P123_API_ID", "API ID"),
        ("TRIALFOLIO_P123_API_ID", "your API ID.", "TRIALFOLIO_P123_API_KEY", "API key"),
    ],
    ids=["key", "id"],
)
def test_a_blank_credential_counts_as_missing(
    cli: Cli,
    monkeypatch: pytest.MonkeyPatch,
    blank: str,
    named: str,
    other: str,
    other_name: str,
) -> None:
    cli.ready()
    monkeypatch.setenv(blank, "   ")
    out = cli.tmp / "out"

    outcome = cli.run_approved(FORMULA, out, "--json")

    assert outcome.exit_code == 5
    error = outcome.error
    assert error["code"] == "provider.auth_failed"
    # It names only the missing one: before 2026-10-04, it asked for both by name.
    assert f"set {blank} to {named}" in error["message"]
    assert other not in error["message"]
    assert other_name not in error["message"]
    assert not out.exists()
    assert cli.server.requests() == []


# Trial Folio's authentication call


@pytest.mark.parametrize(
    ("status", "code", "advice"),
    [
        (400, "provider.auth_failed", "Check the API ID and key"),
        (401, "provider.auth_failed", "Check the API ID and key"),
        (402, "provider.auth_failed", "paying subscription"),
        (403, "provider.auth_failed", "Check the API ID and key"),
        (406, "provider.auth_failed", "inactive"),
        (503, "provider.unavailable", "Try again later"),
    ],
)
def test_a_failed_authentication_gives_its_code_and_sends_no_request(
    cli: Cli, status: int, code: str, advice: str
) -> None:
    cli.ready()
    cli.server.reply("/auth", Reply(status, b"Refused"))
    out = cli.tmp / "out"

    outcome = cli.run_approved(FORMULA, out, "--json")

    assert outcome.exit_code == 5
    error = outcome.error
    assert error["code"] == code
    assert advice in error["message"]
    assert "wasn't sent" in error["message"]
    assert cli.server.requests() == [AUTH]
    record = only_attempt_record(out)
    assert record.outcome == "failed"
    assert not record.possibly_charged
    assert [(e.request, e.status) for e in record.exchanges] == [(AUTH, status)]
    manifest = accounted_for(out, code)
    assert manifest.counts.provider_requests == 0
    assert outcome.counts["provider_requests"] == 0
    assert outcome.ids["attempt_id"] == str(record.attempt_id)


def test_a_403_on_authentication_carries_portfolio123s_message(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", Reply(403, b"API access not enabled"))
    out = cli.tmp / "out"

    outcome = cli.run_approved(FORMULA, out, "--json")

    assert outcome.error["message"].endswith('Portfolio123\'s message: "API access not enabled"')
    assert "API access not enabled" in outcome.stderr


# The backtest request


@pytest.mark.parametrize(
    ("reply", "code", "advice"),
    [
        pytest.param(
            Reply(400, b"Invalid parameter: pitMethod"),
            "provider.unsupported_capability",
            "Check the configuration",
            id="400",
        ),
        pytest.param(
            Reply(409, b"ERROR: Invalid criteria in Rule 1. Error near 'MktCapp'"),
            "provider.unsupported_capability",
            "Check the configuration",
            id="409",
        ),
        pytest.param(
            Reply(402, b"Quota exhausted"),
            "provider.quota_exceeded",
            "Check the account's API credits",
            id="402",
        ),
        pytest.param(
            Reply(404, b"Not found"),
            "provider.request_rejected",
            "Wait before running the command again",
            id="404",
        ),
    ],
)
def test_a_rejected_request_gives_its_code_and_is_possibly_charged(
    cli: Cli, reply: Reply, code: str, advice: str
) -> None:
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", reply)
    out = cli.tmp / "out"

    outcome = cli.run_approved(FORMULA, out, "--json")

    assert outcome.exit_code == 5
    error = outcome.error
    assert error["code"] == code
    assert advice in error["message"]
    assert "may have been charged" in error["message"]
    # The command shows the error, so a screen run's terminal doesn't show the attempt's ending.
    assert "Attempt ended failed" not in outcome.stderr
    assert cli.server.requests() == [AUTH, BACKTEST]
    record = only_attempt_record(out)
    assert record.outcome == "failed"
    assert record.possibly_charged
    assert record.error is not None
    assert record.error.code == code
    manifest = accounted_for(out, code)
    assert manifest.counts.provider_requests == 1
    assert manifest.counts.attempts.failed == 1
    assert not (out / "normalized").exists()


def test_a_400s_message_includes_portfolio123s_sanitized_text(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", Reply(400, b"Invalid\x1bparameter:\n\npitMethod"))
    out = cli.tmp / "out"

    outcome = cli.run_approved(FORMULA, out, "--json")

    message = outcome.error["message"]
    assert message.endswith('Portfolio123\'s message: "Invalid parameter: pitMethod"')
    assert "\x1b" not in outcome.stderr
    assert 'Portfolio123\'s message: "Invalid parameter: pitMethod"' in outcome.stderr
    manifest = accounted_for(out, "provider.unsupported_capability")
    assert manifest.error is not None
    assert manifest.error.message == message


def test_where_the_runs_records_are_escapes_the_output_directory(cli: Cli) -> None:
    # R03-T13's review: stderr named the output directory as given, so a control character in
    # it could act on the terminal, though an error message escapes each path it names.
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", Reply(400, b"Unsupported value"))
    out = cli.tmp / "out \x1b[2J"

    outcome = cli.run_approved(FORMULA, out, "--json")

    assert outcome.error["code"] == "provider.unsupported_capability"
    escaped = str(out).replace("\x1b", "\\u001b")
    assert f"The run's records are in {escaped}." in outcome.stderr
    assert "\x1b" not in outcome.stderr
    assert outcome.summary["output_dir"] == str(out)


def test_a_response_that_fails_validation_is_flagged_after_it_is_saved(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", response("invalid-structure.json"))
    out = cli.tmp / "out"

    outcome = cli.run_approved(FORMULA, out, "--json")

    assert outcome.exit_code == 5
    error = outcome.error
    assert error["code"] == "provider.response_invalid"
    assert "stats" in error["message"]
    record = only_attempt_record(out)
    assert record.outcome == "succeeded"
    assert record.response is not None
    assert (out / record.response.path).exists()
    accounted_for(out, "provider.response_invalid")
    assert not (out / "normalized").exists()


@pytest.mark.parametrize(
    ("reply", "series"),
    [(response("invalid-structure.json"), True), (Reply(200, b"{}"), False)],
    ids=["series-without-stats", "empty-object"],
)
def test_return_series_says_whether_the_saved_response_holds_series(
    cli: Cli, reply: Reply, series: bool
) -> None:
    # Both fail validation, and both are saved decoded; only the first has `results.rows` and
    # `chart`, which the manifest's capability and the report may say were preserved.
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", reply)
    out = cli.tmp / "out"

    outcome = cli.run_approved(FORMULA, out, "--json")

    assert outcome.error["code"] == "provider.response_invalid"
    manifest = accounted_for(out, "provider.response_invalid")
    assert manifest.capabilities.return_series == ("source_only" if series else "absent")
    report = (out / "report.html").read_text()
    assert ("per-period returns: preserved in the saved response" in report) is series
    assert ("Its per-period series is preserved there" in report) is series


# A read timeout (R01-AC06)


def test_a_read_timeout_records_an_unknown_attempt_sent_once(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", Reply(200, b"{}", delay=3))
    out = cli.tmp / "out"

    outcome = cli.run_approved(FORMULA, out, "--json", timeout=1)

    assert outcome.exit_code == 5
    error = outcome.error
    assert error["code"] == "provider.outcome_unknown"
    assert "never retries it automatically" in error["message"]
    record = only_attempt_record(out)
    assert record.outcome == "unknown"
    assert record.possibly_charged
    assert [(e.request, e.result) for e in record.exchanges] == [
        (AUTH, "response"),
        (BACKTEST, "interrupted"),
    ]
    assert cli.server.requests() == [AUTH, BACKTEST]
    manifest = accounted_for(out, "provider.outcome_unknown")
    assert manifest.counts.attempts.unknown == 1
    assert manifest.counts.provider_requests == 1


# A file published before an unexpected failure during the attempt


@pytest.mark.parametrize(
    ("name", "role", "code", "ended"),
    [
        ("request.json", "provider_request", "internal.unexpected", "failed"),
        ("started.json", "start_record", "internal.unexpected", "failed"),
        ("response.json", "provider_response", "provider.outcome_unknown", "unknown"),
    ],
)
def test_a_file_published_before_an_unexpected_failure_is_in_the_manifest(
    cli: Cli, faults: FaultyStores, name: str, role: str, code: str, ended: str
) -> None:
    # A corrected defect: the attempt left out a file its write published before the failure, so
    # the run's manifest didn't list every file of the run.
    cli.ready()
    serve_success(cli.server)
    faults.fail_after(name, RuntimeError("its own message"))
    path = screen_config("formula.yaml")
    out = cli.tmp / "out"

    outcome = cli.run_approved(path, out, "--json", store_factory=faults)

    assert outcome.error["code"] == code
    record = only_attempt_record(out)
    assert record.outcome == ended
    # Only a write that completed is referenced: a 200 whose response.json was published before
    # the failure is unknown, as one whose save failed.
    assert record.response is None
    assert cli.server.requests() == ([AUTH, BACKTEST] if name == "response.json" else [AUTH])
    manifest = accounted_for(out, code)
    listed = {artifact.path: artifact for artifact in manifest.artifacts}
    (published,) = (out / "cases").glob(f"*/attempts/*/{name}")
    content = published.read_bytes()
    entry = listed[published.relative_to(out).as_posix()]
    assert (entry.role, entry.artifact_id, entry.size) == (
        role,
        "sha256:" + hashlib.sha256(content).hexdigest(),
        len(content),
    )
    written = {
        file.relative_to(out).as_posix()
        for file in out.rglob("*")
        if file.is_file() and file.relative_to(out).parts[0] != "logs"
    }
    assert set(listed) == written - {"manifest.json"}
    # The run reads back as a complete one.
    assert cli("report", out, "--out", cli.tmp / "report").exit_code == 0


# An unexpected exception after the attempt


def test_an_unexpected_exception_after_the_attempt_says_the_request_succeeded(
    cli: Cli, faults: FaultyStores
) -> None:
    cli.ready()
    serve_success(cli.server)
    faults.fail_before("report.html", RuntimeError("its own message"))
    path = screen_config("formula.yaml")
    out = cli.tmp / "out"

    outcome = cli.run_approved(path, out, "--json", store_factory=faults)

    assert outcome.exit_code == 1
    error = outcome.error
    assert error["code"] == "internal.unexpected"
    message = error["message"]
    assert message.startswith("Trial Folio failed unexpectedly (RuntimeError).")
    # So nobody runs it again thinking nothing was sent: it may have cost credits.
    assert "The screen backtest request succeeded, and its response was saved." in message
    assert "The run has no manifest, so its output is incomplete." in message
    assert "its own message" not in message
    assert only_attempt_record(out).outcome == "succeeded"
    assert not (out / "manifest.json").exists()
    assert cli.server.requests() == [AUTH, BACKTEST]


# An unexpected exception before the configuration is saved


def test_an_unexpected_failure_saving_the_configuration_leaves_no_manifest(
    cli: Cli, faults: FaultyStores
) -> None:
    # Every manifest lists configuration.yaml, so a manifest written without it would read as a
    # complete run that `trialfolio report` then rejects.
    cli.ready()
    serve_success(cli.server)
    faults.fail_before("configuration.yaml", RuntimeError("its own message"))
    path = screen_config("formula.yaml")
    out = cli.tmp / "out"

    outcome = cli.run_approved(path, out, "--json", store_factory=faults)

    assert outcome.exit_code == 1
    error = outcome.error
    assert error["code"] == "internal.unexpected"
    assert "The screen backtest request wasn't sent." in error["message"]
    record = only_attempt_record(out)
    assert record.outcome == "failed"
    assert record.possibly_charged is False
    assert not (out / "configuration.yaml").exists()
    assert not (out / "report.html").exists()
    assert not (out / "manifest.json").exists()
    assert outcome.summary["outputs"] == {}
    assert cli.server.requests() == []
