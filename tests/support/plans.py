"""The plans of the committed configurations, as Trial Folio's readers and planners give them.

- **`screen_plan`** and **`experiment_plan`** plan a screen and an experiment configuration as
  0.1.0's and 0.3.0's readers do, which still serve a plan without a ranking definition.
- **`ranked_screen`** and **`planned_experiment`** plan one as 0.4.0's readers do, and give, beside
  the configuration's bytes and its plan, what its ranking was validated with: a definition's bytes,
  or a snapshot's two files, which `run` takes with the configuration (`Planned`).
  **`ranked_experiment`** gives an experiment's plan 1.3.0, whose ranking is one of them.
- **`verified_versions`** gives the versions a plan records for a release of Trial Folio, with the
  wrapper's verified versions, so a plan's hash doesn't change with the installed packages.

A configuration is read under its file's name, which no plan records.

TS-T04 wrote them once, from the eight forms of `plan_of`, among them those of `tests/interface/`,
`tests/core/test_plan.py`'s `plan_for`, and the 0.4.0 core modules' `screen` and `experiment`.
`test_plan.py` and `test_experiment_plan.py` compare a plan's hash across processes, so the
processes they start import these, as the tests do.
"""

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from tests.support.paths import screen_config
from trialfolio.configuration import (
    ExperimentConfigurationRead,
    ScreenConfigurationRead,
    read_experiment_configuration,
    read_experiment_configuration_v1_1,
    read_screen_configuration,
    read_screen_configuration_v1_1,
)
from trialfolio.contracts.experiment_plan import PlanV1_1, PlanV1_3
from trialfolio.contracts.plan import Plan, PlanV1_2
from trialfolio.planning import (
    VERIFIED_VERSIONS,
    Versions,
    build_experiment_plan,
    build_experiment_plan_v1_1,
    build_plan,
    build_plan_v1_1,
    installed_versions,
)
from trialfolio.snapshots import SnapshotFiles


def verified_versions(trialfolio: str) -> Versions:
    """The versions a plan records for Trial Folio `trialfolio`, with the first of the wrapper's
    verified versions of `p123api`, `requests`, and `urllib3`."""
    return Versions(
        trialfolio=trialfolio,
        p123api=VERIFIED_VERSIONS["p123api"][0],
        requests=VERIFIED_VERSIONS["requests"][0],
        urllib3=VERIFIED_VERSIONS["urllib3"][0],
    )


def case_ids(plan: PlanV1_1 | PlanV1_3) -> list[str]:
    """The plan's case IDs, in its order."""
    return [case.case_id for case in plan.cases]


def screen_plan(path: Path, versions: Versions | None = None) -> Plan:
    """The plan of the screen configuration at `path`, as 0.1.0's reader and planner give it,
    with `versions`, the installed versions by default."""
    configuration = read_screen_configuration(path.read_bytes(), path.name)
    return build_plan(configuration, versions or installed_versions())


def experiment_plan(path: Path, versions: Versions | None = None) -> PlanV1_1:
    """The plan of a new experiment of the configuration at `path`, as 0.3.0's reader and planner
    give it, with `versions`, the installed versions by default."""
    configuration = read_experiment_configuration(path.read_bytes(), path.name)
    return build_experiment_plan(configuration, versions or installed_versions())


@dataclass(frozen=True)
class Planned[P: BaseModel]:
    """A configuration's bytes and its plan, with what its ranking was validated with: the bytes of
    the definition file it names, or the two files of the snapshot it names, or neither."""

    content: bytes
    plan: P
    definition: bytes | None = None
    snapshot: SnapshotFiles | None = None


def with_ranking[P: BaseModel](
    content: bytes, read: ScreenConfigurationRead | ExperimentConfigurationRead, plan: P
) -> Planned[P]:
    """`plan`, of the configuration `content`, read as `read`, with what its ranking was validated
    with: the snapshot's files, when it names a snapshot, and otherwise its definition's bytes, when
    it has one."""
    if read.snapshot is not None:
        return Planned(content, plan, snapshot=read.snapshot.files)
    definition = None if read.definition is None else read.definition.content
    return Planned(content, plan, definition=definition)


def ranked_screen(path: Path | None = None) -> Planned[PlanV1_2]:
    """The plan 1.2.0 of the screen configuration at `path`, `screen-configs/definition.yaml` by
    default, as 0.4.0's reader and planner give it, whose ranking is a definition or a snapshot."""
    path = path or screen_config("definition.yaml")
    content = path.read_bytes()
    read = read_screen_configuration_v1_1(content, path.name, path)
    plan = build_plan_v1_1(read, installed_versions())
    assert isinstance(plan, PlanV1_2) and read.definition is not None
    return with_ranking(content, read, plan)


def planned_experiment(
    path: Path,
    versions: Versions | None = None,
    revises: str | None = None,
    *,
    content: bytes | None = None,
    source: str | None = None,
) -> Planned[PlanV1_1 | PlanV1_3]:
    """The plan of a new experiment of the configuration at `path`, as 0.4.0's reader and planner
    give it, with `versions`, the installed versions by default, and as a revision of the plan
    whose hash is `revises`, when it's given: a plan 1.3.0 for a configuration whose ranking is a
    definition or a snapshot, and 1.1.0 otherwise. `content` and `source` stand for the file's
    bytes and its name, when they're given."""
    content = path.read_bytes() if content is None else content
    read = read_experiment_configuration_v1_1(content, source or path.name, path)
    plan = build_experiment_plan_v1_1(read, versions or installed_versions(), revises)
    return with_ranking(content, read, plan)


def ranked_experiment(path: Path) -> Planned[PlanV1_3]:
    """`planned_experiment`'s plan of the configuration at `path`, which must be 1.3.0."""
    planned = planned_experiment(path)
    assert isinstance(planned.plan, PlanV1_3)
    return Planned(planned.content, planned.plan, planned.definition, planned.snapshot)
