"""The records check of an experiment with a ranking definition, in the core: a resume refuses
records with a ranking definition that are incomplete or changed, and a record 0.4.0 adds whose
schema version has no reader; and, of an experiment without a definition, it reads 0.3.0's versions
only, and refuses a record or a file only a definition gives.

Traces to docs/contracts.md, running an experiment (a resumed experiment, and checking the records),
uncertain completion, `experiment.json` 1.1.0, and the experiment manifest's version 1.1.0; and, at
the core, to R04-AC12 (records with a ranking definition that are incomplete or changed fail with
`input.not_a_run`, send nothing, and reserve no session; a record with no reader fails with
`artifact.unknown_schema_version`). The real client, `requests`, and `urllib3` run over the fake
server, whose end-of-test check reads every `POST /rank` body (R04-AC09); storage faults wrap the
real store; the clock is fixed; and the ranking lock's file is in the test's temporary directory.

Each experiment is built during the test, through the core, and stopped where the test needs it. The
breaks are made with the editors of `tests/support/broken_runs.py`: an experiment's with
`edit_record` and `unlist_record`, and a copy of an attempt with `copy_attempt`. The breaks of
`ranking-example.yaml`'s complete experiment, one for each way its records may be incomplete or
changed, are tests/support/ranking_records.py's, which TS-T06 moved there, with that experiment and
`script`: they're cases, whose IDs name R04-AC12, of the records check of
tests/core/test_experiment_records.py, beside R03-AC17's (docs/test-refactoring.md, copies that
check less, item 7). TS-T07 separated these tests from tests/core/test_ranking_resume.py
(docs/test-refactoring.md, modules to separate).
"""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.support.broken_runs import Json, copy_attempt, edit_record, labeled_1_1_0, unlist_record
from tests.support.directories import snapshot
from tests.support.experiment_lab import RELEASE_0_4_0, Lab
from tests.support.fake_portfolio123 import AUTH, RANK, FakePortfolio123, Reply, exchange, response
from tests.support.ranking_records import (
    EXAMPLE,
    attempt_at,
    completed_ranking_example,
    first_case_faults,
    script,
)
from trialfolio.contracts.attempt import AttemptRecordV1_3
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_records import read_experiment
from trialfolio.storage import LocalArtifactStore


@pytest.fixture
def lab(tmp_path: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch) -> Lab:
    return Lab(tmp_path, server, monkeypatch, reader=RELEASE_0_4_0, catch=True)


# The records check of an experiment with a definition (R04-AC12). Its breaks of
# `ranking-example.yaml`'s experiment are tests/support/ranking_records.py's, which
# tests/core/test_experiment_resume.py's records check runs, beside R03-AC17's.


def test_an_attempt_a_resume_recorded_from_its_started_json_needs_that_record(lab: Lab) -> None:
    # Only a resume from `started.json` records an attempt `unknown` after its rank_update's 200,
    # without a backtest exchange, so its backtest may have been sent: a copy that lost that start
    # record fails the check, as one that lost a sent backtest's does.
    script(
        lab.server,
        auths=2,
        ranks=[response("rank-update.json") for _ in range(4)],
        backtests=[response("complete.json")] * 4,
    )
    lab.new(arm=first_case_faults(("response.json", "full disk"), ("attempt.json", "unexpected")))
    lab.resume()
    (record,) = lab.attempts(EXAMPLE.cases[0].case_id, AttemptRecordV1_3)
    assert (record.outcome, record.exchanges) == (
        "unknown",
        (exchange(AUTH, 200), exchange(RANK, 200)),
    )
    unlist_record(lab.out, f"{attempt_at(lab.out, 0)}/started.json")
    before = snapshot(lab.out)

    ran = lab.resume()

    error = ran.refused("input.not_a_run")
    assert "its backtest was sent, or may have been, without the start record" in error.message
    assert ran.received == () and ran.published == ()
    assert snapshot(lab.out) == before


def test_a_request_sent_with_a_token_a_401_to_a_rank_update_dropped_fails_the_check(
    lab: Lab,
) -> None:
    # The second case's rank_update got a 401, which dropped the token the first case obtained,
    # so the third case authenticated again. A copy of the fourth case's attempt that names the
    # first case's token can't have been sent.
    script(
        lab.server,
        auths=2,
        ranks=[
            response("rank-update.json"),
            Reply(401, b""),
            response("rank-update.json"),
            response("rank-update.json"),
        ],
        backtests=[response("complete.json")] * 3,
    )
    lab.new().refused("execution.partial")
    first = json.loads((lab.out / attempt_at(lab.out, 0) / "attempt.json").read_bytes())
    copy_attempt(lab.out, attempt_at(lab.out, 3), sequence=9, authenticated_by=first["attempt_id"])

    ran = lab.resume()

    error = ran.refused("input.not_a_run")
    assert "a token that a 401 or 403 to an earlier request had dropped" in error.message
    assert ran.received == () and ran.published == ()


@pytest.mark.parametrize(
    ("path", "listed"),
    [
        ("plans/1/plan.json", False),
        ("plans/1/experiment.json", False),
        ("sessions/2/manifest.json", False),
        ("{attempt}/updating.json", False),
        ("{attempt}/started.json", False),
        ("{attempt}/attempt.json", False),
        ("{settings}", True),
    ],
)
def test_a_record_0_4_0_adds_without_a_reader_fails_the_check(
    lab: Lab, path: str, listed: bool
) -> None:
    completed_ranking_example(lab)
    settings = f"cases/{EXAMPLE.cases[0].case_id}/normalized/settings.csv"
    path = path.format(attempt=attempt_at(lab.out, 1), settings=settings)
    if listed:
        edit_record(
            lab.out,
            "sessions/2/manifest.json",
            lambda d: next(a for a in d["artifacts"] if a["path"] == path).update(
                schema_version="9.9.9"
            ),
        )
    else:
        edit_record(lab.out, path, lambda d: d.update(schema_version="9.9.9"))

    ran = lab.resume()

    error = ran.refused("artifact.unknown_schema_version")
    assert f"`{path}`" in error.message
    assert "9.9.9" not in error.message
    assert ran.received == () and ran.published == ()


def test_without_ranking_the_records_check_reads_0_3_0s_versions_only(lab: Lab) -> None:
    # As `trialfolio run` read an experiment's records until release 0.4.0's R04-T12, which
    # reads them with `ranking`: without it, one with a definition is refused by its version.
    completed_ranking_example(lab)

    with LocalArtifactStore(lab.out) as store, pytest.raises(TrialFolioError) as caught:
        read_experiment(store)

    assert caught.value.code == "artifact.unknown_schema_version"
    assert "experiment manifests 1.0.0" in caught.value.message


def _record_labeled_1_1_0(content: Json) -> None:
    content["schema_version"] = "1.1.0"
    for case in (*content["planned_cases"], *content["retired_cases"]):
        if case["variant"] is not None:
            case["variant"].update(set=None, remove=None)


@pytest.mark.parametrize(
    ("path", "change", "problem"),
    [
        ("sessions/1/manifest.json", labeled_1_1_0, "isn't the version its session's manifest is"),
        ("plans/1/experiment.json", _record_labeled_1_1_0, "isn't the version its plan's"),
    ],
    ids=["a manifest 1.1.0", "an experiment.json 1.1.0"],
)
def test_a_record_1_1_0_of_an_experiment_without_a_definition_fails_the_check(
    lab: Lab, path: str, change: Callable[[Json], None], problem: str
) -> None:
    # Each is valid as version 1.1.0, whose fields are 1.0.0's and more, but only an experiment
    # with a plan 1.3.0 writes it.
    script(lab.server, backtests=[response("complete.json")] * 5)
    assert lab.new("example.yaml").error is None
    edit_record(lab.out, path, change)

    ran = lab.resume("example.yaml")

    error = ran.refused("input.not_a_run")
    assert problem in error.message, error.message
    assert ran.received == () and ran.published == ()


def test_a_rank_updates_file_under_a_plan_without_a_definition_fails_the_check(lab: Lab) -> None:
    # Only an attempt that sends a definition writes the rank_update's files.
    script(lab.server, backtests=[response("complete.json")] * 5)
    assert lab.new("example.yaml").error is None
    (first,) = sorted((lab.out / "cases").iterdir())[:1]
    (directory,) = sorted((first / "attempts").iterdir())
    (directory / "rank-update-request.json").write_bytes(b"{}\n")

    ran = lab.resume("example.yaml")

    error = ran.refused("input.not_a_run")
    assert "holds a file no attempt under its plan writes" in error.message
    assert ran.received == () and ran.published == ()
