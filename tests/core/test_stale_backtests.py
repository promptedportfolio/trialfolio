"""A stale backtest, in the core (D-45): in an experiment session, a case's backtest whose
response is the session's previous backtest's, apart from `cost` and `quotaRemaining`, after the
same backtest request and a different definition, is flagged `provider.response_invalid`; a
resume and the records check re-derive the flag from the saved records by the same rule; and a
case whose succeeded attempt's response failed validation, flagged or not, awaits a repeat, which
then makes it complete, with its tables written once, from the repeat's response.

Traces to docs/contracts.md, running an experiment (a stale backtest; a response that fails
validation; the cases that are due; checking the records, its rule of one succeeded attempt that
passed validation; and the resume's step 8), repeating a case (which cases can be repeated), an
experiment's normalized tables, and the experiment manifest (a case's outcome); and to D-45. The
real client, `requests`, and `urllib3` run over the fake server; the pause never waits; storage
faults wrap the real store; the clock is fixed; and every execution takes the ranking lock on a
file in the test's temporary directory.
"""

import logging
import uuid
from collections.abc import Sequence
from pathlib import Path

import pytest

from tests.support.experiment_lab import RELEASE_0_4_0, Lab, Ran
from tests.support.fake_portfolio123 import (
    AUTH,
    AUTHENTICATED,
    BACKTEST,
    RANK,
    FakePortfolio123,
    Reply,
    response,
)
from tests.support.paths import EXPERIMENT_CONFIGS, RESPONSES
from tests.support.plans import planned_experiment, ranked_experiment
from tests.support.storage_faults import Fault
from trialfolio.contracts.attempt import AttemptRecordV1_1, AttemptRecordV1_3
from trialfolio.contracts.experiment_plan import PlanV1_3
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_records import open_experiment
from trialfolio.experiment_repeats import Repeat
from trialfolio.normalization import case_metrics_rows
from trialfolio.storage import LocalArtifactStore
from trialfolio.tables import metrics_csv, read_metrics_csv

RAISED = "A raised budget, for the repeat."

COMPLETE = (RESPONSES / "complete.json").read_bytes()
"""A response: the baseline's, in each test."""
SAME_RESULTS = (
    (RESPONSES / "same-metrics.json").read_bytes().replace(b'"cost": 5,', b'"cost": 7,', 1)
)
"""`complete.json`'s results, with another `cost` and `quotaRemaining`, as a stale backtest gets."""
CHANGED = (RESPONSES / "changed-metrics.json").read_bytes()
"""Other results, as a backtest ranked by another definition gets."""
INVALID = (RESPONSES / "invalid-structure.json").read_bytes()
"""A decoded response without the layout's required structure."""


EXAMPLE = ranked_experiment(EXPERIMENT_CONFIGS / "ranking-example.yaml").plan
"""Its cases, in order: `baseline`, `value-heavy`, `tilt-earnings-yield`, and `no-sales-yield`,
each ranked by another definition, with the same backtest request."""
BASELINE, VALUE_HEAVY, TILT, NO_SALES = (case.case_id for case in EXAMPLE.cases)


@pytest.fixture
def lab(tmp_path: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch) -> Lab:
    return Lab(tmp_path, server, monkeypatch, reader=RELEASE_0_4_0)


def script(
    server: FakePortfolio123, *backtests: Reply, ranks: Sequence[Reply] | None = None
) -> None:
    """One authentication call, a 200 to each `rank_update`, or `ranks`, and `backtests`."""
    server.reply("/auth", AUTHENTICATED)
    if ranks is None:
        ranks = [response("rank-update.json")] * len(backtests)
    server.reply("/rank", *ranks, method="POST")
    server.reply("/screen/backtest", *backtests)


def ok(body: bytes) -> Reply:
    return Reply(200, body)


BETWEEN = [
    pytest.param(
        None, Reply(400, b"Invalid ranking system"), True, id="a rank_update that got a 400"
    ),
    pytest.param(Reply(200, b"<html>not JSON</html>"), None, True, id="a backtest saved undecoded"),
    pytest.param(Reply(503, b""), None, True, id="a backtest without a response"),
    pytest.param(ok(INVALID), None, False, id="a decoded backtest without the required structure"),
]
"""What `value-heavy` gets between the baseline and `tilt-earnings-yield`, which gets the
baseline's results: its backtest's reply, or None when its `rank_update` gets the reply after it,
so no backtest is sent; and whether `tilt-earnings-yield` is then flagged, against the baseline,
as it is unless `value-heavy` saved a decoded response."""


def script_between(lab: Lab, between: Reply | None, ranks: Reply | None) -> None:
    """The baseline gets `complete.json`, `value-heavy` `between` or, for its `rank_update`,
    `ranks`, `tilt-earnings-yield` the baseline's results, and `no-sales-yield` others."""
    updated = response("rank-update.json")
    backtests = [ok(COMPLETE), *([] if between is None else [between]), ok(SAME_RESULTS)]
    rank_replies = [updated, updated if ranks is None else ranks, updated]
    script(lab.server, *backtests, ok(CHANGED), ranks=[*rank_replies, updated])


def flagged(lab: Lab, ran: Ran) -> str:
    """`value-heavy`'s one attempt's ID, once the test checked that the session flagged it."""
    (record,) = lab.attempts(VALUE_HEAVY, AttemptRecordV1_3)
    assert (record.outcome, record.possibly_charged, record.error) == ("succeeded", True, None)
    assert record.response is not None and record.response.form == "decoded"
    assert not lab.tables(VALUE_HEAVY).exists()
    assert ran.executed.repeat_attempts == {VALUE_HEAVY: record.attempt_id}
    return str(record.attempt_id)


# The flag, in the session


def test_the_previous_cases_results_after_another_definition_are_flagged(
    lab: Lab, caplog: pytest.LogCaptureFixture
) -> None:
    # `value-heavy` gets the baseline's results with another cost and quota; the others get
    # results of their own, so neither is flagged: `tilt-earnings-yield`'s differ from
    # `value-heavy`'s, and `no-sales-yield`'s from its.
    caplog.set_level(logging.INFO, logger="trialfolio")
    script(lab.server, ok(COMPLETE), ok(SAME_RESULTS), ok(CHANGED), ok(COMPLETE))

    ran = lab.run()

    attempt = flagged(lab, ran)
    assert ran.outcomes == ["succeeded", "failed", "succeeded", "succeeded"]
    for case in (BASELINE, TILT, NO_SALES):
        assert (lab.tables(case) / "metrics.csv").exists()
    manifest = ran.executed.manifest
    assert manifest is not None
    assert (manifest.counts.cases.succeeded, manifest.counts.cases.failed) == (3, 1)
    assert manifest.counts.attempts.succeeded == 4
    error = ran.error
    assert error is not None and error.code == "execution.partial"
    # The message names the cases by their keys, and says why, that identical results can be
    # genuine, that the response is saved, and that it awaits a repeat. It gives no option: the
    # CLI ends execution.partial's message with each case's, as for any case awaiting a repeat.
    assert "`value-heavy`, failed (provider.response_invalid)" in error.message
    assert (
        "The backtest of case `value-heavy` returned the same response, apart from cost and"
        " quotaRemaining, as that of case `baseline`, the case before it in session 1, which was"
        " ranked by a different ranking definition. So Portfolio123 may have ranked it by"
        " `baseline`'s definition, although its rank_update succeeded. Identical results can"
        " sometimes be genuine, as when a changed weight doesn't change which stocks the screen"
        " selects. The response is saved, but the case isn't normalized, and it awaits a repeat,"
        " which sends its rank_update and its backtest again, and may be charged again. A case"
        " whose request may have reached Portfolio123"
    ) in error.message
    assert "--repeat" not in error.message
    assert attempt not in error.message
    # The loggable message names them by their case_ids, and holds no key; it names the attempt
    # by its ID.
    assert f"The backtest of case {VALUE_HEAVY} returned the same response" in error.log_message
    assert f"as that of case {BASELINE}, the case before it" in error.log_message
    assert (
        f" The response of attempt {attempt} is saved, but the case isn't normalized, and it"
        " awaits a repeat, which sends its rank_update and its backtest again, and may be charged"
        " again. A case whose request may have reached Portfolio123"
    ) in error.log_message
    for case in EXAMPLE.cases:
        assert case.case_key not in error.log_message
    (invalid,) = [r for r in caplog.records if getattr(r, "event", "") == "experiment.case.invalid"]
    assert getattr(invalid, "case_id", None) == VALUE_HEAVY
    # The report says why the case has no tables, and lists it as awaiting a repeat.
    report = (lab.out / "sessions/1/report.html").read_text(encoding="utf-8")
    assert "repeats the response of the case before it in its session" in report
    assert f"<code>{BASELINE}</code>, which was ranked by a different definition" in report
    assert f"<code>--repeat value-heavy:{attempt}</code>" in report


def test_a_backtest_of_another_request_is_never_flagged(lab: Lab) -> None:
    # ranking-mixed.yaml: `value-heavy`, a ranking variant, then `holdings-50`, whose backtest
    # request differs, and the default rebalance variant, whose request differs again. Each gets
    # the baseline's results, so only `value-heavy` is flagged.
    mixed = planned_experiment(EXPERIMENT_CONFIGS / "ranking-mixed.yaml").plan
    script(lab.server, *(ok(COMPLETE) for _ in mixed.cases))

    ran = lab.run("ranking-mixed.yaml")

    keys = [case.case_key for case in mixed.cases]
    assert keys[:3] == ["baseline", "value-heavy", "holdings-50"]
    assert ran.outcomes == ["succeeded", "failed", *["succeeded"] * (len(keys) - 2)]


@pytest.mark.parametrize(("between", "ranks", "flags"), BETWEEN)
def test_the_previous_backtest_is_the_sessions_latest_with_a_decoded_response(
    lab: Lab, between: Reply | None, ranks: Reply | None, flags: bool
) -> None:
    # `value-heavy` gets no decoded response, or one without the required structure, between
    # the baseline and `tilt-earnings-yield`, which gets the baseline's results: it's compared
    # with the baseline unless `value-heavy` saved a decoded response.
    script_between(lab, between, ranks)

    ran = lab.run()

    assert ran.outcomes[2] == ("failed" if flags else "succeeded")
    if flags:
        assert ran.error is not None
        assert "`tilt-earnings-yield` returned the same response" in ran.error.message
        assert "as that of case `baseline`" in ran.error.message


# The flag, as a resume reads the records


@pytest.mark.parametrize(
    "stop",
    [
        {f"{TILT}/rank-update-request.json": "interrupt"},
        {f"{VALUE_HEAVY}/attempt.json": "full disk"},
    ],
    ids=["after the flagged case's attempt record", "before it, with its response saved"],
)
def test_a_resume_reads_a_stale_backtest_as_the_session_flagged_it(
    lab: Lab, stop: dict[str, Fault]
) -> None:
    # The session stops without its manifest, after `value-heavy`'s attempt, or before its
    # attempt record, which the resume writes from the saved response. Either way, the records
    # check finds the flag again, so the resume writes no table for the case, and doesn't send
    # it, while it sends the cases due.
    script(lab.server, ok(COMPLETE), ok(SAME_RESULTS))
    first = lab.run(arm=lambda store: store.fail_each(stop))
    assert first.executed.manifest is None
    assert not lab.tables(VALUE_HEAVY).exists()

    saved = lab.read()

    missing = saved.missing[VALUE_HEAVY]
    assert missing.invalid is not None and missing.invalid.code == "provider.response_invalid"
    assert missing.identical_to == BASELINE
    assert not saved.valid(VALUE_HEAVY)
    states = [case.state for case in saved.cases(EXAMPLE)]
    assert states[:2] == ["complete", "awaiting_repeat"]

    script(lab.server, ok(CHANGED), ok(COMPLETE))
    resumed = lab.run()

    assert lab.server.requests()[-5:] == [AUTH, RANK, BACKTEST, RANK, BACKTEST]
    assert not lab.tables(VALUE_HEAVY).exists()
    assert resumed.outcomes == ["succeeded", "failed", "succeeded", "succeeded"]
    (record,) = lab.attempts(VALUE_HEAVY, AttemptRecordV1_3)
    assert (record.session, record.outcome) == (1, "succeeded")
    assert resumed.executed.repeat_attempts == {VALUE_HEAVY: record.attempt_id}
    assert resumed.error is not None
    assert "`value-heavy` returned the same response" in resumed.error.message


@pytest.mark.parametrize(("between", "ranks", "flags"), BETWEEN)
def test_a_resume_compares_with_the_sessions_latest_attempt_that_saved_a_decoded_response(
    lab: Lab, between: Reply | None, ranks: Reply | None, flags: bool
) -> None:
    # The session stops before `tilt-earnings-yield`'s tables, or, when it flagged the case,
    # before `no-sales-yield`. The records check compares `tilt-earnings-yield`, which has no
    # tables, with the session's latest attempt before it that saved a decoded response, as the
    # session did: the baseline, unless `value-heavy` saved one, whatever its structure.
    script_between(lab, between, ranks)
    first = lab.run(
        arm=lambda store: store.fail_each(
            {
                f"{TILT}/metrics.csv": "interrupt",
                f"{NO_SALES}/rank-update-request.json": "interrupt",
            }
        )
    )
    assert first.executed.manifest is None
    assert first.outcomes[2] == ("failed" if flags else "succeeded")
    assert not (lab.tables(TILT) / "metrics.csv").exists()

    saved = lab.read()

    missing = saved.missing[TILT]
    if flags:
        assert missing.invalid is not None and missing.invalid.code == "provider.response_invalid"
        assert missing.identical_to == BASELINE
    else:
        assert (missing.invalid, missing.identical_to) == (None, None)


def test_a_resume_names_a_flagged_case_by_the_key_the_plan_it_approves_gives_it(
    lab: Lab,
) -> None:
    # A revision renames `value-heavy` `heavy-value`, and keeps its case_id and its attempts.
    # The resume, which finds the flag again in the records, names the case by its new key, as
    # execution.partial's message lists it, never by the key it ran under.
    script(lab.server, ok(COMPLETE), ok(SAME_RESULTS), ok(CHANGED), ok(COMPLETE))
    flagged(lab, lab.run())

    resumed = lab.run("revisions/ranking-key-renamed.yaml", reason="Renamed a case.")

    error = resumed.error
    assert error is not None and error.code == "execution.partial"
    assert "`heavy-value`, failed (provider.response_invalid)" in error.message
    assert (
        "The backtest of case `heavy-value` returned the same response, apart from cost and"
        " quotaRemaining, as that of case `baseline`, the case before it in session 1"
    ) in error.message
    assert "value-heavy" not in error.message
    manifest = resumed.executed.manifest
    assert manifest is not None and manifest.error is not None
    assert manifest.error.message == error.message


def test_a_resume_names_a_retired_previous_case_by_the_key_it_ran_under(lab: Lab) -> None:
    # `tilt-earnings-yield` gets `value-heavy`'s results, so it's flagged against it. Then a
    # revision changes the baseline's definition, which retires `value-heavy`, adds a case with
    # its key again, and keeps `tilt-earnings-yield`: the resume, which sends the two new cases,
    # names the retired case by its key in the plan it ran under.
    stale_results = CHANGED.replace(b'"cost": 5,', b'"cost": 7,', 1)
    script(lab.server, ok(COMPLETE), ok(CHANGED), ok(stale_results), ok(SAME_RESULTS))
    first = lab.run()
    assert first.outcomes == ["succeeded", "succeeded", "failed", "succeeded"]
    script(lab.server, ok(COMPLETE), ok(CHANGED))

    resumed = lab.run("revisions/ranking-definition-changed.yaml", reason="A revised definition.")

    error = resumed.error
    assert error is not None and error.code == "execution.partial"
    assert (
        "The backtest of case `tilt-earnings-yield` returned the same response, apart from cost"
        " and quotaRemaining, as that of case `value-heavy`, the case before it in session 1"
    ) in error.message


@pytest.mark.parametrize(
    "table", ["metrics.csv", "settings.csv"], ids=["before its tables", "between them"]
)
def test_a_repeats_tables_a_stopped_session_didnt_write_come_from_the_repeat(
    lab: Lab, table: str
) -> None:
    # The session that repeats the flagged `value-heavy` stops after its repeat's attempt
    # record, before its tables, or between them. The repeat's response passed validation, so
    # the case is complete from then, as the records read it, and the stopped session's
    # outcomes, counts, and cases awaiting a repeat agree with them. The next resume writes the
    # tables from the repeat's response, the case's latest succeeded attempt's.
    script(lab.server, ok(COMPLETE), ok(SAME_RESULTS), ok(CHANGED), ok(COMPLETE))
    attempt = flagged(lab, lab.run())
    script(lab.server, ok(CHANGED))
    stopped = lab.run(
        "revisions/ranking-budget-raised.yaml",
        reason=RAISED,
        repeats=[Repeat(VALUE_HEAVY, uuid.UUID(attempt))],
        arm=lambda store: store.fail(f"{VALUE_HEAVY}/{table}", "interrupt"),
    )
    assert stopped.executed.manifest is None
    assert stopped.error is not None and stopped.error.code == "command.interrupted"
    stale, repeat = lab.attempts(VALUE_HEAVY, AttemptRecordV1_3)
    assert repeat.response is not None
    saved = lab.read()
    current = saved.current.plan
    assert isinstance(current, PlanV1_3)
    assert saved.cases(current)[1].state == "complete"
    assert stopped.outcomes == ["succeeded"] * 4
    assert stopped.executed.repeat_attempts == {}
    assert stopped.executed.counts == saved.counts(current)

    missing = saved.missing[VALUE_HEAVY]
    assert (missing.attempt.attempt_id, missing.invalid) == (repeat.attempt_id, None)

    resumed = lab.run("revisions/ranking-budget-raised.yaml", reason=RAISED)

    assert resumed.error is None
    rows = read_metrics_csv((lab.tables(VALUE_HEAVY) / "metrics.csv").read_bytes(), "metrics")
    assert {row.source_artifact for row in rows} == {repeat.response.artifact_id}
    assert stale.outcome == "succeeded"


def test_a_resume_never_flags_a_synthetic_experiments_case(lab: Lab) -> None:
    # A synthetic session stopped before `value-heavy`'s tables: its invented response is the
    # baseline's, but nothing ranked it, so the records check finds no flag, and the resume, with
    # the demo's client, writes its tables.
    lab.new(synthetic=True, arm=lambda store: store.fail(f"{VALUE_HEAVY}/metrics.csv", "interrupt"))
    assert not lab.tables(VALUE_HEAVY).exists()

    with LocalArtifactStore(lab.out) as store:
        missing = open_experiment(store, ranking=True).missing[VALUE_HEAVY]
    assert (missing.invalid, missing.identical_to) == (None, None)
    lab.resume(synthetic=True)

    assert (lab.tables(VALUE_HEAVY) / "settings.csv").exists()


def test_a_synthetic_experiments_identical_responses_are_never_flagged(lab: Lab) -> None:
    # The demo's client answers each case with the same invented response, which nothing ranked.
    ran = lab.new(synthetic=True)

    assert ran.error is None
    saved = lab.read()
    assert [case.state for case in saved.cases(EXAMPLE)] == ["complete"] * 4


# The repeat of a case whose response failed validation


def test_a_repeat_of_a_stale_backtest_completes_its_case_with_its_tables_written_once(
    lab: Lab,
) -> None:
    script(lab.server, ok(COMPLETE), ok(SAME_RESULTS), ok(CHANGED), ok(COMPLETE))
    first = lab.run()
    attempt = flagged(lab, first)

    # Eight requests are counted, so the repeat's two need the raised budget.
    script(lab.server, ok(CHANGED))
    repeated = lab.run(
        "revisions/ranking-budget-raised.yaml",
        reason=RAISED,
        repeats=[Repeat(VALUE_HEAVY, uuid.UUID(attempt))],
    )

    assert repeated.error is None
    assert repeated.outcomes == ["succeeded"] * 4
    stale, repeat = lab.attempts(VALUE_HEAVY, AttemptRecordV1_3)
    assert (stale.outcome, repeat.outcome) == ("succeeded", "succeeded")
    assert (repeat.session, str(repeat.repeat_of)) == (2, attempt)
    assert repeat.response is not None
    # Its tables are written once, from the repeat's response.
    rows = read_metrics_csv((lab.tables(VALUE_HEAVY) / "metrics.csv").read_bytes(), "metrics")
    assert {row.source_artifact for row in rows} == {repeat.response.artifact_id}
    assert sorted(path.name for path in lab.tables(VALUE_HEAVY).iterdir()) == [
        "metrics.csv",
        "settings.csv",
    ]
    manifest = repeated.executed.manifest
    assert manifest is not None
    paths = [artifact.path for artifact in manifest.artifacts]
    metrics = f"cases/{VALUE_HEAVY}/normalized/metrics.csv"
    assert paths.count(metrics) == 1
    # Listed right after the repeat's files, from whose response it's drawn.
    repeat_files = [p for p in paths if f"/{repeat.attempt_id}/" in p]
    assert paths.index(metrics) == paths.index(repeat_files[-1]) + 1
    assert repeated.executed.repeat_attempts == {}
    # The records check accepts the history: a succeeded attempt that failed validation, then
    # its repeat. A resume that sends nothing reads it, and finds the experiment complete.
    saved = lab.read()
    assert saved.valid(VALUE_HEAVY)
    current = saved.current.plan
    assert isinstance(current, PlanV1_3)
    assert [case.state for case in saved.cases(current)] == ["complete"] * 4
    again = lab.run("revisions/ranking-budget-raised.yaml", reason=RAISED)
    assert again.error is None
    assert lab.server.requests()[-1] == BACKTEST


def test_the_same_repeat_after_it_completed_its_case_repeats_nothing_and_resumes(
    lab: Lab,
) -> None:
    # One confirmation, one repeat: the repeat of the flagged `value-heavy` completed it, so the
    # same repeat, given again, as when the command is run again after an interruption, is one
    # whose confirmation is used. It isn't refused: the attempt it names succeeded, but its own
    # response failed validation, whatever its repeat's did.
    script(lab.server, ok(COMPLETE), ok(SAME_RESULTS), ok(CHANGED), ok(COMPLETE))
    repeat = Repeat(VALUE_HEAVY, uuid.UUID(flagged(lab, lab.run())))
    script(lab.server, ok(CHANGED))
    repeated = lab.run("revisions/ranking-budget-raised.yaml", reason=RAISED, repeats=[repeat])
    assert repeated.error is None
    sent = lab.server.requests()

    again = lab.run("revisions/ranking-budget-raised.yaml", reason=RAISED, repeats=[repeat])

    assert again.error is None
    assert again.executed.repeats_used == (repeat,)
    assert lab.server.requests() == sent
    assert len(lab.attempts(VALUE_HEAVY, AttemptRecordV1_3)) == 2
    assert again.outcomes == ["succeeded"] * 4


def test_a_stale_backtests_repeat_without_the_required_structure_isnt_called_stale(
    lab: Lab,
) -> None:
    # The repeat of the flagged `value-heavy` gets a response without the layout's required
    # structure: the case awaits a repeat again, which names the repeat, and the session's
    # message and report give that response's failure, not the stale backtest's.
    script(lab.server, ok(COMPLETE), ok(SAME_RESULTS), ok(CHANGED), ok(COMPLETE))
    attempt = flagged(lab, lab.run())
    script(lab.server, ok(INVALID))

    repeated = lab.run(
        "revisions/ranking-budget-raised.yaml",
        reason=RAISED,
        repeats=[Repeat(VALUE_HEAVY, uuid.UUID(attempt))],
    )

    assert repeated.error is not None and repeated.error.code == "execution.partial"
    assert "returned the same response" not in repeated.error.message
    _, repeat = lab.attempts(VALUE_HEAVY, AttemptRecordV1_3)
    assert repeat.outcome == "succeeded"
    assert repeated.executed.repeat_attempts == {VALUE_HEAVY: repeat.attempt_id}
    report = (lab.out / "sessions/2/report.html").read_text(encoding="utf-8")
    assert "repeats the response of the case before it" not in report
    assert "required structure, so it wasn" in report


def test_a_repeat_of_a_case_whose_response_had_no_required_structure_completes_it(
    lab: Lab,
) -> None:
    # A plan 1.1.0, as in 0.3.0: the case whose response lacks the layout's required structure
    # awaited no repeat there, and was never sent again. Now its repeat makes it complete.
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", ok(COMPLETE), ok(INVALID))
    first = lab.run("default-only.yaml")
    (_, succeeded), (case, invalid) = first.executed.outcomes
    assert (succeeded, invalid) == ("succeeded", "failed")
    (record,) = sorted(
        (
            AttemptRecordV1_1.model_validate_json((path / "attempt.json").read_bytes())
            for path in (lab.out / "cases" / case.case_id / "attempts").iterdir()
        ),
        key=lambda r: r.sequence,
    )
    assert record.outcome == "succeeded"
    assert first.executed.repeat_attempts == {case.case_id: record.attempt_id}

    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", ok(COMPLETE))
    repeated = lab.run(
        "revisions/default-only-budget-3.yaml",
        reason=RAISED,
        repeats=[Repeat(case.case_id, record.attempt_id)],
    )

    assert repeated.error is None
    assert repeated.outcomes == ["succeeded", "succeeded"]
    assert (lab.tables(case.case_id) / "settings.csv").exists()
    saved = lab.read()
    assert saved.valid(case.case_id)


# The records check


def test_tables_drawn_from_a_succeeded_attempt_that_another_follows_are_refused(
    lab: Lab,
) -> None:
    # A case's tables come from its latest succeeded attempt, its last: a succeeded attempt that
    # an attempt follows failed validation, so no table is drawn from it. Here `value-heavy` was
    # flagged, and its repeat got a 400; then a table drawn from the flagged attempt's response
    # is added, as no Trial Folio writes it.
    script(lab.server, ok(COMPLETE), ok(SAME_RESULTS), ok(CHANGED), ok(COMPLETE))
    attempt = flagged(lab, lab.run())
    script(lab.server, ranks=[Reply(400, b"Invalid ranking system")])
    rejected = lab.run(
        "revisions/ranking-budget-raised.yaml",
        reason=RAISED,
        repeats=[Repeat(VALUE_HEAVY, uuid.UUID(attempt))],
    )
    assert rejected.error is not None
    # The repeat's 400 describes the case now, not the stale backtest before it.
    assert "returned the same response" not in rejected.error.message
    assert lab.read().cases(EXAMPLE)[1].state == "awaiting_repeat"
    stale = lab.attempts(VALUE_HEAVY, AttemptRecordV1_3)[0]
    assert stale.response is not None
    content = (lab.out / stale.response.path).read_bytes()
    rows = case_metrics_rows(content, EXAMPLE.cases[1], stale.response)
    lab.tables(VALUE_HEAVY).mkdir()
    (lab.tables(VALUE_HEAVY) / "metrics.csv").write_bytes(metrics_csv(rows))

    with pytest.raises(TrialFolioError) as refused:
        lab.read()

    assert refused.value.code == "input.not_a_run"
    assert "an attempt follows the succeeded attempt they're drawn from" in refused.value.message


def test_a_flagged_attempt_whose_case_has_tables_drawn_from_it_isnt_read_again(lab: Lab) -> None:
    # Tables drawn from a case's latest succeeded attempt passed validation when they were
    # written, as by a version that didn't flag stale backtests, so the check reads the case as
    # complete, and finds no flag: only a case without them is judged again.
    script(lab.server, ok(COMPLETE), ok(SAME_RESULTS), ok(CHANGED), ok(COMPLETE))
    flagged(lab, lab.run())
    stale = lab.attempts(VALUE_HEAVY, AttemptRecordV1_3)[0]
    assert stale.response is not None
    content = (lab.out / stale.response.path).read_bytes()
    rows = case_metrics_rows(content, EXAMPLE.cases[1], stale.response)
    lab.tables(VALUE_HEAVY).mkdir()
    (lab.tables(VALUE_HEAVY) / "metrics.csv").write_bytes(metrics_csv(rows))

    saved = lab.read()

    assert saved.valid(VALUE_HEAVY)
    assert VALUE_HEAVY in saved.missing  # settings.csv, which a resume writes beside it
    assert saved.missing[VALUE_HEAVY].invalid is None
    assert saved.cases(EXAMPLE)[1].state == "complete"
