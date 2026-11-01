"""A resume with a ranking definition, in the core: the attempt record a resume writes for an
attempt stopped after its update record, or after `started.json`, and its message for each place an
attempt stops, with the files such an attempt needs; a case's `settings.csv` 1.1.0, which isn't
written without its weight rows' originals; the budget across runs with both of a case's requests; a
repeat that sends both again; the revisions with a definition; and the ranking lock in a resume.

Traces to docs/contracts.md, sending a definition (an attempt stopped after its update record, and
counting the requests), running an experiment (a resumed experiment, step 7's ranking lock, step 8,
checking the records, and the cases that are due), the ranking lock (when it's taken), uncertain
completion, experiment plans and revisions (the budget across runs), plans with a ranking definition
(revisions), repeating a case (the budget), `experiment.json` 1.1.0, the experiment manifest's
version 1.1.0, and weight rows; and, at the core, to R04-AC10 (each request counted, an attempt
started only when both fit, an attempt stopped after its update record recorded on resume as
possibly charged and sent again only by a confirmed repeat, which sends both requests, and no
backtest sent but right after its own case's `rank_update`), R04-AC12 (records with a ranking
definition that are incomplete fail with `input.not_a_run`, and send nothing: an attempt a stopped
run left without its attempt record needs the files written before it), and R04-AC05 (a resume with
cases due meets the ranking lock before its session record). The real client, `requests`, and
`urllib3` run over the fake server, whose end-of-test check reads every `POST /rank` body
(R04-AC09); storage faults wrap the real store; the clock is fixed; and the ranking lock's file is
in the test's temporary directory.

Each experiment is built during the test, through the core, and stopped where the test needs it: by
a cancellation, by storage faults, or by an interrupt, as a stopped process leaves it, with the
replies `script` gives the fake server, from tests/support/ranking_records.py. TS-T07 separated from
this module the records check of an experiment with a definition, in
tests/core/test_ranking_records.py, and of a run with one, which `trialfolio report` reads, in
tests/core/test_ranking_saved_runs.py (docs/test-refactoring.md, modules to separate).
"""

import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import pytest

from tests.support.broken_runs import edit_record
from tests.support.experiment_lab import RELEASE_0_4_0, Lab
from tests.support.fake_portfolio123 import (
    AUTH,
    BACKTEST,
    RANK,
    FakePortfolio123,
    Reply,
    exchange,
    response,
)
from tests.support.paths import EXPERIMENT_CONFIGS, RANKING_DEFINITIONS
from tests.support.plans import case_ids
from tests.support.ranking_records import EXAMPLE, first_case_faults, script
from tests.support.storage_faults import Fault, StorageFaults
from trialfolio.contracts.attempt import AttemptRecordV1_3
from trialfolio.contracts.experiment_manifest import ExperimentManifest, ExperimentManifestV1_1
from trialfolio.contracts.experiment_plan import PlanV1_1, PlanV1_3
from trialfolio.contracts.experiment_record import ExperimentRecord, ExperimentRecordV1_1
from trialfolio.experiment_repeats import Repeat
from trialfolio.normalization import write_case_settings
from trialfolio.ranking_lock import RankingLock
from trialfolio.storage import LocalArtifactStore, StoredFile
from trialfolio.tables import read_settings_csv_v1_1

REVISED = "A revised ranking definition."

type Json = dict[str, Any]


@pytest.fixture
def lab(tmp_path: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch) -> Lab:
    return Lab(tmp_path, server, monkeypatch, reader=RELEASE_0_4_0, catch=True)


def each_backtest_follows_its_cases_rank_update(
    server: FakePortfolio123, *plans: PlanV1_3, since: int = 0
) -> None:
    """Every `POST /screen/backtest` the server received, from its request `since` on, came right
    after a `POST /rank`, and the two are one case's: its `rank_update`'s params, and its
    backtest's (R04-AC10)."""
    sent = {
        (
            json.dumps(case.requests[0].params.model_dump(mode="json"), sort_keys=True),
            json.dumps(case.requests[1].params.model_dump(mode="json"), sort_keys=True),
        )
        for plan in plans
        for case in plan.cases
    }
    received = server.received
    for place, request in enumerate(received):
        if place < since or request.path != "/screen/backtest":
            continue
        previous = received[place - 1]
        assert place > 0 and previous.path == "/rank", "a backtest was sent without its rank_update"
        pair = (
            json.dumps(json.loads(previous.body), sort_keys=True),
            json.dumps(json.loads(request.body), sort_keys=True),
        )
        assert pair in sent, "a backtest followed another case's rank_update"


# An attempt a stopped run left without its attempt record


def test_an_attempt_stopped_after_its_update_record_is_recorded_unknown_and_not_sent_again(
    lab: Lab,
) -> None:
    # The rank_update was sent, and its response wasn't saved: the process stopped after the
    # update record, its last write before the send, as a killed process leaves it.
    script(
        lab.server,
        auths=2,
        ranks=[response("rank-update.json") for _ in range(4)],
        backtests=[response("complete.json")] * 3,
    )
    first = lab.new(
        arm=first_case_faults(
            ("rank-update-response.json", "full disk"), ("attempt.json", "unexpected")
        )
    )
    assert first.received == (AUTH, RANK)
    baseline = EXAMPLE.cases[0].case_id
    directory = lab.attempt(baseline)
    assert sorted(p.name for p in directory.iterdir()) == [
        "authenticating.json",
        "rank-update-request.json",
        "updating.json",
    ]
    saved = lab.read()
    (stopped,) = saved.attempts_of(baseline)
    assert (stopped.outcome, stopped.possibly_charged, stopped.provider_requests) == (
        "unknown",
        True,
        1,
    )
    assert saved.cases(EXAMPLE)[0].state == "awaiting_repeat"

    resumed = lab.resume()

    # It isn't sent again, and every other case is, each rank_update right before its backtest.
    assert resumed.received == (AUTH, *(RANK, BACKTEST) * 3)
    each_backtest_follows_its_cases_rank_update(lab.server, EXAMPLE)
    (record,) = lab.attempts(baseline, AttemptRecordV1_3)
    assert (record.outcome, record.possibly_charged, record.session) == ("unknown", True, 1)
    assert record.error is not None and record.error.code == "command.interrupted"
    assert record.exchanges == (exchange(AUTH, 200), exchange(RANK, None, "interrupted"))
    assert record.ranking_update.request is not None
    assert record.ranking_update.request.path.endswith("/rank-update-request.json")
    assert (record.ranking_update.response, record.request, record.response) == (None, None, None)
    assert "The screen backtest request wasn't sent" in record.error.message
    manifest = lab.manifest(2, ExperimentManifestV1_1)
    assert manifest.counts.provider_requests == 1 + 2 * 3
    assert (manifest.counts.cases.unknown, manifest.counts.cases.succeeded) == (1, 3)
    error = resumed.refused("execution.partial")
    assert "never sent again automatically" in error.message


@pytest.mark.parametrize(
    ("faults", "code"),
    [
        ((("request.json", "unexpected"), ("attempt.json", "unexpected")), "command.interrupted"),
        ((("request.json", "interrupt"), ("attempt.json", "full disk")), "command.interrupted"),
    ],
    ids=["an unexpected failure", "an interrupt, and a full disk at its attempt record"],
)
def test_an_attempt_stopped_after_its_rank_updates_response_is_recorded_failed(
    lab: Lab, faults: tuple[tuple[str, Fault], ...], code: str
) -> None:
    # The rank_update's 200 was saved, and the backtest's request.json wasn't written, so the
    # backtest wasn't sent; and the attempt's record wasn't either.
    script(
        lab.server,
        auths=2,
        ranks=[response("rank-update.json") for _ in range(4)],
        backtests=[response("complete.json")] * 3,
    )
    lab.new(arm=first_case_faults(*faults))
    baseline = EXAMPLE.cases[0].case_id
    assert not (lab.attempt(baseline) / "attempt.json").exists()
    # Before the resume records it, it reads as the resume will record it.
    (stopped,) = lab.read().attempts_of(baseline)
    assert (
        stopped.outcome,
        stopped.possibly_charged,
        stopped.provider_requests,
        stopped.error_code,
    ) == ("failed", True, 1, code)

    resumed = lab.resume()

    assert resumed.received == (AUTH, *(RANK, BACKTEST) * 3)
    (record,) = lab.attempts(baseline, AttemptRecordV1_3)
    assert (record.outcome, record.possibly_charged) == ("failed", True)
    assert record.error is not None and record.error.code == code
    assert record.exchanges == (
        exchange(AUTH, 200),
        exchange(RANK, 200, note="completed_from_saved_response"),
    )
    updated = record.ranking_update.response
    assert updated is not None and updated.form == "decoded"
    assert updated.path.endswith("/rank-update-response.json")
    assert record.ranking_update.provider_metadata.cost == 1
    assert (record.request, record.response) == (None, None)
    assert lab.manifest(2, ExperimentManifestV1_1).counts.provider_requests == 1 + 2 * 3
    assert lab.read().cases(EXAMPLE)[0].state == "awaiting_repeat"


def test_an_interrupt_at_the_backtests_request_leaves_its_case_awaiting_a_repeat(
    lab: Lab,
) -> None:
    # The attempt records itself, failed and possibly charged, so a resume doesn't send it.
    script(
        lab.server,
        auths=2,
        ranks=[response("rank-update.json") for _ in range(4)],
        backtests=[response("complete.json")] * 3,
    )
    first = lab.new(arm=first_case_faults(("request.json", "interrupt")))
    assert first.refused("command.interrupted")
    baseline = EXAMPLE.cases[0].case_id
    (record,) = lab.attempts(baseline, AttemptRecordV1_3)
    assert (record.outcome, record.possibly_charged) == ("failed", True)

    resumed = lab.resume()

    assert resumed.received == (AUTH, *(RANK, BACKTEST) * 3)
    assert lab.attempts(baseline, AttemptRecordV1_3) == [record]


def test_an_undecoded_rank_update_response_is_recorded_as_invalid(lab: Lab) -> None:
    script(
        lab.server,
        auths=2,
        ranks=[
            Reply(200, b"<html>not JSON</html>"),
            *(response("rank-update.json") for _ in range(3)),
        ],
        backtests=[response("complete.json")] * 3,
    )
    lab.new(arm=first_case_faults(("attempt.json", "unexpected")))
    baseline = EXAMPLE.cases[0].case_id
    assert (lab.attempt(baseline) / "rank-update-response.raw").exists()
    (stopped,) = lab.read().attempts_of(baseline)
    assert (stopped.outcome, stopped.error_code) == ("failed", "provider.response_invalid")

    lab.resume()

    (record,) = lab.attempts(baseline, AttemptRecordV1_3)
    assert (record.outcome, record.possibly_charged) == ("failed", True)
    assert record.error is not None and record.error.code == "provider.response_invalid"
    updated = record.ranking_update.response
    assert updated is not None and updated.form == "undecoded"
    assert record.ranking_update.provider_metadata.cost is None


@pytest.mark.parametrize("saved", [True, False], ids=["with its response", "without one"])
def test_a_running_attempt_is_recorded_from_its_start_record(lab: Lab, saved: bool) -> None:
    # `started.json` was written, so both requests count; with its saved response, the attempt
    # succeeded, and without one, its outcome is unknown, and its case awaits a repeat.
    faults: tuple[tuple[str, Fault], ...] = (
        (("attempt.json", "unexpected"),)
        if saved
        else (
            ("response.json", "full disk"),
            ("attempt.json", "unexpected"),
        )
    )
    script(
        lab.server,
        auths=2,
        ranks=[response("rank-update.json") for _ in range(4)],
        backtests=[response("complete.json")] * 4,
    )
    lab.new(arm=first_case_faults(*faults))
    baseline = EXAMPLE.cases[0].case_id
    stopped = lab.read().attempts_of(baseline)[0]
    assert (stopped.outcome, stopped.provider_requests) == (
        "succeeded" if saved else "unknown",
        2,
    )

    resumed = lab.resume()

    assert resumed.received == (AUTH, *(RANK, BACKTEST) * 3)
    (record,) = lab.attempts(baseline, AttemptRecordV1_3)
    assert record.request is not None and record.request.path.endswith("/request.json")
    assert record.ranking_update.response is not None
    if saved:
        assert (record.outcome, record.error) == ("succeeded", None)
        assert record.exchanges[-1] == exchange(BACKTEST, 200, note="completed_from_saved_response")
        assert record.provider_metadata.cost == 5
        # The tables a stopped run didn't write: settings.csv 1.1.0, with each weight row.
        rows = read_settings_csv_v1_1(
            (lab.out / f"cases/{baseline}/normalized/settings.csv").read_bytes(), "settings"
        )
        assert len([row for row in rows if row.node is not None]) == 9
    else:
        assert record.outcome == "unknown"
        assert record.exchanges == (exchange(AUTH, 200), exchange(RANK, 200))
    assert record.possibly_charged
    assert lab.manifest(2, ExperimentManifestV1_1).counts.provider_requests == 2 + 2 * 3


def test_a_metrics_table_without_its_settings_table_is_completed_with_its_weight_rows(
    lab: Lab,
) -> None:
    script(
        lab.server,
        auths=2,
        ranks=[response("rank-update.json") for _ in range(4)],
        backtests=[response("complete.json")] * 4,
    )
    lab.new(arm=first_case_faults(("settings.csv", "full disk")))
    baseline = EXAMPLE.cases[0].case_id
    assert not (lab.out / f"cases/{baseline}/normalized/settings.csv").exists()

    resumed = lab.resume()

    assert resumed.error is None
    rows = read_settings_csv_v1_1(
        (lab.out / f"cases/{baseline}/normalized/settings.csv").read_bytes(), "settings"
    )
    manifest = lab.manifest(2, ExperimentManifestV1_1)
    listed = {a.path: a for a in manifest.artifacts}
    definition = listed["plans/1/definition.xml"].artifact_id
    weights = [row for row in rows if row.node is not None]
    assert [row.source_artifact for row in weights] == [definition] * 9
    assert listed[f"cases/{baseline}/normalized/settings.csv"].schema_version == "1.1.0"


def test_the_settings_table_of_a_case_ranked_by_a_definition_needs_its_weights_originals(
    tmp_path: Path,
) -> None:
    """Without the originals of its weight rows, a case's `settings.csv` 1.1.0 isn't written: the
    writer refuses before it reads the coverage from `metrics`, which here has none to read
    (docs/test-refactoring.md, the missing tests' item 2)."""
    with LocalArtifactStore(tmp_path / "experiment") as store:
        store.claim("plan.json", b"{}\n")

        with pytest.raises(ValueError, match="needs its weights' originals"):
            write_case_settings(
                store,
                EXAMPLE.cases[0],
                {},
                configuration=StoredFile.of("plans/1/configuration.yaml", b"kind: experiment\n"),
                metrics=(),
            )

        assert [path.name for path in store.root.iterdir()] == ["plan.json"]


def test_an_attempt_with_only_its_authentication_record_is_failed_and_its_case_is_sent(
    lab: Lab,
) -> None:
    script(
        lab.server,
        auths=2,
        ranks=[response("rank-update.json") for _ in range(4)],
        backtests=[response("complete.json")] * 4,
    )
    lab.new(
        arm=first_case_faults(
            ("rank-update-request.json", "unexpected"), ("attempt.json", "unexpected")
        )
    )
    baseline = EXAMPLE.cases[0].case_id
    assert [p.name for p in lab.attempt(baseline).iterdir()] == ["authenticating.json"]

    resumed = lab.resume()

    assert resumed.error is None
    assert resumed.received == (AUTH, *(RANK, BACKTEST) * 4)
    stopped, sent = lab.attempts(baseline, AttemptRecordV1_3)
    assert (stopped.outcome, stopped.possibly_charged) == ("failed", False)
    assert stopped.exchanges == (exchange(AUTH, None, "interrupted"),)
    assert stopped.ranking_update.request is None
    assert sent.outcome == "succeeded" and sent.repeat_of is None


UPDATE: Final = (
    "The rank_update request, which writes the case's ranking definition into ApiRankingSystem,"
)
NEVER: Final = (
    "Trial Folio never retries it automatically: check the account's API credits on"
    " Portfolio123's website before running the command again."
)
UPDATE_ONLY: Final = (
    f"{UPDATE} reached Portfolio123, and may have been charged. The screen backtest request"
    " wasn't sent."
)

STOPPED: Final = {
    "while it authenticated": (
        response("rank-update.json"),
        (("rank-update-request.json", "unexpected"), ("attempt.json", "unexpected")),
        (
            "The run that started the attempt stopped while it authenticated, before its request was"
            " sent. Neither the rank_update request nor the screen backtest request was sent."
        ),
    ),
    "after its start record": (
        response("rank-update.json"),
        (("response.json", "full disk"), ("attempt.json", "unexpected")),
        (
            "The run that started the attempt stopped after its start record was written, before a"
            f" response was saved. {UPDATE} succeeded. The screen backtest request may have been"
            f" charged, and its outcome is unknown: no response was saved. {NEVER}"
        ),
    ),
    "after its update record": (
        response("rank-update.json"),
        (("rank-update-response.json", "full disk"), ("attempt.json", "unexpected")),
        (
            "The run that started the attempt stopped after its update record was written, before"
            f" the rank_update's response was saved. {UPDATE} may have been charged, and its outcome"
            f" is unknown: no response was saved. The screen backtest request wasn't sent. {NEVER}"
        ),
    ),
    "after its rank_update's response was saved": (
        response("rank-update.json"),
        (("request.json", "unexpected"), ("attempt.json", "unexpected")),
        (
            "The run that started the attempt stopped after the rank_update's response was saved,"
            f" before the screen backtest request was sent. {UPDATE_ONLY}"
        ),
    ),
    "after that response was saved undecoded": (
        Reply(200, b"<html>not JSON</html>"),
        (("attempt.json", "unexpected"),),
        (
            "Portfolio123 answered the rank_update request with a 200 whose body couldn't be decoded"
            " as JSON, so it was saved as it came, as rank-update-response.raw. Trial Folio sends the"
            " case's screen backtest only after one whose response it could read, and the run that"
            f" started the attempt stopped. {UPDATE_ONLY}"
        ),
    ),
}
"""Where the first case's attempt stopped, without its attempt record: the reply to its
`rank_update`, the faults that stop it there, and the message of the attempt record the resume
writes for it, in step 8, as written by hand."""


@pytest.mark.parametrize("where", STOPPED)
def test_the_attempt_record_a_resume_writes_says_where_its_run_stopped(
    lab: Lab, where: str
) -> None:
    """Each message of an attempt record that step 8 writes (docs/test-refactoring.md, the missing
    tests' item 5)."""
    first_rank, faults, message = STOPPED[where]
    script(
        lab.server,
        auths=2,
        ranks=[first_rank, *(response("rank-update.json") for _ in range(3))],
        backtests=[response("complete.json")] * 4,
    )
    lab.new(arm=first_case_faults(*faults))
    baseline = EXAMPLE.cases[0].case_id
    assert not (lab.attempt(baseline) / "attempt.json").exists()

    lab.resume()

    stopped = lab.attempts(baseline, AttemptRecordV1_3)[0]
    assert stopped.session == 1
    assert stopped.error is not None
    assert stopped.error.message == message


def _stopped_after_update(lab: Lab) -> Path:
    """An experiment whose first case's attempt stopped after its update record, with the
    rank_update's response saved: the directory of that attempt."""
    script(
        lab.server,
        ranks=[response("rank-update.json") for _ in range(4)],
        backtests=[response("complete.json")] * 3,
    )
    lab.new(arm=first_case_faults(("request.json", "unexpected"), ("attempt.json", "unexpected")))
    return lab.attempt(EXAMPLE.cases[0].case_id)


def _stopped_after_start(lab: Lab) -> Path:
    """The same, stopped after `started.json`, without the backtest's response."""
    script(
        lab.server,
        ranks=[response("rank-update.json") for _ in range(4)],
        backtests=[response("complete.json")] * 4,
    )
    lab.new(arm=first_case_faults(("response.json", "full disk"), ("attempt.json", "unexpected")))
    return lab.attempt(EXAMPLE.cases[0].case_id)


def _stopped_after_update_with_a_token(lab: Lab) -> Path:
    """As `_stopped_after_update`, at the second case's attempt, which sends with the first's
    token, so it has no authentication record: its update record is its only record."""
    script(
        lab.server,
        ranks=[response("rank-update.json") for _ in range(4)],
        backtests=[response("complete.json")] * 3,
    )
    second = EXAMPLE.cases[1].case_id

    def arm(store: StorageFaults) -> None:
        store.fail_before(f"{second}/request.json", RuntimeError())
        store.fail_before(f"{second}/attempt.json", RuntimeError())

    lab.new(arm=arm)
    directory = lab.attempt(second)
    assert sorted(path.name for path in directory.iterdir()) == [
        "rank-update-request.json",
        "rank-update-response.json",
        "updating.json",
    ]
    return directory


def _no_update_record(directory: Path) -> None:
    (directory / "updating.json").unlink()


def _no_rank_request(directory: Path) -> None:
    (directory / "rank-update-request.json").unlink()


def _no_rank_response(directory: Path) -> None:
    (directory / "rank-update-response.json").unlink()


def _two_rank_responses(directory: Path) -> None:
    (directory / "rank-update-response.raw").write_bytes(b"not JSON")


def _rank_response_without_update(directory: Path) -> None:
    (directory / "updating.json").unlink()


@pytest.mark.parametrize(
    ("stop", "change", "problem"),
    [
        (_stopped_after_start, _no_update_record, "without the update record written before it"),
        (_stopped_after_update, _no_rank_request, "not the rank-update-request.json written"),
        (_stopped_after_update, _two_rank_responses, "holds two saved rank_update responses"),
        (_stopped_after_start, _no_rank_response, "not the rank-update-response.json saved"),
        (
            _stopped_after_update,
            _rank_response_without_update,
            "holds the rank_update's response, but not the update record",
        ),
        (
            _stopped_after_update_with_a_token,
            _rank_response_without_update,
            "holds the rank_update's response, but not the update record",
        ),
    ],
    ids=[
        "a start record without its update record",
        "an update record without its request",
        "two saved rank_update responses",
        "a start record without the rank_update's response",
        "a rank_update's response without its update record",
        "a rank_update's response without any record",
    ],
)
def test_an_attempt_without_its_record_needs_the_files_written_before_it(
    lab: Lab, stop: Callable[[Lab], Path], change: Callable[[Path], None], problem: str
) -> None:
    # No manifest lists these files: the run that wrote them stopped before its manifest.
    change(stop(lab))

    ran = lab.resume()

    error = ran.refused("input.not_a_run")
    assert problem in error.message, error.message
    assert ran.received == () and ran.published == ()


# A repeat sends both requests again


def unknown_baseline(lab: Lab) -> uuid.UUID:
    """An experiment whose baseline's rank_update timed out, so its case awaits a repeat, and
    whose other cases succeeded. Returns the attempt a repeat names."""
    script(
        lab.server,
        ranks=[Reply(503, b""), *(response("rank-update.json") for _ in range(3))],
        backtests=[response("complete.json")] * 3,
    )
    lab.new().refused("execution.partial")
    (record,) = lab.attempts(EXAMPLE.cases[0].case_id, AttemptRecordV1_3)
    assert (record.outcome, record.possibly_charged) == ("unknown", True)
    return record.attempt_id


def test_a_confirmed_repeat_sends_the_rank_update_then_the_backtest_once(lab: Lab) -> None:
    budget = (EXPERIMENT_CONFIGS / "revisions/ranking-budget-raised.yaml").name
    attempt_id = unknown_baseline(lab)
    baseline = EXAMPLE.cases[0].case_id
    script(lab.server, ranks=[response("rank-update.json")], backtests=[response("complete.json")])
    # Seven requests are counted, so the repeat's two need the raised budget.
    raised = lab.resume(
        f"revisions/{budget}", reason="A raised budget.", repeats=[Repeat(baseline, attempt_id)]
    )

    assert raised.error is None
    assert raised.received == (AUTH, RANK, BACKTEST)
    each_backtest_follows_its_cases_rank_update(lab.server, EXAMPLE)
    _, repeat = lab.attempts(baseline, AttemptRecordV1_3)
    assert (repeat.outcome, repeat.repeat_of, repeat.session) == ("succeeded", attempt_id, 2)
    assert repeat.exchanges == (exchange(AUTH, 200), exchange(RANK, 200), exchange(BACKTEST, 200))
    assert lab.manifest(2, ExperimentManifestV1_1).counts.attempts.repeats == 1

    # The same command, run again, doesn't repeat it: its confirmation is used.
    again = lab.resume(
        f"revisions/{budget}", reason="A raised budget.", repeats=[Repeat(baseline, attempt_id)]
    )

    assert again.error is None and again.received == ()
    assert again.execution is not None
    assert again.execution.repeats_used == (Repeat(baseline, attempt_id),)


# The budget across runs, with both requests


def test_both_kinds_of_request_are_counted_and_their_costs_summed(lab: Lab) -> None:
    script(
        lab.server,
        ranks=[response("rank-update.json") for _ in range(4)],
        backtests=[response("complete.json")] * 4,
    )
    assert lab.new().error is None

    saved = lab.read()

    assert saved.provider_requests == 8
    assert saved.counts(EXAMPLE).cost == 4 * (1 + 5)
    assert [attempt.provider_requests for attempt in saved.attempts] == [2] * 4


def test_a_repeat_the_budget_cant_cover_waits_for_a_revision_that_raises_it(lab: Lab) -> None:
    # A 503 to the last case's backtest leaves it unknown, with 8 requests counted, so its
    # repeat's two don't fit, and its confirmation stays unused.
    script(
        lab.server,
        ranks=[response("rank-update.json") for _ in range(4)],
        backtests=[*(response("complete.json") for _ in range(3)), Reply(503, b"")],
    )
    lab.new().refused("execution.partial")
    last = EXAMPLE.cases[-1].case_id
    (record,) = lab.attempts(last, AttemptRecordV1_3)
    assert (record.outcome, lab.read().provider_requests) == ("unknown", 8)
    repeat = Repeat(last, record.attempt_id)

    spent = lab.resume(repeats=[repeat])

    error = spent.refused("execution.partial")
    assert spent.received == ()
    assert "budget couldn't cover the next case" in error.message
    assert spent.execution is not None and spent.execution.repeats_used == ()

    script(lab.server, ranks=[response("rank-update.json")], backtests=[response("complete.json")])
    raised = lab.resume(
        "revisions/ranking-budget-raised.yaml", reason="A raised budget.", repeats=[repeat]
    )

    assert raised.error is None
    assert raised.received == (AUTH, RANK, BACKTEST)
    assert lab.read().provider_requests == 10


def one_request_left(lab: Lab) -> Repeat:
    """An experiment whose baseline's rank_update got a 400, which counts one request, and whose
    three other cases succeeded, six more: one of the budget's 8 remains. Returns the repeat that
    names the baseline's attempt."""
    script(
        lab.server,
        auths=2,
        ranks=[
            Reply(400, b"Invalid ranking system"),
            *(response("rank-update.json") for _ in range(3)),
        ],
        backtests=[response("complete.json")] * 3,
    )
    lab.new().refused("execution.partial")
    baseline = EXAMPLE.cases[0].case_id
    (record,) = lab.attempts(baseline, AttemptRecordV1_3)
    assert (record.outcome, record.possibly_charged, lab.read().provider_requests) == (
        "failed",
        True,
        7,
    )
    return Repeat(baseline, record.attempt_id)


def test_a_remaining_budget_of_one_request_never_sends_a_rank_update(lab: Lab) -> None:
    # A case's two requests don't fit the one request left, so the repeat isn't started: its
    # rank_update would be sent, and its backtest not.
    repeat = one_request_left(lab)

    resumed = lab.resume(repeats=[repeat])

    error = resumed.refused("execution.partial")
    assert resumed.received == ()
    assert "budget couldn't cover the next case" in error.message
    assert lab.read().provider_requests == 7
    assert lab.manifest(2, ExperimentManifestV1_1).counts.provider_requests == 7
    assert resumed.execution is not None and resumed.execution.repeats_used == ()


def test_a_resume_whose_budget_covers_no_send_doesnt_take_the_ranking_lock(lab: Lab) -> None:
    # It sends nothing, so it runs while another process holds the lock.
    repeat = one_request_left(lab)

    with RankingLock(lab.lock):
        resumed = lab.resume(repeats=[repeat])

    resumed.refused("execution.partial")
    assert resumed.received == ()
    assert lab.manifest(2, ExperimentManifestV1_1).session == 2


def test_a_changed_definition_retires_the_cases_it_changes_and_keeps_the_others(lab: Lab) -> None:
    script(
        lab.server,
        auths=2,
        ranks=[response("rank-update.json") for _ in range(6)],
        backtests=[response("complete.json")] * 6,
    )
    assert lab.new().error is None
    before = {case.case_key: case.case_id for case in EXAMPLE.cases}

    revised = lab.resume("revisions/ranking-definition-changed.yaml", reason=REVISED)

    assert revised.error is None
    # Its two new cases are sent, each with both requests, beside the 8 counted, within 12.
    assert revised.received == (AUTH, *(RANK, BACKTEST) * 2)
    plan = lab.read().current.plan
    assert isinstance(plan, PlanV1_3)
    each_backtest_follows_its_cases_rank_update(lab.server, EXAMPLE, plan)
    after = {case.case_key: case.case_id for case in plan.cases}
    assert {key: after[key] == before[key] for key in before} == {
        "baseline": False,
        "value-heavy": False,
        "tilt-earnings-yield": True,
        "no-sales-yield": True,
    }
    record = ExperimentRecordV1_1.model_validate_json(
        (lab.out / "plans/2/experiment.json").read_bytes()
    )
    changes = record.plans[-1].changes
    assert changes is not None
    assert [case.case_key for case in changes.cases_retired] == ["baseline", "value-heavy"]
    assert len(lab.attempts(after["tilt-earnings-yield"], AttemptRecordV1_3)) == 1
    revised_definition = (RANKING_DEFINITIONS / "value-momentum-revised.xml").read_bytes()
    assert (lab.out / "plans/2/definition.xml").read_bytes() == revised_definition
    manifest = lab.manifest(2, ExperimentManifestV1_1)
    assert manifest.counts.provider_requests == 12
    assert manifest.counts.retired_cases == 2
    listed = {a.path: a for a in manifest.artifacts}
    assert listed["plans/2/definition.xml"].role == "ranking_definition"


def test_a_changed_ranking_method_retires_every_case(lab: Lab) -> None:
    script(
        lab.server,
        ranks=[response("rank-update.json") for _ in range(4)],
        backtests=[response("complete.json")] * 4,
    )
    assert lab.new().error is None

    revised = lab.resume("revisions/ranking-method-changed.yaml", reason=REVISED)

    # Its budget of 8 is counted already, so none of its new cases is sent.
    revised.refused("execution.partial")
    assert revised.received == ()
    plan = lab.read().current.plan
    assert set(case_ids(plan)).isdisjoint(case_ids(EXAMPLE))
    assert lab.manifest(2, ExperimentManifestV1_1).counts.retired_cases == 4


def test_a_revision_from_a_formula_sends_two_requests_a_case(lab: Lab) -> None:
    # example.yaml's five cases, ranked by a formula, send one request each; its revision ranked
    # by a definition sends two for each of its five new cases, within a budget of 15.
    script(
        lab.server,
        auths=2,
        ranks=[response("rank-update.json") for _ in range(5)],
        backtests=[response("complete.json")] * 10,
    )
    assert lab.new("example.yaml").error is None
    since = len(lab.server.received)

    # A time no entry rebuilt from the records would give, so a kept entry can't pass for one.
    def acquired_earlier(manifest: Json) -> None:
        for artifact in manifest["artifacts"]:
            if artifact["source"] is not None:
                artifact["source"]["acquired_at"] = "2026-10-01T00:00:00Z"

    edit_record(lab.out, "sessions/1/manifest.json", acquired_earlier)
    earlier = ExperimentManifest.model_validate_json(
        (lab.out / "sessions/1/manifest.json").read_bytes()
    )

    revised = lab.resume("revisions/ranking-from-formula.yaml", reason=REVISED)

    assert revised.error is None
    assert revised.received == (AUTH, *(RANK, BACKTEST) * 5)
    saved = lab.read()
    plan = saved.current.plan
    assert isinstance(plan, PlanV1_3)
    each_backtest_follows_its_cases_rank_update(lab.server, plan, since=since)
    assert saved.provider_requests == 5 + 10
    assert isinstance(saved.current.record, ExperimentRecordV1_1)
    assert (lab.out / "plans/2/definition.xml").exists()
    # Session 2's manifest is 1.1.0, and lists the first plan's files, and its attempts', with
    # the versions they have.
    manifest = lab.manifest(2, ExperimentManifestV1_1)
    versions = {a.path: a.schema_version for a in manifest.artifacts}
    assert versions["plans/1/plan.json"] == "1.1.0"
    assert versions["plans/1/experiment.json"] == "1.0.0"
    assert versions["plans/1/configuration.yaml"] == "1.0.0"
    assert versions["plans/2/plan.json"] == "1.3.0"
    assert versions["plans/2/experiment.json"] == "1.1.0"
    assert versions["plans/2/configuration.yaml"] == "1.1.0"
    records = {
        path.rsplit("/", 1)[-1] + ":" + version
        for path, version in versions.items()
        if path.startswith("cases/") and path.endswith("attempt.json") and version
    }
    assert records == {"attempt.json:1.1.0", "attempt.json:1.3.0"}
    settings = {v for p, v in versions.items() if p.endswith("settings.csv")}
    assert settings == {"1.0.0", "1.1.0"}
    # Each file session 1's manifest 1.0.0 lists is listed again as it was, in version 1.1.0's
    # form, its source record included.
    listed = {a.path: a for a in manifest.artifacts}
    for entry in earlier.artifacts:
        if not entry.path.startswith("sessions/"):
            assert listed[entry.path].model_dump(mode="json") == entry.model_dump(mode="json")

    # A revision back to the formula keeps the first plan's cases, which succeeded, and its
    # experiment.json and manifest stay 1.1.0, since an earlier plan has a definition.
    back = lab.resume("example.yaml", reason="The formula again.")

    assert back.error is None and back.received == ()
    third = {a.path: a.schema_version for a in lab.manifest(3, ExperimentManifestV1_1).artifacts}
    assert (third["plans/3/plan.json"], third["plans/3/experiment.json"]) == ("1.1.0", "1.1.0")
    saved = lab.read()
    assert isinstance(saved.current.plan, PlanV1_1)
    assert isinstance(saved.current.record, ExperimentRecordV1_1)
    assert lab.manifest(3, ExperimentManifestV1_1).counts.cases.succeeded == 5
    assert lab.resume("example.yaml").error is None


def test_a_manifest_1_1_0_lists_each_file_no_manifest_listed_with_its_own_version(
    lab: Lab,
) -> None:
    # Session 1, of example.yaml, ended without its manifest, so session 2's, the first, lists
    # every file anew: the first plan's and its attempts' with their versions 1.0.0 and 1.1.0,
    # beside the revision's 1.3.0 and 1.1.0.
    script(
        lab.server,
        auths=2,
        ranks=[response("rank-update.json") for _ in range(5)],
        backtests=[response("complete.json")] * 10,
    )
    first = lab.new("example.yaml", arm=lambda store: store.fail_os("manifest.json"))
    first.refused("storage.write_failed")
    assert not (lab.out / "sessions/1/manifest.json").exists()

    revised = lab.resume("revisions/ranking-from-formula.yaml", reason=REVISED)

    assert revised.error is None
    versions = {a.path: a.schema_version for a in lab.manifest(2, ExperimentManifestV1_1).artifacts}
    assert (
        versions["plans/1/plan.json"],
        versions["plans/1/experiment.json"],
        versions["plans/1/configuration.yaml"],
        versions["plans/2/plan.json"],
        versions["plans/2/experiment.json"],
    ) == ("1.1.0", "1.0.0", "1.0.0", "1.3.0", "1.1.0")
    plans = {saved.plan.plan_hash: saved.number for saved in lab.read().plans}
    for path, version in versions.items():
        if path.endswith(("started.json", "attempt.json")):
            record = json.loads((lab.out / path).read_bytes())
            expected = "1.1.0" if plans[record["plan_hash"]] == 1 else "1.3.0"
            assert version == expected, path
    settings = {v for p, v in versions.items() if p.endswith("settings.csv")}
    assert settings == {"1.0.0", "1.1.0"}


def test_a_resume_of_an_experiment_without_a_definition_keeps_0_3_0s_records(lab: Lab) -> None:
    script(lab.server, auths=2, backtests=[response("complete.json")] * 5)
    assert lab.new("example.yaml", cancel_after=2).refused("execution.partial")

    resumed = lab.resume("example.yaml")

    assert resumed.error is None
    assert (
        ExperimentManifest.model_validate_json(
            (lab.out / "sessions/2/manifest.json").read_bytes()
        ).counts.provider_requests
        == 5
    )
    assert isinstance(lab.read().current.record, ExperimentRecord)


# The ranking lock in a resume (R04-AC05)


def test_a_resume_with_cases_due_meets_the_ranking_lock_before_its_session_record(
    lab: Lab,
) -> None:
    script(
        lab.server,
        auths=2,
        ranks=[response("rank-update.json") for _ in range(4)],
        backtests=[response("complete.json")] * 4,
    )
    lab.new(cancel_after=1).refused("execution.partial")

    with RankingLock(lab.lock):
        held = lab.resume()

    error = held.refused("experiment.locked")
    assert "ApiRankingSystem" in error.message
    assert held.received == () and held.published == ()
    assert not (lab.out / "sessions/2").exists()

    resumed = lab.resume()

    assert resumed.error is None
    assert resumed.received == (AUTH, *(RANK, BACKTEST) * 3)
    assert lab.manifest(2, ExperimentManifestV1_1).session == 2


def test_a_resume_that_sends_nothing_doesnt_take_the_ranking_lock(lab: Lab) -> None:
    script(
        lab.server,
        ranks=[response("rank-update.json") for _ in range(4)],
        backtests=[response("complete.json")] * 4,
    )
    assert lab.new().error is None

    with RankingLock(lab.lock):
        resumed = lab.resume()

    assert resumed.error is None and resumed.received == ()
    assert (
        lab.manifest(2, ExperimentManifestV1_1).counts
        == lab.manifest(1, ExperimentManifestV1_1).counts
    )
