"""The records of a ranking definition, and of a ranking snapshot, accept what docs/contracts.md
describes, and reject what it calls invalid.

Traces to release 0.4.0's test pairing, which names this module for the records' contract tests
(R04-T05): plans 1.2.0 and 1.3.0 (plans with a ranking definition), the snapshot plan, start and
attempt records 1.2.0 and 1.3.0 (sending a definition), `experiment.json` 1.1.0, run manifest
1.1.0 and experiment manifest 1.1.0, the snapshot manifest and record (ranking snapshot output),
and the rows of `settings.csv` 1.1.0 and `differences.csv` 1.1.0 (weight rows). To R04-AC08's
row: the snapshot manifest's model rejects `synthetic` true with an approval other than
`not_required` or with a command, and `synthetic` false with `not_required` or without a command;
and to the changes after 0.4.0's sign-off: run manifest 1.1.0's model accepts `synthetic` true
with `command` null and the approval `not_required`, and rejects `synthetic` true with another
approval or with the command `run`, and `synthetic` false with `not_required`, without a command,
or with the command `demo`. And to the 0.3.0 contracts, which a definition doesn't reach: plan
1.0.0, `settings.csv` 1.0.0, and `differences.csv` 1.0.0 refuse a weight row and a definition.

The models give each record's shapes, and the rules one record can show. The plan's consistency
rules across its cases, such as a `rank_update` whose definition isn't its case's, are release
0.4.0's R04-T07's, which adds their rejected plans here. Each document below is synthetic, and
read as a reader reads it: from JSON text, with `model_validate_json`.
"""

import json
from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from trialfolio.contracts.attempt import (
    AttemptRecordV1_2,
    AttemptRecordV1_3,
    StartRecordV1_2,
    StartRecordV1_3,
)
from trialfolio.contracts.experiment_manifest import ExperimentManifestV1_1
from trialfolio.contracts.experiment_plan import ExperimentPlanCaseV1_3, PlanV1_3
from trialfolio.contracts.experiment_record import ExperimentRecordV1_1
from trialfolio.contracts.manifest import RunManifestV1_1
from trialfolio.contracts.plan import Plan, PlanV1_2
from trialfolio.contracts.ranking_snapshot import (
    RankingSnapshotManifest,
    RankingSnapshotPlan,
    RankingSnapshotRecord,
)
from trialfolio.contracts.screen_settings import SCREEN_SETTINGS
from trialfolio.contracts.tables import (
    DifferencesRow,
    DifferencesRowV1_1,
    SettingsRow,
    SettingsRowV1_1,
)

type Document = dict[str, Any]
type Change = Callable[[Document], object]


def digest(seed: str) -> str:
    return "sha256:" + seed * 32


PLAN_HASH = digest("a1")
EARLIER_PLAN = digest("a0")
DEFINITION_ID = digest("b1")
HEAVY_ID = digest("b2")
BASELINE_ID = "case-0000000000000001"
HEAVY_CASE = "case-0000000000000002"
HOLDINGS_ID = "case-0000000000000003"
DEFAULT_ID = "case-0000000000000004"
ATTEMPT_ID = "1b4e28ba-2fa1-4d2b-883f-0016d3cca427"
EARLIER_ATTEMPT = "2c5f39cb-3ab2-4e3c-994a-1127e4ddb538"
TRANSPORT = {"requests": "2.34.2", "urllib3": "2.8.0"}
WRAPPER = {"p123api": "3.1.0"}

DEFINITION = (
    '<RankingSystem RankType="Higher">\n'
    '\t<StockFormula Name="Earnings Yield" Weight="60.0" RankType="Higher">\n'
    "\t\t<Formula>EarnYield</Formula>\n"
    "\t</StockFormula>\n"
    '\t<StockFormula Name="Sales Yield" Weight="40" RankType="Higher">\n'
    "\t\t<Formula>SalesYield</Formula>\n"
    "\t</StockFormula>\n"
    "</RankingSystem>\n"
)
"""A synthetic definition of two top-level factors, at 60 and 40. The models don't read it."""

HEAVY = DEFINITION.replace('Weight="60.0"', 'Weight="70"').replace('Weight="40"', 'Weight="30"')

# Plan 1.2.0

SETTING_VALUES: dict[str, object] = {
    "universe": "SP500",
    "screen_type": "stock",
    "rules": ["AvgDailyTot(30) > 1000000"],
    "ranking": {"definition": DEFINITION_ID, "ranking_method": "percentile_nas_negative"},
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
WEIGHTS = (("Earnings Yield", "60"), ("Sales Yield", "40"))


def weight_row(node: str, weight: str) -> Document:
    return {
        "setting": "ranking_weight",
        "node": node,
        "category": "strategy",
        "critical": True,
        "value": weight,
        "unit": None,
        "interpretation": "interpreted",
        "expected_provenance": "verified",
        "inference_rule": None,
        "flags": [],
    }


def settings_rows(
    values: dict[str, object] | None = None, weights: tuple[tuple[str, str], ...] = WEIGHTS
) -> list[Document]:
    """The screen settings, with a weight row for each of `weights` right after `ranking`."""
    values = SETTING_VALUES | (values or {})
    rows: list[Document] = []
    for setting in SCREEN_SETTINGS:
        sent = setting.name in values
        rows.append(
            {
                "setting": setting.name,
                "node": None,
                "category": setting.category,
                "critical": setting.category != "other",
                "value": deepcopy(values.get(setting.name, "not_sent")),
                "unit": setting.unit,
                "interpretation": "interpreted" if sent else "not_interpreted",
                "expected_provenance": setting.provenance,
                "inference_rule": "A documented rule, checked 2026-10-01"
                if setting.provenance == "inferred"
                else None,
                "flags": FLAGS.get(setting.name, []),
            }
        )
        if setting.name == "ranking":
            rows.extend(weight_row(node, weight) for node, weight in weights)
    return rows


def rank_update(nodes: str = DEFINITION, method: int = 2) -> Document:
    return {
        "operation": "rank_update",
        "params": {"type": "stock", "nodes": nodes, "rankingMethod": method, "currency": "USD"},
    }


def backtest(**screen: object) -> Document:
    return {
        "operation": "screen_backtest",
        "params": {
            "screen": {
                "type": "stock",
                "universe": "SP500",
                "maxNumHoldings": 25,
                "method": "long",
                "currency": "USD",
                "benchmark": "SPY",
                "ranking": "ApiRankingSystem",
                "rules": [{"formula": "AvgDailyTot(30) > 1000000"}],
            }
            | screen,
            "startDt": "2016-01-01",
            "endDt": "2025-12-31",
            "pitMethod": "Complete",
            "precision": 4,
            "transPrice": 1,
            "slippage": 0.25,
            "rebalFreq": "Every 4 Weeks",
        },
    }


RANK_SOURCE = {
    "title": "API functions: Rank",
    "url": "https://portfolio123.customerly.help/en/articles/43323-api-rank",
    "checked": "2026-10-12",
}
SCREEN_SOURCE = {
    "title": "API: Screen",
    "url": "https://portfolio123.customerly.help/en/articles/43324-api-screen",
    "checked": "2026-10-01",
}
COSTS = [
    {"operation": "rank_update", "credits_per_request": 1, "source": RANK_SOURCE},
    {"operation": "screen_backtest", "credits_per_request": 5, "source": SCREEN_SOURCE},
]
RETRY_POLICY = {"automatic_retries": 0, "wrapper_attempts_per_call": 1, "exchanges_per_call": 1}


def data_sent(strategy: list[str] | None = None) -> list[Document]:
    entry = {"recipient": "Portfolio123", "via": "p123api"}
    return [
        {"category": "credentials", **entry, "settings": []},
        {
            "category": "strategy_definition",
            **entry,
            "settings": strategy or ["universe", "rules", "ranking", "ranking_weight"],
        },
        {
            "category": "backtest_settings",
            **entry,
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
    ]


def file_source() -> Document:
    return {
        "form": "definition",
        "definition": DEFINITION_ID,
        "system": None,
        "snapshot_record": None,
        "snapshot_definition": None,
    }


def plan_1_2() -> Document:
    """A screen whose ranking is a definition file: one case, its two requests."""
    return {
        "schema_version": "1.2.0",
        "trialfolio_version": "0.4.0",
        "canonicalization_version": 1,
        "provider_wrapper": WRAPPER,
        "transport": TRANSPORT,
        "title": "Value and momentum",
        "purpose": None,
        "ranking_source": file_source(),
        "cases": [
            {
                "case_id": BASELINE_ID,
                "requests": [rank_update(), backtest()],
                "settings": settings_rows(),
            }
        ],
        "budget": {"provider_requests": 2, "costs": COSTS, "credits": 6, "authentication_calls": 1},
        "retry_policy": RETRY_POLICY,
        "data_sent": data_sent(),
        "plan_hash": PLAN_HASH,
    }


# Plan 1.3.0


def variant(setting: str, value: object = None, **change: object) -> Document:
    return {
        "setting": setting,
        "value": value,
        "add": None,
        "replace": None,
        "with": None,
        "set": None,
        "remove": None,
        "default": False,
    } | change


HEAVY_SET = [{"node": "Earnings Yield", "weight": "70"}, {"node": "Sales Yield", "weight": "30"}]


def experiment_case(
    key: str,
    case_id: str,
    variant_: Document | None,
    settings: list[Document],
    requests: list[Document],
) -> Document:
    return {
        "case_key": key,
        "case_id": case_id,
        "description": None,
        "variant": variant_,
        "requests": requests,
        "settings": settings,
    }


def baseline_case() -> Document:
    return experiment_case(
        "baseline", BASELINE_ID, None, settings_rows(), [rank_update(), backtest()]
    )


def heavy_case() -> Document:
    """A ranking variant: the top-level weights moved to 70 and 30."""
    return experiment_case(
        "earnings-heavy",
        HEAVY_CASE,
        variant("ranking", set=HEAVY_SET),
        settings_rows(
            {"ranking": {"definition": HEAVY_ID, "ranking_method": "percentile_nas_negative"}},
            (("Earnings Yield", "70"), ("Sales Yield", "30")),
        ),
        [rank_update(HEAVY), backtest()],
    )


def holdings_case() -> Document:
    """A variant of another setting: it sends the baseline's definition."""
    return experiment_case(
        "holdings-50",
        HOLDINGS_ID,
        variant("max_holdings", 50),
        settings_rows({"max_holdings": 50}),
        [rank_update(), backtest(maxNumHoldings=50)],
    )


def default_case() -> Document:
    case = experiment_case(
        "rebalance-weeks-1",
        DEFAULT_ID,
        variant("rebalance_weeks", 1, default=True),
        settings_rows({"rebalance_weeks": 1}),
        [rank_update(), backtest()],
    )
    case["requests"][1]["params"]["rebalFreq"] = "Every Week"
    return case


def plan_1_3() -> Document:
    """Four cases: the baseline, a ranking variant, a holdings variant, and the default."""
    return {
        "schema_version": "1.3.0",
        "trialfolio_version": "0.4.0",
        "canonicalization_version": 1,
        "provider_wrapper": WRAPPER,
        "transport": TRANSPORT,
        "experiment_id": "value-momentum-weights",
        "title": "Value and momentum weights",
        "purpose": "Does the screen's result depend on how its ranking weighs earnings yield?",
        "prior_research": {"status": "unknown", "description": None},
        "ranking_source": file_source(),
        "revises": None,
        "cases": [baseline_case(), heavy_case(), holdings_case(), default_case()],
        "budget": {
            "provider_requests": 8,
            "costs": COSTS,
            "credits": 24,
            "authentication_calls": 8,
        },
        "retry_policy": RETRY_POLICY,
        "data_sent": data_sent(),
        "plan_hash": PLAN_HASH,
    }


# The snapshot plan


def snapshot_plan() -> Document:
    entry = {"recipient": "Portfolio123", "via": "p123api"}
    return {
        "schema_version": "1.0.0",
        "trialfolio_version": "0.4.0",
        "canonicalization_version": 1,
        "provider_wrapper": WRAPPER,
        "transport": TRANSPORT,
        "system": "Value and momentum",
        "requests": [{"operation": "rank_get", "params": {"name": "Value and momentum"}}],
        "budget": {
            "provider_requests": 1,
            "credits_per_request": 1,
            "credits_per_request_source": RANK_SOURCE,
            "credits": 1,
            "authentication_calls": 1,
        },
        "retry_policy": RETRY_POLICY,
        "data_sent": [
            {"category": "credentials", **entry, "settings": []},
            {"category": "strategy_definition", **entry, "settings": ["system"]},
        ],
        "plan_hash": PLAN_HASH,
    }


# Start and attempt records 1.2.0 and 1.3.0


def exchange(request: str, status: int | None = 200, **changes: object) -> Document:
    result = "response" if status is not None else "interrupted"
    return {"request": request, "result": result, "status": status, "note": None} | changes


AUTH = exchange("POST /auth")
RANK = exchange("POST /rank")
SEND = exchange("POST /screen/backtest")
GET_RANK = exchange("GET /rank")
DIRECTORY = f"cases/{BASELINE_ID}/attempts/{ATTEMPT_ID}"
SNAPSHOT_DIRECTORY = f"attempts/{ATTEMPT_ID}"


def update_record() -> Document:
    """`updating.json` 1.2.0: the start record of a screen run's `rank_update`."""
    return {
        "schema_version": "1.2.0",
        "trialfolio_version": "0.4.0",
        "attempt_id": ATTEMPT_ID,
        "case_id": BASELINE_ID,
        "plan_hash": PLAN_HASH,
        "operation": "rank_update",
        "started_at": "2026-10-14T12:01:00Z",
        "provider_wrapper": WRAPPER,
        "transport": TRANSPORT,
        "exchanges": [AUTH],
    }


def start_record_1_2() -> Document:
    """`started.json` 1.2.0: the start record of the backtest, after the `rank_update`'s 200."""
    return update_record() | {"operation": "screen_backtest", "exchanges": [AUTH, RANK]}


def snapshot_start_record() -> Document:
    return update_record() | {"case_id": None, "operation": "rank_get"}


def reference(name: str, directory: str = DIRECTORY) -> Document:
    return {"path": f"{directory}/{name}", "artifact_id": digest("d1")}


def ranking_update(response: str | None = "decoded") -> Document:
    saved = None
    if response is not None:
        name = "rank-update-response." + ("json" if response == "decoded" else "raw")
        saved = reference(name) | {"form": response}
    return {
        "request": reference("rank-update-request.json"),
        "response": saved,
        "provider_metadata": {"cost": 1, "quota_remaining": 1000},
    }


def attempt_record_1_2() -> Document:
    """A screen run's attempt that sent its definition, then its backtest, and succeeded."""
    return {
        "schema_version": "1.2.0",
        "trialfolio_version": "0.4.0",
        "attempt_id": ATTEMPT_ID,
        "case_id": BASELINE_ID,
        "plan_hash": PLAN_HASH,
        "operation": "screen_backtest",
        "started_at": "2026-10-14T12:01:00Z",
        "provider_wrapper": WRAPPER,
        "transport": TRANSPORT,
        "ended_at": "2026-10-14T12:01:30Z",
        "outcome": "succeeded",
        "error": None,
        "exchanges": [AUTH, RANK, SEND],
        "possibly_charged": True,
        "ranking_update": ranking_update(),
        "request": reference("request.json"),
        "response": reference("response.json") | {"form": "decoded"},
        "provider_metadata": {"cost": 5, "quota_remaining": 995},
    }


def snapshot_attempt_record() -> Document:
    """A snapshot's attempt: its authentication, and one `rank_get`, with no case."""
    return attempt_record_1_2() | {
        "case_id": None,
        "operation": "rank_get",
        "exchanges": [AUTH, GET_RANK],
        "ranking_update": None,
        "request": reference("request.json", SNAPSHOT_DIRECTORY),
        "response": reference("response.json", SNAPSHOT_DIRECTORY) | {"form": "decoded"},
        "provider_metadata": {"cost": 1, "quota_remaining": 999},
    }


ERROR = {"code": "provider.unsupported_capability", "message": "Portfolio123 refused it."}
UNKNOWN = {"code": "provider.outcome_unknown", "message": "The outcome is unknown."}


def failed(record: Document, *exchanges: Document, error: Document = ERROR) -> None:
    """An attempt that ended without its backtest's response."""
    record.update(
        outcome="failed",
        error=error,
        exchanges=list(exchanges),
        request=None,
        response=None,
        provider_metadata={"cost": None, "quota_remaining": None},
    )


def unknown(record: Document, *exchanges: Document) -> None:
    failed(record, *exchanges, error=UNKNOWN)
    record["outcome"] = "unknown"


def experiment_update_record() -> Document:
    """`updating.json` 1.3.0, of an attempt sent with its session's token."""
    return {
        "schema_version": "1.3.0",
        "trialfolio_version": "0.4.0",
        "attempt_id": ATTEMPT_ID,
        "case_id": BASELINE_ID,
        "plan_hash": PLAN_HASH,
        "session": 1,
        "sequence": 2,
        "operation": "rank_update",
        "authenticated_by": EARLIER_ATTEMPT,
        "repeat_of": None,
        "started_at": "2026-10-14T12:01:00Z",
        "provider_wrapper": WRAPPER,
        "transport": TRANSPORT,
        "exchanges": [],
    }


def experiment_start_record() -> Document:
    return experiment_update_record() | {"operation": "screen_backtest", "exchanges": [RANK]}


def experiment_attempt_record() -> Document:
    """An experiment's attempt, sent with an earlier attempt's token, that succeeded."""
    record = experiment_update_record() | attempt_record_1_2()
    record.update(
        schema_version="1.3.0",
        session=1,
        sequence=2,
        authenticated_by=EARLIER_ATTEMPT,
        repeat_of=None,
        exchanges=[RANK, SEND],
    )
    order = list(experiment_update_record())[:7] + [
        "operation",
        "authenticated_by",
        "repeat_of",
        "started_at",
        "provider_wrapper",
        "transport",
        "ended_at",
        "outcome",
        "error",
        "exchanges",
        "possibly_charged",
        "ranking_update",
        "request",
        "response",
        "provider_metadata",
    ]
    return {name: record[name] for name in dict.fromkeys(order)}


# experiment.json 1.1.0


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
    document = plan_1_3()
    return {
        "schema_version": "1.1.0",
        "trialfolio_version": "0.4.0",
        "created_at": "2026-10-14T12:00:00Z",
        "experiment_id": document["experiment_id"],
        "title": document["title"],
        "purpose": document["purpose"],
        "prior_research": document["prior_research"],
        "planned_cases": [recorded(case) for case in document["cases"]],
        "retired_cases": [],
        "plans": [plan_entry(1, EARLIER_PLAN, None)],
    }


def source_revision() -> Document:
    """A revision whose only change is the definition's source: a snapshot of the definition the
    file held, which keeps every case."""
    document = experiment_record()
    revision = plan_entry(2, PLAN_HASH, EARLIER_PLAN) | {
        "reason": "The same definition, read from the account by a snapshot.",
        "changes": {
            "versions": [],
            "cases_added": [],
            "cases_retired": [],
            "parts": ["ranking_source"],
        },
    }
    document["plans"].append(revision)
    return document


# Run manifest 1.1.0


def source(
    form: str,
    provenance: str = "verified",
    operation: str | None = "rank_update",
    parser: int | None = None,
    version: str = "1",
) -> Document:
    return {
        "acquired_at": "2026-10-14T12:00:00Z",
        "format": form,
        "format_version": version,
        "parser_version": parser,
        "provenance": provenance,
        "operation": operation,
    }


SOURCES: dict[str, Document] = {
    "configuration": source("screen-configuration", "user_supplied", None, version="1.1.0"),
    "ranking_definition": source("ranking-definition", "user_supplied", None),
    "rank_update_request": source("p123api-rank-update-request"),
    "rank_update_response": source("p123api-rank-update"),
    "rank_update_response_undecoded": source("p123api-rank-update-response_undecoded"),
    "provider_request": source("p123api-screen-backtest-request", operation=None),
    "provider_response": source("p123api-screen-backtest", operation="screen_backtest", parser=1),
}


def listed(
    path: str, role: str, schema_version: str | None = None, sources: dict[str, Document] = SOURCES
) -> Document:
    return {
        "path": path,
        "artifact_id": digest("e1"),
        "size": 100,
        "role": role,
        "schema_version": schema_version,
        "source": sources.get(role),
    }


def run_manifest() -> Document:
    return {
        "schema_version": "1.1.0",
        "artifact_type": "run",
        "trialfolio_version": "0.4.0",
        "created_at": "2026-10-14T12:02:00Z",
        "command": {
            "name": "run",
            "options": {"approve": PLAN_HASH, "json": False},
            "started_at": "2026-10-14T12:00:00Z",
        },
        "synthetic": False,
        "plan_hash": PLAN_HASH,
        "approval": "option",
        "outcome": "completed",
        "error": None,
        "artifacts": [
            listed("plan.json", "plan", "1.2.0"),
            listed("configuration.yaml", "configuration"),
            listed("definition.xml", "ranking_definition"),
            listed(f"{DIRECTORY}/rank-update-request.json", "rank_update_request"),
            listed(f"{DIRECTORY}/updating.json", "update_record", "1.2.0"),
            listed(f"{DIRECTORY}/rank-update-response.json", "rank_update_response"),
            listed(f"{DIRECTORY}/request.json", "provider_request"),
            listed(f"{DIRECTORY}/started.json", "start_record", "1.2.0"),
            listed(f"{DIRECTORY}/response.json", "provider_response"),
            listed(f"{DIRECTORY}/attempt.json", "attempt_record", "1.2.0"),
            listed("normalized/metrics.csv", "metrics", "1.0.0"),
            listed("normalized/settings.csv", "settings", "1.1.0"),
            listed("report.html", "report"),
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
            "results": 1,
            "cases": 1,
            "attempts": {"succeeded": 1, "failed": 0, "unknown": 0, "running": 0},
            "provider_requests": 2,
            "retries": 0,
            "cost": 6,
        },
    }


def artifact(document: Document, role: str) -> Document:
    (found,) = (entry for entry in document["artifacts"] if entry["role"] == role)
    return found


def core_synthetic(document: Document) -> None:
    """The synthetic run the core writes with the demo's client, which no command writes."""
    document.update(synthetic=True, approval="not_required", command=None)


# Experiment manifest 1.1.0

EXPERIMENT_SOURCES = SOURCES | {
    "configuration": source("experiment-configuration", "user_supplied", None, version="1.1.0")
}
EXPERIMENT_ATTEMPT = f"cases/{BASELINE_ID}/attempts/{ATTEMPT_ID}"


def experiment_manifest() -> Document:
    """Session 1's manifest: one case of four succeeded."""
    tables = f"cases/{BASELINE_ID}/normalized"

    def entry(path: str, role: str, version: str | None = None) -> Document:
        return listed(path, role, version, EXPERIMENT_SOURCES)

    return {
        "schema_version": "1.1.0",
        "artifact_type": "experiment",
        "trialfolio_version": "0.4.0",
        "created_at": "2026-10-14T12:05:00Z",
        "experiment_id": "value-momentum-weights",
        "session": 1,
        "command": {
            "name": "run",
            "options": {
                "approve": PLAN_HASH,
                "json": False,
                "revision_reason": False,
                "repeat": False,
            },
            "started_at": "2026-10-14T11:59:00Z",
        },
        "synthetic": False,
        "plan": 1,
        "plan_hash": PLAN_HASH,
        "approval": "option",
        "outcome": "partial",
        "error": {"code": "execution.partial", "message": "Some planned cases didn't succeed."},
        "artifacts": [
            entry("plans/1/configuration.yaml", "configuration"),
            entry("plans/1/definition.xml", "ranking_definition"),
            entry("plans/1/plan.json", "plan", "1.3.0"),
            entry("plans/1/experiment.json", "experiment_record", "1.1.0"),
            entry(f"{EXPERIMENT_ATTEMPT}/authenticating.json", "authentication_record", "1.0.0"),
            entry(f"{EXPERIMENT_ATTEMPT}/rank-update-request.json", "rank_update_request"),
            entry(f"{EXPERIMENT_ATTEMPT}/updating.json", "update_record", "1.3.0"),
            entry(f"{EXPERIMENT_ATTEMPT}/rank-update-response.json", "rank_update_response"),
            entry(f"{EXPERIMENT_ATTEMPT}/request.json", "provider_request"),
            entry(f"{EXPERIMENT_ATTEMPT}/started.json", "start_record", "1.3.0"),
            entry(f"{EXPERIMENT_ATTEMPT}/response.json", "provider_response"),
            entry(f"{EXPERIMENT_ATTEMPT}/attempt.json", "attempt_record", "1.3.0"),
            entry(f"{tables}/metrics.csv", "metrics", "1.0.0"),
            entry(f"{tables}/settings.csv", "settings", "1.1.0"),
            entry("sessions/1/session.json", "session_record", "1.0.0"),
            entry("sessions/1/report.html", "report"),
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
                "planned": 4,
                "succeeded": 1,
                "failed": 0,
                "skipped": 0,
                "unknown": 0,
                "not_yet_run": 3,
            },
            "retired_cases": 0,
            "attempts": {"succeeded": 1, "failed": 0, "unknown": 0, "running": 0, "repeats": 0},
            "retries": 0,
            "provider_requests": 2,
            "authentication_calls": 1,
            "budget": {"provider_requests": 8, "authentication_calls": 8},
            "cost": 6,
        },
    }


# The snapshot manifest and record

SNAPSHOT_SOURCES: dict[str, Document] = {
    "configuration": source(
        "ranking-snapshot-configuration", "user_supplied", None, version="1.0.0"
    ),
    "provider_request": source("p123api-rank-get-request", operation="rank_get"),
    "provider_response": source("p123api-rank-get", operation="rank_get", parser=1),
    "provider_response_undecoded": source(
        "p123api-rank-get-response_undecoded", operation="rank_get"
    ),
    "ranking_definition": source("ranking-definition", operation="rank_get"),
}


def snapshot_manifest() -> Document:
    def entry(path: str, role: str, version: str | None = None) -> Document:
        return listed(path, role, version, SNAPSHOT_SOURCES)

    return {
        "schema_version": "1.0.0",
        "artifact_type": "ranking-snapshot",
        "trialfolio_version": "0.4.0",
        "created_at": "2026-10-14T12:02:00Z",
        "command": {
            "name": "run",
            "options": {"approve": PLAN_HASH, "json": False},
            "started_at": "2026-10-14T12:00:00Z",
        },
        "synthetic": False,
        "plan_hash": PLAN_HASH,
        "approval": "option",
        "outcome": "completed",
        "error": None,
        "artifacts": [
            entry("plan.json", "plan", "1.0.0"),
            entry("configuration.yaml", "configuration"),
            entry(f"{SNAPSHOT_DIRECTORY}/request.json", "provider_request"),
            entry(f"{SNAPSHOT_DIRECTORY}/started.json", "start_record", "1.2.0"),
            entry(f"{SNAPSHOT_DIRECTORY}/response.json", "provider_response"),
            entry(f"{SNAPSHOT_DIRECTORY}/attempt.json", "attempt_record", "1.2.0"),
            entry("definition.xml", "ranking_definition"),
            entry("snapshot.json", "ranking_snapshot_record", "1.0.0"),
        ],
        "parsers": [{"layout": "p123api-rank-get", "layout_version": 1, "parser_version": 1}],
        "license_id": "LicenseRef-NSPRL-1.1",
        "notice_version": "1.0",
        "counts": {
            "attempts": {"succeeded": 1, "failed": 0, "unknown": 0, "running": 0},
            "provider_requests": 1,
            "retries": 0,
            "cost": 1,
        },
    }


def snapshot_failed(document: Document) -> None:
    """A snapshot whose `rank_get` got a 404: no definition, no record."""
    document.update(
        outcome="failed",
        error={"code": "provider.unsupported_capability", "message": "Portfolio123 refused it."},
    )
    document["artifacts"] = [
        entry
        for entry in document["artifacts"]
        if entry["role"]
        not in ("ranking_definition", "ranking_snapshot_record", "provider_response")
    ]
    document["counts"].update(
        attempts={"succeeded": 0, "failed": 1, "unknown": 0, "running": 0}, cost=None
    )


def snapshot_record() -> Document:
    return {
        "schema_version": "1.0.0",
        "trialfolio_version": "0.4.0",
        "requested": "Value and momentum",
        "system": {
            "name": "Value and momentum",
            "id": 424242,
            "ranking_method": 2,
            "currency": "USD",
            "type": "Stock",
        },
        "taken_at": "2026-10-14T12:01:30Z",
        "attempt_id": ATTEMPT_ID,
        "plan_hash": PLAN_HASH,
        "definition": digest("f1"),
        "response": digest("f2"),
    }


# The rows of settings.csv 1.1.0 and differences.csv 1.1.0


def settings_row() -> Document:
    """A screen run's weight row, whose value its definition gives."""
    return {
        "label": BASELINE_ID,
        "setting": "ranking_weight",
        "category": "strategy",
        "critical": True,
        "value": "60",
        "unit": None,
        "interpretation": "interpreted",
        "provenance": "verified",
        "inference_rule": None,
        "original_key": "ranking.definition",
        "original_value": "60.0",
        "source_artifact": digest("c1"),
        "flags": [],
        "node": "Earnings Yield",
    }


DEFINITION_TEXT = json.dumps(SETTING_VALUES["ranking"])


def ranking_settings_row(document: Document) -> None:
    document.update(
        setting="ranking",
        value=DEFINITION_TEXT,
        original_key="ranking",
        original_value="definition: 'ranking/value-momentum.xml'",
        node=None,
    )


def differences_row() -> Document:
    """A weight that differs, which the review declares with `ranking`."""
    return {
        "label": "heavy",
        "baseline_label": "baseline",
        "kind": "setting",
        "name": "ranking_weight",
        "subject": None,
        "category": "strategy",
        "critical": True,
        "baseline_value": "60",
        "value": "70",
        "unit": None,
        "classification": "intended_change",
        "difference": None,
        "difference_unit": None,
        "difference_decimals": None,
        "reason": None,
        "declared_reason": "More weight on earnings yield.",
        "flagged": False,
        "flags": [],
        "node": "Earnings Yield",
    }


def undeclared(document: Document) -> None:
    document.update(
        classification="unexplained_mismatch",
        declared_reason=None,
        flagged=True,
        flags=["critical_unexplained_mismatch"],
    )


VALID: list[tuple[type[BaseModel], Callable[[], Document]]] = [
    (PlanV1_2, plan_1_2),
    (PlanV1_3, plan_1_3),
    (RankingSnapshotPlan, snapshot_plan),
    (StartRecordV1_2, update_record),
    (StartRecordV1_2, start_record_1_2),
    (StartRecordV1_2, snapshot_start_record),
    (AttemptRecordV1_2, attempt_record_1_2),
    (AttemptRecordV1_2, snapshot_attempt_record),
    (StartRecordV1_3, experiment_update_record),
    (StartRecordV1_3, experiment_start_record),
    (AttemptRecordV1_3, experiment_attempt_record),
    (ExperimentRecordV1_1, experiment_record),
    (ExperimentRecordV1_1, source_revision),
    (RunManifestV1_1, run_manifest),
    (ExperimentManifestV1_1, experiment_manifest),
    (RankingSnapshotManifest, snapshot_manifest),
    (RankingSnapshotRecord, snapshot_record),
    (SettingsRowV1_1, settings_row),
    (DifferencesRowV1_1, differences_row),
]
IDS = [
    "plan-1.2.0",
    "plan-1.3.0",
    "snapshot-plan",
    "update-record-1.2.0",
    "start-record-1.2.0",
    "snapshot-start-record",
    "attempt-record-1.2.0",
    "snapshot-attempt-record",
    "update-record-1.3.0",
    "start-record-1.3.0",
    "attempt-record-1.3.0",
    "experiment-record-1.1.0",
    "source-revision",
    "run-manifest-1.1.0",
    "experiment-manifest-1.1.0",
    "snapshot-manifest",
    "snapshot-record",
    "settings-row-1.1.0",
    "differences-row-1.1.0",
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


# Plan 1.2.0


def case_of(document: Document, index: int = 0) -> Document:
    case: Document = document["cases"][index]
    return case


def setting_of(document: Document, name: str, case: int = 0) -> Document:
    (row,) = (row for row in case_of(document, case)["settings"] if row["setting"] == name)
    return row


def weight_of(document: Document, index: int, case: int = 0) -> Document:
    rows = [
        row for row in case_of(document, case)["settings"] if row["setting"] == "ranking_weight"
    ]
    return rows[index]


def rank_params(document: Document, case: int = 0) -> Document:
    params: Document = case_of(document, case)["requests"][0]["params"]
    return params


def move_weights(document: Document, after: str) -> None:
    rows: list[Document] = case_of(document)["settings"]
    weights = [row for row in rows if row["setting"] == "ranking_weight"]
    others = [row for row in rows if row["setting"] != "ranking_weight"]
    index = next(i for i, row in enumerate(others) if row["setting"] == after)
    case_of(document)["settings"] = [*others[: index + 1], *weights, *others[index + 1 :]]


def snapshot_source(document: Document) -> None:
    document["ranking_source"] = {
        "form": "snapshot",
        "definition": DEFINITION_ID,
        "system": "Value and momentum",
        "snapshot_record": digest("f3"),
        "snapshot_definition": digest("f1"),
    }


PLAN_1_2_ACCEPTS: dict[str, Change] = {
    "a snapshot's source": snapshot_source,
    "ranking method 4": lambda d: (
        rank_params(d).update(rankingMethod=4),
        setting_of(d, "ranking")["value"].update(ranking_method="percentile_nas_neutral"),
    ),
    "a purpose": lambda d: d.update(purpose="A reference run of the ranking."),
    "a weight of one node": lambda d: case_of(d).update(
        settings=settings_rows(weights=(("Earnings Yield", "100"),))
    ),
    "nodes by position, and with a decimal weight": lambda d: case_of(d).update(
        settings=settings_rows(weights=(("#1", "12.5"), ("#2", "87.5")))
    ),
    "another documented cost": lambda d: d["budget"]["costs"][0].update(credits_per_request=2),
}


@pytest.mark.parametrize("change", PLAN_1_2_ACCEPTS.values(), ids=PLAN_1_2_ACCEPTS.keys())
def test_plan_1_2_accepts(change: Change) -> None:
    accepts(PlanV1_2, changed(plan_1_2, change))


PLAN_1_2_REJECTS: dict[str, Change] = {
    "version 1.0.0": lambda d: d.update(schema_version="1.0.0"),
    "no ranking_source": lambda d: d.pop("ranking_source"),
    "a ranking_source of another form": lambda d: d["ranking_source"].update(form="file"),
    "a ranking_source without the definition's hash": lambda d: d["ranking_source"].update(
        definition=None
    ),
    "a ranking_source that leaves a field out": lambda d: d["ranking_source"].pop("system"),
    "two cases": lambda d: d.update(cases=[case_of(d), case_of(d)]),
    "one request": lambda d: case_of(d).update(requests=[backtest()]),
    "the backtest first": lambda d: case_of(d).update(requests=[backtest(), rank_update()]),
    "a third request": lambda d: case_of(d)["requests"].append(backtest()),
    "a rank_update with an id": lambda d: rank_params(d).update(id=42),
    "a rank_update with ranking method 1": lambda d: rank_params(d).update(rankingMethod=1),
    "a rank_update with ranking method true": lambda d: rank_params(d).update(rankingMethod=True),
    "a rank_update in another currency": lambda d: rank_params(d).update(currency="EUR"),
    "a rank_update of another type": lambda d: rank_params(d).update(type="etf"),
    "a rank_update with no definition": lambda d: rank_params(d).update(nodes=""),
    "no weight rows": lambda d: case_of(d).update(settings=settings_rows(weights=())),
    "the weight rows before ranking": lambda d: move_weights(d, "rules"),
    "the weight rows after max_holdings": lambda d: move_weights(d, "max_holdings"),
    "a weight row without its node": lambda d: weight_of(d, 0).update(node=None),
    "a node on another row": lambda d: setting_of(d, "universe").update(node="Earnings Yield"),
    "a weight of 0": lambda d: weight_of(d, 0).update(value="0"),
    "a weight not normalized": lambda d: weight_of(d, 0).update(value="60.0"),
    "a weight as a number": lambda d: weight_of(d, 0).update(value=60),
    "a weight row with a unit": lambda d: weight_of(d, 0).update(unit="count"),
    "a weight row that's inferred": lambda d: weight_of(d, 0).update(
        expected_provenance="inferred", inference_rule="A rule"
    ),
    "a weight row with a flag": lambda d: weight_of(d, 0).update(flags=["not_snapshotted"]),
    "a ranking by formula": lambda d: setting_of(d, "ranking").update(
        value={"formula": "EarnYield", "lower_is_better": False}
    ),
    "a ranking by name": lambda d: setting_of(d, "ranking").update(
        value={"name": "Value and momentum"}, flags=["not_snapshotted"]
    ),
    "a definition flagged not_snapshotted": lambda d: setting_of(d, "ranking").update(
        flags=["not_snapshotted"]
    ),
    "a definition's ranking method that isn't documented": lambda d: setting_of(d, "ranking")[
        "value"
    ].update(ranking_method="normal_distribution"),
    "a definition by its path": lambda d: setting_of(d, "ranking")["value"].update(
        definition="ranking/value-momentum.xml"
    ),
    "one provider request": lambda d: d["budget"].update(provider_requests=1),
    "two authentication calls": lambda d: d["budget"].update(authentication_calls=2),
    "the costs in another order": lambda d: d["budget"].update(costs=COSTS[::-1]),
    "one cost": lambda d: d["budget"].update(costs=COSTS[:1]),
    "a cost of another operation": lambda d: d["budget"]["costs"][0].update(operation="rank_get"),
    "1.0.0's budget": lambda d: d.update(
        budget={
            "provider_requests": 2,
            "credits_per_request": 5,
            "credits_per_request_source": SCREEN_SOURCE,
            "credits": 10,
            "authentication_calls": 1,
        }
    ),
    "the weights not among the data sent": lambda d: d.update(
        data_sent=data_sent(["universe", "rules", "ranking"])
    ),
}


@pytest.mark.parametrize("change", PLAN_1_2_REJECTS.values(), ids=PLAN_1_2_REJECTS.keys())
def test_plan_1_2_rejects(change: Change) -> None:
    rejects(PlanV1_2, changed(plan_1_2, change))


def test_plan_1_0_0_refuses_a_definition_and_weight_rows() -> None:
    """A screen whose ranking is a definition writes plan 1.2.0, so plan 1.0.0 stays as 0.3.0
    reads it."""
    document = plan_1_2()
    document.update(schema_version="1.0.0")
    document.pop("ranking_source")
    for row in case_of(document)["settings"]:
        row.pop("node")
    document["budget"] = {
        "provider_requests": 1,
        "credits_per_request": 5,
        "credits_per_request_source": SCREEN_SOURCE,
        "credits": 5,
        "authentication_calls": 1,
    }
    document["data_sent"] = data_sent(["universe", "rules", "ranking"])
    case_of(document)["requests"] = [backtest()]

    with pytest.raises(ValidationError) as caught:
        Plan.model_validate_json(json.dumps(document))

    located = {error["loc"][:4] for error in caught.value.errors(include_input=False)}
    assert ("cases", 0, "settings", 3) in located  # the definition, in place of a form's keys
    assert ("cases", 0, "settings", 4) in located  # a weight row


# Plan 1.3.0


def removal_case() -> Document:
    """A removal variant: `Sales Yield` removed, and `Earnings Yield` at 100."""
    case = experiment_case(
        "no-sales-yield",
        "case-0000000000000005",
        variant("ranking", set=[{"node": "Earnings Yield", "weight": "100"}], remove="Sales Yield"),
        settings_rows(
            {"ranking": {"definition": digest("b3"), "ranking_method": "percentile_nas_negative"}},
            (("Earnings Yield", "100"),),
        ),
        [rank_update(DEFINITION.replace('Weight="60.0"', 'Weight="100"')), backtest()],
    )
    return case


def holdings_on_heavy() -> Document:
    """A holdings variant built on the ranking variant's settings, instead of the baseline's."""
    case = holdings_case()
    case["settings"] = settings_rows(
        {
            "max_holdings": 50,
            "ranking": {"definition": HEAVY_ID, "ranking_method": "percentile_nas_negative"},
        },
        (("Earnings Yield", "70"), ("Sales Yield", "30")),
    )
    case["requests"][0] = rank_update(HEAVY)
    return case


def heavy_variant(document: Document) -> Document:
    found: Document = case_of(document, 1)["variant"]
    return found


PLAN_1_3_ACCEPTS: dict[str, Change] = {
    "a removal variant": lambda d: d["cases"].insert(2, removal_case()),
    "a revision": lambda d: d.update(revises=EARLIER_PLAN),
    "no default": lambda d: d["cases"].pop(),
    "a snapshot's source": snapshot_source,
    "a larger budget": lambda d: d["budget"].update(
        provider_requests=10, authentication_calls=10, credits=30
    ),
    "a ranking variant with a description": lambda d: case_of(d, 1).update(
        description="More weight on earnings yield."
    ),
}


@pytest.mark.parametrize("change", PLAN_1_3_ACCEPTS.values(), ids=PLAN_1_3_ACCEPTS.keys())
def test_plan_1_3_accepts(change: Change) -> None:
    accepts(PlanV1_3, changed(plan_1_3, change))


PLAN_1_3_REJECTS: dict[str, Change] = {
    "version 1.1.0": lambda d: d.update(schema_version="1.1.0"),
    "no ranking_source": lambda d: d.pop("ranking_source"),
    "a case with one request": lambda d: case_of(d, 2).update(requests=[backtest()]),
    "a case without weight rows": lambda d: case_of(d, 2).update(
        settings=settings_rows({"max_holdings": 50}, ())
    ),
    "a holdings variant that changes the weights too": lambda d: weight_of(d, 0, 2).update(
        value="70"
    ),
    "a holdings variant that changes the definition too": lambda d: setting_of(d, "ranking", 2)[
        "value"
    ].update(definition=HEAVY_ID),
    "a holdings variant with set": lambda d: case_of(d, 2)["variant"].update(set=HEAVY_SET),
    "a holdings variant with remove": lambda d: case_of(d, 2)["variant"].update(
        remove="Sales Yield"
    ),
    "a ranking variant with a value": lambda d: heavy_variant(d).update(value=70),
    "a ranking variant with an add": lambda d: heavy_variant(d).update(add="MktCap > 300"),
    "a ranking variant without set": lambda d: heavy_variant(d).update(set=None),
    "a ranking variant with an empty set": lambda d: heavy_variant(d).update(set=[]),
    "a ranking variant that names a node twice": lambda d: heavy_variant(d).update(
        set=[{"node": "Earnings Yield", "weight": "70"}, {"node": "Earnings Yield", "weight": "30"}]
    ),
    "a ranking variant that gives the removed factor a weight": lambda d: heavy_variant(d).update(
        remove="Sales Yield"
    ),
    "a ranking variant's weight of 0": lambda d: heavy_variant(d)["set"][0].update(weight="0"),
    "a ranking variant's weight not normalized": lambda d: heavy_variant(d)["set"][0].update(
        weight="70.0"
    ),
    "a ranking variant's weight as a number": lambda d: heavy_variant(d)["set"][0].update(
        weight=70
    ),
    "a ranking variant's empty node": lambda d: heavy_variant(d)["set"][0].update(node=""),
    "the default a ranking variant": lambda d: heavy_variant(d).update(default=True),
    "the ranking variant after the holdings variant": lambda d: d["cases"].insert(
        2, d["cases"].pop(1)
    ),
    "a variant keyed baseline": lambda d: case_of(d, 1).update(case_key="baseline"),
    "a baseline with a description": lambda d: case_of(d, 0).update(description="The baseline."),
    "a variant first, the other built on it": lambda d: d.update(
        cases=[heavy_case(), holdings_on_heavy()]
    ),
    "a holdings variant with a weight row the baseline doesn't have": lambda d: case_of(
        d, 2
    ).update(settings=settings_rows({"max_holdings": 50}, (*WEIGHTS, ("Quality", "10")))),
    "a repeated case key": lambda d: case_of(d, 2).update(case_key="earnings-heavy"),
    "a repeated case ID": lambda d: case_of(d, 2).update(case_id=HEAVY_CASE),
    "two holdings variants of 50": lambda d: d["cases"].insert(
        3, holdings_case() | {"case_key": "holdings-again", "case_id": "case-0000000000000009"}
    ),
    "a budget below the cases": lambda d: d["budget"].update(
        provider_requests=3, authentication_calls=3, credits=9
    ),
    "authentication calls other than the requests": lambda d: d["budget"].update(
        authentication_calls=7
    ),
    "1.1.0's budget": lambda d: d.update(
        budget={
            "provider_requests": 8,
            "credits_per_request": 5,
            "credits_per_request_source": SCREEN_SOURCE,
            "credits": 40,
            "authentication_calls": 8,
        }
    ),
    "the weights not among the data sent": lambda d: d.update(
        data_sent=data_sent(["universe", "rules", "ranking"])
    ),
    "a plan that revises itself": lambda d: d.update(revises=PLAN_HASH),
}


@pytest.mark.parametrize("change", PLAN_1_3_REJECTS.values(), ids=PLAN_1_3_REJECTS.keys())
def test_plan_1_3_rejects(change: Change) -> None:
    rejects(PlanV1_3, changed(plan_1_3, change))


@pytest.mark.parametrize(
    "case",
    [
        baseline_case() | {"variant": variant("ranking", set=HEAVY_SET)},
        heavy_case() | {"variant": None},
    ],
    ids=["a baseline with a variant", "a variant without one"],
)
def test_a_plan_1_3_case_is_the_baseline_exactly_when_it_has_no_variant(case: Document) -> None:
    """A case read alone, as the plan reads each of its cases."""
    accepts(ExperimentPlanCaseV1_3, baseline_case())
    rejects(ExperimentPlanCaseV1_3, case)


# The snapshot plan


def snapshot_entry(document: Document, index: int) -> Document:
    entry: Document = document["data_sent"][index]
    return entry


SNAPSHOT_PLAN_REJECTS: dict[str, Change] = {
    "a rank_get of another name": lambda d: d["requests"][0]["params"].update(name="Other"),
    "two requests": lambda d: d["requests"].append(d["requests"][0]),
    "a rank_update": lambda d: d["requests"][0].update(operation="rank_update"),
    "a rank_get with an id": lambda d: d["requests"][0]["params"].update(id=424242),
    "a blank system": lambda d: (
        d.update(system=" "),
        d["requests"][0]["params"].update(name=" "),
    ),
    "two provider requests": lambda d: d["budget"].update(provider_requests=2, credits=2),
    "a backtest's cost": lambda d: d["budget"].update(
        credits_per_request=5, credits=5, credits_per_request_source=SCREEN_SOURCE
    ),
    "a cost of 2": lambda d: d["budget"].update(credits_per_request=2, credits=2),
    "a source checked on another day": lambda d: d["budget"]["credits_per_request_source"].update(
        checked="2026-10-13"
    ),
    "backtest settings sent": lambda d: snapshot_entry(d, 1).update(category="backtest_settings"),
    "the system's name not sent": lambda d: snapshot_entry(d, 1).update(settings=[]),
    "the data sent in another order": lambda d: d["data_sent"].reverse(),
    "a third category": lambda d: d["data_sent"].append(snapshot_entry(d, 1)),
    "a title": lambda d: d.update(title="A snapshot"),
    "cases": lambda d: d.update(cases=[]),
}


@pytest.mark.parametrize("change", SNAPSHOT_PLAN_REJECTS.values(), ids=SNAPSHOT_PLAN_REJECTS.keys())
def test_snapshot_plan_rejects(change: Change) -> None:
    rejects(RankingSnapshotPlan, changed(snapshot_plan, change))


# Start records 1.2.0 and 1.3.0

START_1_2_REJECTS: dict[str, tuple[Callable[[], Document], Change]] = {
    "an update record that holds the rank_update's exchange": (
        update_record,
        lambda d: d.update(exchanges=[AUTH, RANK]),
    ),
    "an update record without authentication": (update_record, lambda d: d.update(exchanges=[])),
    "an update record whose one exchange isn't authentication's": (
        update_record,
        lambda d: d.update(exchanges=[RANK]),
    ),
    "an update record after failed authentication": (
        update_record,
        lambda d: d.update(exchanges=[exchange("POST /auth", 401)]),
    ),
    "started.json without the rank_update's exchange": (
        start_record_1_2,
        lambda d: d.update(exchanges=[AUTH]),
    ),
    "started.json after a rank_update's 400": (
        start_record_1_2,
        lambda d: d.update(exchanges=[AUTH, exchange("POST /rank", 400)]),
    ),
    "started.json after an interrupted rank_update": (
        start_record_1_2,
        lambda d: d.update(exchanges=[AUTH, exchange("POST /rank", None)]),
    ),
    "started.json with its exchanges in another order": (
        start_record_1_2,
        lambda d: d.update(exchanges=[RANK, AUTH]),
    ),
    "started.json after another request": (
        start_record_1_2,
        lambda d: d.update(exchanges=[AUTH, exchange("POST /rank/create")]),
    ),
    "a start record's exchange with a note": (
        start_record_1_2,
        lambda d: d.update(exchanges=[AUTH, RANK | {"note": "completed_from_saved_response"}]),
    ),
    "a snapshot's start record with a case": (
        snapshot_start_record,
        lambda d: d.update(case_id=BASELINE_ID),
    ),
    "a case's start record without one": (update_record, lambda d: d.update(case_id=None)),
    "another operation": (update_record, lambda d: d.update(operation="rank_create")),
    "a session's fields": (update_record, lambda d: d.update(session=1)),
}


@pytest.mark.parametrize(
    ("build", "change"), START_1_2_REJECTS.values(), ids=START_1_2_REJECTS.keys()
)
def test_start_record_1_2_rejects(build: Callable[[], Document], change: Change) -> None:
    rejects(StartRecordV1_2, changed(build, change))


def own_authentication(document: Document) -> None:
    document.update(authenticated_by=ATTEMPT_ID, exchanges=[AUTH, *document["exchanges"]])


START_1_3_ACCEPTS: dict[str, tuple[Callable[[], Document], Change]] = {
    "an update record that authenticated": (experiment_update_record, own_authentication),
    "started.json of an attempt that authenticated": (experiment_start_record, own_authentication),
    "a repeat": (experiment_start_record, lambda d: d.update(repeat_of=EARLIER_ATTEMPT)),
}


@pytest.mark.parametrize(
    ("build", "change"), START_1_3_ACCEPTS.values(), ids=START_1_3_ACCEPTS.keys()
)
def test_start_record_1_3_accepts(build: Callable[[], Document], change: Change) -> None:
    accepts(StartRecordV1_3, changed(build, change))


START_1_3_REJECTS: dict[str, tuple[Callable[[], Document], Change]] = {
    "a snapshot's operation": (experiment_update_record, lambda d: d.update(operation="rank_get")),
    "no case": (experiment_update_record, lambda d: d.update(case_id=None)),
    "its own token, without authenticating": (
        experiment_update_record,
        lambda d: d.update(authenticated_by=ATTEMPT_ID),
    ),
    "authenticated, and sent with another's token": (
        experiment_update_record,
        lambda d: d.update(exchanges=[AUTH]),
    ),
    "started.json without the rank_update's exchange": (
        experiment_start_record,
        lambda d: d.update(exchanges=[]),
    ),
    "started.json after a rank_update's 503": (
        experiment_start_record,
        lambda d: d.update(exchanges=[exchange("POST /rank", 503)]),
    ),
    "an update record that holds the rank_update's exchange": (
        experiment_update_record,
        lambda d: d.update(exchanges=[RANK]),
    ),
    "a repeat of itself": (experiment_start_record, lambda d: d.update(repeat_of=ATTEMPT_ID)),
}


@pytest.mark.parametrize(
    ("build", "change"), START_1_3_REJECTS.values(), ids=START_1_3_REJECTS.keys()
)
def test_start_record_1_3_rejects(build: Callable[[], Document], change: Change) -> None:
    rejects(StartRecordV1_3, changed(build, change))


# Attempt records 1.2.0 and 1.3.0


def update_of(document: Document) -> Document:
    update: Document = document["ranking_update"]
    return update


def rank_rejected(document: Document) -> None:
    failed(document, AUTH, exchange("POST /rank", 400))
    update_of(document).update(
        response=None, provider_metadata={"cost": None, "quota_remaining": None}
    )


ATTEMPT_1_2_ACCEPTS: dict[str, tuple[Callable[[], Document], Change]] = {
    "a rank_update rejected with a 400": (attempt_record_1_2, rank_rejected),
    "a rank_update that got a 503": (
        attempt_record_1_2,
        lambda d: (
            unknown(d, AUTH, exchange("POST /rank", 503)),
            update_of(d).update(response=None),
        ),
    ),
    "a rank_update interrupted": (
        attempt_record_1_2,
        lambda d: (
            unknown(d, AUTH, exchange("POST /rank", None)),
            update_of(d).update(response=None),
        ),
    ),
    "a rank_update that never connected": (
        attempt_record_1_2,
        lambda d: (
            failed(d, AUTH, exchange("POST /rank", None, result="not_connected")),
            update_of(d).update(response=None),
            d.update(possibly_charged=False),
        ),
    ),
    "authentication that failed": (
        attempt_record_1_2,
        lambda d: (
            failed(d, exchange("POST /auth", 401)),
            update_of(d).update(request=None, response=None),
            d.update(possibly_charged=False),
        ),
    ),
    "an interrupt before the rank_update's send": (
        attempt_record_1_2,
        lambda d: (
            failed(d, AUTH),
            update_of(d).update(response=None),
            d.update(possibly_charged=False),
        ),
    ),
    "a rank_update's 200 the wrapper couldn't decode": (
        attempt_record_1_2,
        lambda d: (failed(d, AUTH, RANK), d.update(ranking_update=ranking_update("undecoded"))),
    ),
    "a failure after the rank_update's response was saved": (
        attempt_record_1_2,
        lambda d: failed(d, AUTH, RANK),
    ),
    "resumed from its update record, with a saved response": (
        attempt_record_1_2,
        lambda d: failed(d, AUTH, RANK | {"note": "completed_from_saved_response"}),
    ),
    "resumed from its update record, without one": (
        attempt_record_1_2,
        lambda d: (
            unknown(d, AUTH, exchange("POST /rank", None)),
            update_of(d).update(response=None),
        ),
    ),
    "resumed from started.json, without a saved response": (
        attempt_record_1_2,
        lambda d: (unknown(d, AUTH, RANK), d.update(request=reference("request.json"))),
    ),
    "a backtest that got a 503": (
        attempt_record_1_2,
        lambda d: (
            unknown(d, AUTH, RANK, exchange("POST /screen/backtest", 503)),
            d.update(request=reference("request.json")),
        ),
    ),
    "a backtest restarted with its saved response": (
        attempt_record_1_2,
        lambda d: d.update(
            exchanges=[AUTH, RANK, SEND | {"note": "completed_from_saved_response"}]
        ),
    ),
    "a snapshot's 404": (
        snapshot_attempt_record,
        lambda d: (
            failed(d, AUTH, exchange("GET /rank", 404)),
            d.update(request=reference("request.json", SNAPSHOT_DIRECTORY)),
        ),
    ),
}


@pytest.mark.parametrize(
    ("build", "change"), ATTEMPT_1_2_ACCEPTS.values(), ids=ATTEMPT_1_2_ACCEPTS.keys()
)
def test_attempt_record_1_2_accepts(build: Callable[[], Document], change: Change) -> None:
    accepts(AttemptRecordV1_2, changed(build, change))


ATTEMPT_1_2_REJECTS: dict[str, tuple[Callable[[], Document], Change]] = {
    "a backtest without its rank_update": (
        attempt_record_1_2,
        lambda d: (
            d.update(exchanges=[AUTH, SEND]),
            update_of(d).update(request=None, response=None),
        ),
    ),
    "a backtest after a rank_update's 400": (
        attempt_record_1_2,
        lambda d: (
            d.update(exchanges=[AUTH, exchange("POST /rank", 400), SEND]),
            update_of(d).update(response=None),
        ),
    ),
    "a backtest after a rank_update the wrapper couldn't decode": (
        attempt_record_1_2,
        lambda d: d.update(ranking_update=ranking_update("undecoded")),
    ),
    "a backtest after a rank_update whose response wasn't saved": (
        attempt_record_1_2,
        lambda d: update_of(d).update(response=None),
    ),
    "the backtest before the rank_update": (
        attempt_record_1_2,
        lambda d: d.update(exchanges=[AUTH, SEND, RANK]),
    ),
    "two rank_updates": (
        attempt_record_1_2,
        lambda d: d.update(exchanges=[AUTH, RANK, RANK, SEND]),
    ),
    "a request Trial Folio doesn't send": (
        attempt_record_1_2,
        lambda d: d.update(exchanges=[AUTH, RANK, exchange("POST /rank/create"), SEND]),
    ),
    "a rank_update's exchange without its saved request": (
        attempt_record_1_2,
        lambda d: update_of(d).update(request=None),
    ),
    "a rank_update's response saved after a 400": (
        attempt_record_1_2,
        lambda d: failed(d, AUTH, exchange("POST /rank", 400)),
    ),
    "a rank_update's response saved as the backtest's": (
        attempt_record_1_2,
        lambda d: update_of(d).update(response=reference("response.json") | {"form": "decoded"}),
    ),
    "a rank_update's request saved as the backtest's": (
        attempt_record_1_2,
        lambda d: update_of(d).update(request=reference("request.json")),
    ),
    "no ranking_update": (attempt_record_1_2, lambda d: d.update(ranking_update=None)),
    "unknown after a rank_update's 400": (
        attempt_record_1_2,
        lambda d: (rank_rejected(d), d.update(outcome="unknown", error=UNKNOWN)),
    ),
    "unknown without a rank_update exchange": (
        attempt_record_1_2,
        lambda d: (unknown(d, AUTH), update_of(d).update(response=None)),
    ),
    "unknown after a rank_update's 200, without the backtest's request": (
        attempt_record_1_2,
        lambda d: unknown(d, AUTH, RANK),
    ),
    "unknown after a rank_update's 200 the wrapper couldn't decode": (
        attempt_record_1_2,
        lambda d: (
            unknown(d, AUTH, RANK),
            d.update(ranking_update=ranking_update("undecoded"), request=reference("request.json")),
        ),
    ),
    "unknown after a rank_update's 200 whose response wasn't saved": (
        attempt_record_1_2,
        lambda d: (
            unknown(d, AUTH, RANK),
            update_of(d).update(response=None),
            d.update(request=reference("request.json")),
        ),
    ),
    "failed after an interrupted rank_update": (
        attempt_record_1_2,
        lambda d: (
            failed(d, AUTH, exchange("POST /rank", None)),
            update_of(d).update(response=None),
        ),
    ),
    "not possibly charged after a rank_update's 400": (
        attempt_record_1_2,
        lambda d: (rank_rejected(d), d.update(possibly_charged=False)),
    ),
    "possibly charged after nothing was sent": (
        attempt_record_1_2,
        lambda d: (failed(d, AUTH), update_of(d).update(response=None)),
    ),
    "a noted rank_update before a backtest": (
        attempt_record_1_2,
        lambda d: d.update(
            exchanges=[AUTH, RANK | {"note": "completed_from_saved_response"}, SEND]
        ),
    ),
    "a noted rank_update that ended unknown": (
        attempt_record_1_2,
        lambda d: unknown(d, AUTH, RANK | {"note": "completed_from_saved_response"}),
    ),
    "a noted authentication": (
        attempt_record_1_2,
        lambda d: d.update(
            exchanges=[AUTH | {"note": "completed_from_saved_response"}, RANK, SEND]
        ),
    ),
    "a noted backtest that didn't succeed": (
        attempt_record_1_2,
        lambda d: (
            unknown(d, AUTH, RANK, SEND | {"note": "completed_from_saved_response"}),
            d.update(request=reference("request.json")),
        ),
    ),
    "a backtest without its saved request": (attempt_record_1_2, lambda d: d.update(request=None)),
    "a backtest's request saved under another name": (
        attempt_record_1_2,
        lambda d: d.update(request=reference("backtest.json")),
    ),
    "a failed backtest with a saved response": (
        attempt_record_1_2,
        lambda d: d.update(
            exchanges=[AUTH, RANK, exchange("POST /screen/backtest", 400)],
            outcome="failed",
            error=ERROR,
        ),
    ),
    "a noted rank_update before a backtest that failed": (
        attempt_record_1_2,
        lambda d: d.update(
            exchanges=[
                AUTH,
                RANK | {"note": "completed_from_saved_response"},
                exchange("POST /screen/backtest", 400),
            ],
            outcome="failed",
            error=ERROR,
            response=None,
        ),
    ),
    "a backtest's 200 without its saved response": (
        attempt_record_1_2,
        lambda d: d.update(response=None),
    ),
    "a succeeded attempt with an error": (attempt_record_1_2, lambda d: d.update(error=ERROR)),
    "sending without authentication": (
        attempt_record_1_2,
        lambda d: d.update(exchanges=[RANK, SEND]),
    ),
    "sending after failed authentication": (
        attempt_record_1_2,
        lambda d: d.update(exchanges=[exchange("POST /auth", 401), RANK, SEND]),
    ),
    "a snapshot's attempt with a rank_update": (
        snapshot_attempt_record,
        lambda d: d.update(ranking_update=ranking_update()),
    ),
    "a snapshot's attempt that sends a backtest": (
        snapshot_attempt_record,
        lambda d: d.update(exchanges=[AUTH, SEND]),
    ),
    "a snapshot's attempt with a case": (
        snapshot_attempt_record,
        lambda d: d.update(case_id=BASELINE_ID),
    ),
    "a case's attempt without one": (attempt_record_1_2, lambda d: d.update(case_id=None)),
    "the operation rank_update": (attempt_record_1_2, lambda d: d.update(operation="rank_update")),
    "an end before the start": (
        attempt_record_1_2,
        lambda d: d.update(ended_at="2026-10-14T12:00:00Z"),
    ),
}


@pytest.mark.parametrize(
    ("build", "change"), ATTEMPT_1_2_REJECTS.values(), ids=ATTEMPT_1_2_REJECTS.keys()
)
def test_attempt_record_1_2_rejects(build: Callable[[], Document], change: Change) -> None:
    rejects(AttemptRecordV1_2, changed(build, change))


ATTEMPT_1_3_ACCEPTS: dict[str, Change] = {
    "an attempt that authenticated": own_authentication,
    "a repeat": lambda d: d.update(repeat_of=EARLIER_ATTEMPT),
    "authentication that failed": lambda d: (
        failed(d, exchange("POST /auth", 401)),
        update_of(d).update(request=None, response=None),
        d.update(possibly_charged=False, authenticated_by=None),
    ),
    "a rank_update that got a 402": lambda d: (
        failed(
            d,
            exchange("POST /rank", 402),
            error={"code": "provider.quota_exceeded", "message": "No quota."},
        ),
        update_of(d).update(response=None),
    ),
    "resumed from started.json, without a saved response": lambda d: (
        unknown(d, RANK),
        d.update(request=reference("request.json")),
    ),
}


@pytest.mark.parametrize("change", ATTEMPT_1_3_ACCEPTS.values(), ids=ATTEMPT_1_3_ACCEPTS.keys())
def test_attempt_record_1_3_accepts(change: Change) -> None:
    accepts(AttemptRecordV1_3, changed(experiment_attempt_record, change))


ATTEMPT_1_3_REJECTS: dict[str, Change] = {
    "sending with no authentication named": lambda d: d.update(authenticated_by=None),
    "its own token, without authenticating": lambda d: d.update(authenticated_by=ATTEMPT_ID),
    "authenticated, and sent with another's token": lambda d: d.update(
        exchanges=[AUTH, RANK, SEND]
    ),
    "a snapshot's operation": lambda d: d.update(operation="rank_get"),
    "no ranking_update": lambda d: d.update(ranking_update=None),
    "a backtest without its rank_update": lambda d: (
        d.update(exchanges=[SEND]),
        update_of(d).update(request=None, response=None),
    ),
    "a repeat of itself": lambda d: d.update(repeat_of=ATTEMPT_ID),
    "unknown without a rank_update exchange": lambda d: (
        unknown(d),
        update_of(d).update(response=None),
    ),
    "unknown after a rank_update's 200, without the backtest's request": lambda d: unknown(d, RANK),
    "unknown after a rank_update's 200 the wrapper couldn't decode": lambda d: (
        unknown(d, RANK),
        d.update(ranking_update=ranking_update("undecoded"), request=reference("request.json")),
    ),
    "unknown after a rank_update's 200 whose response wasn't saved": lambda d: (
        unknown(d, RANK),
        update_of(d).update(response=None),
        d.update(request=reference("request.json")),
    ),
}


@pytest.mark.parametrize("change", ATTEMPT_1_3_REJECTS.values(), ids=ATTEMPT_1_3_REJECTS.keys())
def test_attempt_record_1_3_rejects(change: Change) -> None:
    rejects(AttemptRecordV1_3, changed(experiment_attempt_record, change))


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


# Run manifest 1.1.0


def demo_synthetic(document: Document) -> None:
    document.update(
        synthetic=True,
        approval="not_required",
        command={"name": "demo", "options": {"json": False}, "started_at": "2026-10-14T12:00:00Z"},
    )


def snapshot_ranking(document: Document) -> None:
    """A run ranked by a snapshot: its definition's copy is `rank_get`'s, beside the record."""
    artifact(document, "ranking_definition")["source"] = source(
        "ranking-definition", operation="rank_get"
    )
    document["artifacts"].insert(3, listed("snapshot.json", "ranking_snapshot_record", "1.0.0"))


RUN_MANIFEST_ACCEPTS: dict[str, Change] = {
    "a synthetic run the core wrote, with no command": core_synthetic,
    "a synthetic run trialfolio demo wrote": demo_synthetic,
    "a run ranked by a snapshot": snapshot_ranking,
    "a rank_update's 200 the wrapper couldn't decode": lambda d: artifact(
        d, "rank_update_response"
    ).update(
        path=f"{DIRECTORY}/rank-update-response.raw",
        role="rank_update_response_undecoded",
        source=SOURCES["rank_update_response_undecoded"],
    ),
}


@pytest.mark.parametrize("change", RUN_MANIFEST_ACCEPTS.values(), ids=RUN_MANIFEST_ACCEPTS.keys())
def test_run_manifest_1_1_accepts(change: Change) -> None:
    accepts(RunManifestV1_1, changed(run_manifest, change))


def definition_source(document: Document) -> Document:
    found: Document = artifact(document, "ranking_definition")["source"]
    return found


RUN_MANIFEST_REJECTS: dict[str, Change] = {
    "synthetic, approved with --approve": lambda d: (
        core_synthetic(d),
        d.update(approval="option"),
    ),
    "synthetic, approved interactively": lambda d: (
        core_synthetic(d),
        d.update(approval="interactive"),
    ),
    "synthetic, with the command run": lambda d: (
        core_synthetic(d),
        d.update(command=run_manifest()["command"]),
    ),
    "not synthetic, with the approval not_required": lambda d: d.update(approval="not_required"),
    "not synthetic, without a command": lambda d: d.update(command=None),
    "not synthetic, with the command demo": lambda d: (
        demo_synthetic(d),
        d.update(synthetic=False, approval="option"),
    ),
    "version 1.0.0": lambda d: d.update(schema_version="1.0.0"),
    "a log listed": lambda d: d["artifacts"].append(listed("logs/trialfolio.log", "report")),
    "a definition's copy with a parser": lambda d: definition_source(d).update(parser_version=1),
    "a definition's copy of another format": lambda d: definition_source(d).update(
        format="p123api-rank-get"
    ),
    "a definition's copy of another version": lambda d: definition_source(d).update(
        format_version="1.0.0"
    ),
    "a definition's copy from a file, verified": lambda d: definition_source(d).update(
        provenance="verified"
    ),
    "a definition's copy from a snapshot, user_supplied": lambda d: definition_source(d).update(
        operation="rank_get"
    ),
    "a definition's copy without its source record": lambda d: artifact(
        d, "ranking_definition"
    ).update(source=None),
    "a definition's copy under another name": lambda d: artifact(d, "ranking_definition").update(
        path="ranking.xml"
    ),
    "a rank_update's request of the backtest's format": lambda d: artifact(
        d, "rank_update_request"
    )["source"].update(format="p123api-screen-backtest-request"),
    "a rank_update's response from the backtest": lambda d: artifact(d, "rank_update_response")[
        "source"
    ].update(operation="screen_backtest"),
    "a rank_update's response parsed": lambda d: artifact(d, "rank_update_response")[
        "source"
    ].update(parser_version=1),
    "a rank_update's response the user supplied": lambda d: artifact(d, "rank_update_response")[
        "source"
    ].update(provenance="user_supplied"),
    "an undecoded rank_update response as the decoded one": lambda d: artifact(
        d, "rank_update_response"
    ).update(path=f"{DIRECTORY}/rank-update-response.raw"),
    "an update record without its schema version": lambda d: artifact(d, "update_record").update(
        schema_version=None
    ),
    "an update record with a source record": lambda d: artifact(d, "update_record").update(
        source=SOURCES["rank_update_request"]
    ),
    "an update record under another name": lambda d: artifact(d, "update_record").update(
        path=f"{DIRECTORY}/update.json"
    ),
    "a snapshot's record without its schema version": lambda d: (
        snapshot_ranking(d),
        artifact(d, "ranking_snapshot_record").update(schema_version=None),
    ),
    "a backtest's source of an operation 1.0.0 doesn't name": lambda d: artifact(
        d, "provider_response"
    )["source"].update(operation="rank_create"),
}


@pytest.mark.parametrize("change", RUN_MANIFEST_REJECTS.values(), ids=RUN_MANIFEST_REJECTS.keys())
def test_run_manifest_1_1_rejects(change: Change) -> None:
    rejects(RunManifestV1_1, changed(run_manifest, change))


# Experiment manifest 1.1.0


def experiment_artifact(document: Document, role: str) -> Document:
    return artifact(document, role)


EXPERIMENT_MANIFEST_ACCEPTS: dict[str, Change] = {
    "a plan ranked by a snapshot": lambda d: (
        experiment_artifact(d, "ranking_definition").update(
            source=source("ranking-definition", operation="rank_get")
        ),
        d["artifacts"].insert(
            2, listed("plans/1/snapshot.json", "ranking_snapshot_record", "1.0.0")
        ),
    ),
    "a synthetic experiment": lambda d: d.update(
        synthetic=True, approval="not_required", command=None
    ),
    "an undecoded rank_update response": lambda d: experiment_artifact(
        d, "rank_update_response"
    ).update(
        path=f"{EXPERIMENT_ATTEMPT}/rank-update-response.raw",
        role="rank_update_response_undecoded",
        source=SOURCES["rank_update_response_undecoded"],
    ),
}


@pytest.mark.parametrize(
    "change", EXPERIMENT_MANIFEST_ACCEPTS.values(), ids=EXPERIMENT_MANIFEST_ACCEPTS.keys()
)
def test_experiment_manifest_1_1_accepts(change: Change) -> None:
    accepts(ExperimentManifestV1_1, changed(experiment_manifest, change))


EXPERIMENT_MANIFEST_REJECTS: dict[str, Change] = {
    "version 1.0.0": lambda d: d.update(schema_version="1.0.0"),
    "a definition's copy in an attempt's directory": lambda d: experiment_artifact(
        d, "ranking_definition"
    ).update(path=f"{EXPERIMENT_ATTEMPT}/definition.xml"),
    "an update record in a plan's directory": lambda d: experiment_artifact(
        d, "update_record"
    ).update(path="plans/1/updating.json"),
    "a rank_update's request at the output's root": lambda d: experiment_artifact(
        d, "rank_update_request"
    ).update(path="rank-update-request.json"),
    "a snapshot's record without the definition's copy": lambda d: (
        d["artifacts"].remove(experiment_artifact(d, "ranking_definition")),
        d["artifacts"].insert(
            1, listed("plans/1/snapshot.json", "ranking_snapshot_record", "1.0.0")
        ),
    ),
    "a definition's copy without its source record": lambda d: experiment_artifact(
        d, "ranking_definition"
    ).update(source=None),
    "a rank_update's response of another format": lambda d: experiment_artifact(
        d, "rank_update_response"
    )["source"].update(format="p123api-screen-backtest"),
    "synthetic, with a command": lambda d: d.update(synthetic=True, approval="not_required"),
    "a configuration of another format": lambda d: experiment_artifact(d, "configuration")[
        "source"
    ].update(format="screen-configuration"),
}


@pytest.mark.parametrize(
    "change", EXPERIMENT_MANIFEST_REJECTS.values(), ids=EXPERIMENT_MANIFEST_REJECTS.keys()
)
def test_experiment_manifest_1_1_rejects(change: Change) -> None:
    rejects(ExperimentManifestV1_1, changed(experiment_manifest, change))


# The snapshot manifest


def snapshot_synthetic(document: Document) -> None:
    """The synthetic snapshot the core takes with the demo's client."""
    document.update(synthetic=True, approval="not_required", command=None)


SNAPSHOT_MANIFEST_ACCEPTS: dict[str, Change] = {
    "a synthetic snapshot the core took": snapshot_synthetic,
    "a snapshot whose rank_get failed": snapshot_failed,
    "a response the wrapper couldn't decode": lambda d: (
        snapshot_failed(d),
        d["artifacts"].insert(
            4,
            listed(
                f"{SNAPSHOT_DIRECTORY}/response.raw",
                "provider_response_undecoded",
                None,
                SNAPSHOT_SOURCES,
            ),
        ),
    ),
    "approved interactively": lambda d: d.update(approval="interactive"),
}


@pytest.mark.parametrize(
    "change", SNAPSHOT_MANIFEST_ACCEPTS.values(), ids=SNAPSHOT_MANIFEST_ACCEPTS.keys()
)
def test_snapshot_manifest_accepts(change: Change) -> None:
    accepts(RankingSnapshotManifest, changed(snapshot_manifest, change))


def snapshot_artifact(document: Document, role: str) -> Document:
    return artifact(document, role)


SNAPSHOT_MANIFEST_REJECTS: dict[str, Change] = {
    "synthetic, approved with --approve": lambda d: (
        snapshot_synthetic(d),
        d.update(approval="option"),
    ),
    "synthetic, with a command": lambda d: d.update(synthetic=True, approval="not_required"),
    "not synthetic, with the approval not_required": lambda d: d.update(approval="not_required"),
    "not synthetic, without a command": lambda d: d.update(command=None),
    "completed without its record": lambda d: d["artifacts"].remove(
        snapshot_artifact(d, "ranking_snapshot_record")
    ),
    "completed without its definition": lambda d: d["artifacts"].remove(
        snapshot_artifact(d, "ranking_definition")
    ),
    "failed, with its definition alone": lambda d: (
        snapshot_failed(d),
        d["artifacts"].append(
            listed("definition.xml", "ranking_definition", None, SNAPSHOT_SOURCES)
        ),
    ),
    "failed, with its definition and record": lambda d: d.update(
        outcome="failed",
        error={"code": "provider.unsupported_capability", "message": "Portfolio123 refused it."},
    ),
    "partial": lambda d: d.update(
        outcome="partial",
        error={"code": "execution.partial", "message": "Some planned cases didn't succeed."},
    ),
    "without its plan": lambda d: d["artifacts"].remove(snapshot_artifact(d, "plan")),
    "without its configuration": lambda d: d["artifacts"].remove(
        snapshot_artifact(d, "configuration")
    ),
    "a start record with a source record": lambda d: snapshot_artifact(d, "start_record").update(
        source=SNAPSHOT_SOURCES["provider_request"]
    ),
    "a configuration without its source record": lambda d: snapshot_artifact(
        d, "configuration"
    ).update(source=None),
    "a definition from a file": lambda d: snapshot_artifact(d, "ranking_definition").update(
        source=source("ranking-definition", "user_supplied", None)
    ),
    "a response of the backtest's format": lambda d: snapshot_artifact(d, "provider_response")[
        "source"
    ].update(format="p123api-screen-backtest"),
    "a response no parser read": lambda d: snapshot_artifact(d, "provider_response")[
        "source"
    ].update(parser_version=None),
    "a request from another operation": lambda d: snapshot_artifact(d, "provider_request")[
        "source"
    ].update(operation="screen_backtest"),
    "a configuration of the screen's format": lambda d: snapshot_artifact(d, "configuration")[
        "source"
    ].update(format="screen-configuration"),
    "a configuration the provider returned": lambda d: snapshot_artifact(d, "configuration")[
        "source"
    ].update(provenance="verified"),
    "a plan in an experiment's place": lambda d: snapshot_artifact(d, "plan").update(
        path="plans/1/plan.json"
    ),
    "an attempt in a case's directory": lambda d: snapshot_artifact(d, "attempt_record").update(
        path=f"cases/{BASELINE_ID}/attempts/{ATTEMPT_ID}/attempt.json"
    ),
    "a role a snapshot has no file of": lambda d: d["artifacts"].append(
        listed("report.html", "report", None, SNAPSHOT_SOURCES)
    ),
    "two provider requests": lambda d: d["counts"].update(provider_requests=2),
    "a retry": lambda d: d["counts"].update(retries=1),
    "capabilities": lambda d: d.update(capabilities=run_manifest()["capabilities"]),
    "a run's artifact type": lambda d: d.update(artifact_type="run"),
    "no parser": lambda d: d.update(parsers=[]),
    "a parser listed twice": lambda d: d.update(parsers=d["parsers"] * 2),
    "the backtest's parser in rank_get's place": lambda d: d["parsers"][0].update(
        layout="p123api-screen-backtest"
    ),
    "another version of rank_get's parser": lambda d: d["parsers"][0].update(parser_version=2),
    "another version of rank_get's layout": lambda d: d["parsers"][0].update(layout_version=2),
    "the backtest's parser beside rank_get's": lambda d: d["parsers"].append(
        {"layout": "p123api-screen-backtest", "layout_version": 1, "parser_version": 1}
    ),
}


@pytest.mark.parametrize(
    "change", SNAPSHOT_MANIFEST_REJECTS.values(), ids=SNAPSHOT_MANIFEST_REJECTS.keys()
)
def test_snapshot_manifest_rejects(change: Change) -> None:
    rejects(RankingSnapshotManifest, changed(snapshot_manifest, change))


# The snapshot record

SNAPSHOT_RECORD_ACCEPTS: dict[str, Change] = {
    "a name other than the one requested": lambda d: d["system"].update(name="Value and Momentum"),
    "a system that can't be a ranking, recorded as it is": lambda d: d["system"].update(
        ranking_method=1, currency="EUR", type="ETF"
    ),
}


@pytest.mark.parametrize(
    "change", SNAPSHOT_RECORD_ACCEPTS.values(), ids=SNAPSHOT_RECORD_ACCEPTS.keys()
)
def test_snapshot_record_accepts(change: Change) -> None:
    accepts(RankingSnapshotRecord, changed(snapshot_record, change))


SNAPSHOT_RECORD_REJECTS: dict[str, Change] = {
    "an ID that's a boolean": lambda d: d["system"].update(id=True),
    "an ID as text": lambda d: d["system"].update(id="424242"),
    "a ranking method as text": lambda d: d["system"].update(ranking_method="2"),
    "a system without its type": lambda d: d["system"].pop("type"),
    "a blank request": lambda d: d.update(requested=" "),
    "a time that isn't UTC": lambda d: d.update(taken_at="2026-10-14T14:01:30+02:00"),
    "an attempt ID not in canonical form": lambda d: d.update(attempt_id=ATTEMPT_ID.upper()),
    "a definition by its path": lambda d: d.update(definition="definition.xml"),
    "version 1.1.0": lambda d: d.update(schema_version="1.1.0"),
}


@pytest.mark.parametrize(
    "change", SNAPSHOT_RECORD_REJECTS.values(), ids=SNAPSHOT_RECORD_REJECTS.keys()
)
def test_snapshot_record_rejects(change: Change) -> None:
    rejects(RankingSnapshotRecord, changed(snapshot_record, change))


# The rows of settings.csv 1.1.0 and differences.csv 1.1.0

SETTINGS_ROW_ACCEPTS: dict[str, Change] = {
    "the ranking row of a definition": ranking_settings_row,
    "a weight a ranking variant sets": lambda d: d.update(
        value="70", original_key="variants.ranking[0].set[0]", original_value="70"
    ),
    "a row of another setting": lambda d: d.update(
        setting="max_holdings",
        value="25",
        unit="count",
        original_key="max_holdings",
        original_value="25",
        node=None,
    ),
}


@pytest.mark.parametrize("change", SETTINGS_ROW_ACCEPTS.values(), ids=SETTINGS_ROW_ACCEPTS.keys())
def test_settings_row_1_1_accepts(change: Change) -> None:
    accepts(SettingsRowV1_1, changed(settings_row, change))


SETTINGS_ROW_REJECTS: dict[str, Change] = {
    "a weight row without its node": lambda d: d.update(node=None),
    "a node on the ranking row": lambda d: (
        ranking_settings_row(d),
        d.update(node="Earnings Yield"),
    ),
    "a blank node": lambda d: d.update(node=""),
    "a weight of 0": lambda d: d.update(value="0"),
    "a weight not normalized": lambda d: d.update(value="60.0"),
    "a weight with a unit": lambda d: d.update(unit="percent"),
    "a weight that's inferred": lambda d: d.update(provenance="inferred", inference_rule="A rule"),
    "a weight with a flag": lambda d: d.update(flags=["not_snapshotted"]),
    "a weight in another category": lambda d: d.update(category="other", critical=False),
    "a ranking by formula": lambda d: (
        ranking_settings_row(d),
        d.update(value='{"formula": "EarnYield", "lower_is_better": false}'),
    ),
    "a definition flagged not_snapshotted": lambda d: (
        ranking_settings_row(d),
        d.update(flags=["not_snapshotted"]),
    ),
    "an original key without its value": lambda d: d.update(original_value=None),
}


@pytest.mark.parametrize("change", SETTINGS_ROW_REJECTS.values(), ids=SETTINGS_ROW_REJECTS.keys())
def test_settings_row_1_1_rejects(change: Change) -> None:
    rejects(SettingsRowV1_1, changed(settings_row, change))


def test_settings_row_1_0_0_refuses_a_weight_row_and_a_definition() -> None:
    """A run or case whose ranking is a definition writes `settings.csv` 1.1.0, so 1.0.0's rows
    stay as 0.3.0 reads them."""
    weight = settings_row()
    weight.pop("node")
    definition = changed(settings_row, ranking_settings_row)
    definition.pop("node")

    rejects(SettingsRow, weight)
    rejects(SettingsRow, definition)


DIFFERENCES_ROW_ACCEPTS: dict[str, Change] = {
    "a weight that differs, undeclared": undeclared,
    "the same weight": lambda d: d.update(value="60", classification="same", declared_reason=None),
    "the same weight, with ranking declared": lambda d: d.update(
        value="60", classification="same", declared_reason=None
    ),
    "a node the result's definition lacks": lambda d: (undeclared(d), d.update(value="absent")),
    "a node the baseline lacks, declared": lambda d: d.update(baseline_value="absent"),
    "a weight against a ranking by name": lambda d: d.update(
        value=None,
        classification="unknown",
        declared_reason=None,
        flagged=True,
        flags=["critical_unknown"],
    ),
    "a definition against a formula": lambda d: (
        undeclared(d),
        d.update(
            name="ranking",
            node=None,
            baseline_value=DEFINITION_TEXT,
            value='{"formula": "EarnYield", "lower_is_better": false}',
        ),
    ),
    "a definition against a ranking by name": lambda d: (
        undeclared(d),
        d.update(
            name="ranking",
            node=None,
            baseline_value=DEFINITION_TEXT,
            value='{"name": "Value and momentum"}',
            flags=["critical_unexplained_mismatch", "not_snapshotted"],
        ),
    ),
    "a metric row": lambda d: d.update(
        kind="metric",
        name="annualized_return",
        subject="strategy",
        category=None,
        critical=None,
        baseline_value="12.30",
        value="12.50",
        unit="percent",
        classification="differenced",
        difference="0.20",
        difference_unit="pp",
        difference_decimals=2,
        declared_reason=None,
        node=None,
    ),
}


@pytest.mark.parametrize(
    "change", DIFFERENCES_ROW_ACCEPTS.values(), ids=DIFFERENCES_ROW_ACCEPTS.keys()
)
def test_differences_row_1_1_accepts(change: Change) -> None:
    accepts(DifferencesRowV1_1, changed(differences_row, change))


DIFFERENCES_ROW_REJECTS: dict[str, Change] = {
    "a weight row without its node": lambda d: d.update(node=None),
    "a node on another setting's row": lambda d: d.update(
        name="max_holdings", baseline_value="25", value="50", unit="count"
    ),
    "the same weight, with a declared reason": lambda d: d.update(
        value="60", classification="same"
    ),
    "a weight flagged intended_change_not_observed": lambda d: d.update(
        value="60",
        classification="same",
        declared_reason=None,
        flagged=True,
        flags=["intended_change_not_observed"],
    ),
    "a declared weight change without its reason": lambda d: d.update(declared_reason=None),
    "an undeclared weight change with a reason": lambda d: (
        undeclared(d),
        d.update(declared_reason="More weight on earnings yield."),
    ),
    "weights that differ, called the same": lambda d: d.update(
        classification="same", declared_reason=None
    ),
    "an unknown weight with both values": lambda d: d.update(
        classification="unknown",
        declared_reason=None,
        flagged=True,
        flags=["critical_unknown"],
    ),
    "an undeclared weight change not flagged": lambda d: (
        undeclared(d),
        d.update(flags=[], flagged=False),
    ),
    "a weight of 0": lambda d: d.update(value="0"),
    "a weight not normalized": lambda d: d.update(value="70.0"),
    "both nodes absent": lambda d: (
        undeclared(d),
        d.update(
            baseline_value="absent", value="absent", classification="same", flags=[], flagged=False
        ),
    ),
    "a definition flagged not_snapshotted": lambda d: (
        undeclared(d),
        d.update(
            name="ranking",
            node=None,
            baseline_value=DEFINITION_TEXT,
            value='{"formula": "EarnYield", "lower_is_better": false}',
            flags=["critical_unexplained_mismatch", "not_snapshotted"],
        ),
    ),
    "a metric row with a node": lambda d: d.update(
        kind="metric",
        name="annualized_return",
        subject="strategy",
        category=None,
        critical=None,
        baseline_value="12.30",
        value="12.50",
        unit="percent",
        classification="differenced",
        difference="0.20",
        difference_unit="pp",
        difference_decimals=2,
        declared_reason=None,
    ),
}


@pytest.mark.parametrize(
    "change", DIFFERENCES_ROW_REJECTS.values(), ids=DIFFERENCES_ROW_REJECTS.keys()
)
def test_differences_row_1_1_rejects(change: Change) -> None:
    rejects(DifferencesRowV1_1, changed(differences_row, change))


def test_differences_row_1_0_0_refuses_a_weight_row() -> None:
    document = differences_row()
    document.pop("node")

    rejects(DifferencesRow, document)
