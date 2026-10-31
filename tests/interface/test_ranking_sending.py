"""`trialfolio run` sends each case's ranking definition in R04-T01's verified sequence: its
`rank_update`, which writes the definition into `ApiRankingSystem`, then its backtest, ranked by
that system's name, with nothing between them; each attempt writes its files in their order, and
records the definition it sent; and after a failing reply to a `rank_update`, the backtest isn't
sent, and the attempt gets the outcome and the error code sending a definition gives.

Traces to R04-AC03 through the CLI, as release 0.4.0's test pairing gives it for
`tests/interface/test_ranking_sending.py`: a screen run with a definition sends `POST /auth`,
`POST /rank`, then `POST /screen/backtest`, and each case of `ranking-example.yaml` and
`ranking-mixed.yaml`, after the run's one `POST /auth`, its `POST /rank` and then its
`POST /screen/backtest`; each `rank_update`'s body holds the case's definition, byte for byte the
plan's, and each backtest's `screen.ranking` is `"ApiRankingSystem"`. Each attempt writes
`rank-update-request.json`, `updating.json`, `rank-update-response.json`, `request.json`,
`started.json`, `response.json`, and `attempt.json`, in that order, as the storage faults' record
shows, and `rank-update-request.json` holds the body's definition. The records are 1.2.0 for the
screen and 1.3.0 for the experiment, valid against their schemas: the update record names
`rank_update`, `started.json`'s exchanges end with `POST /rank` and its 200, and the attempt
record's `ranking_update` references the request and the response, with its `cost`. After each
failing reply to a `rank_update`, the backtest isn't sent: `failed` and possibly charged, with
`provider.unsupported_capability` after a 400 or a 409, `provider.quota_exceeded` after a 402,
which stops an experiment (D-32), and `provider.auth_failed` after a 401 or a 403, after which the
next case authenticates again; `unknown`, with `provider.outcome_unknown`, after a 503 or a read
timeout; and `failed`, with `provider.response_invalid` and `rank-update-response.raw`, after a
200 that isn't JSON (docs/contracts.md, sending a definition).

`tests/interface/test_ranking_run.py` and `test_ranking_experiment.py`, which R04-T12 wrote, check
already through the CLI that a screen run's three requests come in that order, that its backtest
ranks by `ApiRankingSystem`, and that each of `ranking-example.yaml`'s cases sends its plan's
definition, then its backtest; these tests check the rest of the row. The core's checks of the
same are in `tests/core/test_ranking_screen_run.py` and `test_ranking_execution.py`. The CLI's
entry function runs in the test
process, with the fake Portfolio123 server below `urllib3`, whose end-of-test check reads every
`POST /rank` body (R04-AC09), the fixed clock, storage faults that only record what's published,
and the ranking lock in the test's own directory. Every expected value is written by hand.
"""

import json
from pathlib import Path
from typing import cast

import pytest

from tests.support.cli import Cli
from tests.support.environment import Outcome
from tests.support.experiment_builder import (
    ExperimentBuilder,
    experiment_config,
    returns,
    returns_each,
)
from tests.support.fake_portfolio123 import AUTH, AUTHENTICATED, BACKTEST, RANK, Received, Reply
from tests.support.paths import RANKING_DEFINITIONS, RESPONSES, SCREEN_CONFIGS
from tests.support.saved_records import attempt_directories
from tests.support.storage_faults import FaultyStores
from trialfolio.contracts.attempt import (
    AttemptRecordV1_2,
    AttemptRecordV1_3,
    Exchange,
    StartRecordV1_2,
    StartRecordV1_3,
)
from trialfolio.contracts.experiment_plan import PlanV1_3
from trialfolio.contracts.plan import PlanV1_2

DEFINITION = SCREEN_CONFIGS / "definition.yaml"
VALUE_MOMENTUM = RANKING_DEFINITIONS / "value-momentum.xml"
EXAMPLE = experiment_config("ranking-example.yaml")
MIXED = experiment_config("ranking-mixed.yaml")
SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"

RANK_UPDATED = Reply(200, (RESPONSES / "rank-update.json").read_bytes())
"""`rank-update.json`'s 200, whose `cost` is 1."""

ATTEMPT_FILES = [
    "rank-update-request.json",
    "updating.json",
    "rank-update-response.json",
    "request.json",
    "started.json",
    "response.json",
    "attempt.json",
]
"""The files of an attempt that sends a definition, in the order it writes them."""

FAILURES = [
    pytest.param(
        Reply(400, b"Invalid ranking system"), "failed", "provider.unsupported_capability", id="400"
    ),
    pytest.param(Reply(409, b"Conflict"), "failed", "provider.unsupported_capability", id="409"),
    pytest.param(Reply(402, b""), "failed", "provider.quota_exceeded", id="402"),
    pytest.param(Reply(401, b""), "failed", "provider.auth_failed", id="401"),
    pytest.param(Reply(403, b""), "failed", "provider.auth_failed", id="403"),
    pytest.param(Reply(503, b""), "unknown", "provider.outcome_unknown", id="503"),
    pytest.param(
        Reply(200, b"<html>not JSON</html>"),
        "failed",
        "provider.response_invalid",
        id="200 not JSON",
    ),
]
"""Each failing reply to a `rank_update`, with the attempt's outcome and error code."""


def exchange(request: str, status: int) -> Exchange:
    return Exchange(request=request, result="response", status=status, note=None)


def serve_screen(cli: Cli, rank: Reply = RANK_UPDATED) -> None:
    """Scripts a screen run with a definition: authentication, its `POST /rank`, then its
    backtest's `complete.json`, whose `cost` is 5."""
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/rank", rank, method="POST")
    cli.server.reply("/screen/backtest", returns())


def run_screen(
    cli: Cli, out: Path, faults: FaultyStores | None = None, timeout: int | None = None
) -> Outcome:
    """Runs `definition.yaml` into `out`, approved with its plan's hash, with `--json`."""
    if faults is None:
        return cli.run_approved(DEFINITION, out, "--json", timeout=timeout)
    return cli.run_approved(DEFINITION, out, "--json", store_factory=faults, timeout=timeout)


def received(cli: Cli, request: str) -> list[Received]:
    return [r for r in cli.server.received if r.request == request]


def nodes(rank: Received) -> str:
    return cast("str", json.loads(rank.body)["nodes"])


def attempt_of(out: Path, case_id: str) -> Path:
    (attempt,) = attempt_directories(out, case_id)
    return attempt


def written(faults: FaultyStores, out: Path, attempt: Path) -> list[str]:
    """The names of the files the store published in `attempt`'s directory, in order."""
    directory = attempt.relative_to(out).as_posix() + "/"
    return [path.removeprefix(directory) for path in faults.published if path.startswith(directory)]


def keys_of_schema(content: bytes, schema: str) -> None:
    """A record holds exactly the fields its committed schema gives, in its order, every one it
    requires among them; its model has checked their values."""
    loaded: dict[str, object] = json.loads(SCHEMAS.joinpath(f"{schema}.schema.json").read_bytes())
    fields = list(json.loads(content))
    assert fields == list(cast("dict[str, object]", loaded["properties"])), schema
    assert set(cast("list[str]", loaded["required"])) <= set(fields), schema


# A screen run


def test_a_screen_runs_rank_update_body_holds_the_plans_definition_byte_for_byte(
    cli: Cli,
) -> None:
    cli.ready()
    serve_screen(cli)
    out = cli.tmp / "run"

    outcome = run_screen(cli, out)

    assert outcome.exit_code == 0, outcome.stderr
    assert cli.server.requests() == [AUTH, RANK, BACKTEST]
    plan = PlanV1_2.model_validate_json((out / "plan.json").read_bytes())
    (case,) = plan.cases
    (rank,) = received(cli, RANK)
    assert nodes(rank) == case.requests[0].params.nodes
    assert nodes(rank).encode("utf-8") == VALUE_MOMENTUM.read_bytes()
    assert json.loads(rank.body) == {
        "type": "stock",
        "nodes": VALUE_MOMENTUM.read_text(encoding="utf-8"),
        "rankingMethod": 2,
        "currency": "USD",
    }


def test_a_screen_runs_attempt_writes_its_files_in_order(cli: Cli, faults: FaultyStores) -> None:
    cli.ready()
    serve_screen(cli)
    out = cli.tmp / "run"

    outcome = run_screen(cli, out, faults)

    assert outcome.exit_code == 0, outcome.stderr
    plan = PlanV1_2.model_validate_json((out / "plan.json").read_bytes())
    attempt = attempt_of(out, plan.cases[0].case_id)
    assert written(faults, out, attempt) == ATTEMPT_FILES
    # The update record comes after the rank_update's request, and the backtest's records after
    # its saved response, so each start record is the last write before its send.
    (rank,) = received(cli, RANK)
    request = (attempt / "rank-update-request.json").read_bytes()
    assert json.loads(request) == json.loads(rank.body)
    assert json.loads(request)["nodes"] == nodes(rank)


def test_a_screen_runs_records_are_1_2_0_and_name_its_rank_update(cli: Cli) -> None:
    cli.ready()
    serve_screen(cli)
    out = cli.tmp / "run"

    outcome = run_screen(cli, out)

    assert outcome.exit_code == 0, outcome.stderr
    plan = PlanV1_2.model_validate_json((out / "plan.json").read_bytes())
    attempt = attempt_of(out, plan.cases[0].case_id)
    updating = (attempt / "updating.json").read_bytes()
    started = (attempt / "started.json").read_bytes()
    finished = (attempt / "attempt.json").read_bytes()
    keys_of_schema(updating, "start-record-1.2.0")
    keys_of_schema(started, "start-record-1.2.0")
    keys_of_schema(finished, "attempt-record-1.2.0")
    update = StartRecordV1_2.model_validate_json(updating)
    start = StartRecordV1_2.model_validate_json(started)
    record = AttemptRecordV1_2.model_validate_json(finished)
    assert (update.schema_version, update.operation) == ("1.2.0", "rank_update")
    assert update.exchanges == (exchange(AUTH, 200),)
    assert (start.operation, start.exchanges) == (
        "screen_backtest",
        (exchange(AUTH, 200), exchange(RANK, 200)),
    )
    assert (record.schema_version, record.outcome) == ("1.2.0", "succeeded")
    assert record.exchanges == (exchange(AUTH, 200), exchange(RANK, 200), exchange(BACKTEST, 200))
    ranking = record.ranking_update
    assert ranking is not None
    assert ranking.request is not None and ranking.response is not None
    directory = attempt.relative_to(out).as_posix()
    assert ranking.request.path == f"{directory}/rank-update-request.json"
    assert ranking.response.path == f"{directory}/rank-update-response.json"
    assert ranking.response.form == "decoded"
    assert ranking.provider_metadata.cost == 1
    assert record.provider_metadata.cost == 5


@pytest.mark.parametrize(("reply", "outcome", "code"), FAILURES)
def test_after_a_failing_reply_to_a_screen_runs_rank_update_its_backtest_isnt_sent(
    cli: Cli, reply: Reply, outcome: str, code: str
) -> None:
    cli.ready()
    serve_screen(cli, rank=reply)
    out = cli.tmp / "run"

    ran = run_screen(cli, out)

    assert ran.exit_code == 5, ran.stderr
    assert ran.error_code == code
    assert cli.server.requests() == [AUTH, RANK]
    plan = PlanV1_2.model_validate_json((out / "plan.json").read_bytes())
    attempt = attempt_of(out, plan.cases[0].case_id)
    record = AttemptRecordV1_2.model_validate_json((attempt / "attempt.json").read_bytes())
    assert (record.outcome, record.possibly_charged) == (outcome, True)
    assert record.error is not None and record.error.code == code
    assert not (attempt / "request.json").exists()
    assert not (attempt / "started.json").exists()
    assert (attempt / "rank-update-response.raw").exists() == (code == "provider.response_invalid")


def test_a_screen_runs_rank_update_that_times_out_is_unknown_and_sends_no_backtest(
    cli: Cli,
) -> None:
    cli.ready()
    serve_screen(cli, rank=Reply(200, b"{}", delay=3))
    out = cli.tmp / "run"

    ran = run_screen(cli, out, timeout=1)

    assert ran.exit_code == 5, ran.stderr
    assert ran.error_code == "provider.outcome_unknown"
    assert cli.server.requests() == [AUTH, RANK]
    plan = PlanV1_2.model_validate_json((out / "plan.json").read_bytes())
    attempt = attempt_of(out, plan.cases[0].case_id)
    record = AttemptRecordV1_2.model_validate_json((attempt / "attempt.json").read_bytes())
    assert (record.outcome, record.possibly_charged) == ("unknown", True)
    assert record.exchanges[-1] == Exchange(
        request=RANK, result="interrupted", status=None, note=None
    )


# An experiment


def four(reply: Reply) -> tuple[Reply, ...]:
    return (reply,) * 4


def read_plan(out: Path) -> PlanV1_3:
    return PlanV1_3.model_validate_json((out / "plans" / "1" / "plan.json").read_bytes())


@pytest.mark.parametrize("config", [EXAMPLE, MIXED], ids=["ranking-example", "ranking-mixed"])
def test_each_case_sends_its_rank_update_then_its_backtest_after_one_authentication(
    cli: Cli, experiments: ExperimentBuilder[Outcome], config: Path
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = experiments.run(config, out, ranks=four(RANK_UPDATED), sends=returns_each(4))

    assert outcome.exit_code == 0, outcome.stderr
    assert cli.server.requests() == [
        AUTH,
        RANK,
        BACKTEST,
        RANK,
        BACKTEST,
        RANK,
        BACKTEST,
        RANK,
        BACKTEST,
    ]
    plan = read_plan(out)
    ranks = received(cli, RANK)
    for case, rank in zip(plan.cases, ranks, strict=True):
        assert nodes(rank) == case.requests[0].params.nodes, case.case_key
    for backtest in received(cli, BACKTEST):
        assert json.loads(backtest.body)["screen"]["ranking"] == "ApiRankingSystem"


def test_every_case_but_a_ranking_variant_sends_the_baselines_definition(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    """`ranking-mixed.yaml`'s `holdings-50` and the default `rebalance-weeks-1` change another
    setting, so they send the baseline's definition, as the baseline does: three of its four
    cases."""
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = experiments.run(MIXED, out, ranks=four(RANK_UPDATED), sends=returns_each(4))

    assert outcome.exit_code == 0, outcome.stderr
    plan = read_plan(out)
    assert [case.case_key for case in plan.cases] == [
        "baseline",
        "value-heavy",
        "holdings-50",
        "rebalance-weeks-1",
    ]
    sent = [nodes(rank).encode("utf-8") for rank in received(cli, RANK)]
    baseline = VALUE_MOMENTUM.read_bytes()
    assert [definition == baseline for definition in sent] == [True, False, True, True]
    assert sent[1] == (RANKING_DEFINITIONS / "value-heavy.xml").read_bytes()


def test_each_attempt_of_an_experiment_writes_its_files_in_order(
    cli: Cli, experiments: ExperimentBuilder[Outcome], faults: FaultyStores
) -> None:
    """The session's first attempt authenticates, so it writes `authenticating.json` first; the
    others send with its token (experiment attempts)."""
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = experiments.run(
        EXAMPLE, out, ranks=four(RANK_UPDATED), sends=returns_each(4), store_factory=faults
    )

    assert outcome.exit_code == 0, outcome.stderr
    plan = read_plan(out)
    for place, (case, rank) in enumerate(zip(plan.cases, received(cli, RANK), strict=True)):
        attempt = attempt_of(out, case.case_id)
        first = ["authenticating.json"] if place == 0 else []
        assert written(faults, out, attempt) == first + ATTEMPT_FILES, case.case_key
        request = json.loads((attempt / "rank-update-request.json").read_bytes())
        assert request["nodes"] == nodes(rank)


def test_an_experiments_records_are_1_3_0_and_name_each_rank_update(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = experiments.run(EXAMPLE, out, ranks=four(RANK_UPDATED), sends=returns_each(4))

    assert outcome.exit_code == 0, outcome.stderr
    for place, case in enumerate(read_plan(out).cases):
        attempt = attempt_of(out, case.case_id)
        updating = (attempt / "updating.json").read_bytes()
        started = (attempt / "started.json").read_bytes()
        finished = (attempt / "attempt.json").read_bytes()
        keys_of_schema(updating, "start-record-1.3.0")
        keys_of_schema(started, "start-record-1.3.0")
        keys_of_schema(finished, "attempt-record-1.3.0")
        update = StartRecordV1_3.model_validate_json(updating)
        start = StartRecordV1_3.model_validate_json(started)
        record = AttemptRecordV1_3.model_validate_json(finished)
        # Only the session's first attempt authenticates.
        authentication = (exchange(AUTH, 200),) if place == 0 else ()
        assert (update.schema_version, update.operation) == ("1.3.0", "rank_update")
        assert update.exchanges == authentication
        assert (start.operation, start.exchanges) == (
            "screen_backtest",
            (*authentication, exchange(RANK, 200)),
        )
        assert (record.schema_version, record.outcome) == ("1.3.0", "succeeded")
        assert record.exchanges == (*authentication, exchange(RANK, 200), exchange(BACKTEST, 200))
        directory = attempt.relative_to(out).as_posix()
        ranking = record.ranking_update
        assert ranking.request is not None and ranking.response is not None
        assert ranking.request.path == f"{directory}/rank-update-request.json"
        assert ranking.response.path == f"{directory}/rank-update-response.json"
        assert ranking.response.form == "decoded"
        assert ranking.provider_metadata.cost == 1


@pytest.mark.parametrize(
    ("reply", "outcome", "code"),
    [failure for failure in FAILURES if failure.id not in ("401", "402", "403")],
)
def test_after_a_failing_reply_to_a_cases_rank_update_the_next_case_is_sent(
    cli: Cli, experiments: ExperimentBuilder[Outcome], reply: Reply, outcome: str, code: str
) -> None:
    """The baseline's backtest isn't sent; its attempt gets the outcome and the error code, and
    the three cases after it are sent with the session's token."""
    cli.ready()
    out = cli.tmp / "experiment"

    ran = experiments.run(EXAMPLE, out, ranks=(reply, *(RANK_UPDATED,) * 3), sends=returns_each(3))

    assert ran.exit_code == 6, ran.stderr
    assert ran.error_code == "execution.partial"
    assert cli.server.requests() == [AUTH, RANK, RANK, BACKTEST, RANK, BACKTEST, RANK, BACKTEST]
    baseline = attempt_of(out, read_plan(out).cases[0].case_id)
    record = AttemptRecordV1_3.model_validate_json((baseline / "attempt.json").read_bytes())
    assert (record.outcome, record.possibly_charged) == (outcome, True)
    assert record.error is not None and record.error.code == code
    assert not (baseline / "started.json").exists()
    assert (baseline / "rank-update-response.raw").exists() == (code == "provider.response_invalid")


def test_a_rank_updates_402_stops_the_experiment(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    """Every later case would be refused the same way, so the run starts none (D-32)."""
    cli.ready()
    out = cli.tmp / "experiment"

    ran = experiments.run(EXAMPLE, out, ranks=(Reply(402, b""),))

    assert ran.exit_code == 6, ran.stderr
    assert ran.error_code == "execution.partial"
    assert "provider.quota_exceeded" in ran.error["message"]
    assert cli.server.requests() == [AUTH, RANK]
    plan = read_plan(out)
    baseline = attempt_of(out, plan.cases[0].case_id)
    record = AttemptRecordV1_3.model_validate_json((baseline / "attempt.json").read_bytes())
    assert (record.outcome, record.possibly_charged) == ("failed", True)
    assert record.error is not None and record.error.code == "provider.quota_exceeded"
    for case in plan.cases[1:]:
        assert not (out / "cases" / case.case_id).exists(), case.case_key


@pytest.mark.parametrize("status", [401, 403])
def test_after_a_401_or_a_403_to_a_rank_update_the_next_case_authenticates_again(
    cli: Cli, experiments: ExperimentBuilder[Outcome], status: int
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    ran = experiments.run(
        EXAMPLE,
        out,
        ranks=(Reply(status, b""), *(RANK_UPDATED,) * 3),
        sends=returns_each(3),
        authenticates=(AUTHENTICATED, AUTHENTICATED),
    )

    assert ran.exit_code == 6, ran.stderr
    assert cli.server.requests() == [
        AUTH,
        RANK,
        AUTH,
        RANK,
        BACKTEST,
        RANK,
        BACKTEST,
        RANK,
        BACKTEST,
    ]
    plan = read_plan(out)
    baseline = attempt_of(out, plan.cases[0].case_id)
    record = AttemptRecordV1_3.model_validate_json((baseline / "attempt.json").read_bytes())
    assert (record.outcome, record.possibly_charged) == ("failed", True)
    assert record.error is not None and record.error.code == "provider.auth_failed"
    # The next case's attempt made the session's second authentication call.
    second = attempt_of(out, plan.cases[1].case_id)
    assert (second / "authenticating.json").exists()
