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
from dataclasses import dataclass
from typing import Final, Literal, TextIO

from trialfolio.contracts.plan import Budget, Plan, PlanSetting, RetryPolicy
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


def _shown(text: str) -> str:
    """`text` with each character a terminal could act on written as an escape, such as
    `\\u001b`."""
    return "".join(
        (f"\\u{ord(char):04x}" if ord(char) <= 0xFFFF else f"\\U{ord(char):08x}")
        if unicodedata.category(char) in _ESCAPED_CATEGORIES
        else char
        for char in text
    )


def _json_lines(value: object, *, indent: int | None = None) -> list[str]:
    # json.dumps escapes every line break inside text, so each "\n" in its output is its own.
    return [
        _shown(line) for line in json.dumps(value, ensure_ascii=False, indent=indent).split("\n")
    ]


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _budget_lines(budget: Budget) -> list[str]:
    source = budget.credits_per_request_source
    return [
        (
            f"Budget: at most {_count(budget.provider_requests, 'provider request')}, each sent "
            f"at most once: {_count(budget.credits, 'credit')} at Portfolio123's documented cost "
            f"of {budget.credits_per_request} per request ({_shown(source.title)}, checked "
            f"{source.checked.isoformat()})."
        ),
        "  A request that reaches Portfolio123 may be charged even if it fails.",
        (
            f"  At most {_count(budget.authentication_calls, 'authentication call')}, whose cost "
            "isn't documented. Authentication cost no credits when last measured, and the "
            "credits above leave it out."
        ),
    ]


def _retry_lines(policy: RetryPolicy) -> list[str]:
    return [
        (
            f"Retries: {policy.automatic_retries} automatic. Trial Folio never resends a request "
            "on its own; running the command again is a new attempt."
        ),
        (
            f"  p123api makes {_count(policy.wrapper_attempts_per_call, 'HTTP attempt')} per "
            f"call, and Trial Folio allows {_count(policy.exchanges_per_call, 'exchange')} per "
            "call, so it refuses p123api's re-authentication after a 401 or 403, and any "
            "redirect."
        ),
    ]


def _setting_line(row: PlanSetting) -> list[str]:
    value: object = row.model_dump(mode="json")["value"]
    shown = _shown(value) if isinstance(value, str) else _json_lines(value)[0]
    if row.unit is not None:
        shown = f"{shown} {row.unit}"
    notes = [row.expected_provenance]
    if "inferred_default" in row.flags:
        notes.append("inferred default")
    if "not_snapshotted" in row.flags:
        notes.append("not snapshotted: it names an object in the account, which can change")
    if value == "not_modeled":
        notes.append("not modeled by this provider path")
    if value == "not_sent":
        notes.append("not sent, and Portfolio123's default isn't documented")
    lines = [f"  {row.setting}: {shown} ({'; '.join(notes)})"]
    if row.inference_rule is not None:
        lines.append(f"      Rule: {_shown(row.inference_rule)}")
    return lines


def format_plan(plan: Plan) -> str:
    """The full plan display: the title and purpose, the request exactly as it will be sent,
    every resolved setting with its expected provenance and markings, the budget, the retry
    policy, the data sent, and the plan hash with how to approve it. It holds configuration
    values and formulas, so it's for a terminal only, never a log."""
    shown_hash = plan_hash(plan)
    purpose = "none declared" if plan.purpose is None else _shown(plan.purpose)
    lines = [
        f"Plan {shown_hash}",
        "",
        f"Title: {_shown(plan.title)}",
        f"Purpose: {purpose}",
    ]
    for case in plan.cases:
        lines += ["", f"Case {case.case_id}"]
        for request in case.requests:
            params = request.params.model_dump(mode="json")
            lines += [
                (
                    f"The request, exactly as p123api's {request.operation} will send it to "
                    "Portfolio123:"
                ),
                *(f"  {line}" for line in _json_lines(params, indent=2)),
            ]
        lines.append("Settings, with the provenance each value will have once it's sent:")
        for row in case.settings:
            lines += _setting_line(row)
    lines += ["", *_budget_lines(plan.budget), "", *_retry_lines(plan.retry_policy), ""]
    lines.append("Data sent to Portfolio123, through p123api:")
    for entry in plan.data_sent:
        carried = (
            ", ".join(entry.settings)
            if entry.settings
            else "the API ID and key, to authenticate; they're never recorded"
        )
        lines.append(f"  {entry.category}: {carried}")
    lines += [
        (
            "  Nothing else is sent: not the title, the purpose, data_vendor, the configuration "
            "file, file paths, earlier results, or logs."
        ),
        "",
        f"Plan hash: {shown_hash}",
        (
            f"Approve it by typing {APPROVE_ANSWER} when asked in a terminal, or with --approve "
            f"{shown_hash}"
        ),
    ]
    return "\n".join(lines) + "\n"


def format_plan_summary(plan: Plan, *, full_plan_hint: bool) -> str:
    """The plan hash and the budget, and nothing from the configuration. With
    `full_plan_hint`, it also says how to see the full plan."""
    lines = [f"Plan hash: {plan_hash(plan)}", *_budget_lines(plan.budget)]
    if full_plan_hint:
        lines.append("Run the command in a terminal to see the full plan.")
    return "\n".join(lines) + "\n"


def _write(stderr: TextIO, text: str) -> None:
    stderr.write(text)
    stderr.flush()


def _not_approved(shown_hash: str, reason: str) -> TrialFolioError:
    return TrialFolioError(
        "plan.approval_required",
        f"{reason} Nothing was sent, and no output was created. To approve this plan, run the "
        f"command again with --approve {shown_hash}, or run it without --approve in a terminal "
        f"and type {APPROVE_ANSWER}.",
    )


def obtain_approval(plan: Plan, approve: str | None, *, stdin: TextIO, stderr: TextIO) -> Approval:
    """Shows the plan on `stderr`, and obtains its approval: from `approve`, the value of
    `--approve`, or else by asking on a terminal (approval).

    - With `approve`, it never asks. A value that's exactly the plan's hash approves it, with
      the method `option`, and only the hash and the budget are shown.
    - Without it, when `stdin` and `stderr` are both terminals, it shows the full plan and asks
      the user to type `approve`, which approves the plan shown, with the method `interactive`.
      Any other answer, an empty line, or the end of input is a refusal.

    Raises `TrialFolioError` with `plan.approval_required` when the plan isn't approved, once
    the plan hash has been shown, with the full plan when `stderr` is a terminal. The message
    gives the exact option that approves this plan. A `KeyboardInterrupt` while it asks is left
    to the caller.
    """
    shown_hash = plan_hash(plan)
    on_terminal = stderr.isatty()
    if approve is not None:
        try:
            approved = check_approval(plan, approve)
        except TrialFolioError:
            text = (
                format_plan(plan) if on_terminal else format_plan_summary(plan, full_plan_hint=True)
            )
            _write(stderr, text)
            raise _not_approved(
                shown_hash,
                "The hash given with --approve isn't this plan's hash. Approval takes the full "
                "hash, exactly as shown.",
            ) from None
        _write(stderr, format_plan_summary(plan, full_plan_hint=False))
        return Approval(approved, "option")
    if on_terminal and stdin.isatty():
        _write(stderr, format_plan(plan))
        _write(stderr, f"\nType {APPROVE_ANSWER} to run this plan, or anything else to stop: ")
        answer = stdin.readline().removesuffix("\n").removesuffix("\r")
        if answer != APPROVE_ANSWER:
            raise _not_approved(
                shown_hash, f"The plan wasn't approved: the answer wasn't {APPROVE_ANSWER}."
            )
        return Approval(check_approval(plan, shown_hash), "interactive")
    _write(
        stderr,
        format_plan(plan) if on_terminal else format_plan_summary(plan, full_plan_hint=True),
    )
    raise _not_approved(
        shown_hash,
        "Running a plan needs its approval. Without --approve, Trial Folio asks for it only "
        "when stdin and stderr are both terminals.",
    )
