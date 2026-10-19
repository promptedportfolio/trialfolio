"""Trial Folio writes only `ApiRankingSystem`: each command that reaches Portfolio123 with a
ranking definition sends only its authentication, each case's `rank_update`, and each case's
backtest, and every `rank_update` it sends is exactly `{"type": "stock", "nodes": …,
"rankingMethod": …, "currency": "USD"}`, with no `id`, which would write another system.

Traces to R04-AC09 through the CLI, as release 0.4.0's test pairing gives it for
`tests/interface/test_ranking_writes.py`: each command that reaches the server with a definition
runs, a screen run, an experiment, a resume, a repeat, and a revision, and the requests each
sends are only `POST /auth`, `POST /rank`, and `POST /screen/backtest`, with each backtest right
after its own case's `POST /rank`; no request goes to `/rank/create`, `/rank/<id>/touch`, or any
other path. A screen run ranked by a snapshot, which writes the snapshot's definition, is checked
the same way. Beside each test's own check, the fake Portfolio123 server checks every request it
received when the test ends, and fails the test on a break (R04-AC09's double, which
`tests/provider/test_fake_rank_checks.py` shows can fail).

A snapshot's run, which only reads, sends only `POST /auth` and one `GET /rank`: R04-T10 checks
that through the CLI in `tests/interface/test_ranking_snapshot.py`
(`test_an_approved_snapshot_sends_one_rank_get_and_writes_its_directory`), so it isn't run again
here. The client's own check, that its `rank_update` sends its params through `p123api` with no
`id`, is `tests/provider/test_ranking_client.py`'s; and R04-AC07's live check has the owner
confirm that only `ApiRankingSystem` changed in the account. The CLI's entry function runs in the
test process, with the fake server below `urllib3`, the fixed clock, storage faults, and the
ranking lock in the test's own directory. Every expected value is written by hand.
"""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pytest

from tests.interface.conftest import AUTHENTICATED, Cli, FaultyStores, Outcome, plan_hash_for
from tests.support.experiment_builder import (
    UNAVAILABLE,
    ExperimentBuilder,
    experiment_config,
    returns,
)
from tests.support.fake_portfolio123 import Received, Reply
from tests.support.snapshot_builder import SnapshotBuilder, naming

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DEFINITION = FIXTURES / "screen-configs" / "definition.yaml"
EXAMPLE = experiment_config("ranking-example.yaml")
BUDGET_RAISED = experiment_config("revisions/ranking-budget-raised.yaml")
DEFINITION_CHANGED = experiment_config("revisions/ranking-definition-changed.yaml")
RESPONSES = FIXTURES / "responses"

AUTH, RANK, BACKTEST = "POST /auth", "POST /rank", "POST /screen/backtest"
RANK_UPDATED = Reply(200, (RESPONSES / "rank-update.json").read_bytes())

RANK_UPDATE_KEYS = ["type", "nodes", "rankingMethod", "currency"]
"""A `rank_update`'s params, in the order Trial Folio sends them, and no others: no `id`."""


def four(reply: Reply) -> tuple[Reply, ...]:
    return (reply,) * 4


def sent(cli: Cli, before: int) -> tuple[Received, ...]:
    """The requests the server received from the command that ran after `before` of them."""
    return cli.server.received[before:]


def writes_only_api_ranking_system(requests: Sequence[Received]) -> None:
    """Each request is Trial Folio's authentication, a `rank_update`, or a backtest, by its method
    and its whole path, query included; each backtest follows a `rank_update` of its own; and each
    `rank_update`'s body has exactly its four params, in order, writing a stock system in USD
    with one of the two ranking methods, and no `id`."""
    assert requests
    assert {r.method + " " + r.path for r in requests} <= {AUTH, RANK, BACKTEST}
    sends = [r.request for r in requests if r.request != AUTH]
    assert sends[0::2] == [RANK] * (len(sends) // 2)
    assert sends[1::2] == [BACKTEST] * (len(sends) // 2)
    for request in requests:
        if request.request != RANK:
            continue
        body = json.loads(request.body, object_pairs_hook=list)
        assert [key for key, _ in body] == RANK_UPDATE_KEYS
        params = dict(body)
        assert "id" not in params
        assert (params["type"], params["currency"]) == ("stock", "USD")
        assert params["rankingMethod"] in (2, 4)


def summary_cases(outcome: Outcome) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", outcome.summary["cases"])


# A screen run


@pytest.mark.parametrize("ranking", ["definition", "snapshot"])
def test_a_screen_run_sends_only_its_authentication_rank_update_and_backtest(
    cli: Cli, monkeypatch: pytest.MonkeyPatch, ranking: str
) -> None:
    """Ranked by a definition file, or by a snapshot of a system, whose definition it writes into
    `ApiRankingSystem`; the system the snapshot read isn't written (D-36)."""
    config = DEFINITION
    if ranking == "snapshot":
        builder = SnapshotBuilder(monkeypatch, cli.tmp / "builder")
        config = naming(DEFINITION, builder.snapshot(cli.tmp / "snapshot"), cli.tmp / "configs")
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/rank", RANK_UPDATED, method="POST")
    cli.server.reply("/screen/backtest", returns())

    outcome = cli("run", config, "--out", cli.tmp / "run", "--approve", plan_hash_for(config))

    assert outcome.exit_code == 0, outcome.stderr
    assert cli.server.requests() == [AUTH, RANK, BACKTEST]
    writes_only_api_ranking_system(cli.server.received)
    assert cli.server.problems() == []


# An experiment, its resume, a repeat, and a revision


def test_an_experiment_sends_only_its_authentication_and_each_cases_two_requests(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    cli.ready()

    outcome = experiments.run(
        EXAMPLE, cli.tmp / "experiment", ranks=four(RANK_UPDATED), sends=four(returns())
    )

    assert outcome.exit_code == 0, outcome.stderr
    assert len(cli.server.received) == 9
    writes_only_api_ranking_system(cli.server.received)
    assert cli.server.problems() == []


def test_a_resume_sends_only_its_authentication_and_each_due_cases_two_requests(
    cli: Cli, experiments: ExperimentBuilder[Outcome], faults: FaultyStores
) -> None:
    """The first run is interrupted after its authentication, as its first attempt writes its
    update record, before its `rank_update` is sent, so every case is due; the resume sends
    them."""
    cli.ready()
    out = cli.tmp / "experiment"
    faults.fail_before("updating.json", KeyboardInterrupt())
    stopped = experiments.run(EXAMPLE, out, authenticates=(AUTHENTICATED,), store_factory=faults)
    assert stopped.exit_code == 130, stopped.stderr
    assert cli.server.requests() == [AUTH]
    before = len(cli.server.received)

    resumed = experiments.run(EXAMPLE, out, ranks=four(RANK_UPDATED), sends=four(returns()))

    assert resumed.exit_code == 0, resumed.stderr
    assert cast("dict[str, object]", resumed.summary["ids"])["session"] == 2
    assert len(sent(cli, before)) == 9
    writes_only_api_ranking_system(sent(cli, before))
    assert cli.server.problems() == []


def test_a_repeat_sends_only_its_authentication_and_the_cases_two_requests(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    """The baseline's backtest gets a 503, so it awaits a repeat; the repeat, confirmed by its
    attempt's ID, sends its `rank_update` and its backtest again."""
    cli.ready()
    out = cli.tmp / "experiment"
    first = experiments.run(
        BUDGET_RAISED, out, ranks=four(RANK_UPDATED), sends=(UNAVAILABLE, *(returns(),) * 3)
    )
    assert first.exit_code == 6, first.stderr
    (baseline,) = [case for case in summary_cases(first) if case["case_key"] == "baseline"]
    attempt = cast("str", baseline["repeat_attempt_id"])
    before = len(cli.server.received)

    repeated = experiments.run(
        BUDGET_RAISED,
        out,
        "--repeat",
        f"baseline:{attempt}",
        ranks=(RANK_UPDATED,),
        sends=(returns(),),
    )

    assert repeated.exit_code == 0, repeated.stderr
    assert [r.request for r in sent(cli, before)] == [AUTH, RANK, BACKTEST]
    writes_only_api_ranking_system(sent(cli, before))
    assert cli.server.problems() == []


def test_a_revision_sends_only_its_authentication_and_each_new_cases_two_requests(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    """`ranking-definition-changed.yaml` gives the baseline another definition, which adds two
    cases, each of which writes its own definition."""
    cli.ready()
    out = cli.tmp / "experiment"
    first = experiments.run(EXAMPLE, out, ranks=four(RANK_UPDATED), sends=four(returns()))
    assert first.exit_code == 0, first.stderr
    before = len(cli.server.received)

    revised = experiments.run(
        DEFINITION_CHANGED,
        out,
        "--revision-reason",
        "The Value factors weigh 60 and 40.",
        ranks=(RANK_UPDATED, RANK_UPDATED),
        sends=(returns(), returns()),
    )

    assert revised.exit_code == 0, revised.stderr
    assert [r.request for r in sent(cli, before)] == [AUTH, RANK, BACKTEST, RANK, BACKTEST]
    writes_only_api_ranking_system(sent(cli, before))
    assert cli.server.problems() == []
