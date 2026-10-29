"""The fake Portfolio123 server's check of every `POST /rank` body and every path can fail: a test
of the double itself, as `tests/test_network_guard.py` is of the guard.

Traces to R04-AC09 and release 0.4.0's test doubles: the server checks, at the end of every test
that uses it, that no `rank_update` carries an `id`, or any parameter but `type`, `nodes`,
`rankingMethod`, and `currency`, in that order, with a method of 2 or 4, and that no request goes
to a path Trial Folio doesn't send. Each break is sent to the server directly, in a test of its
own, as its exact text, so a check that compared parsed objects, ignoring the keys' order, would
let one through; and a nested run shows that a test using the `server` fixture, which
`tests/conftest.py` gives every directory, fails at its end, so a check that weren't run there
would let them all through.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import requests

from tests.support.fake_portfolio123 import AUTHENTICATED, CREDENTIALS, FakePortfolio123, Reply
from tests.support.paths import ROOT
from trialfolio.provider import P123ScreenBacktestClient

GOOD: dict[str, object] = {
    "type": "stock",
    "nodes": '<RankingSystem RankType="Higher">\n</RankingSystem>',
    "rankingMethod": 2,
    "currency": "USD",
}
"""A body as `rank_update` sends it."""

BREAKS: dict[str, tuple[str, bytes]] = {
    "an id": (
        "/rank",
        json.dumps({"id": 1234, **GOOD}).encode(),
    ),
    "another key": (
        "/rank",
        json.dumps({**GOOD, "name": "ApiRankingSystem"}).encode(),
    ),
    "its keys in another order": (
        "/rank",
        json.dumps(
            {key: GOOD[key] for key in ("nodes", "type", "rankingMethod", "currency")}
        ).encode(),
    ),
    "ranking method 1": (
        "/rank",
        json.dumps({**GOOD, "rankingMethod": 1}).encode(),
    ),
    "a type other than stock": (
        "/rank",
        json.dumps({**GOOD, "type": "etf"}).encode(),
    ),
    "a currency other than USD": (
        "/rank",
        json.dumps({**GOOD, "currency": "EUR"}).encode(),
    ),
    "a request to /rank/create": (
        "/rank/create",
        json.dumps(GOOD).encode(),
    ),
    "a request to /rank/<id>/touch": (
        "/rank/1234/touch",
        b"",
    ),
}


@pytest.mark.parametrize("name", BREAKS)
def test_the_end_of_test_check_fails_on_each_break(name: str) -> None:
    path, body = BREAKS[name]
    server = FakePortfolio123()
    try:
        requests.post(f"{server.endpoint}{path}", data=body, timeout=5)
    finally:
        with pytest.raises(AssertionError, match="Trial Folio doesn't send"):
            server.close()


def test_a_body_as_rank_update_sends_it_passes() -> None:
    server = FakePortfolio123()
    try:
        server.reply("/auth", AUTHENTICATED)
        server.reply("/rank", Reply(200, b"{}"), method="POST")
        with P123ScreenBacktestClient(CREDENTIALS, endpoint=server.endpoint) as client:
            client.authenticate()
            client.rank_update(GOOD)
    finally:
        server.close()

    assert server.received[-1].body == json.dumps(GOOD).encode()
    assert server.problems() == []


def test_get_rank_with_a_query_is_a_request_trial_folio_sends() -> None:
    # A snapshot's `rank_get` names the system in its query, which the path is matched without.
    server = FakePortfolio123()
    server.reply("/rank", Reply(200, b"{}"), method="GET")
    try:
        answered = requests.get(f"{server.endpoint}/rank?name=x", timeout=5)
    finally:
        server.close()

    assert answered.status_code == 200
    assert server.problems() == []


PROBE = """\
import requests

from tests.conftest import server  # noqa: F401 - the tests' own fixture


def test_probe(server):
    body = {body!r}
    requests.post(server.endpoint + "/rank", data=body.encode(), timeout=5)
"""


@pytest.mark.parametrize(
    ("body", "fails"),
    [(json.dumps({"id": 1234, **GOOD}), True), (json.dumps(GOOD), False)],
    ids=["a body with an id", "a body as rank_update sends it"],
)
def test_a_test_using_the_server_fails_at_its_end(tmp_path: Path, body: str, fails: bool) -> None:
    probe = tmp_path / "test_probe.py"
    probe.write_text(PROBE.format(body=body), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-c",
            str(ROOT / "pyproject.toml"),
            "--rootdir",
            str(ROOT),
            str(probe),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    output = result.stdout + result.stderr
    if fails:
        assert result.returncode == pytest.ExitCode.TESTS_FAILED, output
        assert "ERROR at teardown of test_probe" in output, output
        assert "Trial Folio doesn't send" in output, output
    else:
        assert result.returncode == pytest.ExitCode.OK, output
