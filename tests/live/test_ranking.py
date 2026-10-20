"""The live ranking check: a real experiment of two cases, each writing its definition into
`ApiRankingSystem` before its backtest, changes a metric between its cases; a screen run with the
baseline's definition restores the baseline case's metrics; a snapshot of `ApiRankingSystem`
reads back the definition the restore wrote, and plans offline; and the experiment resumes
offline.

Traces to R04-AC07, and to release 0.4.0's verification commands:
`TRIALFOLIO_LIVE_BUDGET_CREDITS=19 uv run pytest -m live tests/live/test_ranking.py`, with the
credentials injected as AGENTS.md describes; and to R04-AC08's and R04-AC09's live parts. The
marker keeps it out of the default suite and of `scripts/check`. It runs only with the owner
present, who grants its network access for this one command.

The test refuses to start, with a failure that says why, when the command selects another live
check, without both credentials, or with a budget that's missing or below the credits of its
three plans, 19, as 0.1.0's and 0.3.0's live checks do. Each live check reads the whole budget,
so it runs alone.

Its steps are the live check's, in [release 0.4.0](docs/releases/0.4.0-ranking-weights.md):

1. **The experiment,** `experiment-configs/ranking-live.yaml`: `formula.yaml`'s screen settings,
   ranked by `ranking/live.xml`, two top-level composites at 50 each, each holding one factor,
   and one variant, `earnings-heavy`, which sets them to 80 and 20. Two cases, 4 provider
   requests, 12 credits at the documented costs. One `POST /auth` serves both cases, and each
   sends `POST /rank` and then `POST /screen/backtest`, each a 200; at least one of
   `earnings-heavy`'s metrics differs from the baseline's (D-20): one available in both cases,
   whose values differ as numbers. A metric unavailable in either case shows no changed value.
2. **The restore,** `screen-configs/ranking-live.yaml`: the baseline's case as a screen run, 2
   requests and 6 credits, after `ApiRankingSystem` held `earnings-heavy`'s definition. Its
   `case_id` is the baseline's, and every value of its `metrics.csv` equals the baseline case's.
3. **The snapshot,** `ranking-snapshot-configs/api-ranking-system.yaml`: one `rank_get` of
   `ApiRankingSystem`, 1 request and 1 credit. Its `definition.xml` is the restore's definition
   as XML, by its canonical form, and `snapshot.json` gives ranking method 2, `USD`, and `Stock`:
   Portfolio123 stores a definition as equivalent XML, in its own serialization, so not always
   byte for byte, as R04-T13's first live check found, and the owner decided on 2026-10-19. The
   restore's configuration, with the snapshot in place of its definition, then plans offline,
   without credentials, with the restore's weights; its case is the restore's exactly when the
   snapshot holds the definition's bytes, since a case is identified by its definition's bytes.
4. **The resume:** the experiment's command again, under the full guard and without the
   credentials. It resumes, sends nothing, takes no ranking lock, and writes `sessions/2/`.

The installed `trialfolio run` runs each command, with `--approve` and the plan's hash, into a new
directory under `reference/ranking-live-check/payloads/`, which is git-ignored, with the default
endpoint and timeout. Only the three runs may reach Portfolio123's API host, besides localhost.
They take the machine's ranking lock, with `TRIALFOLIO_LOCK_DIR` unset, so no other Trial Folio
process that writes `ApiRankingSystem` runs beside them. Nothing from the responses, the
definitions sent, or the account leaves the git-ignored folder: no assertion shows anything from
them, only outcomes, counts, codes, verdicts, and the credits used. So what the records say is
read out as plain values before it's checked: a failing assertion shows its operands.

Before and after the test, the owner notes the account's ranking systems in the Portfolio123
website: only `ApiRankingSystem` should change (R04-AC07, R04-AC09). The test can't compare them:
Trial Folio reads no list of the account's ranking systems. The run record,
`reference/ranking-live-check/README.md`, gives what the owner found.
"""

import json
import os
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pytest
import trialfolio_network_guard as network_guard

from tests.live.test_screen_backtest import (
    error_code,
    portfolio123_host,
    refuse,
    refuse_beside_another,
    trialfolio,
)
from tests.support.snapshot_builder import naming
from trialfolio.acknowledgment import ACCEPT_VALUE, ACCEPT_VARIABLE
from trialfolio.cli import API_ID_VARIABLE, API_KEY_VARIABLE
from trialfolio.configuration import (
    read_experiment_configuration_v1_1,
    read_ranking_snapshot_configuration,
    read_screen_configuration_v1_1,
)
from trialfolio.contracts.attempt import AttemptRecordV1_2
from trialfolio.contracts.experiment_plan import PlanV1_3
from trialfolio.contracts.plan import PlanV1_2
from trialfolio.contracts.ranking_snapshot import RankingSnapshotRecord
from trialfolio.experiment_records import read_experiment
from trialfolio.planning import (
    build_experiment_plan_v1_1,
    build_plan_v1_1,
    build_snapshot_plan,
    installed_versions,
)
from trialfolio.ranking_lock import LOCK_DIRECTORY_VARIABLE
from trialfolio.storage import LocalArtifactStore
from trialfolio.tables import read_metrics_csv

pytestmark = pytest.mark.live

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
EXPERIMENT = FIXTURES / "experiment-configs" / "ranking-live.yaml"
DEFINITION = FIXTURES / "experiment-configs" / "ranking" / "live.xml"
RESTORE = FIXTURES / "screen-configs" / "ranking-live.yaml"
SNAPSHOT = FIXTURES / "ranking-snapshot-configs" / "api-ranking-system.yaml"
PAYLOADS = REPO_ROOT / "reference" / "ranking-live-check" / "payloads"
"""Git-ignored, like every `payloads/` folder under `reference/` (REQ-11)."""
BUDGET_VARIABLE = "TRIALFOLIO_LIVE_BUDGET_CREDITS"

AUTH, RANK, BACKTEST = "POST /auth", "POST /rank", "POST /screen/backtest"


def metric_values(path: Path) -> dict[tuple[str, str], tuple[str | None, str]]:
    """Each metric of a `metrics.csv`, by its subject and ID: its value, and whether it's
    available. Read as plain values, never shown."""
    rows = read_metrics_csv(path.read_bytes(), path.name)
    return {(row.subject, row.metric_id): (row.value, row.availability) for row in rows}


def _as_number(value: str) -> Decimal | str:
    """A metric's value as a number, so that values that differ only in their digits after the
    point, such as `9.6` and `9.60`, are the same; a date as its text."""
    try:
        return Decimal(value)
    except InvalidOperation:
        return value


def changed_value(before: tuple[str | None, str], after: tuple[str | None, str] | None) -> bool:
    """Whether a metric of `metric_values` changed between two cases: it's available in both,
    and its two values differ, as numbers. A metric that's unavailable in either case shows no
    value that changed, so it isn't evidence that a variant changes a metric (D-20)."""
    if after is None:
        return False
    (first, available), (second, still) = before, after
    if first is None or second is None or "unavailable" in (available, still):
        return False
    return _as_number(first) != _as_number(second)


def canonical(content: bytes) -> str:
    """A definition as XML, by its canonical form (C14N 2.0): its elements, attributes, values,
    and text, whatever the order of its attributes, and whatever lies outside its root."""
    return ET.canonicalize(content.decode("utf-8"))


def weights(plan: PlanV1_2) -> list[tuple[str | None, object]]:
    """Each weight row of a screen run's plan: its node's canonical path, and its weight."""
    return [(row.node, row.value) for row in plan.cases[0].settings if row.node is not None]


def events(log: Path) -> list[str]:
    """Each event a log file names, in order. Events hold no values (REQ-06)."""
    return [str(json.loads(line)["event"]) for line in log.read_text("utf-8").splitlines()]


def test_a_live_weight_variant_changes_a_metric_and_the_baselines_definition_restores_it(
    request: pytest.FixtureRequest,
) -> None:
    # Before anything else, the test refuses to start without what it needs.
    refuse_beside_another(request)
    missing = [name for name in (API_ID_VARIABLE, API_KEY_VARIABLE) if not os.environ.get(name)]
    if missing:
        refuse(f"set {' and '.join(missing)}, as AGENTS.md says, for this command only.")
    versions = installed_versions()
    experiment_read = read_experiment_configuration_v1_1(
        EXPERIMENT.read_bytes(), str(EXPERIMENT), EXPERIMENT
    )
    experiment_plan = build_experiment_plan_v1_1(experiment_read, versions)
    restore_plan = build_plan_v1_1(
        read_screen_configuration_v1_1(RESTORE.read_bytes(), str(RESTORE), RESTORE), versions
    )
    snapshot_plan = build_snapshot_plan(
        read_ranking_snapshot_configuration(SNAPSHOT.read_bytes(), str(SNAPSHOT)), versions
    )
    assert isinstance(experiment_plan, PlanV1_3)
    assert isinstance(restore_plan, PlanV1_2)
    credits = (
        experiment_plan.budget.credits + restore_plan.budget.credits + snapshot_plan.budget.credits
    )
    given = os.environ.get(BUDGET_VARIABLE, "")
    if not (given.isascii() and given.isdecimal()):
        refuse(f"set {BUDGET_VARIABLE} to the approved budget in credits, at least {credits}.")
    budget = int(given)
    if budget < credits:
        refuse(f"the three plans need {credits} credits, and {BUDGET_VARIABLE} is {budget}.")
    assert credits == 19
    baseline, heavy = experiment_plan.cases
    assert (baseline.case_key, heavy.case_key) == ("baseline", "earnings-heavy")
    assert restore_plan.cases[0].case_id == baseline.case_id
    assert experiment_plan.budget.provider_requests == 4

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = PAYLOADS / f"experiment-{stamp}"
    restored = PAYLOADS / f"restore-{stamp}"
    snapshot = PAYLOADS / f"snapshot-{stamp}"
    for directory in (out, restored, snapshot):
        assert not directory.exists()
    PAYLOADS.mkdir(parents=True, exist_ok=True)
    # The owner, who runs the check, acknowledges the license for these processes only. Each run
    # takes the machine's ranking lock.
    environment = {
        **{name: value for name, value in os.environ.items() if name != LOCK_DIRECTORY_VARIABLE},
        ACCEPT_VARIABLE: ACCEPT_VALUE,
    }
    live = {**environment, network_guard.ALLOW_ENV: portfolio123_host()}
    offline = {
        name: value
        for name, value in environment.items()
        if name not in (API_ID_VARIABLE, API_KEY_VARIABLE)
    }
    command = ("run", EXPERIMENT, "--out", out, "--approve", experiment_plan.plan_hash)
    spent = 0

    # 1. The experiment.
    exit_code, summary = trialfolio(*command, env=live)

    code = error_code(summary)
    assert exit_code == 0, f"the experiment failed with {code}; its records are in {out}"
    assert summary["outcome"] == "completed"
    assert [(case["case_key"], case["outcome"]) for case in summary["cases"]] == [
        ("baseline", "succeeded"),
        ("earnings-heavy", "succeeded"),
    ]
    counts = summary["counts"]
    assert (counts["provider_requests"], counts["authentication_calls"]) == (4, 1)
    cost = counts["cost"]
    assert isinstance(cost, int), "Portfolio123 reported no cost"
    spent += cost
    assert spent <= budget, f"the requests used {spent} credits, over the budget of {budget}"
    with LocalArtifactStore(str(out)) as store:
        saved = read_experiment(store, ranking=True)
    # Plain values, read out of the records before they're checked, as the docstring says.
    exchanges = [
        None
        if attempt.record is None
        else [(e.request, e.result, e.status) for e in attempt.record.exchanges]
        for attempt in saved.attempts
    ]
    attempts = [(attempt.case_id, attempt.outcome) for attempt in saved.attempts]
    first = metric_values(out / "cases" / baseline.case_id / "normalized" / "metrics.csv")
    second = metric_values(out / "cases" / heavy.case_id / "normalized" / "metrics.csv")
    changed = sum(changed_value(first[key], second.get(key)) for key in first)
    assert attempts == [(baseline.case_id, "succeeded"), (heavy.case_id, "succeeded")]
    answered = ("response", 200)
    assert exchanges == [
        [(AUTH, *answered), (RANK, *answered), (BACKTEST, *answered)],
        [(RANK, *answered), (BACKTEST, *answered)],
    ]
    assert first.keys() == second.keys()
    assert changed >= 1, "no metric of earnings-heavy differs from the baseline's"

    # 2. The restore, after ApiRankingSystem held earnings-heavy's definition.
    exit_code, summary = trialfolio(
        "run", RESTORE, "--out", restored, "--approve", restore_plan.plan_hash, env=live
    )

    code = error_code(summary)
    assert exit_code == 0, f"the restore failed with {code}; its records are in {restored}"
    assert summary["ids"]["case_id"] == baseline.case_id
    counts = summary["counts"]
    assert counts["provider_requests"] == 2
    cost = counts["cost"]
    assert isinstance(cost, int), "Portfolio123 reported no cost"
    spent += cost
    assert spent <= budget, f"the requests used {spent} credits, over the budget of {budget}"
    (attempt_path,) = restored.glob("cases/*/attempts/*/attempt.json")
    record = AttemptRecordV1_2.model_validate_json(attempt_path.read_bytes())
    restore_exchanges = [(e.request, e.result, e.status) for e in record.exchanges]
    restore = metric_values(restored / "normalized" / "metrics.csv")
    differing = sum(restore.get(key) != value for key, value in first.items())
    assert restore_exchanges == [(AUTH, *answered), (RANK, *answered), (BACKTEST, *answered)]
    assert restore.keys() == first.keys()
    assert differing == 0, f"{differing} of the restore's metrics differ from the baseline case's"

    # 3. The snapshot, which reads back the definition the restore wrote.
    exit_code, summary = trialfolio(
        "run", SNAPSHOT, "--out", snapshot, "--approve", snapshot_plan.plan_hash, env=live
    )

    code = error_code(summary)
    assert exit_code == 0, f"the snapshot failed with {code}; its records are in {snapshot}"
    counts = summary["counts"]
    assert counts["provider_requests"] == 1
    cost = counts["cost"]
    assert isinstance(cost, int), "Portfolio123 reported no cost"
    spent += cost
    assert spent <= budget, f"the requests used {spent} credits, over the budget of {budget}"
    # Portfolio123 stores a definition as equivalent XML, in its own serialization, so the
    # snapshot gives the restore's definition as XML, not always byte for byte.
    read_back = (snapshot / "definition.xml").read_bytes()
    as_xml = canonical(read_back) == canonical(DEFINITION.read_bytes())
    same_bytes = read_back == DEFINITION.read_bytes()
    system = RankingSnapshotRecord.model_validate_json(
        (snapshot / "snapshot.json").read_bytes()
    ).system
    as_sent = (system.ranking_method, system.currency, system.type) == (2, "USD", "Stock")
    assert as_xml, "the snapshot's definition.xml isn't, as XML, the definition the restore sent"
    assert as_sent, "snapshot.json doesn't give ranking method 2, USD, and Stock"
    # The restore's configuration, with the snapshot in place of its definition, plans offline,
    # with the restore's weights. A case is identified by its definition's bytes, so its case is
    # the restore's exactly when the snapshot holds the definition's bytes.
    named = naming(RESTORE, snapshot, PAYLOADS / f"named-{stamp}")
    named_plan = build_plan_v1_1(
        read_screen_configuration_v1_1(named.read_bytes(), str(named), named), versions
    )
    # The plan holds the snapshot's definition, so what it says is read out as plain values
    # before it's checked, as the docstring says: a failing assertion shows its operands.
    by_definition = isinstance(named_plan, PlanV1_2)
    named_case = named_plan.cases[0].case_id
    same_weights = isinstance(named_plan, PlanV1_2) and weights(named_plan) == weights(restore_plan)
    as_restore = named_case == baseline.case_id
    exit_code, summary = trialfolio(
        "run", named, "--out", PAYLOADS / f"unsent-{stamp}", env=offline
    )

    shown = summary["ids"]["case_id"] == named_case
    assert by_definition, "the configuration naming the snapshot doesn't plan with a definition"
    assert exit_code == 2
    assert error_code(summary) == "plan.approval_required"
    assert shown, "the command's case_id isn't that of the plan the snapshot gives"
    assert same_weights, "the plan the snapshot gives doesn't have the restore's weights"
    assert as_restore == same_bytes, "the case isn't the restore's exactly when the bytes are"
    assert not (PAYLOADS / f"unsent-{stamp}").exists()
    print(f"The snapshot held the definition's bytes: {'yes' if same_bytes else 'no'}.")

    # 4. The resume, under the full guard: localhost only, and no credentials.
    exit_code, summary = trialfolio(*command, env=offline)

    code = error_code(summary)
    assert exit_code == 0, f"the resume failed with {code}; its records are in {out}"
    assert summary["outcome"] == "completed"
    assert summary["ids"]["session"] == 2
    counts = summary["counts"]
    assert (counts["provider_requests"], counts["authentication_calls"]) == (4, 1)
    assert (out / "sessions" / "2" / "manifest.json").is_file()
    assert (out / "sessions" / "2" / "report.html").is_file()
    # The first run took the ranking lock; the resume, which sent nothing, didn't.
    assert events(out / "logs" / "trialfolio.log").count("ranking.lock.taken") == 1
    print(f"Credits used, as Portfolio123 reported them: {spent}, of a budget of {budget}.")
