"""The messages that end an experiment's session (docs/contracts.md, the executor's
`execution.partial` and its endings without a manifest; a stale backtest).

- **`execution.partial`,** when the session reached its end with a planned case that didn't
  succeed: what happened to each, by its key in the message and by its `case_id` in the logged
  one, Portfolio123's own message for each whose error carries one, a stale backtest's message,
  why no later case started, that a case whose request may have reached Portfolio123 is sent
  again only by a confirmed repeat, and, for a setting Portfolio123 rejected, how to revise it.
- **The endings without a manifest:** before the first case, whether the first plan was
  recorded, so the directory can be resumed; and after an attempt, what the latest attempt's
  records say of its request, and what the records say of the manifest.

Nothing here writes or logs. Portfolio123's own text can repeat configuration values, so the
logged message never holds it.
"""

from collections.abc import Callable, Sequence
from typing import Final

from trialfolio.attempts import (
    ExperimentAttempt,
    ExperimentAttemptResult,
    RankingExperimentAttempt,
    record_detail,
)
from trialfolio.display import series
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_execution.cases import StopReason
from trialfolio.experiment_execution.ledger import Ledger
from trialfolio.experiment_records import AnyPlan, AnyPlanCase
from trialfolio.manifests import ManifestDetails, running_detail, updating_detail

MANIFEST_DETAILS: Final = ManifestDetails(
    written="The session's manifest was written, so the experiment's output is complete.",
    left=(
        "The session's manifest.json was published before the failure, and couldn't be removed,"
        " so the experiment reads as complete although the run failed."
    ),
    missing=(
        "The attempts recorded so far are kept. The session has no manifest, so the experiment's"
        " output reads as incomplete until running the same command again resumes it."
    ),
)
"""The sentences that say what the records hold of the session's manifest."""

_STOP_MESSAGES: Final[dict[StopReason, str]] = {
    "budget": (
        "The experiment's budget couldn't cover the next case, so it and the cases after it"
        " weren't started. A revision that raises budget.provider_requests lets them run."
    ),
    "authentication_budget": (
        "The experiment's budget of authentication calls is spent, so the next case, which"
        " would authenticate before its request, and the cases after it weren't started. A"
        " revision that raises budget.provider_requests, which sets the authentication calls"
        " too, lets them run."
    ),
    "authentication": (
        "Trial Folio's own authentication call failed, so no later case started: each would"
        " have failed the same way. Once the cause is fixed, running the same command again"
        " resumes the experiment, and runs the cases not started."
    ),
    "quota": (
        "Portfolio123 refused a request because the account's API quota or credits are"
        " exhausted, so no later case started: each would have been refused the same way. Once"
        " the account has credits again, running the same command again resumes the"
        " experiment, and runs the cases not started."
    ),
    "cancelled": (
        "The run was cancelled, so no later case started. Running it again, approved by the"
        " same hash, resumes the experiment, and runs the cases not started."
    ),
}


def partial(
    plan: AnyPlan, ledger: Ledger, stopped: tuple[StopReason, TrialFolioError | None] | None
) -> TrialFolioError | None:
    """`execution.partial` when a case of `plan` didn't succeed, with what happened to each,
    and why the session stopped, if `stopped` says it did."""
    missed = [case for case in plan.cases if ledger.outcome(case.case_id) != "succeeded"]
    if not missed:
        return None

    def listing(named: Callable[[AnyPlanCase], str]) -> str:
        return "; ".join(f"{named(case)}, {ledger.described(case.case_id)}" for case in missed)

    lead = f"{len(missed)} of the {len(plan.cases)} planned cases didn't succeed:"
    why = _why(stopped)
    charged = _charged(missed, ledger)
    # A stale backtest's message says why its response failed validation, by the case's key,
    # and its loggable message by its case_id (D-45).
    flagged = [failure for case in missed if (failure := ledger.flagged(case.case_id))]
    stale_said = "".join(f" {failure.message}" for failure in flagged)
    stale_logged = "".join(f" {failure.log_message}" for failure in flagged)
    # Portfolio123's own text can repeat configuration values, so logs never hold it. The
    # loggable message leaves out the revision's sentence too (D-38).
    said = _provider_said(missed, ledger)
    revise = _revise(missed, ledger)
    tail = " Every planned case is accounted for in the session's manifest."
    keys = listing(lambda c: f"`{c.case_key}`")
    return TrialFolioError(
        "execution.partial",
        f"{lead} {keys}.{said}{stale_said}{why}{charged}{revise}{tail}",
        f"{lead} {listing(lambda c: c.case_id)}.{stale_logged}{why}{charged}{tail}",
    )


def _why(stopped: tuple[StopReason, TrialFolioError | None] | None) -> str:
    """Why no later case started, with the error that stopped them, if any."""
    if stopped is None:
        return ""
    reason, error = stopped
    why = " " + _STOP_MESSAGES[reason]
    if error is not None:
        why += f" The error was {error.code}."
    return why


def _charged(missed: Sequence[AnyPlanCase], ledger: Ledger) -> str:
    """That a case whose request may have reached Portfolio123 is sent again only by a
    confirmed repeat, when a case awaits one."""
    if any(ledger.state(case.case_id) == "awaiting_repeat" for case in missed):
        return (
            " A case whose request may have reached Portfolio123 is never sent again"
            " automatically: a confirmed repeat sends it."
        )
    return ""


def _provider_said(missed: Sequence[AnyPlanCase], ledger: Ledger) -> str:
    """Portfolio123's own message for each case whose error carries one, by the case's key."""
    return "".join(
        f' Portfolio123\'s message for `{case.case_key}`: "{text}".'
        for case in missed
        if (text := ledger.provider_said(case.case_id)) is not None
    )


def _revise(missed: Sequence[AnyPlanCase], ledger: Ledger) -> str:
    """For each case that got `provider.unsupported_capability`, that a repeat sends the same
    request again, so the fix is to change the setting and revise the plan (D-38)."""
    rejected = [
        f"`{case.case_key}`"
        for case in missed
        if ledger.outcome_code(case.case_id) == "provider.unsupported_capability"
    ]
    if not rejected:
        return ""
    return (
        f" Portfolio123 rejected a setting of {series(rejected)}: a repeat sends the same"
        " request again, so change the setting instead, and revise the plan with"
        " --revision-reason."
    )


def before_cases(failure: TrialFolioError, *, recorded: bool) -> TrialFolioError:
    """The error of a session that stopped before its first case: nothing was sent. Its
    directory can be resumed only once its first plan's `experiment.json` is written, as
    `recorded` says."""
    if not recorded:
        detail = (
            "Nothing was sent. The experiment's first plan wasn't recorded, so its output is"
            " incomplete, and the directory can't be resumed: remove the directory, and run the"
            " command again."
        )
        return failure.with_detail(detail)
    detail = (
        "Nothing was sent. The session has no manifest, so the experiment's output reads as"
        " incomplete until running the same command again resumes it."
    )
    return failure.with_detail(detail)


def incomplete(
    failure: TrialFolioError,
    *,
    detail: str,
    manifest: str,
    last: ExperimentAttemptResult | None,
) -> TrialFolioError:
    """The error of a session that stopped without its manifest, with `detail`, what its
    records say. An attempt's own error already says what happened to its request, and so does
    its attempt record once it's written, so the error of `last`, the session's last attempt,
    when it wrote that record, gets only what the records say of the manifest, `manifest`."""
    if failure.message.endswith(detail):
        return failure
    if last is not None and last.recorded and failure is last.error:
        detail = manifest
    return failure.with_detail(detail)


def attempt_detail(
    current: ExperimentAttempt | RankingExperimentAttempt | None,
    results: Sequence[ExperimentAttemptResult],
) -> str:
    """What the records say of the request of `current`, the attempt under way, or else of the
    session's last attempt, among its `results`."""
    if current is not None and current.start_record is not None:
        ranking = isinstance(current, RankingExperimentAttempt)
        return running_detail("the attempt under way", ranking=ranking)
    if isinstance(current, RankingExperimentAttempt) and current.update_record is not None:
        return updating_detail("the attempt under way")
    if results:
        last = results[-1]
        record = last.record
        if not last.recorded:
            if last.start is not None:
                return running_detail("the last attempt", ranking=last.update is not None)
            if last.update is not None:
                return updating_detail("the last attempt")
            return "The last attempt's request wasn't sent."
        detail = record_detail(record)
        return f"Of the last attempt: {detail}"
    return "No case's request was sent."
