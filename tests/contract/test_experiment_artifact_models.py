"""An experiment's artifact models accept what docs/contracts.md describes, and reject what it calls
invalid.

Traces to docs/contracts.md: experiment plans and revisions (plan 1.1.0), experiment output
(`experiment.json` and the session record), experiment attempts (start and attempt records 1.1.0,
and the authentication record), the experiment manifest, and the JSON summary's version 1.2.0.
Also to R03-AC03's model checks, that `experiment.json`'s entries are numbered from 1, that each
revises the one before it, and that every plan records the approval `not_required` or none does;
and to R03-AC08's, that the manifest's case counts add up. Each document below is synthetic, and
read as a reader reads it: from JSON text, with `model_validate_json`. R03-T06 wrote them.
"""

import json
from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from trialfolio.contracts.attempt import AttemptRecordV1_1, AuthenticationRecord, StartRecordV1_1
from trialfolio.contracts.common import RevisionReason
from trialfolio.contracts.experiment_manifest import ExperimentManifest
from trialfolio.contracts.experiment_plan import PlanV1_1, PlanVariant
from trialfolio.contracts.experiment_record import ExperimentRecord, SessionRecord
from trialfolio.contracts.screen_settings import SCREEN_SETTINGS
from trialfolio.contracts.summary import JsonSummaryV1_2

type Document = dict[str, Any]
type Change = Callable[[Document], object]


def digest(seed: str) -> str:
    return "sha256:" + seed * 32


PLAN_HASH = digest("a1")
EARLIER_PLAN = digest("a0")
BASELINE_ID = "case-0000000000000001"
HOLDINGS_ID = "case-0000000000000002"
DEFAULT_ID = "case-0000000000000003"
RETIRED_ID = "case-0000000000000004"
ATTEMPT_ID = "1b4e28ba-2fa1-4d2b-883f-0016d3cca427"
EARLIER_ATTEMPT = "2c5f39cb-3ab2-4e3c-994a-1127e4ddb538"
TRANSPORT = {"requests": "2.34.2", "urllib3": "2.8.0"}

# The plan, version 1.1.0

SETTING_VALUES: dict[str, object] = {
    "universe": "SP500",
    "screen_type": "stock",
    "rules": ["AvgDailyTot(30) > 1000000"],
    "ranking": {"formula": "EarnYield", "lower_is_better": False},
    "max_holdings": 25,
    "position_method": "long",
    "benchmark": "SPY",
    "currency": "USD",
    "start_date": "2016-01-01",
    "end_date": "2025-12-31",
    "rebalance_weeks": 4,
    "transaction_price": "open",
    "slippage_percent": "0.25",
    "commission": "not_modeled",
    "pit_method": "complete",
    "data_vendor": "FactSet",
    "precision": 4,
    "risk_stats_period": "monthly",
}
FLAGS = {
    "universe": ["not_snapshotted"],
    "data_vendor": ["inferred_default"],
    "risk_stats_period": ["inferred_default"],
}
SETTING_INDEX = {setting.name: index for index, setting in enumerate(SCREEN_SETTINGS)}


def settings_rows() -> list[Document]:
    rows: list[Document] = []
    for setting in SCREEN_SETTINGS:
        sent = setting.name in SETTING_VALUES
        rows.append(
            {
                "setting": setting.name,
                "category": setting.category,
                "critical": setting.category != "other",
                "value": SETTING_VALUES.get(setting.name, "not_sent"),
                "unit": setting.unit,
                "interpretation": "interpreted" if sent else "not_interpreted",
                "expected_provenance": setting.provenance,
                "inference_rule": "A documented rule, checked 2026-10-01"
                if setting.provenance == "inferred"
                else None,
                "flags": FLAGS.get(setting.name, []),
            }
        )
    return rows


def params() -> Document:
    return {
        "screen": {
            "type": "stock",
            "universe": "SP500",
            "maxNumHoldings": 25,
            "method": "long",
            "currency": "USD",
            "benchmark": "SPY",
            "ranking": {"formula": "EarnYield", "lowerIsBetter": False},
            "rules": [{"formula": "AvgDailyTot(30) > 1000000"}],
        },
        "startDt": "2016-01-01",
        "endDt": "2025-12-31",
        "pitMethod": "Complete",
        "precision": 4,
        "transPrice": 1,
        "slippage": 0.25,
        "rebalFreq": "Every 4 Weeks",
    }


def variant(setting: str, value: object = None, **change: object) -> Document:
    return {
        "setting": setting,
        "value": value,
        "add": None,
        "replace": None,
        "with": None,
        "default": False,
    } | change


def plan_case(
    key: str,
    case_id: str,
    variant_: Document | None = None,
    rows: dict[str, object] | None = None,
    sent: Callable[[Document], object] = lambda params: None,
) -> Document:
    settings = settings_rows()
    for name, value in (rows or {}).items():
        settings[SETTING_INDEX[name]]["value"] = value
    request = params()
    sent(request)
    return {
        "case_key": key,
        "case_id": case_id,
        "description": None,
        "variant": variant_,
        "requests": [{"operation": "screen_backtest", "params": request}],
        "settings": settings,
    }


def baseline_case() -> Document:
    return plan_case("baseline", BASELINE_ID)


def holdings_case() -> Document:
    case = plan_case(
        "holdings-50",
        HOLDINGS_ID,
        variant("max_holdings", 50),
        {"max_holdings": 50},
        lambda params: params["screen"].update(maxNumHoldings=50),
    )
    return case | {"description": "Twice the holdings."}


def default_case() -> Document:
    return plan_case(
        "rebalance-weeks-1",
        DEFAULT_ID,
        variant("rebalance_weeks", 1, default=True),
        {"rebalance_weeks": 1},
        lambda params: params.update(rebalFreq="Every Week"),
    )


def rules_case(change: Document, rules: list[str]) -> Document:
    return plan_case(
        "rules-changed",
        "case-0000000000000005",
        change,
        {"rules": rules},
        lambda params: params["screen"].update(rules=[{"formula": rule} for rule in rules]),
    )


def default_on_holdings() -> Document:
    """The default rebalance variant, built on the holdings variant's settings instead of the
    baseline's."""
    return plan_case(
        "rebalance-weeks-1",
        DEFAULT_ID,
        variant("rebalance_weeks", 1, default=True),
        {"max_holdings": 50, "rebalance_weeks": 1},
        lambda params: (
            params["screen"].update(maxNumHoldings=50),
            params.update(rebalFreq="Every Week"),
        ),
    )


def slippage_case() -> Document:
    return plan_case(
        "slippage-050",
        "case-0000000000000006",
        variant("slippage_percent", "0.5"),
        {"slippage_percent": "0.5"},
        lambda params: params.update(slippage=0.5),
    )


def plan() -> Document:
    """Three cases: the baseline, a holdings variant, and the default rebalance variant."""
    return {
        "schema_version": "1.1.0",
        "trialfolio_version": "0.3.0",
        "canonicalization_version": 1,
        "provider_wrapper": {"p123api": "3.1.0"},
        "transport": TRANSPORT,
        "experiment_id": "earnyield-sensitivity",
        "title": "Earnings yield sensitivity",
        "purpose": "How do holdings change the screen's results?",
        "prior_research": {"status": "partial", "description": "Earlier work."},
        "revises": None,
        "cases": [baseline_case(), holdings_case(), default_case()],
        "budget": {
            "provider_requests": 4,
            "credits_per_request": 5,
            "credits_per_request_source": {
                "title": "API: Screen",
                "url": "https://portfolio123.customerly.help/en/articles/43324-api-screen",
                "checked": "2026-10-01",
            },
            "credits": 20,
            "authentication_calls": 4,
        },
        "retry_policy": {
            "automatic_retries": 0,
            "wrapper_attempts_per_call": 1,
            "exchanges_per_call": 1,
        },
        "data_sent": [
            {
                "category": "credentials",
                "recipient": "Portfolio123",
                "via": "p123api",
                "settings": [],
            },
            {
                "category": "strategy_definition",
                "recipient": "Portfolio123",
                "via": "p123api",
                "settings": ["universe", "rules", "ranking"],
            },
            {
                "category": "backtest_settings",
                "recipient": "Portfolio123",
                "via": "p123api",
                "settings": [
                    "screen_type",
                    "max_holdings",
                    "position_method",
                    "benchmark",
                    "currency",
                    "start_date",
                    "end_date",
                    "rebalance_weeks",
                    "transaction_price",
                    "slippage_percent",
                    "pit_method",
                    "precision",
                ],
            },
        ],
        "plan_hash": PLAN_HASH,
    }


# experiment.json, and the session record


def recorded(case: Document) -> Document:
    return {name: case[name] for name in ("case_key", "case_id", "description", "variant")}


def plan_entry(number: int, plan_hash: str, revises: str | None) -> Document:
    return {
        "plan": number,
        "plan_hash": plan_hash,
        "revises": revises,
        "plan_artifact_id": digest(f"{number}b"),
        "configuration_artifact_id": digest(f"{number}c"),
        "approval": "option",
        "reason": None,
        "changes": None,
    }


def experiment_record() -> Document:
    """The record of the first plan."""
    plan_document = plan()
    return {
        "schema_version": "1.0.0",
        "trialfolio_version": "0.3.0",
        "created_at": "2026-10-09T12:00:00Z",
        "experiment_id": plan_document["experiment_id"],
        "title": plan_document["title"],
        "purpose": plan_document["purpose"],
        "prior_research": plan_document["prior_research"],
        "planned_cases": [recorded(case) for case in plan_document["cases"]],
        "retired_cases": [],
        "plans": [plan_entry(1, PLAN_HASH, None)],
    }


def revised_record() -> Document:
    """The record of a revision, plan 3, whose 2 was never recorded: it changed the holdings
    variant's value to 40, under its key, and the purpose, with a new Trial Folio version."""
    document = experiment_record()
    holdings = document["planned_cases"][1]
    retired = recorded(holdings_case()) | {"plan": 1}
    holdings.update(case_id=RETIRED_ID, variant=variant("max_holdings", 40))
    revision = plan_entry(3, digest("a3"), PLAN_HASH) | {
        "reason": "Fewer holdings, and a clearer purpose.",
        "changes": {
            "versions": [{"package": "trialfolio", "previous": "0.3.0", "current": "0.3.1"}],
            "cases_added": [{"case_id": RETIRED_ID, "case_key": "holdings-50"}],
            "cases_retired": [{"case_id": HOLDINGS_ID, "case_key": "holdings-50"}],
            "parts": ["purpose"],
        },
    }
    document.update(
        trialfolio_version="0.3.1",
        purpose="How do fewer holdings change the screen's results?",
        retired_cases=[retired],
        plans=[*document["plans"], revision],
    )
    return document


def session_record() -> Document:
    return {
        "schema_version": "1.0.0",
        "trialfolio_version": "0.3.0",
        "session": 1,
        "started_at": "2026-10-09T12:00:00Z",
    }


# The attempt's records, version 1.1.0

AUTHENTICATION = {"request": "POST /auth", "result": "response", "status": 200, "note": None}
SEND = {"request": "POST /screen/backtest", "result": "response", "status": 200, "note": None}
ATTEMPT_DIRECTORY = f"cases/{HOLDINGS_ID}/attempts/{ATTEMPT_ID}"


def authentication_record() -> Document:
    return {
        "schema_version": "1.0.0",
        "trialfolio_version": "0.3.0",
        "attempt_id": ATTEMPT_ID,
        "case_id": HOLDINGS_ID,
        "plan_hash": PLAN_HASH,
        "session": 1,
        "sequence": 2,
        "repeat_of": None,
        "started_at": "2026-10-09T12:01:00Z",
    }


def start_record() -> Document:
    """An attempt that authenticated itself."""
    return {
        "schema_version": "1.1.0",
        "trialfolio_version": "0.3.0",
        "attempt_id": ATTEMPT_ID,
        "case_id": HOLDINGS_ID,
        "plan_hash": PLAN_HASH,
        "session": 1,
        "sequence": 2,
        "authenticated_by": ATTEMPT_ID,
        "repeat_of": None,
        "started_at": "2026-10-09T12:01:00Z",
        "provider_wrapper": {"p123api": "3.1.0"},
        "transport": TRANSPORT,
        "exchanges": [AUTHENTICATION],
    }


def attempt_record() -> Document:
    """A succeeded attempt sent with the token an earlier attempt of its session obtained."""
    return start_record() | {
        "authenticated_by": EARLIER_ATTEMPT,
        "ended_at": "2026-10-09T12:01:30Z",
        "outcome": "succeeded",
        "error": None,
        "exchanges": [SEND],
        "possibly_charged": True,
        "request": {"path": f"{ATTEMPT_DIRECTORY}/request.json", "artifact_id": digest("d1")},
        "response": {
            "path": f"{ATTEMPT_DIRECTORY}/response.json",
            "artifact_id": digest("d2"),
            "form": "decoded",
        },
        "provider_metadata": {"cost": 5, "quota_remaining": 1000},
    }


# The experiment manifest


def source(form: str, parser_version: int | None, provenance: str, operation: str | None) -> Any:
    return {
        "acquired_at": "2026-10-09T12:00:00Z",
        "format": form,
        "format_version": "1.0.0" if form == "experiment-configuration" else "1",
        "parser_version": parser_version,
        "provenance": provenance,
        "operation": operation,
    }


def listed(path: str, role: str, schema_version: str | None = "1.0.0") -> Document:
    sources = {
        "configuration": source("experiment-configuration", None, "user_supplied", None),
        "provider_request": source("p123api-screen-backtest-request", None, "verified", None),
        "provider_response": source("p123api-screen-backtest", 1, "verified", "screen_backtest"),
    }
    return {
        "path": path,
        "artifact_id": digest("e1"),
        "size": 100,
        "role": role,
        "schema_version": schema_version,
        "source": sources.get(role),
    }


def manifest() -> Document:
    """Session 1's manifest: the holdings case succeeded, the default case failed, and the
    baseline is unknown."""
    tables = f"cases/{HOLDINGS_ID}/normalized"
    return {
        "schema_version": "1.0.0",
        "artifact_type": "experiment",
        "trialfolio_version": "0.3.0",
        "created_at": "2026-10-09T12:05:00Z",
        "experiment_id": "earnyield-sensitivity",
        "session": 1,
        "command": {
            "name": "run",
            "options": {
                "approve": PLAN_HASH,
                "json": False,
                "revision_reason": False,
                "repeat": False,
            },
            "started_at": "2026-10-09T11:59:00Z",
        },
        "synthetic": False,
        "plan": 1,
        "plan_hash": PLAN_HASH,
        "approval": "option",
        "outcome": "partial",
        "error": {"code": "execution.partial", "message": "Some planned cases didn't succeed."},
        "artifacts": [
            listed("plans/1/configuration.yaml", "configuration"),
            listed("plans/1/plan.json", "plan", "1.1.0"),
            listed("plans/1/experiment.json", "experiment_record"),
            listed(f"{ATTEMPT_DIRECTORY}/authenticating.json", "authentication_record"),
            listed(f"{ATTEMPT_DIRECTORY}/started.json", "start_record", "1.1.0"),
            listed(f"{ATTEMPT_DIRECTORY}/attempt.json", "attempt_record", "1.1.0"),
            listed(f"{ATTEMPT_DIRECTORY}/request.json", "provider_request", None),
            listed(f"{ATTEMPT_DIRECTORY}/response.json", "provider_response", None),
            listed(f"{tables}/metrics.csv", "metrics"),
            listed(f"{tables}/settings.csv", "settings"),
            listed("sessions/1/session.json", "session_record"),
            listed("sessions/1/report.html", "report", None),
        ],
        "parsers": [
            {"layout": "p123api-screen-backtest", "layout_version": 1, "parser_version": 1}
        ],
        "license_id": "LicenseRef-NSPRL-1.1",
        "notice_version": "1.0",
        "capabilities": {
            "return_series": "source_only",
            "statistical_validation": "not_assessed",
            "trading_readiness": "not_assessed",
        },
        "reproducibility": {
            "status": "incomplete",
            "external_references": [{"setting": "universe", "snapshotted": False}],
        },
        "counts": {
            "cases": {
                "planned": 3,
                "succeeded": 1,
                "failed": 1,
                "skipped": 0,
                "unknown": 1,
                "not_yet_run": 0,
            },
            "retired_cases": 0,
            "attempts": {"succeeded": 1, "failed": 1, "unknown": 1, "running": 0, "repeats": 0},
            "retries": 0,
            "provider_requests": 3,
            "authentication_calls": 2,
            "budget": {"provider_requests": 4, "authentication_calls": 4},
            "cost": 5,
        },
    }


def synthetic(document: Document) -> None:
    document.update(synthetic=True, approval="not_required", command=None)


def completed(document: Document) -> None:
    document.update(outcome="completed", error=None)
    document["counts"]["cases"].update(succeeded=3, failed=0, unknown=0)


# The JSON summary, version 1.2.0


def summary_case(key: str, case_id: str, outcome: str, repeat: str | None = None) -> Document:
    return {"case_key": key, "case_id": case_id, "outcome": outcome, "repeat_attempt_id": repeat}


def summary() -> Document:
    """A resumed experiment that ended partial, with a case awaiting a repeat."""
    return {
        "schema_version": "1.2.0",
        "command": "run",
        "trialfolio_version": "0.3.0",
        "outcome": "partial",
        "exit_code": 6,
        "ids": {"experiment_id": "earnyield-sensitivity", "plan_hash": PLAN_HASH, "session": 2},
        "output_dir": "runs/study",
        "outputs": {"manifest": "sessions/2/manifest.json", "report": "sessions/2/report.html"},
        "cases": [
            summary_case("baseline", BASELINE_ID, "unknown", ATTEMPT_ID),
            summary_case("holdings-50", HOLDINGS_ID, "succeeded"),
            summary_case("rebalance-weeks-1", DEFAULT_ID, "failed"),
        ],
        "counts": {
            "cases_planned": 3,
            "cases_succeeded": 1,
            "cases_failed": 1,
            "cases_skipped": 0,
            "cases_unknown": 1,
            "cases_not_yet_run": 0,
            "cases_retired": 0,
            "attempts": 3,
            "repeats": 0,
            "provider_requests": 3,
            "authentication_calls": 2,
            "cost": 5,
            "metrics_unavailable": 0,
            "warnings": 0,
        },
        "statistical_validation": "not_assessed",
        "trading_readiness": "not_assessed",
        "error": {"code": "execution.partial", "message": "Some planned cases didn't succeed."},
    }


VALID: list[tuple[type[BaseModel], Callable[[], Document]]] = [
    (PlanV1_1, plan),
    (ExperimentRecord, experiment_record),
    (ExperimentRecord, revised_record),
    (SessionRecord, session_record),
    (AuthenticationRecord, authentication_record),
    (StartRecordV1_1, start_record),
    (AttemptRecordV1_1, attempt_record),
    (ExperimentManifest, manifest),
    (JsonSummaryV1_2, summary),
]
IDS = [
    "plan",
    "experiment-record",
    "revised-experiment-record",
    "session-record",
    "authentication-record",
    "start-record",
    "attempt-record",
    "manifest",
    "summary",
]


def changed(build: Callable[[], Document], change: Change) -> Document:
    document = deepcopy(build())
    change(document)
    return document


def accepts(model: type[BaseModel], document: Document) -> None:
    model.model_validate_json(json.dumps(document))


def rejects(model: type[BaseModel], document: Document) -> None:
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(document))


@pytest.mark.parametrize(("model", "build"), VALID, ids=IDS)
def test_documents_round_trip(model: type[BaseModel], build: Callable[[], Document]) -> None:
    """A valid document reads, and writes back as the same JSON."""
    document = build()

    written = model.model_validate_json(json.dumps(document)).model_dump_json()

    assert json.loads(written) == document


@pytest.mark.parametrize(("model", "build"), VALID, ids=IDS)
def test_unknown_fields_are_rejected(model: type[BaseModel], build: Callable[[], Document]) -> None:
    rejects(model, build() | {"unexpected": 1})


# Plan 1.1.0


def cases_of(document: Document) -> list[Document]:
    cases: list[Document] = document["cases"]
    return cases


def with_case(case: Document) -> Change:
    """Adds a case in its place: a rule variant's before the others, and any other last."""
    if case["variant"]["setting"] == "rules":
        return lambda document: cases_of(document).insert(1, case)
    return lambda document: cases_of(document).append(case)


PLAN_ACCEPTS: dict[str, Change] = {
    "a revision": lambda d: d.update(revises=EARLIER_PLAN),
    "a replaced rule": with_case(
        rules_case(
            variant("rules", replace="AvgDailyTot(30) > 1000000", **{"with": "Price > 5"}),
            ["Price > 5"],
        )
    ),
    "an added rule": with_case(
        rules_case(
            variant("rules", add="MktCap > 300"), ["AvgDailyTot(30) > 1000000", "MktCap > 300"]
        )
    ),
    "a slippage variant": with_case(slippage_case()),
    "no default": lambda d: cases_of(d).pop(),
    "unknown prior research without a description": lambda d: d.update(
        prior_research={"status": "unknown", "description": None}
    ),
    "a budget of exactly the cases": lambda d: d["budget"].update(
        provider_requests=3, authentication_calls=3, credits=15
    ),
}


@pytest.mark.parametrize("change", PLAN_ACCEPTS.values(), ids=PLAN_ACCEPTS.keys())
def test_plan_accepts(change: Change) -> None:
    accepts(PlanV1_1, changed(plan, change))


def screen_params(document: Document, case: int) -> Document:
    screen: Document = cases_of(document)[case]["requests"][0]["params"]["screen"]
    return screen


def setting_of(document: Document, case: int, name: str) -> Document:
    row: Document = cases_of(document)[case]["settings"][SETTING_INDEX[name]]
    return row


PLAN_REJECTS: dict[str, Change] = {
    "version 1.0.0": lambda d: d.update(schema_version="1.0.0"),
    "a null purpose": lambda d: d.update(purpose=None),
    "partial prior research without a description": lambda d: d.update(
        prior_research={"status": "partial", "description": None}
    ),
    "one case": lambda d: d.update(cases=cases_of(d)[:1]),
    "a variant first, the others built on it": lambda d: d.update(
        cases=[holdings_case(), default_on_holdings()]
    ),
    "a baseline with a variant": lambda d: cases_of(d)[0].update(
        variant=variant("max_holdings", 50)
    ),
    "a baseline with a description": lambda d: cases_of(d)[0].update(description="The baseline."),
    "a variant keyed baseline": lambda d: cases_of(d)[1].update(case_key="baseline"),
    "a repeated case key": with_case(slippage_case() | {"case_key": "holdings-50"}),
    "a repeated case ID": lambda d: cases_of(d)[2].update(case_id=HOLDINGS_ID),
    "a variant that changes another setting too": lambda d: (
        setting_of(d, 1, "benchmark").update(value="IWM"),
        screen_params(d, 1).update(benchmark="IWM"),
    ),
    "a variant whose setting isn't its change": lambda d: (
        setting_of(d, 1, "max_holdings").update(value=40),
        screen_params(d, 1).update(maxNumHoldings=40),
    ),
    "a variant that changes nothing": lambda d: (
        cases_of(d)[1]["variant"].update(value=25),
        setting_of(d, 1, "max_holdings").update(value=25),
        cases_of(d)[1]["requests"][0]["params"]["screen"].update(maxNumHoldings=25),
    ),
    "a request that isn't what the settings send": lambda d: cases_of(d)[1]["requests"][0][
        "params"
    ]["screen"].update(maxNumHoldings=25),
    "two cases with one change": lambda d: cases_of(d).insert(
        2, holdings_case() | {"case_key": "holdings-again", "case_id": "case-0000000000000009"}
    ),
    "the variants out of order": lambda d: cases_of(d).insert(1, cases_of(d).pop()),
    "a rule variant that adds a baseline rule": with_case(
        rules_case(
            variant("rules", add="AvgDailyTot(30) > 1000000"),
            ["AvgDailyTot(30) > 1000000", "AvgDailyTot(30) > 1000000"],
        )
    ),
    "a rule variant that replaces no baseline rule": with_case(
        rules_case(
            variant("rules", replace="Price > 1", **{"with": "Price > 5"}),
            ["AvgDailyTot(30) > 1000000"],
        )
    ),
    "a rule variant that replaces a rule with itself": with_case(
        rules_case(
            variant(
                "rules",
                replace="AvgDailyTot(30) > 1000000",
                **{"with": "AvgDailyTot(30) > 1000000"},
            ),
            ["AvgDailyTot(30) > 1000000"],
        )
    ),
    "a rule variant with add and replace": with_case(
        rules_case(
            variant(
                "rules",
                add="MktCap > 300",
                replace="AvgDailyTot(30) > 1000000",
                **{"with": "Price > 5"},
            ),
            ["Price > 5"],
        )
    ),
    "a rule variant with a value": with_case(
        rules_case(
            variant("rules", 5, add="MktCap > 300"), ["AvgDailyTot(30) > 1000000", "MktCap > 300"]
        )
    ),
    "a holdings variant with an add": lambda d: cases_of(d)[1]["variant"].update(
        add="MktCap > 300"
    ),
    "a slippage variant given as a number": with_case(
        slippage_case() | {"variant": variant("slippage_percent", 0.5)}
    ),
    "a default that isn't a rebalance variant": lambda d: cases_of(d)[1]["variant"].update(
        default=True
    ),
    "a default under another key": lambda d: cases_of(d)[2].update(case_key="weekly"),
    "a default with a description": lambda d: cases_of(d)[2].update(description="Weekly."),
    "a budget below the cases": lambda d: d["budget"].update(
        provider_requests=2, authentication_calls=2, credits=10
    ),
    "authentication calls other than the requests": lambda d: d["budget"].update(
        authentication_calls=5
    ),
    "credits that aren't requests times their cost": lambda d: d["budget"].update(credits=5),
    "a plan that revises itself": lambda d: d.update(revises=PLAN_HASH),
    "an experiment ID that's a device name": lambda d: d.update(experiment_id="aux"),
}


@pytest.mark.parametrize("change", PLAN_REJECTS.values(), ids=PLAN_REJECTS.keys())
def test_plan_rejects(change: Change) -> None:
    rejects(PlanV1_1, changed(plan, change))


@pytest.mark.parametrize(
    "document",
    [
        variant("max_holdings"),
        variant("max_holdings", "50"),
        variant("max_holdings", 50, add="MktCap > 300"),
        variant("rebalance_weeks", 2),
        variant("slippage_percent", "0.250"),
        variant("rules"),
        variant("rules", 5, add="MktCap > 300"),
        variant("rules", add="MktCap > 300", replace="Price > 1", **{"with": "Price > 5"}),
        variant("rules", replace="Price > 1"),
        variant("rules", **{"with": "Price > 5"}),
        variant("rules", add="MktCap > 300", default=True),
    ],
    ids=[
        "no-value",
        "holdings-as-text",
        "value-and-add",
        "rebalance-weeks-2",
        "slippage-not-normalized",
        "no-change",
        "rule-change-and-value",
        "add-and-replace",
        "replace-without-with",
        "with-without-replace",
        "default-rule",
    ],
)
def test_plan_variant_rejects(document: Document) -> None:
    """A variant gives its setting's change, as the configuration does, and nothing else."""
    rejects(PlanVariant, document)


def test_a_rule_variant_writes_with_by_its_name() -> None:
    document = changed(
        plan,
        with_case(
            rules_case(
                variant("rules", replace="AvgDailyTot(30) > 1000000", **{"with": "Price > 5"}),
                ["Price > 5"],
            )
        ),
    )

    written = json.loads(PlanV1_1.model_validate_json(json.dumps(document)).model_dump_json())

    assert written["cases"][1]["variant"]["with"] == "Price > 5"
    assert "with_" not in written["cases"][1]["variant"]


# experiment.json


def entries(document: Document) -> list[Document]:
    plans: list[Document] = document["plans"]
    return plans


VERSIONS_ONLY: Document = {
    "versions": [{"package": "trialfolio", "previous": "0.3.1", "current": "0.3.2"}],
    "cases_added": [],
    "cases_retired": [],
    "parts": [],
}


def only_versions(document: Document) -> None:
    """The revision changes only Trial Folio's version, so every case is kept."""
    entries(document)[1]["changes"] = deepcopy(VERSIONS_ONLY)
    document.update(retired_cases=[])
    document["planned_cases"][1].update(case_id=HOLDINGS_ID, variant=variant("max_holdings", 50))


EXPERIMENT_RECORD_ACCEPTS: dict[str, Change] = {
    "plans numbered with a gap": lambda d: None,  # revised_record's 1 and 3
    "a revision whose only change is of versions": only_versions,
    "a synthetic experiment": lambda d: [
        entry.update(approval="not_required") for entry in entries(d)
    ],
}


@pytest.mark.parametrize(
    "change", EXPERIMENT_RECORD_ACCEPTS.values(), ids=EXPERIMENT_RECORD_ACCEPTS.keys()
)
def test_experiment_record_accepts(change: Change) -> None:
    accepts(ExperimentRecord, changed(revised_record, change))


EXPERIMENT_RECORD_REJECTS: dict[str, Change] = {
    # R03-AC03's three model checks.
    "entries not numbered from 1": lambda d: (
        entries(d)[0].update(plan=2),
        d["retired_cases"][0].update(plan=2),
    ),
    "entries out of order": lambda d: entries(d)[1].update(plan=1),
    "an entry that doesn't revise the one before it": lambda d: entries(d)[1].update(
        revises=EARLIER_PLAN
    ),
    "not_required for some plans and not others": lambda d: entries(d)[0].update(
        approval="not_required"
    ),
    "a first plan that revises one": lambda d: entries(d)[0].update(
        revises=EARLIER_PLAN, reason="A reason.", changes=deepcopy(VERSIONS_ONLY)
    ),
    "a first plan with a reason": lambda d: entries(d)[0].update(reason="A reason."),
    "a revision without a reason": lambda d: entries(d)[1].update(reason=None),
    "a revision without its changes": lambda d: entries(d)[1].update(changes=None),
    "a blank reason": lambda d: entries(d)[1].update(reason="  "),
    "a revision that changes nothing": lambda d: (
        only_versions(d),
        entries(d)[1]["changes"].update(versions=[]),
    ),
    "a version change that changes nothing": lambda d: entries(d)[1]["changes"]["versions"][
        0
    ].update(current="0.3.0"),
    "versions out of order": lambda d: entries(d)[1]["changes"]["versions"].insert(
        0, {"package": "p123api", "previous": "3.1.0", "current": "3.2.0"}
    ),
    "a version changed twice": lambda d: entries(d)[1]["changes"]["versions"].append(
        entries(d)[1]["changes"]["versions"][0]
    ),
    "parts out of order": lambda d: entries(d)[1]["changes"].update(parts=["purpose", "title"]),
    "a part twice": lambda d: entries(d)[1]["changes"].update(parts=["purpose", "purpose"]),
    "an unknown part": lambda d: entries(d)[1]["changes"].update(parts=["settings"]),
    "a case added that isn't planned": lambda d: entries(d)[1]["changes"]["cases_added"][0].update(
        case_id="case-00000000000000ff"
    ),
    "a case retired that isn't retired": lambda d: d.update(retired_cases=[]),
    "a retired case the revision didn't record": lambda d: entries(d)[1]["changes"].update(
        cases_retired=[]
    ),
    "a retired case under another key": lambda d: d["retired_cases"][0].update(case_key="other"),
    "a retired case from a plan that isn't earlier": lambda d: d["retired_cases"].append(
        d["retired_cases"][0] | {"case_id": "case-00000000000000ee", "plan": 3}
    ),
    "a retired case from a plan the history skips": lambda d: d["retired_cases"].append(
        d["retired_cases"][0] | {"case_id": "case-00000000000000ee", "plan": 2}
    ),
    "a case both planned and retired": lambda d: (
        d["retired_cases"][0].update(case_id=BASELINE_ID),
        entries(d)[1]["changes"]["cases_retired"][0].update(case_id=BASELINE_ID),
    ),
    "a variant first": lambda d: d["planned_cases"].reverse(),
    "one planned case": lambda d: d.update(planned_cases=d["planned_cases"][:1]),
    "a planned variant without a variant": lambda d: d["planned_cases"][2].update(variant=None),
    "a planned baseline with a variant": lambda d: d["planned_cases"][0].update(
        variant=variant("max_holdings", 50)
    ),
    "a planned baseline with a description": lambda d: d["planned_cases"][0].update(
        description="The baseline."
    ),
    "repeated planned keys": lambda d: d["planned_cases"][2].update(case_key="holdings-50"),
    "repeated plan hashes": lambda d: entries(d).append(
        entries(d)[1]
        | {"plan": 4, "plan_hash": PLAN_HASH, "revises": entries(d)[1]["plan_hash"]}
        | {"changes": VERSIONS_ONLY}
    ),
    "no plans": lambda d: d.update(plans=[]),
}


@pytest.mark.parametrize(
    "change", EXPERIMENT_RECORD_REJECTS.values(), ids=EXPERIMENT_RECORD_REJECTS.keys()
)
def test_experiment_record_rejects(change: Change) -> None:
    rejects(ExperimentRecord, changed(revised_record, change))


def test_a_reason_is_valid_utf_8_text() -> None:
    """JSON text can escape a lone surrogate, which no UTF-8 text holds, so experiment.json
    couldn't hold the reason (approving a revision)."""
    with pytest.raises(ValidationError):
        TypeAdapter(RevisionReason).validate_python("Why \ud800")


def test_a_first_plan_has_retired_no_case() -> None:
    retired = recorded(holdings_case()) | {"case_id": RETIRED_ID, "plan": 1}

    rejects(
        ExperimentRecord, changed(experiment_record, lambda d: d.update(retired_cases=[retired]))
    )


@pytest.mark.parametrize(
    "change",
    [lambda d: d.update(session=0), lambda d: d.update(started_at="2026-10-09T12:00:00+01:00")],
    ids=["session-0", "not-utc"],
)
def test_session_record_rejects(change: Change) -> None:
    rejects(SessionRecord, changed(session_record, change))


# The attempt's records


def failed_authentication(document: Document) -> None:
    """An attempt whose own authentication call failed, so it has no start record."""
    document.update(
        authenticated_by=None,
        outcome="failed",
        error={"code": "provider.auth_failed", "message": "Portfolio123 refused the credentials."},
        exchanges=[AUTHENTICATION | {"status": 401}],
        possibly_charged=False,
        request=None,
        response=None,
    )


def resumed_from_authentication(document: Document) -> None:
    """The attempt record a resume writes for an attempt whose only record is its authentication
    record."""
    document.update(
        authenticated_by=None,
        outcome="failed",
        error={"code": "command.interrupted", "message": "The run was interrupted."},
        exchanges=[AUTHENTICATION | {"result": "interrupted", "status": None}],
        possibly_charged=False,
        request=None,
        response=None,
    )


def unknown_without_response(document: Document) -> None:
    """A `running` attempt a resume recorded without a saved response: its exchanges are its
    start record's, here none, since it sent with an earlier attempt's token."""
    document.update(
        outcome="unknown",
        error={"code": "provider.outcome_unknown", "message": "No response was recorded."},
        exchanges=[],
        possibly_charged=True,
        response=None,
    )


ATTEMPT_ACCEPTS: dict[str, Change] = {
    "its own authentication": lambda d: d.update(
        authenticated_by=ATTEMPT_ID, exchanges=[AUTHENTICATION, SEND]
    ),
    "a failed authentication": failed_authentication,
    "an attempt resumed from its authentication record": resumed_from_authentication,
    "an unknown attempt without its exchanges": unknown_without_response,
    "a repeat": lambda d: d.update(repeat_of=EARLIER_ATTEMPT),
    "an interrupt after its own authentication, before its start record": lambda d: d.update(
        authenticated_by=None,
        outcome="failed",
        error={"code": "command.interrupted", "message": "The run was interrupted."},
        exchanges=[AUTHENTICATION],
        possibly_charged=False,
        request=None,
        response=None,
    ),
}


@pytest.mark.parametrize("change", ATTEMPT_ACCEPTS.values(), ids=ATTEMPT_ACCEPTS.keys())
def test_attempt_record_accepts(change: Change) -> None:
    accepts(AttemptRecordV1_1, changed(attempt_record, change))


ATTEMPT_REJECTS: dict[str, Change] = {
    "version 1.0.0": lambda d: d.update(schema_version="1.0.0"),
    "a send without authentication": lambda d: d.update(authenticated_by=None),
    "an unknown attempt without authentication": lambda d: (
        unknown_without_response(d),
        d.update(authenticated_by=None),
    ),
    "its own token without authenticating": lambda d: d.update(authenticated_by=ATTEMPT_ID),
    "its own token after a failed authentication": lambda d: d.update(
        authenticated_by=ATTEMPT_ID,
        exchanges=[AUTHENTICATION | {"status": 401}, SEND],
    ),
    "another's token after authenticating": lambda d: d.update(exchanges=[AUTHENTICATION, SEND]),
    "a send after a failed authentication": lambda d: (
        failed_authentication(d),
        d.update(
            exchanges=[AUTHENTICATION | {"status": 401}, SEND | {"status": 400}],
            request=attempt_record()["request"],
            possibly_charged=True,
        ),
    ),
    "a repeat of itself": lambda d: d.update(repeat_of=ATTEMPT_ID),
    "session 0": lambda d: d.update(session=0),
    "sequence 0": lambda d: d.update(sequence=0),
    "two sends": lambda d: d.update(exchanges=[SEND, SEND]),
    "a succeeded attempt without its response": lambda d: d.update(response=None),
    "not possibly charged after a send": lambda d: d.update(possibly_charged=False),
}


@pytest.mark.parametrize("change", ATTEMPT_REJECTS.values(), ids=ATTEMPT_REJECTS.keys())
def test_attempt_record_rejects(change: Change) -> None:
    rejects(AttemptRecordV1_1, changed(attempt_record, change))


START_ACCEPTS: dict[str, Change] = {
    "an earlier attempt's token": lambda d: d.update(
        authenticated_by=EARLIER_ATTEMPT, exchanges=[]
    ),
    "a repeat": lambda d: d.update(repeat_of=EARLIER_ATTEMPT),
}


@pytest.mark.parametrize("change", START_ACCEPTS.values(), ids=START_ACCEPTS.keys())
def test_start_record_accepts(change: Change) -> None:
    accepts(StartRecordV1_1, changed(start_record, change))


START_REJECTS: dict[str, Change] = {
    "no authenticated_by": lambda d: d.update(authenticated_by=None),
    "its own token without authenticating": lambda d: d.update(exchanges=[]),
    "another's token after authenticating": lambda d: d.update(authenticated_by=EARLIER_ATTEMPT),
    "a failed authentication": lambda d: d.update(exchanges=[AUTHENTICATION | {"status": 401}]),
    "the request's exchange": lambda d: d.update(exchanges=[SEND]),
    "two exchanges": lambda d: d.update(exchanges=[AUTHENTICATION, AUTHENTICATION]),
    "a repeat of itself": lambda d: d.update(repeat_of=ATTEMPT_ID),
}


@pytest.mark.parametrize("change", START_REJECTS.values(), ids=START_REJECTS.keys())
def test_start_record_rejects(change: Change) -> None:
    rejects(StartRecordV1_1, changed(start_record, change))


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(repeat_of=ATTEMPT_ID),
        lambda d: d.update(sequence=0),
        lambda d: d.update(attempt_id=ATTEMPT_ID.replace("-", "")),
    ],
    ids=["repeat-of-itself", "sequence-0", "attempt-id-without-hyphens"],
)
def test_authentication_record_rejects(change: Change) -> None:
    rejects(AuthenticationRecord, changed(authentication_record, change))


# The experiment manifest


def artifacts(document: Document) -> list[Document]:
    listed_artifacts: list[Document] = document["artifacts"]
    return listed_artifacts


def without(path: str) -> Change:
    return lambda d: d.update(artifacts=[a for a in artifacts(d) if a["path"] != path])


MANIFEST_ACCEPTS: dict[str, Change] = {
    "completed": completed,
    "synthetic": synthetic,
    "run by the core, without a command": lambda d: d.update(command=None),
    "a case without its tables": lambda d: (
        without(f"cases/{HOLDINGS_ID}/normalized/metrics.csv")(d),
        without(f"cases/{HOLDINGS_ID}/normalized/settings.csv")(d),
    ),
    "an undecoded response": lambda d: artifacts(d)[7].update(
        path=f"{ATTEMPT_DIRECTORY}/response.raw", role="provider_response_undecoded"
    ),
    "a revision, plan 3, without plan 2's directory": lambda d: (
        d.update(plan=3),
        artifacts(d).extend(
            listed(f"plans/3/{name}", role)
            for name, role in (
                ("configuration.yaml", "configuration"),
                ("plan.json", "plan"),
                ("experiment.json", "experiment_record"),
            )
        ),
    ),
    "a repeat counted": lambda d: d["counts"]["attempts"].update(repeats=1),
    "requests counted above a lowered budget": lambda d: d["counts"]["budget"].update(
        provider_requests=2, authentication_calls=2
    ),
}


@pytest.mark.parametrize("change", MANIFEST_ACCEPTS.values(), ids=MANIFEST_ACCEPTS.keys())
def test_manifest_accepts(change: Change) -> None:
    accepts(ExperimentManifest, changed(manifest, change))


def case_counts(document: Document) -> Document:
    counts: Document = document["counts"]["cases"]
    return counts


def only_plan_3(document: Document) -> None:
    """The current plan is 3, and the first plan isn't listed."""
    document.update(plan=3)
    for artifact in artifacts(document):
        artifact["path"] = artifact["path"].replace("plans/1/", "plans/3/")


def attempt_directory(name: str) -> Change:
    """Names the attempt's directory `name`, 36 characters that aren't a version 4 UUID in
    canonical form."""
    return lambda d: [
        artifact.update(path=artifact["path"].replace(ATTEMPT_ID, name))
        for artifact in artifacts(d)
    ]


MANIFEST_REJECTS: dict[str, Change] = {
    # R03-AC08: the case counts add up.
    "case counts that add up to less": lambda d: case_counts(d).update(planned=4),
    "case counts that add up to more": lambda d: case_counts(d).update(not_yet_run=1),
    "one planned case": lambda d: case_counts(d).update(planned=1, failed=0, unknown=0),
    "completed with a case that didn't succeed": lambda d: d.update(
        outcome="completed", error=None
    ),
    "partial with every case succeeded": lambda d: case_counts(d).update(
        succeeded=3, failed=0, unknown=0
    ),
    "failed": lambda d: d.update(outcome="failed"),
    "partial with another error": lambda d: d["error"].update(code="storage.write_failed"),
    "synthetic with an approval": lambda d: d.update(synthetic=True),
    "not_required for an experiment that isn't synthetic": lambda d: d.update(
        approval="not_required"
    ),
    "synthetic with a command": lambda d: (synthetic(d), d.update(command=manifest()["command"])),
    "a command other than run": lambda d: d["command"].update(name="demo"),
    "the configuration's path in the options": lambda d: d["command"]["options"].update(
        config="study.yaml"
    ),
    "more repeats than attempts": lambda d: d["counts"]["attempts"].update(repeats=4),
    "a retry": lambda d: d["counts"].update(retries=1),
    "a file at another role's path": lambda d: artifacts(d)[1].update(role="experiment_record"),
    "a start record listed as the attempt record": lambda d: artifacts(d)[4].update(
        role="attempt_record"
    ),
    "a configuration without its source record": lambda d: artifacts(d)[0].update(source=None),
    "a configuration read by a parser": lambda d: artifacts(d)[0]["source"].update(
        parser_version=1
    ),
    "the lock listed": lambda d: artifacts(d).append(listed("experiment.lock", "report", None)),
    "the logs listed": lambda d: artifacts(d).append(listed("logs/trialfolio.log", "report", None)),
    "another session's record and report": lambda d: [
        artifact.update(path=artifact["path"].replace("sessions/1/", "sessions/2/"))
        for artifact in artifacts(d)
    ],
    "its own manifest listed": lambda d: artifacts(d).append(
        listed("sessions/1/manifest.json", "report", None)
    ),
    "no report": without("sessions/1/report.html"),
    "no session record": without("sessions/1/session.json"),
    "a plan without its experiment record": without("plans/1/experiment.json"),
    "a plan newer than the current plan": lambda d: artifacts(d).extend(
        listed(f"plans/2/{name}", role)
        for name, role in (
            ("configuration.yaml", "configuration"),
            ("plan.json", "plan"),
            ("experiment.json", "experiment_record"),
        )
    ),
    "a current plan that isn't listed": lambda d: d.update(plan=2),
    "no first plan": only_plan_3,
    "a case with metrics.csv alone": without(f"cases/{HOLDINGS_ID}/normalized/settings.csv"),
    "a path listed twice": lambda d: artifacts(d).append(artifacts(d)[4]),
    "a case ID's directory named by its key": lambda d: artifacts(d)[8].update(
        path="cases/holdings-50/normalized/metrics.csv"
    ),
    # An attempt's directory is named by its attempt_id, a version 4 UUID in canonical form.
    "an attempt's directory of hyphens": attempt_directory("-" * 36),
    "an attempt's directory with misplaced hyphens": attempt_directory(
        "1b4e28ba2-fa1-4d2b-883f-0016d3cca427"
    ),
    "an attempt's directory named by a version 1 UUID": attempt_directory(
        "1b4e28ba-2fa1-1d2b-883f-0016d3cca427"
    ),
    "an attempt's directory named by a UUID of another variant": attempt_directory(
        "1b4e28ba-2fa1-4d2b-c83f-0016d3cca427"
    ),
    "no parser": lambda d: d.update(parsers=[]),
    "a parser listed twice": lambda d: d["parsers"].append(d["parsers"][0]),
    "an experiment ID that's a device name": lambda d: d.update(experiment_id="com1"),
    "a run's artifact type": lambda d: d.update(artifact_type="run"),
}


@pytest.mark.parametrize("change", MANIFEST_REJECTS.values(), ids=MANIFEST_REJECTS.keys())
def test_manifest_rejects(change: Change) -> None:
    rejects(ExperimentManifest, changed(manifest, change))


LISTED_FILES = [artifact["path"].rpartition("/")[2] for artifact in manifest()["artifacts"]]


@pytest.mark.parametrize("index", range(len(LISTED_FILES)), ids=LISTED_FILES)
def test_a_files_name_is_its_roles_exactly(index: int) -> None:
    """The dot in a role's file name is a dot: `plans/1/planXjson` isn't the plan's `plan.json`,
    and `sessions/1/reportXhtml` isn't the session's report."""

    def substitute(document: Document) -> None:
        artifact = artifacts(document)[index]
        stem, _, extension = artifact["path"].rpartition(".")
        artifact["path"] = f"{stem}X{extension}"

    rejects(ExperimentManifest, changed(manifest, substitute))


# The JSON summary, version 1.2.0


def without_approval(document: Document) -> None:
    """`run --json` without `--approve`, resuming: the plan is built, and no session is
    reserved, so nothing was written."""
    document.update(
        outcome="failed",
        exit_code=2,
        output_dir=None,
        outputs={},
        error={"code": "plan.approval_required", "message": "Running this plan needs approval."},
    )
    document["ids"].pop("session")


def locked(document: Document) -> None:
    """`experiment.locked`: the configuration is valid, and the records were never read."""
    without_approval(document)
    document.update(
        exit_code=4,
        ids={"experiment_id": "earnyield-sensitivity"},
        counts={},
        error={"code": "experiment.locked", "message": "Another process holds the lock."},
    )
    document.pop("cases")


def before_the_plan(document: Document) -> None:
    """A resume that fails with `environment.unsupported`: it has read and checked the records,
    so its counts are known, and it hasn't built the plan, or reserved a session."""
    without_approval(document)
    document.update(
        exit_code=3,
        ids={"experiment_id": "earnyield-sensitivity"},
        error={
            "code": "environment.unsupported",
            "message": "The installed requests isn't a verified version.",
        },
    )
    document.pop("cases")


RUN_COUNTS: Document = {
    "attempts": 3,
    "provider_requests": 3,
    "metrics_unavailable": 0,
    "warnings": 0,
    "cost": 5,
}


def every_case_succeeded(document: Document) -> None:
    """Each of the three cases succeeded, and the counts say so. The outcome is left as it is."""
    document["counts"].update(cases_succeeded=3, cases_failed=0, cases_unknown=0)
    for case in document["cases"]:
        case.update(outcome="succeeded", repeat_attempt_id=None)


def completed_run(document: Document) -> None:
    document.update(outcome="completed", exit_code=0, error=None)


SUMMARY_ACCEPTS: dict[str, Change] = {
    "without approval": without_approval,
    "locked": locked,
    "a resume before its plan is built": before_the_plan,
    "completed": lambda d: (completed_run(d), every_case_succeeded(d)),
    "a new experiment before its session": lambda d: (
        d["ids"].pop("session"),
        d.update(
            outcome="failed",
            exit_code=4,
            outputs={},
            error={"code": "storage.write_failed", "message": "session.json wasn't written."},
        ),
    ),
    "a revision's cases, the retired counted": lambda d: d["counts"].update(cases_retired=1),
    "an invalid configuration, as a screen run's": lambda d: d.update(
        outcome="failed",
        exit_code=3,
        ids={},
        output_dir=None,
        outputs={},
        cases=None,
        counts={
            "attempts": 0,
            "provider_requests": 0,
            "metrics_unavailable": 0,
            "warnings": 0,
            "cost": None,
        },
        error={"code": "config.invalid", "message": "study.yaml isn't a valid configuration."},
    ),
}


@pytest.mark.parametrize("change", SUMMARY_ACCEPTS.values(), ids=SUMMARY_ACCEPTS.keys())
def test_summary_accepts(change: Change) -> None:
    document = changed(summary, change)
    if document.get("cases", True) is None:
        document.pop("cases")

    accepts(JsonSummaryV1_2, document)


def summary_cases(document: Document) -> list[Document]:
    cases: list[Document] = document["cases"]
    return cases


SUMMARY_REJECTS: dict[str, Change] = {
    "version 1.1.0": lambda d: d.update(schema_version="1.1.0"),
    "null cases": lambda d: (locked(d), d.update(cases=None)),
    "cases without an experiment": lambda d: (
        d["ids"].pop("experiment_id"),
        d["ids"].pop("session"),
        d.update(counts=RUN_COUNTS),
    ),
    "a session without an experiment": lambda d: (
        d["ids"].pop("experiment_id"),
        d.pop("cases"),
        d.update(counts=RUN_COUNTS),
    ),
    "cases without the plan hash": lambda d: d["ids"].pop("plan_hash"),
    "the plan hash without cases": lambda d: (without_approval(d), d.pop("cases")),
    "an experiment's counts without an experiment": lambda d: (
        d.update(ids={"plan_hash": PLAN_HASH}),
        d.pop("cases"),
    ),
    "a run's counts for an experiment": lambda d: d.update(counts=RUN_COUNTS),
    "an experiment's case ID in ids": lambda d: d["ids"].update(case_id=BASELINE_ID),
    "an experiment's attempt ID in ids": lambda d: d["ids"].update(attempt_id=ATTEMPT_ID),
    "an experiment run with demo": lambda d: d.update(command="demo"),
    "a session without an output directory": lambda d: d.update(output_dir=None, outputs={}),
    "a case's tables in outputs": lambda d: d["outputs"].update(
        metrics=f"cases/{HOLDINGS_ID}/normalized/metrics.csv"
    ),
    "cases that don't start with the baseline": lambda d: summary_cases(d).reverse(),
    "no cases": lambda d: d.update(cases=[], counts={}),
    "one case": lambda d: d.update(cases=summary_cases(d)[:1], counts={}),
    "a repeated case key": lambda d: summary_cases(d)[2].update(case_key="holdings-50"),
    "a repeated case ID": lambda d: summary_cases(d)[2].update(case_id=HOLDINGS_ID),
    "case counts that aren't the cases'": lambda d: d["counts"].update(
        cases_failed=2, cases_unknown=0
    ),
    "case counts that don't add up": lambda d: (
        before_the_plan(d),
        d["counts"].update(cases_planned=4),
    ),
    "a skipped case with every case listed": lambda d: d["counts"].update(
        cases_skipped=1, cases_planned=4
    ),
    "a repeat attempt for a succeeded case": lambda d: summary_cases(d)[1].update(
        repeat_attempt_id=ATTEMPT_ID
    ),
    # A run ends completed or partial only once it has run its plan, and it's completed exactly
    # when every case succeeded, as its session's manifest's outcome is.
    "completed with cases that didn't succeed": completed_run,
    "completed with a case not yet run": lambda d: (
        completed_run(d),
        every_case_succeeded(d),
        summary_cases(d)[2].update(outcome="not_yet_run"),
        d["counts"].update(cases_succeeded=2, cases_not_yet_run=1),
    ),
    "partial with every case succeeded": every_case_succeeded,
    "completed without cases": lambda d: (
        completed_run(d),
        every_case_succeeded(d),
        d["ids"].pop("plan_hash"),
        d.pop("cases"),
    ),
    "partial without cases": lambda d: (d["ids"].pop("plan_hash"), d.pop("cases")),
    "a skipped case outcome": lambda d: summary_cases(d)[2].update(outcome="skipped"),
    "more repeats than attempts": lambda d: d["counts"].update(repeats=4),
    "a session 0": lambda d: d["ids"].update(session=0),
    "an experiment ID that's a device name": lambda d: d["ids"].update(experiment_id="lpt1"),
}


@pytest.mark.parametrize("change", SUMMARY_REJECTS.values(), ids=SUMMARY_REJECTS.keys())
def test_summary_rejects(change: Change) -> None:
    rejects(JsonSummaryV1_2, changed(summary, change))


def test_a_summary_without_cases_leaves_the_key_out() -> None:
    document = changed(summary, locked)

    written = json.loads(
        JsonSummaryV1_2.model_validate_json(json.dumps(document)).model_dump_json()
    )

    assert "cases" not in written
