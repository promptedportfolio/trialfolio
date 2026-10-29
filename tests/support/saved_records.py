"""Readers of the records a command saved: a screen run's one attempt, an experiment case's
attempts and their records, a session's manifest, and an experiment's plan. Each record is read with the model the test
gives, such as `AttemptRecordV1_1` or `AttemptRecordV1_3`, which pins the record's
`schema_version`.

TS-T03 wrote them once, for the interface's modules, which read an attempt's records four ways,
and a session's manifest seven. TS-T04 added `saved_plan`, from two of the eight forms of
`plan_of`, and the core's experiments read their records through them too.
"""

import json
from pathlib import Path
from typing import overload

from pydantic import BaseModel

from trialfolio.contracts.attempt import AttemptRecord, AttemptRecordV1_1, AttemptRecordV1_3
from trialfolio.contracts.experiment_plan import PlanV1_1, PlanV1_3


def only_attempt(out: Path) -> Path:
    """The directory of the one attempt of the screen run in `out`."""
    (directory,) = (out / "cases").glob("*/attempts/*")
    return directory


def only_attempt_record(out: Path) -> AttemptRecord:
    """The attempt record of the one attempt of the screen run in `out`."""
    return AttemptRecord.model_validate_json((only_attempt(out) / "attempt.json").read_bytes())


def attempt_directories(out: Path, case_id: str) -> list[Path]:
    """The directories of the attempts of the case `case_id`, of the experiment in `out`, by
    name."""
    return sorted((out / "cases" / case_id / "attempts").iterdir())


def attempt_records[R: (AttemptRecordV1_1, AttemptRecordV1_3)](
    out: Path, case_id: str, model: type[R]
) -> list[R]:
    """The attempt records of the case `case_id`, of the experiment in `out`, read as `model`, by
    session and then sequence."""
    records = [
        model.model_validate_json(path.read_bytes())
        for path in (out / "cases" / case_id / "attempts").glob("*/attempt.json")
    ]
    return sorted(records, key=lambda record: (record.session, record.sequence))


def session_manifest[M: BaseModel](out: Path, session: int, model: type[M]) -> M:
    """The manifest of the session `session`, of the experiment in `out`, read as `model`."""
    return model.model_validate_json((out / f"sessions/{session}/manifest.json").read_bytes())


@overload
def saved_plan(out: Path, number: int = 1) -> PlanV1_1 | PlanV1_3: ...


@overload
def saved_plan[P: (PlanV1_1, PlanV1_3)](out: Path, number: int, model: type[P]) -> P: ...


def saved_plan(
    out: Path, number: int = 1, model: type[PlanV1_1] | type[PlanV1_3] | None = None
) -> PlanV1_1 | PlanV1_3:
    """The plan `plans/<number>/plan.json` of the experiment in `out`, read as `model`, or, without
    one, as the model its `schema_version` names."""
    content = (out / "plans" / str(number) / "plan.json").read_bytes()
    if model is None:
        model = PlanV1_1 if json.loads(content)["schema_version"] == "1.1.0" else PlanV1_3
    return model.model_validate_json(content)
