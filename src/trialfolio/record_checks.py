"""What the readers of saved records share in checking them: `runs.py`, which reads a run back for
`trialfolio report` and a review, and `experiment_records.py`, which reads an experiment's records
for a resume (docs/contracts.md, a complete run, and checking the records).

- **A record.** It's a JSON object, with a schema version its reader reads, and valid against its
  model, and a manifest's entry for it gives a version its reader reads, or none.
- **A plan.** It recomputes to its `plan_hash` (plan hashing).
- **A listed file.** It has the size and `artifact_id` its manifest's entry records.
- **A case's normalized tables.** Each reads back as a valid table, its rows are labeled with the
  case's `case_id`, `metrics.csv` holds one row for each of the layout's metrics, in order, each in
  the metric's unit, `settings.csv` one for each of the plan's settings, in order, and each row was
  drawn from the file it should be. From 0.4.0, a weight row of `settings.csv` 1.1.0 is its plan's
  weight row, by its node and its value.
- **A definition's copy.** From 0.4.0, a plan's `definition.xml`, read as a definition's file is
  read, has the hash its plan's `ranking_source` gives (a complete run, and checking the records).

The two readers refuse differently: a run's error names the run as its reader is told to, once
the check has failed, and an experiment's names the output directory. So `RecordChecks` takes the
functions that make a reader's errors, and the schema versions it reads. Each reader words the
problems with a listed file and with the tables in its own sentences, and checks the tables in its
own order, so for those this module gives only the tests. The checks of a record's JSON, its
schema version, and its model are `trialfolio.file_checks`', which a snapshot's reader shares.

Nothing here reads a file, writes, or logs.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel

from trialfolio.contracts.experiment_manifest import ExperimentArtifact, ExperimentArtifactV1_1
from trialfolio.contracts.experiment_plan import PlanV1_1, PlanV1_3
from trialfolio.contracts.manifest import ManifestArtifact, ManifestArtifactV1_1
from trialfolio.contracts.plan import Plan, PlanV1_2
from trialfolio.contracts.plan_parts import PlanSetting, PlanSettingV1_2
from trialfolio.contracts.tables import MetricsRow, SettingsRow, SettingsRowV1_1
from trialfolio.errors import TrialFolioError
from trialfolio.file_checks import (
    artifact_id,
    check_version,
    json_object,
    matches,
    named,
    validated,
)
from trialfolio.normalization import METRICS, setting_text
from trialfolio.planning import plan_hash
from trialfolio.ranking_definitions import DefinitionProblem, read_definition

__all__ = [
    "AnyArtifact",
    "AnySettingsRow",
    "RecordChecks",
    "artifact_id",
    "definition_hash",
    "drawn_from",
    "holds_each_metric",
    "holds_each_setting",
    "holds_each_weight",
    "labeled",
    "matches",
    "named",
]

_METRIC_ROWS: Final = tuple((metric.subject, metric.metric_id, metric.unit) for metric in METRICS)
"""`metrics.csv`'s rows, in order, by subject and `metric_id`, with the unit the layout fixes."""

type AnySettingsRow = SettingsRow | SettingsRowV1_1
"""A row of `settings.csv` 1.0.0, or of 1.1.0, a run's or a case's whose ranking is a definition."""

type AnyArtifact = (
    ManifestArtifact | ManifestArtifactV1_1 | ExperimentArtifact | ExperimentArtifactV1_1
)
"""A manifest's entry for a file: a run's or an experiment's, of either version."""


@dataclass(frozen=True)
class RecordChecks:
    """A reader's checks of its records, which refuse as the reader does."""

    refused: Callable[[str], Exception]
    """Makes the reader's `input.not_a_run` for a problem: a sentence that names no value, such as
    "`plan.json` isn't JSON."."""
    unknown_version: Callable[[str, str], Exception]
    """Makes the reader's `artifact.unknown_schema_version` for the file at a path, from a sentence
    that names the versions this version reads, never the file's own, which is text from a file."""
    readable: Mapping[str, tuple[str, tuple[str, ...]]]
    """The schema versions the reader reads, for each kind of file whose version it checks, with
    what they're called in messages, such as "plans"."""
    manifest: str
    """How a message names the manifest whose entry gives a file's version, such as "its
    manifest"."""

    def record[M: BaseModel](self, model: type[M], content: bytes, path: str, kind: str) -> M:
        """The record of `kind` in `content`, the file at `path`, checked against its schema
        version, then its model."""
        self.check_version(self.json_object(content, path).get("schema_version"), path, kind)
        return self.validated(model, content, path, self.readable[kind][0].removesuffix("s"))

    def json_object(self, content: bytes, path: str) -> dict[str, object]:
        """The JSON object in `content`, the file at `path`."""
        return json_object(content, named(path), self.refused)

    def check_version(self, version: object, path: str, kind: str, *, listed: bool = False) -> None:
        """Checks the schema version of the file at `path`, from the file itself or, when
        `listed`, from its manifest's entry, where a file without one has none. A kind of file
        whose version the reader doesn't check, such as a saved response, passes."""
        if kind not in self.readable or (listed and version is None):
            return
        name, readable = self.readable[kind]
        where = f"{self.manifest} gives it" if listed else "it has"
        check_version(
            version,
            readable,
            named(path),
            self.refused,
            lambda: self.unknown_version(
                path,
                f"{where} a schema version this version has no reader for. It reads {name}"
                f" {' or '.join(readable)}.",
            ),
        )

    def validated[M: BaseModel](self, model: type[M], content: bytes, path: str, what: str) -> M:
        """`content`, the file at `path`, as `model`. `what` names the model in a message, such
        as "run manifest"."""
        return validated(model, content, named(path), what, self.refused)

    def check_plan_hash(self, plan: Plan | PlanV1_1 | PlanV1_2 | PlanV1_3, file: str) -> None:
        """Checks that `plan` recomputes to its `plan_hash`. `file` names its file in the
        messages, such as "its plan.json"."""
        try:
            recomputed = plan_hash(plan)
        except ValueError as error:
            # The message names the kind of value canonical JSON can't write, never the value.
            raise self.refused(f"{file} can't be hashed ({error}).") from None
        if recomputed != plan.plan_hash:
            raise self.refused(
                f"{file} doesn't recompute to its plan_hash, so the plan changed after it was"
                " approved."
            )

    def table_rows[R](
        self, read: Callable[[bytes, str], tuple[R, ...]], content: bytes, path: str
    ) -> tuple[R, ...]:
        """The rows of the table in `content`, the file at `path`, as `read` reads them."""
        try:
            return read(content, f"its {named(path)}")
        except TrialFolioError as error:
            # The tables' messages name the line and the column, never a value.
            raise self.refused(error.message) from None


def labeled(rows: Iterable[MetricsRow | AnySettingsRow], case_id: str) -> bool:
    """Whether each row of a case's tables is labeled with its `case_id`."""
    return all(row.label == case_id for row in rows)


def holds_each_metric(rows: Sequence[MetricsRow]) -> bool:
    """Whether `metrics.csv`'s rows are one for each of the layout's metrics, in order, each in
    the metric's unit."""
    return tuple((row.subject, row.metric_id, row.unit) for row in rows) == _METRIC_ROWS


def holds_each_setting(
    rows: Sequence[SettingsRow] | Sequence[SettingsRowV1_1],
    planned: Sequence[PlanSetting] | Sequence[PlanSettingV1_2],
) -> bool:
    """Whether `settings.csv`'s rows are one for each of the plan's settings, in order. The
    weight rows share one name, so `holds_each_weight` tells them apart by their nodes."""
    return tuple(row.setting for row in rows) == tuple(setting.setting for setting in planned)


def holds_each_weight(rows: Sequence[SettingsRowV1_1], planned: Sequence[PlanSettingV1_2]) -> bool:
    """Whether the weight rows of `settings.csv` 1.1.0 give the weights their plan's weight rows
    give, node for node: the weights of the case's definition, which the plan's models check
    (weight rows)."""
    weights = tuple((row.node, row.value) for row in rows if row.node is not None)
    return weights == tuple(
        (setting.node, setting_text(setting.value))
        for setting in planned
        if setting.node is not None
    )


def drawn_from(rows: Iterable[MetricsRow | AnySettingsRow], *sources: str) -> bool:
    """Whether each row was drawn from one of `sources`, by its `artifact_id`."""
    return all(row.source_artifact in sources for row in rows)


def definition_hash(content: bytes) -> str | None:
    """The hash of the definition a plan's `definition.xml`, whose bytes are `content`, holds,
    read as a definition's file is read, each carriage return and line feed, and each carriage
    return alone, read as a line feed (ranking definitions): the `definition` its plan's
    `ranking_source` gives. None when it isn't a definition Trial Folio reads."""
    try:
        return read_definition(content).hash
    except DefinitionProblem:
        return None
