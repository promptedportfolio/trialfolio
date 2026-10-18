"""Plans and approval, the CLI's side: the plan display, and how the CLI obtains the approved hash
(docs/contracts.md, approval).

The core (`trialfolio.planning`) builds plans and checks approvals, and never prompts. This
module writes the plan display to stderr directly, never through logging, because it holds
configuration values and formulas. For the same reason it shows the full plan only when stderr is
a terminal: when it asks for confirmation, and when approval fails. Otherwise, and with a matching
`--approve`, it shows only the plan hash and the budget.

Text from the configuration is shown with its control and formatting characters escaped, so a
title or formula can't move the cursor, clear the terminal, or reorder what's shown.
"""

import json
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal, TextIO

from trialfolio.contracts.experiment_plan import PlanBudgetV1_1
from trialfolio.contracts.plan import (
    Budget,
    DataSent,
    Plan,
    PlanRequest,
    PlanSetting,
    RetryPolicy,
)
from trialfolio.contracts.ranking_snapshot import (
    RankGetRequest,
    RankingSnapshotPlan,
    SnapshotDataSent,
)
from trialfolio.errors import TrialFolioError
from trialfolio.planning import check_approval, plan_hash

APPROVE_ANSWER: Final = "approve"
"""What the user types to approve the plan shown. Any other answer is a refusal."""

ApprovalMethod = Literal["interactive", "option"]
"""How a plan was approved, as the manifest records it."""


@dataclass(frozen=True)
class Approval:
    """An approved plan's hash, and how it was approved."""

    plan_hash: str
    method: ApprovalMethod


_ESCAPED_CATEGORIES: Final = frozenset({"Cc", "Cf", "Zl", "Zp"})
"""Control and formatting characters, and the line and paragraph separators."""


def shown(text: str) -> str:
    """`text` with each character a terminal could act on written as an escape, such as
    `\\u001b`."""
    return "".join(
        (f"\\u{ord(char):04x}" if ord(char) <= 0xFFFF else f"\\U{ord(char):08x}")
        if unicodedata.category(char) in _ESCAPED_CATEGORIES
        else char
        for char in text
    )


def json_lines(value: object, *, indent: int | None = None) -> list[str]:
    """`value` as JSON, one line of text to an item, each line shown as `shown` shows text."""
    # json.dumps escapes every line break inside text, so each "\n" in its output is its own.
    return [
        shown(line) for line in json.dumps(value, ensure_ascii=False, indent=indent).split("\n")
    ]


def counted(number: int, noun: str) -> str:
    """`number` and `noun`, in the plural unless it's 1."""
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def budget_lines(budget: Budget | PlanBudgetV1_1) -> list[str]:
    """The budget, as the plan display shows it: the requests and their credits at the
    documented cost, that a request may be charged even if it fails, and the authentication
    calls."""
    source = budget.credits_per_request_source
    return [
        (
            f"Budget: at most {counted(budget.provider_requests, 'provider request')}, each sent "
            f"at most once: {counted(budget.credits, 'credit')} at Portfolio123's documented cost "
            f"of {budget.credits_per_request} per request ({shown(source.title)}, checked "
            f"{source.checked.isoformat()})."
        ),
        "  A request that reaches Portfolio123 may be charged even if it fails.",
        (
            f"  At most {counted(budget.authentication_calls, 'authentication call')}, whose cost "
            "isn't documented. Authentication cost no credits when last measured, and the "
            "credits above leave it out."
        ),
    ]


def retry_lines(policy: RetryPolicy) -> list[str]:
    """The retry policy, as the plan display shows it."""
    return [
        (
            f"Retries: {policy.automatic_retries} automatic. Trial Folio never resends a request "
            "on its own; running the command again is a new attempt."
        ),
        (
            f"  p123api makes {counted(policy.wrapper_attempts_per_call, 'HTTP attempt')} per "
            f"call, and Trial Folio allows {counted(policy.exchanges_per_call, 'exchange')} per "
            "call, so it refuses p123api's re-authentication after a 401 or 403, and any "
            "redirect."
        ),
    ]


def setting_lines(row: PlanSetting) -> list[str]:
    """A resolved setting with its expected provenance and markings, as the plan display shows
    it, and its inference rule, if it has one."""
    value: object = row.model_dump(mode="json")["value"]
    text = shown(value) if isinstance(value, str) else json_lines(value)[0]
    if row.unit is not None:
        text = f"{text} {row.unit}"
    notes = [row.expected_provenance]
    if "inferred_default" in row.flags:
        notes.append("inferred default")
    if "not_snapshotted" in row.flags:
        notes.append("not snapshotted: it names an object in the account, which can change")
    if value == "not_modeled":
        notes.append("not modeled by this provider path")
    if value == "not_sent":
        notes.append("not sent, and Portfolio123's default isn't documented")
    lines = [f"  {row.setting}: {text} ({'; '.join(notes)})"]
    if row.inference_rule is not None:
        lines.append(f"      Rule: {shown(row.inference_rule)}")
    return lines


def request_lines(
    requests: Sequence[PlanRequest] | Sequence[RankGetRequest], indent: str = ""
) -> list[str]:
    """Each request of a case, exactly as it will be sent."""
    lines: list[str] = []
    for request in requests:
        params = request.params.model_dump(mode="json")
        lines += [
            (
                f"{indent}The request, exactly as p123api's {request.operation} will send it to "
                "Portfolio123:"
            ),
            *(f"{indent}  {line}" for line in json_lines(params, indent=2)),
        ]
    return lines


def data_sent_lines(
    data_sent: Sequence[DataSent] | Sequence[SnapshotDataSent], not_sent: str
) -> list[str]:
    """The data sent, its recipient, and what isn't sent: `not_sent`, and earlier results and
    logs."""
    lines = ["Data sent to Portfolio123, through p123api:"]
    for entry in data_sent:
        carried = (
            ", ".join(entry.settings)
            if entry.settings
            else "the API ID and key, to authenticate; they're never recorded"
        )
        lines.append(f"  {entry.category}: {carried}")
    lines.append(f"  Nothing else is sent: not {not_sent}, earlier results, or logs.")
    return lines


def read_answer(stdin: TextIO) -> str | None:
    """The line typed, without its line ending, or None when it isn't text in `stdin`'s
    encoding. The end of input is an empty answer."""
    try:
        return stdin.readline().removesuffix("\n").removesuffix("\r")
    except UnicodeDecodeError:  # It isn't text, so it isn't an answer either.
        return None


def format_plan(plan: Plan) -> str:
    """The full plan display: the title and purpose, the request exactly as it will be sent,
    every resolved setting with its expected provenance and markings, the budget, the retry
    policy, the data sent, and the plan hash with how to approve it. It holds configuration
    values and formulas, so it's for a terminal only, never a log."""
    shown_hash = plan_hash(plan)
    purpose = "none declared" if plan.purpose is None else shown(plan.purpose)
    lines = [
        f"Plan {shown_hash}",
        "",
        f"Title: {shown(plan.title)}",
        f"Purpose: {purpose}",
    ]
    for case in plan.cases:
        lines += ["", f"Case {case.case_id}", *request_lines(case.requests)]
        lines.append("Settings, with the provenance each value will have once it's sent:")
        for row in case.settings:
            lines += setting_lines(row)
    lines += ["", *budget_lines(plan.budget), "", *retry_lines(plan.retry_policy), ""]
    lines += data_sent_lines(
        plan.data_sent, "the title, the purpose, data_vendor, the configuration file, file paths"
    )
    lines += [
        "",
        f"Plan hash: {shown_hash}",
        (
            f"Approve it by typing {APPROVE_ANSWER} when asked in a terminal, or with --approve "
            f"{shown_hash}"
        ),
    ]
    return "\n".join(lines) + "\n"


def format_snapshot_plan(plan: RankingSnapshotPlan) -> str:
    """The full display of a ranking snapshot's plan (ranking snapshot output): the system's name,
    the request exactly as it will be sent, the budget, that nothing is written to the account,
    the retry policy, the data sent, and the plan hash with how to approve it. It holds the
    configuration's text, so it's for a terminal only, never a log."""
    shown_hash = plan_hash(plan)
    lines = [
        f"Ranking snapshot plan {shown_hash}",
        "",
        f"Ranking system: {shown(plan.system)}",
        (
            "It reads the ranking system saved in the account by this name, with one rank_get, and"
            " saves its definition, as Portfolio123 holds it, in a ranking snapshot. It writes"
            " nothing to the account."
        ),
        "",
        *request_lines(plan.requests),
        "p123api sends these params as the query of GET /rank.",
        "",
        *budget_lines(plan.budget),
        "",
        *retry_lines(plan.retry_policy),
        "",
        *data_sent_lines(plan.data_sent, "the configuration file, file paths"),
        "",
        f"Plan hash: {shown_hash}",
        (
            f"Approve it by typing {APPROVE_ANSWER} when asked in a terminal, or with --approve "
            f"{shown_hash}"
        ),
    ]
    return "\n".join(lines) + "\n"


def _full_plan(plan: Plan | RankingSnapshotPlan) -> str:
    """The full display of a screen's plan, or of a snapshot's."""
    if isinstance(plan, RankingSnapshotPlan):
        return format_snapshot_plan(plan)
    return format_plan(plan)


def format_plan_summary(plan: Plan | RankingSnapshotPlan, *, full_plan_hint: bool) -> str:
    """The plan hash and the budget, and nothing from the configuration. With
    `full_plan_hint`, it also says how to see the full plan."""
    lines = [f"Plan hash: {plan_hash(plan)}", *budget_lines(plan.budget)]
    if full_plan_hint:
        lines.append("Run the command in a terminal to see the full plan.")
    return "\n".join(lines) + "\n"


def write_shown(stderr: TextIO, text: str) -> None:
    """Writes `text` to `stderr` directly, never through logging, and flushes it."""
    stderr.write(text)
    stderr.flush()


def _not_approved(shown_hash: str, reason: str) -> TrialFolioError:
    return TrialFolioError(
        "plan.approval_required",
        f"{reason} Nothing was sent, and no output was created. To approve this plan, run the "
        f"command again with --approve {shown_hash}, or run it without --approve in a terminal "
        f"and type {APPROVE_ANSWER}.",
    )


def obtain_approval(
    plan: Plan | RankingSnapshotPlan,
    approve: str | None,
    *,
    stdin: TextIO,
    stderr: TextIO,
    refused: str | None = None,
) -> Approval:
    """Shows the plan on `stderr`, a screen's or a ranking snapshot's, and obtains its approval:
    from `approve`, the value of `--approve`, or else by asking on a terminal (approval).

    - With `approve`, it never asks. A value that's exactly the plan's hash approves it, with
      the method `option`, and only the hash and the budget are shown.
    - Without it, when `stdin` and `stderr` are both terminals, it shows the full plan and asks
      the user to type `approve`, which approves the plan shown, with the method `interactive`.
      Any other answer, a line that isn't text in `stdin`'s encoding, an empty line, or the end
      of input is a refusal.

    Raises `TrialFolioError` with `plan.approval_required` when the plan isn't approved, once
    the plan hash has been shown, with the full plan when `stderr` is a terminal. The message
    gives the exact option that approves this plan. A `KeyboardInterrupt` while it asks is left
    to the caller. With `refused`, the reason the command can't run this plan, such as an option
    only an experiment takes, it doesn't ask, and raises it with that reason, as when approval
    fails.
    """
    shown_hash = plan_hash(plan)
    on_terminal = stderr.isatty()
    if refused is not None:
        write_shown(
            stderr,
            _full_plan(plan) if on_terminal else format_plan_summary(plan, full_plan_hint=True),
        )
        raise _not_approved(shown_hash, refused)
    if approve is not None:
        try:
            approved = check_approval(plan, approve)
        except TrialFolioError:
            text = (
                _full_plan(plan) if on_terminal else format_plan_summary(plan, full_plan_hint=True)
            )
            write_shown(stderr, text)
            raise _not_approved(
                shown_hash,
                "The hash given with --approve isn't this plan's hash. Approval takes the full "
                "hash, exactly as shown.",
            ) from None
        write_shown(stderr, format_plan_summary(plan, full_plan_hint=False))
        return Approval(approved, "option")
    if on_terminal and stdin.isatty():
        write_shown(stderr, _full_plan(plan))
        write_shown(stderr, f"\nType {APPROVE_ANSWER} to run this plan, or anything else to stop: ")
        if read_answer(stdin) != APPROVE_ANSWER:
            raise _not_approved(
                shown_hash, f"The plan wasn't approved: the answer wasn't {APPROVE_ANSWER}."
            )
        return Approval(check_approval(plan, shown_hash), "interactive")
    write_shown(
        stderr,
        _full_plan(plan) if on_terminal else format_plan_summary(plan, full_plan_hint=True),
    )
    raise _not_approved(
        shown_hash,
        "Running a plan needs its approval. Without --approve, Trial Folio asks for it only "
        "when stdin and stderr are both terminals.",
    )
