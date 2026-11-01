"""`experiment.json` 1.1.0, the experiment record of a ranking definition, accepts what
docs/contracts.md describes, and rejects what it calls invalid, and an entry taken from a 1.0.0
record reads with `set` and `remove` null.

Traces to release 0.4.0's test pairing, which names tests/contract/test_ranking_artifact_models.py
for the records' contract tests (R04-T05), here for `experiment.json` 1.1.0. Each document is
tests/support/ranking_documents.py's, synthetic, changed one way, and read as a reader reads it:
from JSON text, with `model_validate_json`. TS-T07 separated these tests from
tests/contract/test_ranking_artifact_models.py (docs/test-refactoring.md, modules to separate).
"""

from collections.abc import Callable

import pytest

from tests.support.contract_checks import Change, Document, accepts, changed, digest, rejects
from tests.support.ranking_documents import (
    EARLIER_PLAN,
    HEAVY_SET,
    HOLDINGS_ID,
    PLAN_HASH,
    experiment_record,
    holdings_case,
    plan_entry,
    recorded,
    source_revision,
    variant,
)
from trialfolio.contracts.experiment_record import ExperimentRecordV1_1

# experiment.json 1.1.0


def planned(document: Document, index: int) -> Document:
    case: Document = document["planned_cases"][index]
    return case


def last_changes(document: Document) -> Document:
    changes: Document = document["plans"][-1]["changes"]
    return changes


EXPERIMENT_RECORD_REJECTS: dict[str, tuple[Callable[[], Document], Change]] = {
    "version 1.0.0": (experiment_record, lambda d: d.update(schema_version="1.0.0")),
    "a 1.0.0 variant, without set and remove": (
        experiment_record,
        lambda d: (planned(d, 2)["variant"].pop("set"), planned(d, 2)["variant"].pop("remove")),
    ),
    "a ranking variant without set": (
        experiment_record,
        lambda d: planned(d, 1)["variant"].update(set=None),
    ),
    "a holdings variant with set": (
        experiment_record,
        lambda d: planned(d, 2)["variant"].update(set=HEAVY_SET),
    ),
    "a baseline with a ranking variant": (
        experiment_record,
        lambda d: planned(d, 0).update(variant=variant("ranking", set=HEAVY_SET)),
    ),
    "the default a ranking variant": (
        experiment_record,
        lambda d: planned(d, 1)["variant"].update(default=True),
    ),
    "ranking_source after case_keys": (
        source_revision,
        lambda d: last_changes(d).update(parts=["case_keys", "ranking_source"]),
    ),
    "ranking_source twice": (
        source_revision,
        lambda d: last_changes(d).update(parts=["ranking_source", "ranking_source"]),
    ),
    "a part 1.1.0 doesn't name": (
        source_revision,
        lambda d: last_changes(d).update(parts=["ranking_definition"]),
    ),
    "a revision that changes nothing": (
        source_revision,
        lambda d: last_changes(d).update(parts=[]),
    ),
    "a revision without its reason": (
        source_revision,
        lambda d: d["plans"][-1].update(reason=None),
    ),
    "a revision of a plan other than the one before it": (
        source_revision,
        lambda d: d["plans"][-1].update(revises=digest("a9")),
    ),
    "a retired case of the current plan": (
        source_revision,
        lambda d: (
            d["retired_cases"].append(
                recorded(holdings_case()) | {"case_id": "case-000000000000000a", "plan": 2}
            ),
            last_changes(d).update(parts=["ranking_source"]),
        ),
    ),
}


@pytest.mark.parametrize(
    ("build", "change"), EXPERIMENT_RECORD_REJECTS.values(), ids=EXPERIMENT_RECORD_REJECTS.keys()
)
def test_experiment_record_1_1_rejects(build: Callable[[], Document], change: Change) -> None:
    rejects(ExperimentRecordV1_1, changed(build, change))


def test_an_entry_taken_from_a_1_0_0_record_is_written_with_set_and_remove_null() -> None:
    """A 1.0.0 `experiment.json`'s entries, such as a holdings variant's, read in 1.1.0 with
    `set` and `remove` null, and are otherwise unchanged."""
    document = experiment_record()
    document["retired_cases"] = [
        recorded(holdings_case())
        | {"case_id": "case-000000000000000a", "variant": variant("max_holdings", 40), "plan": 1}
    ]
    document["plans"].append(
        plan_entry(2, PLAN_HASH, EARLIER_PLAN)
        | {
            "reason": "Fewer holdings.",
            "changes": {
                "versions": [],
                "cases_added": [{"case_id": HOLDINGS_ID, "case_key": "holdings-50"}],
                "cases_retired": [{"case_id": "case-000000000000000a", "case_key": "holdings-50"}],
                "parts": [],
            },
        }
    )

    accepts(ExperimentRecordV1_1, document)
