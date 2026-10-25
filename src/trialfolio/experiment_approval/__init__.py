"""An experiment's plan display, its approval, and the confirmation of its repeats: the CLI's side
of running an experiment (docs/contracts.md, running an experiment, experiment plans and
revisions, and repeating a case).

The core builds the plan, reads and checks the experiment's records, and checks the approval and
the repeats again, and never prompts. This package, as `trialfolio.approval` does for a screen:

- **Shows the plan** on stderr directly, never through logging, because it holds configuration
  values: the full plan only when stderr is a terminal, when it asks for approval and when
  approval fails, and otherwise only the plan hash and the budget. For a resume, the full plan
  shows the experiment's progress too: each case's outcome so far, each case awaiting a repeat
  with the option that repeats it, the retired cases, and the budget counted so far. For a
  revision, it shows what changed from the current plan, and the reason.
- **Checks the reason and the repeats** against the plan and the records (step 5): a reason
  needs a revision, and each `--repeat` a case of the plan that can be repeated.
- **Obtains the approval** (step 6): the plan's hash, from `--approve` or by typing `approve` on
  a terminal; for a revision, with a reason, or the command fails with `plan.changed`.
- **Confirms the repeats** that `--repeat` names without an attempt ID, by typing `repeat` on a
  terminal, and passes on the attempts it showed.

Text from the configuration, and the reason, is shown with its control and formatting
characters escaped. Each error's loggable message names a case by its `case_id`, never by its
key, which is the user's text.

The package's modules, each importing only those before it: `run`, what a run of the
configuration builds before its approval, which the others read; `display`, the full plan and
its summary; `repeats`, the check and the confirmation of the repeats; and `approval`, the steps
in their order.

From release 0.4.0, a plan 1.3.0, whose baseline's ranking is a definition, shows more (plans with
a ranking definition, the display): that the run overwrites `ApiRankingSystem`, what the ranking
lock does and doesn't exclude, the definition's source, each node's weight among the baseline's
settings, each ranking variant's change, each case's `rank_update` with its whole definition as
text, and the budget with each operation's documented cost, what a case's attempt costs, and, in
a resume, the most the requests counted so far can have cost apart from the most the remaining
ones can cost. Each case's attempt sends two requests, so the budget the display and the repeat's
prompt count covers half as many cases (R04-T12). A resume that sends no case says so in place of
the line that the run overwrites `ApiRankingSystem`, on a terminal or not (D-45).

A case whose succeeded attempt's response failed validation awaits a repeat, which names that
attempt, and the display and the repeat's prompt say that its response failed validation, rather
than that its request may have been charged without succeeding (D-45).

It imports the modules that read an experiment's records, which import `p123api`, so the CLI
imports it only once `installed_versions` has checked them.
"""

from trialfolio.experiment_approval.approval import ExperimentApproval, approve_experiment
from trialfolio.experiment_approval.display import format_experiment_plan, format_experiment_summary
from trialfolio.experiment_approval.repeats import REPEAT_ANSWER
from trialfolio.experiment_approval.run import AnySavedCase, ExperimentRun, RepeatOption

__all__ = [
    "REPEAT_ANSWER",
    "AnySavedCase",
    "ExperimentApproval",
    "ExperimentRun",
    "RepeatOption",
    "approve_experiment",
    "format_experiment_plan",
    "format_experiment_summary",
]
