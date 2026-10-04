"""No credential or token canary appears in any artifact, log, or output of `trialfolio run`, even
after an authentication failure, or a backtest failure, when the wrapper's exception carries the
bearer token.

Traces to R01-AC04, and to docs/contracts.md, credentials (redaction) and logging, through the
CLI's entry function in the test process at `TRIALFOLIO_LOG_LEVEL=DEBUG`, with the real client,
`requests`, and `urllib3` over the fake server. The scan covers every file under the test's
temporary directory, which holds the output directory and the temporary home with the per-user
configuration and log directories, and stdout and stderr.
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
from tests.support import canaries
from tests.support.fake_portfolio123 import Reply


def approved_run(cli: Cli, out: Path) -> Outcome:
    path = config("formula.yaml")
    return cli("run", path, "--out", out, "--approve", plan_hash_for(path), "--json")


def leaks(cli: Cli, outcome: Outcome) -> list[str]:
    """Where a credential or token canary appears: each file under the test's directory, and
    stdout and stderr."""
    return canaries.leaks([cli.tmp], stdout=outcome.stdout, stderr=outcome.stderr)


@pytest.fixture(autouse=True)
def debug(cli: Cli, monkeypatch: pytest.MonkeyPatch) -> None:
    """DEBUG level, set once `cli` has cleared the environment it starts with."""
    monkeypatch.setenv("TRIALFOLIO_LOG_LEVEL", "DEBUG")


@pytest.mark.parametrize(
    ("authentication", "backtest", "exit_code"),
    [
        pytest.param(Reply(401, b"Unauthorized"), None, 5, id="authentication 401"),
        pytest.param(
            AUTHENTICATED, Reply(400, b"Invalid parameter: pitMethod"), 5, id="backtest 400"
        ),
        pytest.param(
            AUTHENTICATED,
            Reply(
                400,
                f"Bad key {canaries.API_KEY} for {canaries.API_ID} with {canaries.TOKEN}".encode(),
            ),
            5,
            id="backtest 400 echoing the credentials",
        ),
        pytest.param(AUTHENTICATED, Reply(401, b"Unauthorized"), 5, id="backtest 401"),
        pytest.param(AUTHENTICATED, Reply(403, b"Forbidden"), 5, id="backtest 403"),
        pytest.param(AUTHENTICATED, response("complete.json"), 0, id="success"),
    ],
)
def test_no_credential_or_token_canary_appears_anywhere(
    cli: Cli, authentication: Reply, backtest: Reply | None, exit_code: int
) -> None:
    cli.ready()
    # A second authentication reply, in case the wrapper's re-authentication got through.
    cli.server.reply("/auth", authentication, AUTHENTICATED)
    if backtest is not None:
        cli.server.reply("/screen/backtest", backtest)
    out = cli.tmp / "out"

    outcome = approved_run(cli, out)

    assert outcome.exit_code == exit_code, outcome.stderr
    # The log holds DEBUG events, so the scan covers the most detailed level.
    assert '"level": "DEBUG"' in (out / "logs" / "trialfolio.log").read_text()
    assert leaks(cli, outcome) == []


def test_the_wrappers_reauthentication_after_a_401_is_refused(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    cli.server.reply("/screen/backtest", Reply(401, b"Unauthorized"))

    outcome = approved_run(cli, cli.tmp / "out")

    assert outcome.exit_code == 5
    assert cli.server.requests() == ["POST /auth", "POST /screen/backtest"]
    assert leaks(cli, outcome) == []
