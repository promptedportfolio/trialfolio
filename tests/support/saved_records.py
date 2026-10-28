"""Readers of the records a command saved: a screen run's one attempt, an experiment case's
attempts and their records, and a session's manifest. Each record is read with the model the test
gives, such as `AttemptRecordV1_1` or `AttemptRecordV1_3`, which pins the record's
`schema_version`.

TS-T03 wrote them once, for the interface's modules, which read an attempt's records four ways,
and a session's manifest seven.
"""

from pathlib import Path

from pydantic import BaseModel

from trialfolio.contracts.attempt import AttemptRecord, AttemptRecordV1_1, AttemptRecordV1_3


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
