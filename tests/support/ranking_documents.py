"""A valid document of each record of a ranking definition, and of a ranking snapshot, which the
records' contract tests change: plans 1.2.0 and 1.3.0, the snapshot plan, start and attempt records
1.2.0 and 1.3.0, `experiment.json` 1.1.0, run manifest 1.1.0, experiment manifest 1.1.0, the
snapshot manifest and record, and the rows of `settings.csv` 1.1.0 and `differences.csv` 1.1.0; 19
documents, of 14 models, which `VALID`, in tests/contract/test_ranking_artifact_models.py, pairs
with their models. Each is synthetic, and the plans are consistent, as their consistency rules
require: each definition's hash is its text's, and each case's weight rows are its definition's.

TS-T07 moved them here from tests/contract/test_ranking_artifact_models.py, whose first 1,000 lines
they were, when it separated that module's tests by family (docs/test-refactoring.md, modules to
separate).
"""

import hashlib
import json
from copy import deepcopy

from tests.support.contract_checks import Document, digest
from trialfolio.contracts.screen_settings import SCREEN_SETTINGS


def hash_of(definition: str) -> str:
    """A definition's hash, as its case's `ranking` row holds it: of its UTF-8 text."""
    return "sha256:" + hashlib.sha256(definition.encode("utf-8")).hexdigest()


PLAN_HASH = digest("a1")
EARLIER_PLAN = digest("a0")
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
"""A synthetic definition of two top-level factors, at 60 and 40, which the models read as Trial
Folio reads a definition."""

HEAVY = DEFINITION.replace('Weight="60.0"', 'Weight="70"').replace('Weight="40"', 'Weight="30"')
"""The definition the ranking variant that sets the factors to 70 and 30 gives: each weight that
differs rewritten in its normalized form."""

NO_SALES = DEFINITION.replace(
    '\n\t<StockFormula Name="Sales Yield" Weight="40" RankType="Higher">\n'
    "\t\t<Formula>SalesYield</Formula>\n\t</StockFormula>",
    "",
).replace('Weight="60.0"', 'Weight="100"')
"""The definition the removal of Sales Yield gives, with Earnings Yield at 100: the element taken
out with its line, and the weight rewritten."""

DEFINITION_ID = hash_of(DEFINITION)
HEAVY_ID = hash_of(HEAVY)

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
