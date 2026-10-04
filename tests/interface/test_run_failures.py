"""`trialfolio run` gives each provider failure its documented code, exit 5, and a message that
says what to do; a failure after the claim is accounted for, with the attempt record and a
manifest whose outcome is `failed`; and a read timeout records an `unknown` attempt that isn't
retried.

Traces to R01-AC05 (authentication, unavailable-provider, quota, unsupported-capability,
rejected-request, and response-validation errors) and R01-AC06 (a simulated read timeout), and to
release 0.1.0's failure table, through the CLI's entry function in the test process, with the real
client, `requests`, and `urllib3` over the fake server.
"""

from pathlib import Path

import pytest

from tests.interface.conftest import (
    AUTHENTICATED,
    Cli,
    Outcome,
    config,
    plan_hash_for,
    response,
)
from tests.support.fake_portfolio123 import Reply
from trialfolio.contracts.attempt import AttemptRecord
from trialfolio.contracts.manifest import RunManifest

AUTH = "POST /auth"
BACKTEST = "POST /screen/backtest"


def approved_run(cli: Cli, out: Path, *, timeout: int | None = None) -> Outcome:
    """Runs `formula.yaml`, approved with its plan's full hash, with a JSON summary."""
    path = config("formula.yaml")
    return cli(
        "run", path, "--out", out, "--approve", plan_hash_for(path), "--json", timeout=timeout
    )


def error_of(outcome: Outcome) -> dict[str, str]:
    error = outcome.summary["error"]
    assert isinstance(error, dict)
    return error  # pyright: ignore[reportUnknownVariableType]


def the_attempt(out: Path) -> AttemptRecord:
    (attempt_dir,) = (out / "cases").glob("*/attempts/*")
    return AttemptRecord.model_validate_json((attempt_dir / "attempt.json").read_bytes())


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
    path = config("formula.yaml")
    out = cli.tmp / "out"

    outcome = cli.without_module(
        "p123api", "run", path, "--out", out, "--approve", plan_hash_for(path), "--json"
    )

    assert outcome.exit_code == 3, outcome.stderr
    error = error_of(outcome)
    assert error["code"] == "environment.unsupported"
    assert "p123api is installed, but it can't be imported" in error["message"]
    assert "Plan hash" not in outcome.stderr
    assert not out.exists()


def test_missing_credentials_fail_before_anything_is_written_or_sent(cli: Cli) -> None:
    cli.accept_license()
    out = cli.tmp / "out"

    outcome = approved_run(cli, out)

    assert outcome.exit_code == 5
    error = error_of(outcome)
    assert error["code"] == "provider.auth_failed"
    assert "TRIALFOLIO_P123_API_ID" in error["message"]
    assert "TRIALFOLIO_P123_API_KEY" in error["message"]
    assert not out.exists()
    assert cli.server.requests() == []
    assert outcome.summary["output_dir"] is None


def test_a_blank_credential_counts_as_missing(cli: Cli, monkeypatch: pytest.MonkeyPatch) -> None:
    cli.ready()
    monkeypatch.setenv("TRIALFOLIO_P123_API_KEY", "   ")
    out = cli.tmp / "out"

    outcome = approved_run(cli, out)

    assert outcome.exit_code == 5
    error = error_of(outcome)
    assert error["code"] == "provider.auth_failed"
    assert "TRIALFOLIO_P123_API_KEY" in error["message"]
    assert "TRIALFOLIO_P123_API_ID" not in error["message"]
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

    outcome = approved_run(cli, out)

    assert outcome.exit_code == 5
    error = error_of(outcome)
    assert error["code"] == code
    assert advice in error["message"]
    assert "wasn't sent" in error["message"]
    assert cli.server.requests() == [AUTH]
    record = the_attempt(out)
    assert record.outcome == "failed"
    assert not record.possibly_charged
    assert [(e.request, e.status) for e in record.exchanges] == [(AUTH, status)]
    manifest = accounted_for(out, code)
    assert manifest.counts.provider_requests == 0
    assert outcome.summary["counts"]["provider_requests"] == 0  # pyright: ignore[reportIndexIssue]
    assert outcome.summary["ids"]["attempt_id"] == str(record.attempt_id)  # pyright: ignore[reportIndexIssue]


def test_a_403_on_authentication_carries_portfolio123s_message(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", Reply(403, b"API access not enabled"))
    out = cli.tmp / "out"

    outcome = approved_run(cli, out)

    assert error_of(outcome)["message"].endswith(
        'Portfolio123\'s message: "API access not enabled"'
    )
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

    outcome = approved_run(cli, out)

    assert outcome.exit_code == 5
    error = error_of(outcome)
    assert error["code"] == code
    assert advice in error["message"]
    assert "may have been charged" in error["message"]
    assert cli.server.requests() == [AUTH, BACKTEST]
    record = the_attempt(out)
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

    outcome = approved_run(cli, out)

    message = error_of(outcome)["message"]
    assert message.endswith('Portfolio123\'s message: "Invalid parameter: pitMethod"')
    assert "\x1b" not in outcome.stderr
    assert 'Portfolio123\'s message: "Invalid parameter: pitMethod"' in outcome.stderr
    manifest = accounted_for(out, "provider.unsupported_capability")
    assert manifest.error is not None
    assert manifest.error.message == message


def test_a_response_that_fails_validation_is_flagged_after_it_is_saved(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", response("invalid-structure.json"))
    out = cli.tmp / "out"

    outcome = approved_run(cli, out)

    assert outcome.exit_code == 5
    error = error_of(outcome)
    assert error["code"] == "provider.response_invalid"
    assert "stats" in error["message"]
    record = the_attempt(out)
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

    outcome = approved_run(cli, out)

    assert error_of(outcome)["code"] == "provider.response_invalid"
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

    outcome = approved_run(cli, out, timeout=1)

    assert outcome.exit_code == 5
    error = error_of(outcome)
    assert error["code"] == "provider.outcome_unknown"
    assert "never retries it automatically" in error["message"]
    record = the_attempt(out)
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
