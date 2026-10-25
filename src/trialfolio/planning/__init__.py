"""Plans and approval, the core's side (docs/contracts.md, plans and approval).

The core builds plans and checks approvals, and never prompts. `trialfolio.approval` is the
CLI's side: it shows the plan and obtains the approved hash.

The package's modules, each importing only those before it:

- `hashing`: a plan's hash, recomputed from its contents, never from its stored `plan_hash`, and
  `check_approval`, which passes only exactly that hash.
- `versions`: the versions a plan records, with `installed_versions`, which refuses an
  environment no release has verified, with `environment.unsupported`, and `Versions.of`, the
  versions a plan was built with.
- `cases`: what a screen's plans and an experiment's share: the settings a case resolves to, its
  `case_id`, its requests, a ranking definition's weight rows and source, and the retry policy,
  the data sent, and the documented costs.
- `screen`: a screen's plans, 1.0.0 and 1.2.0, and a ranking snapshot's.
- `experiment`: an experiment's plan compiler, for plans 1.1.0 and 1.3.0.
- `revisions`: an experiment's revisions, what they change, and its `experiment.json`.

Each builder takes what a configuration's reader read, a definition included, so it reads no
file, and nothing in a plan varies between invocations: it holds no timestamps, output directory,
file paths, attempt IDs, credentials, or account information. The plans' models check the
consistency of what they build, a ranking variant's definition included.
"""

from trialfolio.planning.cases import (
    DATA_SENT,
    DATA_SENT_V1_2,
    RANKING_COSTS,
    RETRY_POLICY,
    case_id,
    ranking_source,
    resolve_settings,
)
from trialfolio.planning.experiment import build_experiment_plan, build_experiment_plan_v1_1
from trialfolio.planning.hashing import AnyPlan, check_approval, plan_hash
from trialfolio.planning.revisions import (
    PlanRevision,
    PlanRevisionV1_1,
    first_experiment_record,
    first_experiment_record_v1_1,
    plan_changes,
    plan_changes_v1_1,
    plan_revision,
    plan_revision_v1_1,
    retired_cases,
    retired_cases_v1_1,
    revised_experiment_record,
    revised_experiment_record_v1_1,
)
from trialfolio.planning.screen import BUDGET, build_plan, build_plan_v1_1, build_snapshot_plan
from trialfolio.planning.versions import (
    VERIFIED_VERSIONS,
    ProviderPackage,
    Versions,
    installed_versions,
)

__all__ = [
    "BUDGET",
    "DATA_SENT",
    "DATA_SENT_V1_2",
    "RANKING_COSTS",
    "RETRY_POLICY",
    "VERIFIED_VERSIONS",
    "AnyPlan",
    "PlanRevision",
    "PlanRevisionV1_1",
    "ProviderPackage",
    "Versions",
    "build_experiment_plan",
    "build_experiment_plan_v1_1",
    "build_plan",
    "build_plan_v1_1",
    "build_snapshot_plan",
    "case_id",
    "check_approval",
    "first_experiment_record",
    "first_experiment_record_v1_1",
    "installed_versions",
    "plan_changes",
    "plan_changes_v1_1",
    "plan_hash",
    "plan_revision",
    "plan_revision_v1_1",
    "ranking_source",
    "resolve_settings",
    "retired_cases",
    "retired_cases_v1_1",
    "revised_experiment_record",
    "revised_experiment_record_v1_1",
]
