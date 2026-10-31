"""A resume's records check, in the core: before it sends or writes anything, a resume reads and
checks the experiment's records, and refuses records that are incomplete or changed, a record whose
schema version has no reader, a plan's hash it wasn't given, and a directory whose first plan wasn't
recorded.

Traces to docs/contracts.md, running an experiment (a resumed experiment, and checking the records),
and experiment plans and revisions (approving a revision); and, at the core, to R03-AC17 (records
that are incomplete or changed fail with `input.not_a_run`, and send and write nothing); and, for
the records check's cases whose IDs name it, to R04-AC12 (an experiment's records with a ranking
definition that are incomplete or changed fail the same), as tests/core/test_ranking_resume.py
traced it until TS-T06 made its test of them cases of tests/core/test_experiment_resume.py's
(docs/test-refactoring.md, copies that check less, item 7). TS-T07 separated the records check from
that module, with its catalog of breaks (docs/test-refactoring.md, modules to separate). The real
client, `requests`, and `urllib3` run over the fake server; storage faults wrap the real store; the
clock is fixed.

Each experiment is built during the test, through the core, and stopped where the test needs it: by
a cancellation, by storage faults, or by an interrupt, as a stopped process leaves it. The breaks
are made with the editors of `tests/support/broken_runs.py`, which TS-T05 moved there from
tests/core/test_experiment_resume.py: each edit updates the latest manifest's entry, and, for a
plan's file, the `artifact_id` each `experiment.json` records, so only the check under test can
tell. Its breaks of an experiment with a ranking definition, R04-AC12's, are
tests/support/ranking_records.py's, of `ranking-example.yaml`'s experiment, which the lab reads as
release 0.4.0 does.
"""

import json
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest

from tests.support.broken_runs import (
    Json,
    copy_attempt,
    edit_attempt,
    edit_record,
    rewrite_record,
    unlist_record,
)
from tests.support.directories import snapshot
from tests.support.experiment_lab import RELEASE_0_3_0, RELEASE_0_4_0, Lab, Reader, unknown_baseline
from tests.support.fake_portfolio123 import AUTHENTICATED, FakePortfolio123, Reply, response
from tests.support.paths import EXPERIMENT_CONFIGS
from tests.support.plans import experiment_plan
from tests.support.ranking_records import RANKING_BREAKS, completed_ranking_example
from trialfolio.canonical import sha256_hex
from trialfolio.contracts.experiment_plan import PlanV1_1
from trialfolio.experiment_repeats import Repeat
from trialfolio.planning import plan_hash
from trialfolio.tables import metrics_csv, read_metrics_csv, read_settings_csv, settings_csv


@pytest.fixture
def lab(tmp_path: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch) -> Lab:
    return Lab(tmp_path, server, monkeypatch, reader=RELEASE_0_3_0, catch=True)


EXAMPLE = experiment_plan(EXPERIMENT_CONFIGS / "example.yaml")
DEFAULT_ONLY = experiment_plan(EXPERIMENT_CONFIGS / "default-only.yaml")


# The records check (R03-AC17)


def _attempt_of(out: Path, case: int) -> str:
    """The directory of the one attempt of `EXAMPLE`'s case at that place."""
    (directory,) = sorted((out / "cases" / EXAMPLE.cases[case].case_id / "attempts").iterdir())
    return directory.relative_to(out).as_posix()


def _completed(lab: Lab) -> None:
    """A complete experiment of `example.yaml`: its first two cases in session 1, the rest in
    session 2, and a revision that renames a key, and sends nothing, in session 3."""
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply("/screen/backtest", *(response("complete.json") for _ in range(5)))
    lab.new(cancel_after=2)
    assert lab.resume().error is None
    assert lab.resume("revisions/key-renamed.yaml", reason="A clearer key.").error is None


def _stray(out: Path, path: str) -> None:
    """Adds a file the layout doesn't have, or that no manifest lists."""
    (out / path).parent.mkdir(parents=True, exist_ok=True)
    (out / path).write_bytes(b"stray\n")


def _revision_changed(out: Path, **fields: object) -> None:
    """Changes the revision's plan, with its hash recomputed, and its `experiment.json` and the
    latest manifest's entries to match, so only the check under test can tell: the revision
    sent nothing, so no attempt names it."""
    plan = PlanV1_1.model_validate_json((out / "plans/2/plan.json").read_bytes())
    draft = plan.model_copy(update=fields)
    other = draft.model_copy(update={"plan_hash": plan_hash(draft)})
    data = (other.model_dump_json(indent=2) + "\n").encode()
    rewrite_record(out, "plans/2/plan.json", data)

    def record(content: Json) -> None:
        if "experiment_id" in fields:
            content["experiment_id"] = fields["experiment_id"]
        content["plans"][-1].update(
            plan_hash=other.plan_hash, plan_artifact_id="sha256:" + sha256_hex(data)
        )

    edit_record(out, "plans/2/experiment.json", record)


def _table(out: Path, case: int, name: str, change: dict[str, str]) -> None:
    """Changes a field of every row of the case's table, which stays valid."""
    path = f"cases/{EXAMPLE.cases[case].case_id}/normalized/{name}"
    if name == "metrics.csv":
        metrics = read_metrics_csv((out / path).read_bytes(), name)
        data = metrics_csv([row.model_copy(update=change) for row in metrics])
    else:
        settings = read_settings_csv((out / path).read_bytes(), name)
        data = settings_csv([row.model_copy(update=change) for row in settings])
    rewrite_record(out, path, data)


def _without_last_row(out: Path, case: int, name: str) -> None:
    """Drops the last row of the case's table, which stays a valid table."""
    path = f"cases/{EXAMPLE.cases[case].case_id}/normalized/{name}"
    if name == "metrics.csv":
        data = metrics_csv(read_metrics_csv((out / path).read_bytes(), name)[:-1])
    else:
        data = settings_csv(read_settings_csv((out / path).read_bytes(), name)[:-1])
    rewrite_record(out, path, data)


def _manifest_of_session_2(out: Path) -> None:
    """Changes the latest manifest, `sessions/3/manifest.json`, to name session 2, with its own
    session's files those of `sessions/2/`, so its model accepts it."""

    def change(manifest: Json) -> None:
        manifest["session"] = 2
        for artifact in manifest["artifacts"]:
            if artifact["path"].startswith("sessions/3/"):
                path = artifact["path"].replace("sessions/3/", "sessions/2/")
                data = (out / path).read_bytes()
                artifact.update(path=path, artifact_id="sha256:" + sha256_hex(data), size=len(data))

    edit_record(out, "sessions/3/manifest.json", change)


def _attempt_id(out: Path, case: int) -> str:
    """The `attempt_id` of the one attempt of `EXAMPLE`'s case at that place."""
    return json.loads((out / _attempt_of(out, case) / "attempt.json").read_bytes())["attempt_id"]


def _first_attempt_id(out: Path) -> str:
    return _attempt_id(out, 0)


_ANOTHER_ATTEMPT = str(uuid.uuid4())

BREAKS: dict[str, tuple[Callable[[Path], object], str]] = {
    "a listed file missing": (
        lambda out: (out / _attempt_of(out, 0) / "attempt.json").unlink(),
        "which is missing",
    ),
    "the first plan's experiment.json missing": (
        lambda out: (out / "plans/1/experiment.json").unlink(),
        "which is missing",
    ),
    "a listed file changed": (
        lambda out: (out / "plans/1/configuration.yaml").write_bytes(b"changed\n"),
        "doesn't match its artifact_id in the latest manifest",
    ),
    "a plan that doesn't recompute": (
        lambda out: edit_record(
            out, "plans/1/plan.json", lambda d: d.update(title="Another title")
        ),
        "doesn't recompute to its plan_hash",
    ),
    "experiment.json's last entry, by number": (
        lambda out: edit_record(
            out, "plans/2/experiment.json", lambda d: d["plans"][-1].update(plan=3)
        ),
        "last entry isn't its directory's plan: it gives another number",
    ),
    "experiment.json's last entry, by hash": (
        lambda out: edit_record(
            out,
            "plans/2/experiment.json",
            lambda d: d["plans"][-1].update(plan_hash="sha256:" + "0" * 64),
        ),
        "it gives another plan_hash than its plan.json",
    ),
    "experiment.json's last entry, by artifact_id": (
        lambda out: edit_record(
            out,
            "plans/2/experiment.json",
            lambda d: d["plans"][-1].update(configuration_artifact_id="sha256:" + "0" * 64),
        ),
        "has another artifact_id than it records",
    ),
    "experiment.json's last entry, by plan.json's artifact_id": (
        lambda out: edit_record(
            out,
            "plans/2/experiment.json",
            lambda d: d["plans"][-1].update(plan_artifact_id="sha256:" + "0" * 64),
        ),
        "has another artifact_id than it records",
    ),
    "experiment.json's earlier entries": (
        lambda out: edit_record(
            out, "plans/2/experiment.json", lambda d: d["plans"][0].update(approval="interactive")
        ),
        "earlier entries aren't those of the previous plan's",
    ),
    "a manifest that disagrees with the plans' approval": (
        lambda out: edit_record(
            out,
            "sessions/3/manifest.json",
            lambda d: d.update(synthetic=True, approval="not_required"),
        ),
        "is synthetic, though the experiment's plans don't record",
    ),
    "an attempt naming a case its plan doesn't have": (
        lambda out: copy_attempt(
            out, _attempt_of(out, 3), case_id="case-0123456789abcdef", sequence=9
        ),
        "name a case their plan doesn't have",
    ),
    "an attempt naming a plan the experiment doesn't have": (
        lambda out: edit_attempt(
            out, _attempt_of(out, 3), lambda d: d.update(plan_hash="sha256:" + "1" * 64)
        ),
        "name a plan the experiment doesn't have",
    ),
    "records that name another attempt than their directory's": (
        lambda out: edit_attempt(
            out, _attempt_of(out, 3), lambda d: d.update(attempt_id=_ANOTHER_ATTEMPT)
        ),
        "name another attempt",
    ),
    "an attempt naming a session the experiment doesn't have": (
        lambda out: edit_attempt(out, _attempt_of(out, 3), lambda d: d.update(session=9)),
        "name a session the experiment doesn't have",
    ),
    "two attempts of a session with one sequence": (
        lambda out: edit_attempt(out, _attempt_of(out, 3), lambda d: d.update(sequence=1)),
        "have the same sequence",
    ),
    "a request sent with another session's token": (
        lambda out: edit_attempt(
            out, _attempt_of(out, 3), lambda d: d.update(authenticated_by=_first_attempt_id(out))
        ),
        "was sent with a token no attempt of its session obtained",
    ),
    # The fifth case's request, sent with the token of the fourth, which sent with the third's.
    "a request sent with the token of an attempt that didn't authenticate": (
        lambda out: edit_attempt(
            out, _attempt_of(out, 4), lambda d: d.update(authenticated_by=_attempt_id(out, 3))
        ),
        "was sent with a token no attempt of its session obtained",
    ),
    "a repeat_of that names no charged attempt": (
        lambda out: edit_attempt(
            out, _attempt_of(out, 3), lambda d: d.update(repeat_of=_ANOTHER_ATTEMPT)
        ),
        "names in repeat_of an attempt",
    ),
    "an attempt after its case's succeeded attempt": (
        lambda out: copy_attempt(
            out, _attempt_of(out, 3), sequence=9, repeat_of=_first_attempt_id(out)
        ),
        "follows its case's succeeded attempt",
    ),
    "a table in a case without a succeeded attempt": (
        lambda out: shutil.copytree(
            out / "cases" / EXAMPLE.cases[0].case_id / "normalized",
            out / "cases" / "case-0123456789abcdef" / "normalized",
        ),
        "has normalized tables, but no succeeded attempt",
    ),
    # Tables are written after the attempt record, so a running attempt's case has none.
    "tables beside an attempt without its attempt record": (
        lambda out: unlist_record(out, f"{_attempt_of(out, 1)}/attempt.json"),
        "has normalized tables, but no succeeded attempt",
    ),
    "settings.csv without its metrics.csv": (
        lambda out: _stray(out, "cases/case-0123456789abcdef/normalized/settings.csv"),
        "is there without its metrics.csv",
    ),
    "a listed table missing": (
        lambda out: (out / "cases" / EXAMPLE.cases[0].case_id / "normalized/metrics.csv").rename(
            out / "cases" / EXAMPLE.cases[0].case_id / "normalized/.metrics.csv"
        ),
        "which is missing",
    ),
    "a stray file in an attempt's directory": (
        lambda out: _stray(out, f"{_attempt_of(out, 1)}/notes.txt"),
        "holds a file no attempt writes",
    ),
    "a stray entry in plans/": (
        lambda out: _stray(out, "plans/latest/plan.json"),
        "holds an entry that isn't a numbered directory",
    ),
    "a stray entry in cases/": (
        lambda out: _stray(out, "cases/notes.txt"),
        "holds an entry that isn't a case's directory",
    ),
    "a stray entry in a case's directory": (
        lambda out: _stray(out, f"cases/{EXAMPLE.cases[1].case_id}/notes.txt"),
        "holds an entry no case has",
    ),
    "a stray entry in a case's attempts": (
        lambda out: _stray(out, f"cases/{EXAMPLE.cases[1].case_id}/attempts/notes.txt"),
        "holds an entry that isn't an attempt's directory",
    ),
    "a stray file in a plan's directory": (
        lambda out: _stray(out, "plans/2/notes.txt"),
        "holds a file no plan has",
    ),
    "a stray file in a session's directory": (
        lambda out: _stray(out, "sessions/2/notes.txt"),
        "holds a file no session has",
    ),
    "a session record that names another session": (
        lambda out: edit_record(out, "sessions/1/session.json", lambda d: d.update(session=2)),
        "`sessions/1/session.json` names another session than its directory's",
    ),
    # Not an experiment's, whatever its version: the type is checked before the version.
    "a manifest that isn't an experiment's": (
        lambda out: edit_record(
            out,
            "sessions/3/manifest.json",
            lambda d: d.update(artifact_type="run", schema_version="9.9.9"),
        ),
        "isn't an experiment's manifest",
    ),
    "a manifest that names another session": (
        _manifest_of_session_2,
        "`sessions/3/manifest.json` names another session than its directory's",
    ),
    "an attempt record that doesn't hold its start record's": (
        lambda out: edit_record(
            out,
            f"{_attempt_of(out, 1)}/attempt.json",
            lambda d: d["transport"].update(urllib3="2.8.1"),
        ),
        "the attempt record doesn't hold its start record's",
    ),
    "records that give an attempt two starts": (
        lambda out: edit_record(
            out,
            f"{_attempt_of(out, 1)}/attempt.json",
            lambda d: d.update(started_at="2026-10-03T13:00:00Z", ended_at="2026-10-03T13:00:01Z"),
        ),
        "they give it another plan, place, or start",
    ),
    "an attempt that authenticated without its authentication record": (
        lambda out: unlist_record(out, f"{_attempt_of(out, 0)}/authenticating.json"),
        "exactly when it has its authentication record",
    ),
    "a file an attempt record references, changed": (
        lambda out: rewrite_record(
            out, f"{_attempt_of(out, 1)}/request.json", b'{"another": "request"}\n'
        ),
        "doesn't match the artifact_id its attempt record gives it",
    ),
    "an experiment.json that doesn't record its plan's declaration": (
        lambda out: edit_record(
            out, "plans/2/experiment.json", lambda d: d.update(title="Another")
        ),
        "doesn't record the experiment and its planned cases as its plan declares them",
    ),
    "an experiment.json that doesn't record its plan's cases": (
        lambda out: edit_record(
            out,
            "plans/2/experiment.json",
            lambda d: d["planned_cases"][1].update(description="Another description."),
        ),
        "doesn't record the experiment and its planned cases as its plan declares them",
    ),
    "a plan of another experiment": (
        lambda out: _revision_changed(out, experiment_id="another-experiment"),
        "is another experiment's plan",
    ),
    "a plan that doesn't revise the previous one": (
        lambda out: _revision_changed(out, revises="sha256:" + "0" * 64),
        "doesn't revise the previous plan",
    ),
    "a manifest of another experiment": (
        lambda out: edit_record(
            out, "sessions/3/manifest.json", lambda d: d.update(experiment_id="another-one")
        ),
        "is another experiment's manifest",
    ),
    "a manifest that names a plan the experiment doesn't have": (
        lambda out: edit_record(
            out, "sessions/3/manifest.json", lambda d: d.update(plan_hash="sha256:" + "0" * 64)
        ),
        "names a plan the experiment doesn't have",
    ),
    "an attempt record that names a token without its start record": (
        lambda out: unlist_record(out, f"{_attempt_of(out, 1)}/started.json"),
        "the attempt record names a token, without a start record",
    ),
    "an attempt record that references a file outside its directory": (
        lambda out: edit_record(
            out,
            f"{_attempt_of(out, 1)}/attempt.json",
            lambda d: d["request"].update(path=f"{_attempt_of(out, 2)}/request.json"),
        ),
        "references a file that isn't in its directory",
    ),
    "a stray file in a case's tables": (
        lambda out: _stray(out, f"cases/{EXAMPLE.cases[1].case_id}/normalized/notes.txt"),
        "holds a file no case has",
    ),
    "a metrics.csv labeled with another case": (
        lambda out: _table(out, 1, "metrics.csv", {"label": EXAMPLE.cases[2].case_id}),
        "labels its rows with another case",
    ),
    "a metrics.csv without one of the layout's metrics": (
        lambda out: _without_last_row(out, 1, "metrics.csv"),
        "doesn't hold one row for each of the layout's metrics",
    ),
    "a settings.csv without one of its plan's settings": (
        lambda out: _without_last_row(out, 1, "settings.csv"),
        "doesn't hold one row for each of its plan's settings",
    ),
    "a metrics.csv drawn from another response": (
        lambda out: _table(out, 1, "metrics.csv", {"source_artifact": "sha256:" + "0" * 64}),
        "was drawn from another response",
    ),
    "a settings.csv labeled with another case": (
        lambda out: _table(out, 1, "settings.csv", {"label": EXAMPLE.cases[2].case_id}),
        "settings.csv` labels its rows with another case",
    ),
    "a settings.csv drawn from another configuration": (
        lambda out: _table(out, 1, "settings.csv", {"source_artifact": "sha256:" + "0" * 64}),
        "was drawn from another configuration",
    ),
}


@dataclass(frozen=True)
class Checked:
    """An experiment whose records a test breaks: the release whose reader the lab reads it with,
    how the lab completes it, and the configuration a resume reads, or None for its own."""

    reader: Reader
    completed: Callable[[Lab], None]
    resumed_with: str | None


CHECKED: Final = {
    "R03-AC17": Checked(RELEASE_0_3_0, _completed, "revisions/key-renamed.yaml"),
    "R04-AC12": Checked(RELEASE_0_4_0, completed_ranking_example, None),
}
"""`example.yaml`'s experiment, and `ranking-example.yaml`'s, with a ranking definition, by the
criterion their records check traces to."""

BROKEN_RECORDS: Final = [
    pytest.param(CHECKED[criterion], *breaks[name], id=f"{criterion}-{name}")
    for criterion, breaks in (("R03-AC17", BREAKS), ("R04-AC12", RANKING_BREAKS))
    for name in sorted(breaks)
]
"""Each break of each experiment, with the problem the check's message gives for it."""


@pytest.mark.parametrize(("checked", "breaking", "problem"), BROKEN_RECORDS)
def test_records_that_are_broken_fail_the_check_and_nothing_is_written(
    tmp_path: Path,
    server: FakePortfolio123,
    monkeypatch: pytest.MonkeyPatch,
    checked: Checked,
    breaking: Callable[[Path], object],
    problem: str,
) -> None:
    lab = Lab(tmp_path, server, monkeypatch, reader=checked.reader, catch=True)
    checked.completed(lab)
    breaking(lab.out)
    before = snapshot(lab.out)

    ran = lab.resume(checked.resumed_with)

    error = ran.refused("input.not_a_run")
    assert problem in error.message, error.message
    assert ran.received == () and ran.published == ()
    assert snapshot(lab.out) == before


@pytest.mark.parametrize(
    ("path", "listed"),
    [
        ("plans/2/experiment.json", False),
        ("plans/2/plan.json", False),
        ("sessions/1/session.json", False),
        ("sessions/3/manifest.json", False),
        ("{attempt}/authenticating.json", False),
        ("{attempt}/started.json", False),
        ("{attempt}/attempt.json", False),
        ("plans/1/plan.json", True),
    ],
)
def test_a_schema_version_without_a_reader_fails_the_check(
    lab: Lab, path: str, listed: bool
) -> None:
    _completed(lab)
    path = path.format(attempt=_attempt_of(lab.out, 0))
    if listed:
        edit_record(
            lab.out,
            "sessions/3/manifest.json",
            lambda d: next(a for a in d["artifacts"] if a["path"] == path).update(
                schema_version="9.9.9"
            ),
        )
    else:
        edit_record(lab.out, path, lambda d: d.update(schema_version="9.9.9"))

    ran = lab.resume("revisions/key-renamed.yaml")

    error = ran.refused("artifact.unknown_schema_version")
    assert f"`{path}`" in error.message
    assert ("the latest manifest gives it" in error.message) == listed
    assert ran.published == ()


def test_a_saved_configuration_whose_schema_version_has_no_reader_fails_the_check(
    lab: Lab,
) -> None:
    # A plan's configuration.yaml that no manifest lists, as when the run that recorded its plan
    # stopped before its manifest, gives its own schema version, and one without a reader fails
    # as a record's does, not as a broken record.
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"))
    lab.new("default-only.yaml", arm=lambda store: store.fail_os("attempt.json"))
    path = "plans/1/configuration.yaml"
    data = (lab.out / path).read_bytes().replace(b"schema_version: 1.0.0", b"schema_version: 9.9.9")
    assert b"9.9.9" in data
    (lab.out / path).write_bytes(data)
    # Its experiment.json records the file's new artifact_id, so only the version can fail.
    record = json.loads((lab.out / "plans/1/experiment.json").read_bytes())
    record["plans"][-1]["configuration_artifact_id"] = "sha256:" + sha256_hex(data)
    (lab.out / "plans/1/experiment.json").write_text(json.dumps(record, indent=2) + "\n")

    ran = lab.resume("default-only.yaml")

    error = ran.refused("artifact.unknown_schema_version")
    assert f"`{path}`" in error.message
    assert "It reads experiment configurations 1.0.0." in error.message
    assert ran.received == () and ran.published == ()


@pytest.mark.parametrize("status", [401, 403])
def test_a_request_sent_with_a_token_a_401_or_403_dropped_fails_the_check(
    lab: Lab, status: int
) -> None:
    # The second case's request got a 401 or 403, which dropped the token the first case
    # obtained, so the third case authenticated again. A copy of the fifth case's attempt that
    # names the first case's token can't have been sent.
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply(
        "/screen/backtest",
        response("complete.json"),
        Reply(status),
        response("complete.json"),
        response("complete.json"),
        response("complete.json"),
    )
    assert lab.new().refused("execution.partial")
    copy_attempt(
        lab.out, _attempt_of(lab.out, 4), sequence=9, authenticated_by=_first_attempt_id(lab.out)
    )

    ran = lab.resume()

    error = ran.refused("input.not_a_run")
    assert "a token that a 401 or 403 to an earlier request had dropped" in error.message
    assert ran.received == () and ran.published == ()


def test_a_request_sent_with_a_later_attempts_token_fails_the_check(lab: Lab) -> None:
    # The second case's request got a 403, so the third case authenticated again. The second
    # case's records, changed to name the third case's token, name one obtained after its send.
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply(
        "/screen/backtest",
        response("complete.json"),
        Reply(403),
        response("complete.json"),
        response("complete.json"),
        response("complete.json"),
    )
    assert lab.new().refused("execution.partial")
    later = json.loads((lab.out / _attempt_of(lab.out, 2) / "attempt.json").read_bytes())
    edit_attempt(
        lab.out, _attempt_of(lab.out, 1), lambda d: d.update(authenticated_by=later["attempt_id"])
    )

    ran = lab.resume()

    error = ran.refused("input.not_a_run")
    assert "was sent with a token no attempt of its session obtained before it" in error.message
    assert ran.received == () and ran.published == ()


def test_an_attempt_sent_again_without_a_confirmed_repeat_fails_the_check(lab: Lab) -> None:
    attempt_id = unknown_baseline(lab)
    baseline = DEFAULT_ONLY.cases[0].case_id
    raised = (
        (EXPERIMENT_CONFIGS / "default-only.yaml")
        .read_bytes()
        .replace(b"provider_requests: 2", b"provider_requests: 3")
    )
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"))
    (lab.out.parent / "raised.yaml").write_bytes(raised)
    repeat = Repeat(baseline, attempt_id)
    assert (
        lab.resume(lab.out.parent / "raised.yaml", reason="More.", repeats=[repeat]).error is None
    )
    (_, repeated) = sorted(
        (lab.out / "cases" / baseline / "attempts").iterdir(),
        key=lambda p: json.loads((p / "attempt.json").read_bytes())["session"],
    )
    edit_attempt(
        lab.out, repeated.relative_to(lab.out).as_posix(), lambda d: d.update(repeat_of=None)
    )

    ran = lab.resume(lab.out.parent / "raised.yaml")

    error = ran.refused("input.not_a_run")
    assert "without a confirmed repeat of it" in error.message


def test_an_attempt_record_with_an_authentication_but_no_record_of_it_fails_the_check(
    lab: Lab,
) -> None:
    # Trial Folio's own authentication call got a 401, so the attempt record holds its exchange,
    # and the attempt has no start record: its authentication record must be there.
    lab.server.reply("/auth", Reply(401))
    assert lab.new("default-only.yaml").refused("execution.partial")
    (directory,) = lab.attempt_directories(DEFAULT_ONLY.cases[0].case_id)
    unlist_record(lab.out, f"{directory.relative_to(lab.out).as_posix()}/authenticating.json")

    ran = lab.resume("default-only.yaml")

    error = ran.refused("input.not_a_run")
    assert "authenticated without writing its authentication record" in error.message


def test_a_synthetic_experiments_manifest_that_isnt_synthetic_fails_the_check(lab: Lab) -> None:
    assert lab.new("default-only.yaml", synthetic=True).error is None
    edit_record(
        lab.out, "sessions/1/manifest.json", lambda d: d.update(synthetic=False, approval="option")
    )

    ran = lab.resume("default-only.yaml", synthetic=True)

    assert "isn't synthetic, though" in ran.refused("input.not_a_run").message


def test_resuming_needs_the_plans_own_hash(lab: Lab) -> None:
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", response("complete.json"))
    lab.new("default-only.yaml", cancel_after=1)

    ran = lab.resume("default-only.yaml", approve="sha256:" + "0" * 64)

    ran.refused("plan.approval_required")
    assert ran.received == () and ran.published == ()


def test_a_directory_whose_first_plan_wasnt_recorded_cant_be_resumed(lab: Lab) -> None:
    first = lab.new(arm=lambda store: store.fail_os("/plans/1/experiment.json"))
    assert first.refused("storage.write_failed")

    ran = lab.resume()

    error = ran.refused("output.not_empty")
    assert "Remove the directory, and run the command again" in error.message
    assert ran.published == ()
