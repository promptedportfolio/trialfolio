"""The counts add up: after each experiment R03-AC05, R03-AC06, R03-AC07, R03-AC10, and R03-AC14
name, the session's manifest gives planned = succeeded + failed + skipped + unknown + not yet run,
and each of its counts is the one the test holds, written by hand from the replies it scripted,
never as the code under test computes it. The session's report shows each count, as the manifest
records it, and so does the JSON summary, which also counts the planned cases' unavailable metrics
and the warnings the command logged, as for a run. A case is counted by its latest attempt that
may have reached Portfolio123, so a repeat whose authentication failed leaves it `unknown`.

Traces to R03-AC08's interface part, and to docs/contracts.md, the experiment manifest (its
`counts`, and a case's outcome for them), reports (the counts in the experiment report's section
5), and JSON summary (an experiment's `counts`). tests/core/test_experiment_report.py checks the
report's wording of each count at the core; tests/contract/test_experiment_artifact_models.py
checks that the manifest's model rejects case counts that don't add up.

Each test writes `example.yaml`'s or `default-only.yaml`'s experiment with the experiment
builder, through the CLI's entry function in the test process, over the fake server, or kills a
run with `SIGKILL` under the test launcher while the server holds a reply. Every response sent
with a 200 reports a cost of 5 credits, and `missing-metrics.json` has 3 unavailable metrics.
"""

import json
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from tests.support.cli import Cli
from tests.support.environment import Outcome
from tests.support.experiment_builder import (
    AUTHENTICATED,
    REFUSED,
    REJECTED,
    UNAVAILABLE,
    ExperimentBuilder,
    experiment_config,
    held,
    returns,
)
from tests.support.fake_portfolio123 import Reply
from tests.support.html_report import Document, parse
from trialfolio.contracts.experiment_manifest import ExperimentManifest, ExperimentManifestCounts

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Windows has no SIGKILL")

EXAMPLE = experiment_config("example.yaml")
DEFAULT_ONLY = experiment_config("default-only.yaml")
HOLDINGS = "holdings-50"

NOT_FOUND = Reply(404, b"Not found")
"""A 404 to a case's request: `failed`, possibly charged, with `provider.request_rejected`."""
QUOTA = Reply(402, b"")
"""A 402 to a case's request: `failed`, possibly charged, with `provider.quota_exceeded`, which
stops the later cases (D-32)."""
FORBIDDEN = Reply(403, b"")
"""A 403 to a case's request: `failed`, possibly charged. The next case authenticates again."""

type Builder = ExperimentBuilder[Outcome]


@dataclass(frozen=True, kw_only=True)
class Expected:
    """The counts a test holds, written by hand from the replies it scripted. A count left out
    is 0. No session ends with an attempt left `running`, which a resume records first, and 0.3.0
    skips no case, so neither has a field."""

    planned: int
    succeeded: int = 0
    failed: int = 0
    unknown: int = 0
    not_yet_run: int = 0
    retired: int = 0
    attempts_succeeded: int = 0
    attempts_failed: int = 0
    attempts_unknown: int = 0
    attempts_running: int = 0
    """Only in the records a run without approval reads, before a resume records the attempt."""
    repeats: int = 0
    provider_requests: int
    authentication_calls: int
    budget: int
    """The current plan's `provider_requests`, and so its authentication calls too."""
    cost: int | None
    metrics_unavailable: int = 0
    warnings: int = 0
    """Those the command logged: no later case starts (`experiment.stopped`), the session ended
    partial (`experiment.session.ended`), a resume recorded a stopped run's attempt
    (`experiment.attempt.recorded`), or the adapter refused the wrapper's resend after a 403
    (`provider.request.refused`)."""

    def recorded(self) -> dict[str, int | None]:
        """As `recorded` gives a manifest's counts."""
        return {
            "planned": self.planned,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": 0,
            "unknown": self.unknown,
            "not_yet_run": self.not_yet_run,
            "retired_cases": self.retired,
            "attempts_succeeded": self.attempts_succeeded,
            "attempts_failed": self.attempts_failed,
            "attempts_unknown": self.attempts_unknown,
            "attempts_running": self.attempts_running,
            "repeats": self.repeats,
            "retries": 0,
            "provider_requests": self.provider_requests,
            "authentication_calls": self.authentication_calls,
            "budget_provider_requests": self.budget,
            "budget_authentication_calls": self.budget,
            "cost": self.cost,
        }

    def summary(self) -> dict[str, int | None]:
        """As the JSON summary gives them."""
        attempts = (
            self.attempts_succeeded
            + self.attempts_failed
            + self.attempts_unknown
            + self.attempts_running
        )
        return {
            "cases_planned": self.planned,
            "cases_succeeded": self.succeeded,
            "cases_failed": self.failed,
            "cases_skipped": 0,
            "cases_unknown": self.unknown,
            "cases_not_yet_run": self.not_yet_run,
            "cases_retired": self.retired,
            "attempts": attempts,
            "repeats": self.repeats,
            "provider_requests": self.provider_requests,
            "authentication_calls": self.authentication_calls,
            "cost": self.cost,
            "metrics_unavailable": self.metrics_unavailable,
            "warnings": self.warnings,
        }


def recorded(counts: ExperimentManifestCounts) -> dict[str, int | None]:
    """A manifest's counts, by name."""
    return {
        "planned": counts.cases.planned,
        "succeeded": counts.cases.succeeded,
        "failed": counts.cases.failed,
        "skipped": counts.cases.skipped,
        "unknown": counts.cases.unknown,
        "not_yet_run": counts.cases.not_yet_run,
        "retired_cases": counts.retired_cases,
        "attempts_succeeded": counts.attempts.succeeded,
        "attempts_failed": counts.attempts.failed,
        "attempts_unknown": counts.attempts.unknown,
        "attempts_running": counts.attempts.running,
        "repeats": counts.attempts.repeats,
        "retries": counts.retries,
        "provider_requests": counts.provider_requests,
        "authentication_calls": counts.authentication_calls,
        "budget_provider_requests": counts.budget.provider_requests,
        "budget_authentication_calls": counts.budget.authentication_calls,
        "cost": counts.cost,
    }


PLANNED = re.compile(
    r"Planned cases: (\d+) = (\d+) succeeded \+ (\d+) failed \+ (\d+) skipped \+ (\d+) unknown \+"
    r" (\d+) not yet run\."
)
ATTEMPTS = re.compile(r"(\d+) succeeded, (\d+) failed, (\d+) unknown, (\d+) running")
BUDGET = re.compile(
    r"Provider requests: (\d+) of the budget's (\d+)\. Authentication calls: (\d+) of its (\d+)\."
)
COST = re.compile(r"(\d+) credits, ")


def shown(document: Document) -> dict[str, int | None]:
    """The counts the report's section 5 shows, by the names `recorded` gives a manifest's."""

    def numbers(pattern: re.Pattern[str], text: str) -> list[int]:
        found = pattern.match(text)
        assert found is not None, text
        return [int(number) for number in found.groups()]

    def one(term: str) -> str:
        (text,) = document.dd(term)
        return text

    section = document.root.by_id("cases")
    planned, succeeded, failed, skipped, unknown, not_yet_run = numbers(
        PLANNED, section.find_all("p")[0].text
    )
    attempts = numbers(ATTEMPTS, one("Attempts"))
    requests, budget_requests, calls, budget_calls = numbers(
        BUDGET, one("Counted against the budget")
    )
    cost = one("Cost")
    return {
        "planned": planned,
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "unknown": unknown,
        "not_yet_run": not_yet_run,
        "retired_cases": int(one("Retired cases")),
        "attempts_succeeded": attempts[0],
        "attempts_failed": attempts[1],
        "attempts_unknown": attempts[2],
        "attempts_running": attempts[3],
        "repeats": int(one("Repeats").split(":")[0]),
        "retries": int(one("Retries")),
        "provider_requests": requests,
        "authentication_calls": calls,
        "budget_provider_requests": budget_requests,
        "budget_authentication_calls": budget_calls,
        "cost": None if cost == "Not reported" else numbers(COST, cost)[0],
    }


def logged_warnings(out: Path) -> list[str]:
    """The events the last command that logged into `out` logged as warnings."""
    lines = (out / "logs" / "trialfolio.log").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines]
    starts = [i for i, event in enumerate(events) if event["event"] == "cli.command.started"]
    return [event["event"] for event in events[starts[-1] :] if event["level"] == "WARNING"]


def assert_counts(outcome: Outcome, out: Path, session: int, expected: Expected) -> None:
    """The session's manifest adds up, and holds the counts the test expects; its report shows
    each of them; and the command's summary gives them, with the unavailable metrics and the
    warnings it logged."""
    manifest = ExperimentManifest.model_validate_json(
        (out / f"sessions/{session}/manifest.json").read_bytes()
    )
    cases = manifest.counts.cases
    document = parse((out / f"sessions/{session}/report.html").read_text(encoding="utf-8"))

    assert cases.planned == (
        cases.succeeded + cases.failed + cases.skipped + cases.unknown + cases.not_yet_run
    )
    assert recorded(manifest.counts) == expected.recorded()
    assert shown(document) == recorded(manifest.counts)
    assert outcome.ids["session"] == session
    assert outcome.summary["counts"] == expected.summary()
    assert len(logged_warnings(out)) == expected.warnings


def repeat_option(outcome: Outcome, key: str) -> str:
    """The `--repeat` value that confirms a repeat of the case `key`, from the summary."""
    return f"{key}:{outcome.cases_by_key[key]['repeat_attempt_id']}"


def outcome_shown(out: Path, session: int, key: str) -> str:
    """The outcome the session's report gives the planned case `key`: the first word of its
    Outcome cell."""
    document = parse((out / f"sessions/{session}/report.html").read_text(encoding="utf-8"))
    table = document.table_after("Planned cases")
    header, *rows = document.rows(table)
    column = [cell.text for cell in header].index("Outcome")
    (row,) = (row for row in rows if row[0].text == key)
    return re.split(r"[ :]", row[column].text)[0]


# A failed case, and the later cases still run (R03-AC05)

ONE_CASE_ENDED = Expected(
    planned=5,
    succeeded=4,
    attempts_succeeded=4,
    provider_requests=5,
    authentication_calls=1,
    budget=6,
    cost=20,
    metrics_unavailable=3,
    warnings=1,
)
"""Every case sent once, and four succeeded: each case of the table adds how the fifth ended."""
FAILED = replace(ONE_CASE_ENDED, failed=1, attempts_failed=1)


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        pytest.param(REJECTED, FAILED, id="400"),
        pytest.param(NOT_FOUND, FAILED, id="404"),
        pytest.param(UNAVAILABLE, replace(ONE_CASE_ENDED, unknown=1, attempts_unknown=1), id="503"),
    ],
)
def test_a_failed_or_uncertain_case_is_counted_and_the_later_cases_are_too(
    cli: Cli, experiments: Builder, reply: Reply, expected: Expected
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # The baseline's response has 3 unavailable metrics; holdings-50's request gets the reply.
    sends = [returns("missing-metrics.json"), returns(), reply, returns(), returns()]

    outcome = experiments.run(EXAMPLE, out, sends=sends)

    assert outcome.exit_code == 6, outcome.stderr
    assert_counts(outcome, out, 1, expected)


STOPPED_AT_THE_BASELINE = Expected(
    planned=5,
    failed=1,
    not_yet_run=4,
    attempts_failed=1,
    provider_requests=0,
    authentication_calls=1,
    budget=6,
    cost=None,
    warnings=2,
)
"""The baseline's attempt sent nothing: it's failed, no request is counted, and the session
stops, and ends partial. The table's two other stops change it by what their sessions sent
first."""


@pytest.mark.parametrize(
    ("sends", "authenticates", "expected"),
    [
        pytest.param(
            [returns(), returns(), QUOTA],
            [AUTHENTICATED],
            # Cases 4 and 5 don't start: the session stops, and ends partial.
            replace(
                STOPPED_AT_THE_BASELINE,
                succeeded=2,
                not_yet_run=2,
                attempts_succeeded=2,
                provider_requests=3,
                cost=10,
            ),
            id="402",
        ),
        pytest.param([], [REFUSED], STOPPED_AT_THE_BASELINE, id="authentication-401"),
        pytest.param([], [UNAVAILABLE], STOPPED_AT_THE_BASELINE, id="authentication-503"),
        pytest.param(
            [returns(), FORBIDDEN],
            [AUTHENTICATED, REFUSED],
            # liquidity-100m's request gets a 403, which may have been charged; holdings-50
            # authenticates again, gets a 401, and sends nothing; cases 4 and 5 don't start.
            replace(
                STOPPED_AT_THE_BASELINE,
                succeeded=1,
                failed=2,
                not_yet_run=2,
                attempts_succeeded=1,
                attempts_failed=2,
                provider_requests=2,
                authentication_calls=2,
                cost=5,
                warnings=3,
            ),
            id="403-then-authentication-401",
        ),
    ],
)
def test_after_a_stop_the_cases_not_started_are_counted_not_yet_run(
    cli: Cli,
    experiments: Builder,
    sends: list[Reply],
    authenticates: list[Reply],
    expected: Expected,
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = experiments.run(EXAMPLE, out, sends=sends, authenticates=authenticates)

    assert outcome.exit_code == 6, outcome.stderr
    assert_counts(outcome, out, 1, expected)


# A send killed in flight, which the resume records as unknown (R03-AC06)


@posix_only
def test_a_send_killed_in_flight_is_counted_unknown_and_as_one_request(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # Killed once the server has the authentication call and two requests, while it holds
    # liquidity-100m's response: its start record is left without an attempt record, `running`,
    # and the session without a manifest.
    experiments.kill(EXAMPLE, out, sends=[returns(), held(returns())], received=3)
    assert not (out / "sessions/1/manifest.json").exists()

    waiting = experiments.run(EXAMPLE, out, approve=False)

    # Without approval, nothing is written, and the summary counts the records as they are: the
    # `running` attempt as unknown, and as one provider request.
    assert waiting.exit_code == 2
    assert waiting.summary["counts"] == (
        Expected(
            planned=5,
            succeeded=1,
            unknown=1,
            not_yet_run=3,
            attempts_succeeded=1,
            attempts_running=1,
            provider_requests=2,
            authentication_calls=1,
            budget=6,
            cost=5,
        ).summary()
    )

    resumed = experiments.run(EXAMPLE, out, sends=[returns(), returns(), returns()])

    assert resumed.exit_code == 6, resumed.stderr
    assert_counts(
        resumed,
        out,
        2,
        Expected(
            planned=5,
            succeeded=4,
            unknown=1,
            attempts_succeeded=4,
            attempts_unknown=1,
            provider_requests=5,
            authentication_calls=2,
            budget=6,
            cost=20,
            warnings=2,
        ),
    )


# A revision that retires a case (R03-AC07)


def test_a_revision_counts_the_case_it_retires_and_only_the_current_plans_cases(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # holdings-50's response has 3 unavailable metrics.
    sends = [returns(), returns(), returns("missing-metrics.json"), returns(), returns()]
    first = experiments.run(EXAMPLE, out, sends=sends)
    assert first.exit_code == 0, first.stderr
    assert_counts(
        first,
        out,
        1,
        Expected(
            planned=5,
            succeeded=5,
            attempts_succeeded=5,
            provider_requests=5,
            authentication_calls=1,
            budget=6,
            cost=25,
            metrics_unavailable=3,
        ),
    )

    revised = experiments.run(
        experiment_config("revisions/holdings-40.yaml"),
        out,
        "--revision-reason",
        "Tries 40 holdings instead of 50.",
        sends=[returns()],
    )

    # The new holdings-50 case is sent; the old one is retired, with its attempt, which is still
    # counted, and its unavailable metrics no longer are.
    assert revised.exit_code == 0, revised.stderr
    assert_counts(
        revised,
        out,
        2,
        Expected(
            planned=5,
            succeeded=5,
            retired=1,
            attempts_succeeded=6,
            provider_requests=6,
            authentication_calls=2,
            budget=6,
            cost=30,
        ),
    )


def test_a_revision_that_removes_a_variant_plans_one_case_fewer(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # The baseline's and slippage-050's responses each have 3 unavailable metrics.
    missing = returns("missing-metrics.json")
    sends = [missing, returns(), returns(), returns(), missing]
    assert experiments.run(EXAMPLE, out, sends=sends).exit_code == 0

    revised = experiments.run(
        experiment_config("revisions/variant-removed.yaml"),
        out,
        "--revision-reason",
        "Drops slippage.",
    )

    assert revised.exit_code == 0, revised.stderr
    assert_counts(
        revised,
        out,
        2,
        Expected(
            planned=4,
            succeeded=4,
            retired=1,
            attempts_succeeded=5,
            provider_requests=5,
            authentication_calls=1,
            budget=6,
            cost=25,
            metrics_unavailable=3,
        ),
    )


# A spent budget (R03-AC10)

BASELINE_UNKNOWN = Expected(
    planned=2,
    succeeded=1,
    unknown=1,
    attempts_succeeded=1,
    attempts_unknown=1,
    provider_requests=2,
    authentication_calls=1,
    budget=2,
    cost=5,
    warnings=1,
)
"""`default-only.yaml`'s first session, whose baseline's 503 leaves it unknown, and whose default
variant succeeds: each later session of the spent budget's test changes it."""


def test_a_repeat_the_spent_budget_doesnt_start_is_counted_once_a_revision_raises_it(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # default-only.yaml's budget is its 2 cases: the baseline's 503 leaves it unknown.
    first = experiments.run(DEFAULT_ONLY, out, sends=[UNAVAILABLE, returns()])
    assert first.exit_code == 6, first.stderr
    assert_counts(first, out, 1, BASELINE_UNKNOWN)
    option = repeat_option(first, "baseline")

    spent = experiments.run(DEFAULT_ONLY, out, "--repeat", option)

    # The spent budget doesn't start the repeat: the counts are the first session's, with one more
    # warning.
    assert spent.exit_code == 6, spent.stderr
    assert_counts(spent, out, 2, replace(BASELINE_UNKNOWN, warnings=2))

    raised = experiments.run(
        experiment_config("revisions/default-only-budget-3.yaml"),
        out,
        "--revision-reason",
        "Raises the budget.",
        "--repeat",
        option,
        sends=[returns()],
    )

    assert raised.exit_code == 0, raised.stderr
    assert_counts(
        raised,
        out,
        3,
        replace(
            BASELINE_UNKNOWN,
            succeeded=2,
            unknown=0,
            attempts_succeeded=2,
            repeats=1,
            provider_requests=3,
            authentication_calls=2,
            budget=3,
            cost=10,
            warnings=0,
        ),
    )


def test_spent_authentication_calls_are_counted_without_a_provider_request(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # Each run's authentication call gets a 401, so the baseline sends nothing, and the default
    # variant doesn't start; then the budget's 2 authentication calls are spent.
    for session in (1, 2):
        outcome = experiments.run(DEFAULT_ONLY, out, authenticates=[REFUSED])
        assert outcome.exit_code == 6, outcome.stderr
        assert_counts(
            outcome,
            out,
            session,
            Expected(
                planned=2,
                failed=1,
                not_yet_run=1,
                attempts_failed=session,
                provider_requests=0,
                authentication_calls=session,
                budget=2,
                cost=None,
                warnings=2,
            ),
        )
    received = len(cli.server.received)

    third = experiments.run(DEFAULT_ONLY, out)

    assert third.exit_code == 6, third.stderr
    assert len(cli.server.received) == received
    assert_counts(
        third,
        out,
        3,
        Expected(
            planned=2,
            failed=1,
            not_yet_run=1,
            attempts_failed=2,
            provider_requests=0,
            authentication_calls=2,
            budget=2,
            cost=None,
            warnings=2,
        ),
    )


def test_a_lowered_budget_keeps_the_requests_counted_above_it(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    first = experiments.run(
        EXAMPLE, out, sends=[returns(), returns(), UNAVAILABLE, returns(), returns()]
    )
    assert first.exit_code == 6
    # A repeat of holdings-50 ends unknown too: six requests in all.
    repeated = experiments.run(
        EXAMPLE, out, "--repeat", repeat_option(first, HOLDINGS), sends=[UNAVAILABLE]
    )
    assert repeated.exit_code == 6

    lowered = experiments.run(
        experiment_config("revisions/budget-lowered.yaml"),
        out,
        "--revision-reason",
        "Lowers the budget.",
        "--repeat",
        repeat_option(repeated, HOLDINGS),
    )

    # The revision sends nothing: its budget, 5, is spent, and so the repeat doesn't start.
    assert lowered.exit_code == 6, lowered.stderr
    assert_counts(
        lowered,
        out,
        3,
        Expected(
            planned=5,
            succeeded=4,
            unknown=1,
            attempts_succeeded=4,
            attempts_unknown=2,
            repeats=1,
            provider_requests=6,
            authentication_calls=2,
            budget=5,
            cost=20,
            warnings=2,
        ),
    )


# A repeat (R03-AC14)

REPEATED = Expected(
    planned=5,
    succeeded=4,
    attempts_succeeded=4,
    attempts_unknown=1,
    repeats=1,
    provider_requests=6,
    authentication_calls=2,
    budget=6,
    cost=20,
    warnings=1,
)
"""Four cases succeeded, and holdings-50's first attempt is unknown; its repeat, in a second
session, is counted: each case of the table adds how the repeat ended, and so how its case is."""


@pytest.mark.parametrize(
    ("sends", "authenticates", "outcome", "expected"),
    [
        pytest.param(
            [returns()],
            [AUTHENTICATED],
            "succeeded",
            replace(REPEATED, succeeded=5, attempts_succeeded=5, cost=25, warnings=0),
            id="200",
        ),
        pytest.param(
            [REJECTED],
            [AUTHENTICATED],
            "failed",
            replace(REPEATED, failed=1, attempts_failed=1),
            id="400",
        ),
        pytest.param(
            [UNAVAILABLE],
            [AUTHENTICATED],
            "unknown",
            replace(REPEATED, unknown=1, attempts_unknown=2),
            id="503",
        ),
        pytest.param(
            [],
            [REFUSED],
            # The repeat sent nothing, so its failed attempt changes nothing known about the
            # case's request: it's still unknown, by the attempt the repeat repeated.
            "unknown",
            replace(REPEATED, unknown=1, attempts_failed=1, provider_requests=5),
            id="authentication-401",
        ),
    ],
)
def test_a_repeat_is_counted_and_its_case_by_its_latest_attempt_that_may_have_been_charged(
    cli: Cli,
    experiments: Builder,
    sends: list[Reply],
    authenticates: list[Reply],
    outcome: str,
    expected: Expected,
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    first = experiments.run(
        EXAMPLE, out, sends=[returns(), returns(), UNAVAILABLE, returns(), returns()]
    )
    assert first.exit_code == 6

    repeated = experiments.run(
        EXAMPLE,
        out,
        "--repeat",
        repeat_option(first, HOLDINGS),
        sends=sends,
        authenticates=authenticates,
    )

    assert repeated.exit_code == (0 if outcome == "succeeded" else 6), repeated.stderr
    assert_counts(repeated, out, 2, expected)
    assert repeated.cases_by_key[HOLDINGS]["outcome"] == outcome
    assert outcome_shown(out, 2, HOLDINGS) == outcome
