"""The experiment report's case ledger, its section 5: every case of the experiment, with its
outcome and its attempts (release 0.3.0, R03-T10).

`ledger` gives the section's parts: the counts, and the session's facts; each case of the current
plan, in the plan's order, whatever its outcome; each case awaiting a repeat, with the option that
repeats it; each retired case; every attempt, by case; and the versions. `variant_change` and
`case_description` describe a case as the report's other tables of cases do too.
"""

from collections.abc import Sequence

from trialfolio.contracts.attempt import AttemptRecordV1_1, Exchange
from trialfolio.contracts.experiment_plan import PlanVariant
from trialfolio.notices import LICENSE_ID, NOTICE_VERSION
from trialfolio.report.evidence import CaseView, ExperimentContext, RetiredCaseView
from trialfolio.report.fragments import (
    attempt_counts,
    budget_limit,
    plan_versions,
    rendered_by,
    reported_cost,
)
from trialfolio.report.page import code, facts, moment, table, text
from trialfolio.report.vocabulary import EXCHANGE_RESULTS, EXPERIMENT_APPROVALS


def ledger(experiment: ExperimentContext) -> list[str]:
    """Section 5's parts, after its heading."""
    cases = experiment.evidence.counts.cases
    rows = [
        f"<tr><td>{code(view.case.case_key)}</td><td>{code(view.case.case_id)}</td>"
        f"<td>{variant_change(view.case.variant)}</td>"
        f"<td>{case_description(view.case.description)}</td>"
        f"<td>{_outcome(experiment, view)}</td><td>{_attempt_count(view.attempts)}</td></tr>"
        for view in experiment.cases
    ]
    return [
        (
            f"<p>Planned cases: {cases.planned} = {cases.succeeded} succeeded +"
            f" {cases.failed} failed + {cases.skipped} skipped + {cases.unknown} unknown +"
            f" {cases.not_yet_run} not yet run. Every case of the current plan appears below,"
            " in the plan's order, whatever its outcome, and so does every case a revision"
            " retired, with all its attempts.</p>"
        ),
        *_synthetic_records(experiment),
        *facts(_session_facts(experiment)),
        "<h3>Planned cases</h3>",
        *table(("Case", "case_id", "Change", "Description", "Outcome", "Attempts"), rows),
        *_awaiting(experiment),
        *_retired(experiment),
        *_attempts(experiment),
        *_versions(experiment),
    ]


def variant_change(variant: PlanVariant | None) -> str:
    if variant is None:
        return "The baseline"
    if variant.value is not None:
        default = ", the default rebalance variant" if variant.default else ""
        return f"{code(variant.setting)} set to {code(str(variant.value))}{default}"
    if variant.add is not None:
        return f"Adds the rule {code(variant.add)}"
    return f"Replaces the rule {code(variant.replace or '')} with {code(variant.with_ or '')}"


def case_description(description: str | None) -> str:
    return "" if description is None else text(description)


def _session_facts(experiment: ExperimentContext) -> list[tuple[str, str]]:
    evidence = experiment.evidence
    plan = evidence.plan
    budget = plan.budget
    counts = evidence.counts
    attempts = counts.attempts
    return [
        ("Plan", f"Plan {evidence.plan_number}, {code(plan.plan_hash)}, the current plan"),
        ("Approval", EXPERIMENT_APPROVALS[evidence.approval]),
        (
            "Budget",
            (
                f"{budget.provider_requests} provider requests, {budget_limit(budget)}, and at most"
                f" {budget.authentication_calls} authentication calls, for every run of the"
                " experiment."
            ),
        ),
        (
            "Counted against the budget",
            (
                f"Provider requests: {counts.provider_requests} of the budget's"
                f" {counts.budget.provider_requests}. Authentication calls:"
                f" {counts.authentication_calls} of its {counts.budget.authentication_calls}. Each"
                " counts every attempt of the experiment. A provider request is a send that may"
                " have reached Portfolio123, which may be charged even when it fails."
            ),
        ),
        attempt_counts(attempts),
        (
            "Repeats",
            f"{attempts.repeats}: the attempts that repeat a case, each after a confirmation",
        ),
        ("Retired cases", str(counts.retired_cases)),
        ("Retries", str(counts.retries)),
        ("Cost", _cost(experiment)),
    ]


def _cost(experiment: ExperimentContext) -> str:
    cost = experiment.evidence.counts.cost
    if cost is not None and experiment.synthetic:
        return f"{cost} credits, as the invented responses report: nothing was charged"
    return reported_cost(cost)


def _synthetic_records(experiment: ExperimentContext) -> list[str]:
    if not experiment.synthetic:
        return []
    return [
        (
            "<p>The experiment is synthetic, so its attempts, their exchanges, and the counts"
            " below are invented, as a real experiment would record them. Nothing was sent"
            " to Portfolio123, and nothing was charged.</p>"
        )
    ]


def _outcome(experiment: ExperimentContext, view: CaseView) -> str:
    """The case's outcome, with the error code of the attempt that gives it, what it means,
    and whether it awaits a repeat or a resume sends it."""
    outcome = view.outcome
    error = _outcome_code(view)
    shown = code(outcome) + (f" ({code(error)})" if error is not None else "")
    if outcome == "succeeded":
        response = "invented response" if experiment.synthetic else "response"
        meaning = f"its {response} was saved and normalized."
    elif view.invalid is not None:
        meaning = "its response was saved, but couldn't be normalized."
    elif view.repeat_attempt is not None:
        if outcome == "unknown":
            meaning = "its request may have been charged, and no response was saved."
        else:
            meaning = "its request may have reached Portfolio123, and may have been charged."
        meaning += " Awaiting a repeat."
    elif outcome == "failed":
        meaning = (
            "no attempt's request could have reached Portfolio123. A resume sends it, within"
            " the budget."
        )
    else:
        meaning = "it has no attempt. A resume sends it, within the budget."
    return f"{shown}: {meaning}"


def _outcome_code(view: CaseView) -> str | None:
    """The error code that gives a case's outcome: its response's `provider.response_invalid`,
    or the error of its latest possibly charged attempt, or else of its latest attempt."""
    if view.invalid is not None:
        return view.invalid.code
    if view.outcome in ("succeeded", "not_yet_run"):
        return None
    charged = [attempt for attempt in view.attempts if attempt.possibly_charged]
    latest = (charged or list(view.attempts))[-1]
    return None if latest.error is None else latest.error.code


def _attempt_count(attempts: Sequence[AttemptRecordV1_1]) -> str:
    repeats = sum(attempt.repeat_of is not None for attempt in attempts)
    if not repeats:
        return str(len(attempts))
    return f"{len(attempts)}, {repeats} of them {'a repeat' if repeats == 1 else 'repeats'}"


def _awaiting(experiment: ExperimentContext) -> list[str]:
    awaiting = [
        (view, attempt) for view in experiment.cases if (attempt := view.repeat_attempt) is not None
    ]
    parts = ["<h3>Cases awaiting a repeat</h3>"]
    if not awaiting:
        return [
            *parts,
            (
                "<p>None: no planned case has a request that may have been charged without"
                " succeeding.</p>"
            ),
        ]
    items = [_awaiting_item(experiment, view, attempt) for view, attempt in awaiting]
    if experiment.synthetic:
        how = (
            " <code>trialfolio run</code> doesn't resume a synthetic experiment: only Trial"
            " Folio's core repeats a case of one, with the demo's client, given the attempt"
            " below."
        )
    else:
        how = (
            " Running the experiment again with the option given below for a case, and the"
            " plan's approval, repeats it: the option confirms the possible repeat charge, by"
            " naming the attempt."
        )
    return [
        *parts,
        (
            "<p>A case awaiting a repeat has an attempt whose request may have reached"
            " Portfolio123, and so may have been charged, and no attempt that succeeded. A"
            " resume never sends its request again on its own. A repeat sends it again, as a"
            " new attempt of the same case, which may be charged again, and counts against"
            " the budget. Each case is listed with its latest attempt whose request may have"
            f" been charged.{how}</p>"
        ),
        "<ul>",
        *items,
        "</ul>",
    ]


def _awaiting_item(
    experiment: ExperimentContext, view: CaseView, attempt: AttemptRecordV1_1
) -> str:
    """A case awaiting a repeat, with its latest possibly charged attempt, and, unless the
    experiment is synthetic, the option that repeats it."""
    error = "" if attempt.error is None else f" ({code(attempt.error.code)})"
    lead = (
        f"{code(view.case.case_key)}, {code(view.case.case_id)}: attempt"
        f" {code(str(attempt.attempt_id))}, {code(attempt.outcome)}{error}."
    )
    if experiment.synthetic:
        return f"<li>{lead}</li>"
    option = f"--repeat {view.case.case_key}:{attempt.attempt_id}"
    return f"<li>{lead} The option that repeats it: {code(option)}</li>"


def _retired(experiment: ExperimentContext) -> list[str]:
    retired = experiment.evidence.retired
    parts = ["<h3>Retired cases</h3>"]
    if not retired:
        return [*parts, "<p>None: no revision retired a case.</p>"]
    rows = [
        f"<tr><td>{code(view.case.case_key)}</td><td>{code(view.case.case_id)}</td>"
        f"<td>{variant_change(view.case.variant)}</td>"
        f"<td>{case_description(view.case.description)}</td><td>{view.case.plan}</td>"
        f"<td>{code(view.outcome)}</td><td>{_attempt_count(view.attempts)}</td></tr>"
        for view in retired
    ]
    heads = ("Case", "case_id", "Change", "Description", "Last plan", "Outcome", "Attempts")
    return [
        *parts,
        (
            "<p>Each case an earlier plan included and the current plan doesn't, with the key,"
            " description, and change it had in the last plan that included it. It and its"
            " attempts stay in the record, and the budget counts its attempts.</p>"
        ),
        *table(heads, rows),
    ]


def _attempts(experiment: ExperimentContext) -> list[str]:
    parts = [
        "<h3>Attempts</h3>",
        (
            "<p>Every attempt of the experiment, by case: the current plan's cases in its"
            " order, then the retired cases. A case's attempts are in the order they were"
            " made: by session, and then by their place in the session. A repeat names the"
            " attempt whose possible charge its confirmation acknowledged.</p>"
        ),
    ]
    views: list[tuple[str, CaseView | RetiredCaseView]] = [
        *(("", view) for view in experiment.cases),
        *((" (retired)", view) for view in experiment.evidence.retired),
    ]
    if not any(view.attempts for _, view in views):
        return [*parts, "<p>The experiment has no attempt yet.</p>"]
    heads = (
        "Attempt",
        "Session · place",
        "Plan",
        "Started",
        "Outcome",
        "Possibly charged",
        "Error",
        "Repeats",
        "Exchanges",
    )
    for retired, view in views:
        if not view.attempts:
            continue
        caption = f"{code(view.case.case_key)}{retired}, {code(view.case.case_id)}"
        rows = [_attempt_row(experiment, attempt) for attempt in view.attempts]
        parts.extend(table(heads, rows, caption=caption))
    return parts


def _attempt_row(experiment: ExperimentContext, attempt: AttemptRecordV1_1) -> str:
    plan = experiment.plan_numbers.get(attempt.plan_hash)
    error = (
        ""
        if attempt.error is None
        else f"{code(attempt.error.code)}: {text(attempt.error.message)}"
    )
    repeats = "" if attempt.repeat_of is None else f"Repeats attempt {code(str(attempt.repeat_of))}"
    exchanges = "<br>".join(_exchange(exchange) for exchange in attempt.exchanges) or "None"
    return (
        f'<tr><td class="long">{code(str(attempt.attempt_id))}</td>'
        f"<td>{attempt.session} · {attempt.sequence}</td>"
        f"<td>{plan if plan is not None else code(attempt.plan_hash)}</td>"
        f"<td>{moment(attempt.started_at)}</td><td>{code(attempt.outcome)}</td>"
        f"<td>{'Yes' if attempt.possibly_charged else 'No'}</td><td>{error}</td>"
        f'<td class="long">{repeats}</td><td>{exchanges}</td></tr>'
    )


def _exchange(exchange: Exchange) -> str:
    result = EXCHANGE_RESULTS[exchange.result]
    status = "" if exchange.status is None else f" {exchange.status}"
    note = "" if exchange.note is None else f", {code(exchange.note)}"
    return f"{code(exchange.request)}: {result}{status}{note}"


def _versions(experiment: ExperimentContext) -> list[str]:
    plan = experiment.plan
    command = experiment.evidence.command
    if command is not None:
        written = (
            f"Trial Folio {text(plan.trialfolio_version)}, command {code(command.name)},"
            f" started {moment(command.started_at)}"
        )
    elif experiment.synthetic:
        written = (
            f"Trial Folio {text(plan.trialfolio_version)}, through its core, with the demo's"
            " client: no <code>trialfolio</code> command writes a synthetic experiment"
        )
    else:
        written = (
            f"Trial Folio {text(plan.trialfolio_version)}, through its core, for an"
            " interface other than the <code>trialfolio</code> commands"
        )
    entries = [
        ("Session written by", written),
        *plan_versions(plan),
        (
            "License and notice",
            f"Recorded with the session: {code(LICENSE_ID)}, notice version {NOTICE_VERSION}",
        ),
        rendered_by(experiment.version),
    ]
    return ["<h3>Versions</h3>", *facts(entries)]
