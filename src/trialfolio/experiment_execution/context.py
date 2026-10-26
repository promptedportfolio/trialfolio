"""What an experiment's executor and three of its parts read, and none changes: the plan it runs,
how it was approved, the store, the clock, whether it's synthetic, the session's number, the
experiment's records when it resumes one, and the command; and the fields of its logs.
"""

from dataclasses import dataclass

from trialfolio.attempts import Clock
from trialfolio.contracts.common import Approval
from trialfolio.contracts.experiment_manifest import ExperimentCommandRecord
from trialfolio.experiment_records import AnyPlan, SavedExperiment
from trialfolio.storage import ArtifactStore


@dataclass(frozen=True)
class SessionContext:
    """One execution's inputs, which the executor, its writer, its case runner, and its manifest's
    builder share; its ledger takes only the plan and the experiment's records."""

    plan: AnyPlan
    """The plan the session runs: the current plan, or a revision of it."""
    approval: Approval
    store: ArtifactStore
    clock: Clock
    synthetic: bool
    session: int
    """The session's number: 1 for a new experiment, and otherwise after every session in the
    directory."""
    experiment: SavedExperiment | None
    """The experiment's records, for a resume; None for a new experiment."""
    command: ExperimentCommandRecord | None

    def log_fields(self, event: str, case_id: str | None = None) -> dict[str, str]:
        """A log record's fields: its event, and the plan by its hash and the case by its
        `case_id`, never by its key."""
        fields = {"event": event, "plan_hash": self.plan.plan_hash}
        if case_id is not None:
            fields["case_id"] = case_id
        return fields
