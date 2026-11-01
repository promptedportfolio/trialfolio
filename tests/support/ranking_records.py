"""The core's records check of an experiment with a ranking definition (release 0.4.0's R04-AC12):
`ranking-example.yaml`'s experiment, which `completed_ranking_example` runs through the lab, over
the fake server, and `RANKING_BREAKS`, the breaks of its records, each with the problem the
records check's message gives for it. It isn't a double: each break changes real files of a real
experiment, with the editors of `tests/support/broken_runs.py`.

TS-T06 moved them here from tests/core/test_ranking_resume.py, with `script`, which scripts the
fake server's replies, and `attempt_at`, so that the records check of
tests/core/test_experiment_resume.py, which TS-T07 separated into
tests/core/test_experiment_records.py, runs them, beside R03-AC17's breaks, as one test, and
tests/core/test_ranking_resume.py and, since TS-T07, test_ranking_records.py still use them
(docs/test-refactoring.md, copies that check less, item 7). Their two editors of a record's exchanges, `transport_changed` and
`rank_update_status`, are broken_runs.py's, which they repeated. TS-T07 moved here
`first_case_faults`, which arms storage faults at the first case's attempt, from
tests/core/test_ranking_resume.py, whose records check, now tests/core/test_ranking_records.py, it
shares.
"""

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

from tests.support.broken_runs import (
    edit_record,
    rank_update_status,
    record_1_1_0,
    rewrite_record,
    transport_changed,
    unlist_record,
)
from tests.support.experiment_lab import Arm, Lab
from tests.support.fake_portfolio123 import (
    AUTHENTICATED,
    FakePortfolio123,
    Reply,
    each_its_own,
    response,
)
from tests.support.paths import EXPERIMENT_CONFIGS, RANKING_DEFINITIONS
from tests.support.plans import ranked_experiment
from tests.support.storage_faults import Fault, StorageFaults
from trialfolio.canonical import sha256_hex
from trialfolio.tables import read_settings_csv_v1_1, settings_csv_v1_1

EXAMPLE: Final = ranked_experiment(EXPERIMENT_CONFIGS / "ranking-example.yaml").plan
"""`ranking-example.yaml`'s plan, whose cases `attempt_at` and the breaks name by their place."""


def script(
    server: FakePortfolio123,
    *,
    auths: int = 1,
    ranks: Sequence[Reply] = (),
    backtests: Sequence[Reply] = (),
) -> None:
    """Scripts the server's replies. Each backtest's 200 gets a response of its own, so no case is
    a stale backtest of the one before it (D-45), unless a test scripts the server itself."""
    server.reply("/auth", *(AUTHENTICATED for _ in range(auths)))
    server.reply("/rank", *ranks, method="POST")
    server.reply("/screen/backtest", *each_its_own(backtests))


def attempt_at(out: Path, case: int) -> str:
    """The directory of the one attempt of `EXAMPLE`'s case at that place."""
    (directory,) = sorted((out / "cases" / EXAMPLE.cases[case].case_id / "attempts").iterdir())
    return directory.relative_to(out).as_posix()


def completed_ranking_example(lab: Lab) -> None:
    """A complete experiment of `ranking-example.yaml`: its first two cases in session 1, the
    rest in session 2, each sent with its session's token but the first."""
    script(
        lab.server,
        auths=2,
        ranks=[response("rank-update.json") for _ in range(4)],
        backtests=[response("complete.json")] * 4,
    )
    lab.new(cancel_after=2).refused("execution.partial")
    assert lab.resume().error is None


def first_case_faults(*faults: tuple[str, Fault]) -> Arm:
    """Faults at `EXAMPLE`'s first case's attempt only, each a file's name and its kind of
    fault."""
    first = EXAMPLE.cases[0].case_id

    def arm(store: StorageFaults) -> None:
        for name, fault in faults:
            store.fail(f"{first}/{name}", fault)

    return arm


def _weight_row_changed(out: Path) -> None:
    path = f"cases/{EXAMPLE.cases[1].case_id}/normalized/settings.csv"
    rows = read_settings_csv_v1_1((out / path).read_bytes(), "settings")
    changed = [
        row.model_copy(update={"value": "45"}) if row.node == "Value/Earnings Yield" else row
        for row in rows
    ]
    rewrite_record(out, path, settings_csv_v1_1(changed))


def _weight_row_source(out: Path) -> None:
    path = f"cases/{EXAMPLE.cases[1].case_id}/normalized/settings.csv"
    rows = read_settings_csv_v1_1((out / path).read_bytes(), "settings")
    other = "sha256:" + "0" * 64
    changed = [
        row.model_copy(update={"source_artifact": other}) if row.node else row for row in rows
    ]
    rewrite_record(out, path, settings_csv_v1_1(changed))


def _weight_row_drawn_from(case: int, node: str, file: str) -> Callable[[Path], None]:
    """Gives the weight row of `node`, in the settings.csv of `EXAMPLE`'s case at that place, the
    `artifact_id` of `file`, one of the plan's, as its source."""

    def change(out: Path) -> None:
        path = f"cases/{EXAMPLE.cases[case].case_id}/normalized/settings.csv"
        rows = read_settings_csv_v1_1((out / path).read_bytes(), "settings")
        source = "sha256:" + sha256_hex((out / file).read_bytes())
        assert any(row.node == node and row.source_artifact != source for row in rows)
        changed = [
            row.model_copy(update={"source_artifact": source}) if row.node == node else row
            for row in rows
        ]
        rewrite_record(out, path, settings_csv_v1_1(changed))

    return change


def _start_record_as_update_record(out: Path) -> None:
    """The second case's `started.json`, replaced by its `updating.json`. The attempt sent with its
    session's token, so its update record holds no exchange, and both records then name the
    rank_update."""
    directory = attempt_at(out, 1)
    rewrite_record(
        out, f"{directory}/started.json", (out / directory / "updating.json").read_bytes()
    )


def _update_record_as_start_record(out: Path) -> None:
    """The second case's `updating.json`, replaced by its `started.json`, which is gone: both
    records then name the backtest, and the update record holds the rank_update's 200."""
    directory = attempt_at(out, 1)
    rewrite_record(
        out, f"{directory}/updating.json", (out / directory / "started.json").read_bytes()
    )
    unlist_record(out, f"{directory}/started.json")


RANKING_BREAKS: Final[dict[str, tuple[Callable[[Path], object], str]]] = {
    "an attempt with started.json and no updating.json": (
        lambda out: unlist_record(out, f"{attempt_at(out, 0)}/updating.json"),
        "without the update record written before it",
    ),
    "an update record that disagrees with its start record": (
        lambda out: edit_record(out, f"{attempt_at(out, 1)}/updating.json", transport_changed),
        "the start record doesn't hold the update record's values",
    ),
    "a started.json that names the rank_update, as its updating.json does": (
        _start_record_as_update_record,
        "a start record doesn't name the request it comes before",
    ),
    "an updating.json that names the backtest, as its missing started.json did": (
        _update_record_as_start_record,
        "a start record doesn't name the request it comes before",
    ),
    "an attempt record that sent its backtest, without its started.json": (
        lambda out: unlist_record(out, f"{attempt_at(out, 1)}/started.json"),
        "its backtest was sent, or may have been, without the start record written before it",
    ),
    "a started.json whose exchanges don't end with the rank_update's 200": (
        lambda out: edit_record(out, f"{attempt_at(out, 1)}/started.json", rank_update_status(500)),
        "isn't a valid start record",
    ),
    "a rank-update-request.json whose bytes aren't what the attempt record records": (
        lambda out: rewrite_record(out, f"{attempt_at(out, 2)}/rank-update-request.json", b"{}\n"),
        "doesn't match the artifact_id its attempt record gives it",
    ),
    "an attempt record 1.1.0 under a plan 1.3.0": (
        lambda out: record_1_1_0(out, attempt_at(out, 0)),
        "aren't the version an attempt under their plan writes",
    ),
    "a backtest's exchange after a rank_update that didn't get a 200": (
        lambda out: edit_record(out, f"{attempt_at(out, 3)}/attempt.json", rank_update_status(500)),
        "isn't a valid attempt record",
    ),
    "a plan whose definition.xml is missing": (
        lambda out: unlist_record(out, "plans/1/definition.xml"),
        "`plans/1/definition.xml` is missing",
    ),
    "a plan whose definition.xml isn't its ranking_source's": (
        lambda out: rewrite_record(
            out, "plans/1/definition.xml", (RANKING_DEFINITIONS / "value-heavy.xml").read_bytes()
        ),
        "isn't its plan's ranking definition",
    ),
    "a weight row that isn't its definition's": (
        _weight_row_changed,
        "weight rows aren't its case's definition's",
    ),
    "a weight row drawn from another file": (
        _weight_row_source,
        "weight rows aren't its case's definition's",
    ),
    "a weight row its ranking variant changes, drawn from the definition": (
        _weight_row_drawn_from(1, "Value", "plans/1/definition.xml"),
        "weight rows aren't its case's definition's",
    ),
    "a weight row its definition gives, drawn from the configuration": (
        _weight_row_drawn_from(0, "Value", "plans/1/configuration.yaml"),
        "weight rows aren't its case's definition's",
    ),
    "a settings.csv listed as 1.0.0 under a plan 1.3.0": (
        lambda out: edit_record(
            out,
            "sessions/2/manifest.json",
            lambda d: next(a for a in d["artifacts"] if a["path"].endswith("settings.csv")).update(
                schema_version="1.0.0"
            ),
        ),
        "another version than its case's plan's",
    ),
}
