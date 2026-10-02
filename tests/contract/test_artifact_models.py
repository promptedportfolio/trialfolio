"""The artifact models accept what docs/contracts.md describes, and reject what it calls invalid.

Traces to docs/contracts.md: plan contents, execution outcomes and attempts, artifact storage
(the manifest), normalized tables, the JSON summary, license acknowledgment, and canonical
hashing's form for datetimes. Each document below is synthetic, and read as a reader reads it:
from JSON text, with `model_validate_json`.
"""

import json
from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from trialfolio.contracts.acknowledgment import AcknowledgmentRecord
from trialfolio.contracts.attempt import AttemptRecord, StartRecord
from trialfolio.contracts.manifest import RunManifest
from trialfolio.contracts.plan import Plan
from trialfolio.contracts.screen_settings import SCREEN_SETTINGS
from trialfolio.contracts.summary import JsonSummary
from trialfolio.contracts.tables import (
    METRICS_COLUMNS,
    SETTINGS_COLUMNS,
    MetricsRow,
    SettingsRow,
)

type Document = dict[str, Any]
type Change = Callable[[Document], object]

PLAN_HASH = "sha256:" + "a1" * 32
ARTIFACT_ID = "sha256:" + "b2" * 32
CASE_ID = "case-0123456789abcdef"
ATTEMPT_ID = "1b4e28ba-2fa1-4d2b-883f-0016d3cca427"
VERSIONS = {"provider_wrapper": {"p123api": "3.1.0"}}
TRANSPORT = {"requests": "2.34.2", "urllib3": "2.8.0"}

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
INFERRED = {"commission", "data_vendor", "risk_stats_period"}
FLAGS = {"universe": ["not_snapshotted"], "data_vendor": ["inferred_default"]} | {
    "risk_stats_period": ["inferred_default"]
}


def plan_settings() -> list[Document]:
    rows: list[Document] = []
    for setting in SCREEN_SETTINGS:
        value = SETTING_VALUES.get(setting.name, "not_sent")
        provenance = (
            "inferred"
            if setting.name in INFERRED
            else "verified"
            if setting.name in SETTING_VALUES
            else "unknown"
        )
        rows.append(
            {
                "setting": setting.name,
                "category": setting.category,
                "critical": setting.category != "other",
                "value": value,
                "unit": setting.unit,
                "interpretation": "interpreted"
                if setting.name in SETTING_VALUES
                else "not_interpreted",
                "expected_provenance": provenance,
                "inference_rule": "A documented rule, checked 2026-10-01"
                if provenance == "inferred"
                else None,
                "flags": FLAGS.get(setting.name, []),
            }
        )
    return rows


def plan() -> Document:
    return {
        "schema_version": "1.0.0",
        "trialfolio_version": "0.1.0",
        "canonicalization_version": 1,
        "provider_wrapper": {"p123api": "3.1.0"},
        "transport": TRANSPORT,
        "title": "Café screen",
        "purpose": None,
        "cases": [
            {
                "case_id": CASE_ID,
                "requests": [
                    {
                        "operation": "screen_backtest",
                        "params": {
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
                            "slippage": 1.0,
                            "rebalFreq": "Every 4 Weeks",
                        },
                    }
                ],
                "settings": plan_settings(),
            }
        ],
        "budget": {
            "provider_requests": 1,
            "credits_per_request": 5,
            "credits_per_request_source": {
                "title": "API: Screen",
                "url": "https://portfolio123.customerly.help/en/articles/43324-api-screen",
                "checked": "2026-10-01",
            },
            "credits": 5,
            "authentication_calls": 1,
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
        ],
        "plan_hash": PLAN_HASH,
    }


def start_record() -> Document:
    return {
        "schema_version": "1.0.0",
        "trialfolio_version": "0.1.0",
        "attempt_id": ATTEMPT_ID,
        "case_id": CASE_ID,
        "plan_hash": PLAN_HASH,
        "started_at": "2026-10-02T15:04:05Z",
        "provider_wrapper": {"p123api": "3.1.0"},
        "transport": TRANSPORT,
        "exchanges": [{"request": "POST /auth", "result": "response", "status": 200, "note": None}],
    }


def attempt_record() -> Document:
    return start_record() | {
        "ended_at": "2026-10-02T15:04:35.250000Z",
        "outcome": "succeeded",
        "error": None,
        "exchanges": [
            {"request": "POST /auth", "result": "response", "status": 200, "note": None},
            {"request": "POST /screen/backtest", "result": "response", "status": 200, "note": None},
        ],
        "possibly_charged": True,
        "request": {
            "path": f"cases/{CASE_ID}/attempts/{ATTEMPT_ID}/request.json",
            "artifact_id": ARTIFACT_ID,
        },
        "response": {
            "path": f"cases/{CASE_ID}/attempts/{ATTEMPT_ID}/response.json",
            "artifact_id": ARTIFACT_ID,
            "form": "decoded",
        },
        "provider_metadata": {"cost": 5, "quota_remaining": 1000},
    }


def manifest() -> Document:
    source = {
        "acquired_at": "2026-10-02T15:04:35Z",
        "format": "p123api-screen-backtest",
        "format_version": "1",
        "parser_version": 1,
        "provenance": "verified",
        "operation": "screen_backtest",
    }
    return {
        "schema_version": "1.0.0",
        "artifact_type": "run",
        "trialfolio_version": "0.1.0",
        "created_at": "2026-10-02T15:04:40Z",
        "command": {
            "name": "run",
            "options": {"config": "screen.yaml", "out": "runs/baseline", "approve": PLAN_HASH},
            "started_at": "2026-10-02T15:04:00Z",
        },
        "synthetic": False,
        "plan_hash": PLAN_HASH,
        "approval": "option",
        "outcome": "completed",
        "error": None,
        "artifacts": [
            {
                "path": "plan.json",
                "artifact_id": ARTIFACT_ID,
                "size": 4096,
                "role": "plan",
                "schema_version": "1.0.0",
                "source": None,
            },
            {
                "path": f"cases/{CASE_ID}/attempts/{ATTEMPT_ID}/response.json",
                "artifact_id": ARTIFACT_ID,
                "size": 65536,
                "role": "provider_response",
                "schema_version": None,
                "source": source,
            },
        ],
        "parsers": [
            {"layout": "p123api-screen-backtest", "layout_version": 1, "parser_version": 1}
        ],
        "license_id": "LicenseRef-NSPRL-1.0",
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
            "provider_requests": 1,
            "retries": 0,
            "cost": 5,
        },
    }


def metrics_row() -> Document:
    return {
        "label": "baseline",
        "subject": "strategy",
        "metric_id": "annualized_return",
        "source_label": "annualized_return",
        "value": "12.30",
        "unit": "percent",
        "source_decimals": 2,
        "availability": "available",
        "unavailable_reason": None,
        "origin": "reported",
        "provenance": "verified",
        "period_start": "2016-01-04",
        "period_end": "2025-12-31",
        "benchmark": None,
        "source_artifact": ARTIFACT_ID,
        "source_location": "stats.port.annualized_return",
    }


def settings_row() -> Document:
    return {
        "label": "baseline",
        "setting": "slippage_percent",
        "category": "costs",
        "critical": True,
        "value": "0.25",
        "unit": "percent",
        "interpretation": "interpreted",
        "provenance": "verified",
        "inference_rule": None,
        "original_key": "slippage_percent",
        "original_value": "0.250",
        "source_artifact": ARTIFACT_ID,
        "flags": [],
    }


def summary() -> Document:
    return {
        "schema_version": "1.0.0",
        "command": "run",
        "trialfolio_version": "0.1.0",
        "outcome": "completed",
        "exit_code": 0,
        "ids": {"plan_hash": PLAN_HASH, "case_id": CASE_ID, "attempt_id": ATTEMPT_ID},
        "output_dir": "runs/baseline/",
        "outputs": {"manifest": "manifest.json", "report": "report.html"},
        "counts": {
            "attempts": 1,
            "provider_requests": 1,
            "metrics_unavailable": 0,
            "warnings": 0,
            "cost": 5,
        },
        "statistical_validation": "not_assessed",
        "trading_readiness": "not_assessed",
        "error": None,
    }


def acknowledgment() -> Document:
    return {
        "license_id": "LicenseRef-NSPRL-1.0",
        "notice_version": "1.0",
        "acknowledged_at": "2026-10-02T15:00:00Z",
        "method": "command",
    }


VALID: list[tuple[type[BaseModel], Callable[[], Document]]] = [
    (Plan, plan),
    (StartRecord, start_record),
    (AttemptRecord, attempt_record),
    (RunManifest, manifest),
    (MetricsRow, metrics_row),
    (SettingsRow, settings_row),
    (JsonSummary, summary),
    (AcknowledgmentRecord, acknowledgment),
]


def changed(build: Callable[[], Document], change: Change) -> Document:
    document = deepcopy(build())
    change(document)
    return document


def rejects(model: type[BaseModel], document: Document) -> None:
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(document))


@pytest.mark.parametrize(("model", "build"), VALID, ids=lambda item: getattr(item, "__name__", ""))
def test_documents_round_trip(model: type[BaseModel], build: Callable[[], Document]) -> None:
    """A valid document reads, and writes back as the same JSON."""
    document = build()

    written = model.model_validate_json(json.dumps(document)).model_dump_json()

    assert json.loads(written) == document


@pytest.mark.parametrize(("model", "build"), VALID, ids=lambda item: getattr(item, "__name__", ""))
def test_unknown_fields_are_rejected(model: type[BaseModel], build: Callable[[], Document]) -> None:
    rejects(model, build() | {"unexpected": 1})


def test_slippage_is_sent_as_a_float() -> None:
    """Plan contents: `slippage` is a JSON float, `1.0` for a whole number, never `1`."""
    written = Plan.model_validate_json(json.dumps(plan())).model_dump_json()

    assert '"slippage":1.0' in written


def test_datetimes_are_written_in_utc_with_z() -> None:
    """Canonical hashing: datetimes are UTC ISO 8601 with a `Z` suffix."""
    record = StartRecord.model_validate_json(json.dumps(start_record()))

    assert '"started_at":"2026-10-02T15:04:05Z"' in record.model_dump_json()


def settings_of(document: Document) -> list[Document]:
    return document["cases"][0]["settings"]


PLAN_CHANGES: dict[str, Change] = {
    "two cases": lambda d: d["cases"].append(d["cases"][0]),
    "settings out of order": lambda d: settings_of(d).reverse(),
    "a setting missing": lambda d: settings_of(d).pop(),
    "wrong unit": lambda d: settings_of(d)[4].update(unit="weeks"),
    "critical other": lambda d: settings_of(d)[16].update(critical=True),
    "integer as text": lambda d: settings_of(d)[4].update(value="25"),
    "decimal not normalized": lambda d: settings_of(d)[12].update(value="0.250"),
    "inferred without a rule": lambda d: settings_of(d)[13].update(inference_rule=None),
    "rule without inference": lambda d: settings_of(d)[0].update(inference_rule="A rule"),
    "coverage flag before execution": lambda d: settings_of(d)[8].update(
        flags=["coverage_mismatch"]
    ),
    "token not documented": lambda d: settings_of(d)[18].update(value="zero"),
    "credits not the product": lambda d: d["budget"].update(credits=10),
    "a retry": lambda d: d["retry_policy"].update(automatic_retries=1),
    "transPrice true": lambda d: d["cases"][0]["requests"][0]["params"].update(transPrice=True),
    "slippage negative": lambda d: d["cases"][0]["requests"][0]["params"].update(slippage=-0.25),
    "rule with a type": lambda d: d["cases"][0]["requests"][0]["params"]["screen"]["rules"][
        0
    ].update(type="common"),
    "credentials with settings": lambda d: d["data_sent"][0].update(settings=["universe"]),
    "category twice": lambda d: d["data_sent"].append(d["data_sent"][1]),
    "uppercase hash": lambda d: d.update(plan_hash=PLAN_HASH.upper()),
    "prefixed version": lambda d: d.update(trialfolio_version="v0.1.0"),
    "end before start": lambda d: d["cases"][0]["requests"][0]["params"].update(endDt="2015-12-31"),
    "holdings 0": lambda d: settings_of(d)[4].update(value=0),
    "impossible date": lambda d: settings_of(d)[8].update(value="2016-13-45"),
    "too many decimals": lambda d: settings_of(d)[12].update(value="0.123456"),
    "a value not accepted": lambda d: settings_of(d)[1].update(value="etf"),
    "blank text": lambda d: settings_of(d)[0].update(value="  "),
    "not sent but interpreted": lambda d: settings_of(d)[18].update(interpretation="interpreted"),
}


@pytest.mark.parametrize("change", PLAN_CHANGES.values(), ids=PLAN_CHANGES.keys())
def test_plan_rejects(change: Change) -> None:
    rejects(Plan, changed(plan, change))


def interrupted_backtest(document: Document) -> None:
    document["exchanges"][1] = {
        "request": "POST /screen/backtest",
        "result": "interrupted",
        "status": None,
        "note": None,
    }


def failed_authentication(document: Document) -> None:
    document.update(
        outcome="failed",
        error={"code": "provider.auth_failed", "message": "Check the API ID and key."},
        exchanges=[{"request": "POST /auth", "result": "response", "status": 401, "note": None}],
        possibly_charged=False,
        request=None,
        response=None,
        provider_metadata={"cost": None, "quota_remaining": None},
    )


def unknown_outcome(document: Document) -> None:
    interrupted_backtest(document)
    document.update(
        outcome="unknown",
        error={"code": "provider.outcome_unknown", "message": "Not retried."},
        response=None,
    )


def restarted_without_response(document: Document) -> None:
    """Uncertain completion: a running attempt restarted with nothing saved is unknown, possibly
    charged, though its start record holds only the authentication exchange."""
    document.update(
        outcome="unknown",
        error={"code": "provider.outcome_unknown", "message": "Not retried."},
        exchanges=[document["exchanges"][0]],
        possibly_charged=True,
        response=None,
    )


def restarted_with_saved_response(document: Document) -> None:
    document["exchanges"][1]["note"] = "completed_from_saved_response"


def undecoded_capture(document: Document) -> None:
    """A 200 the wrapper couldn't decode is succeeded for capture; the run's result is flagged."""
    document["response"] = {
        "path": f"cases/{CASE_ID}/attempts/{ATTEMPT_ID}/response.raw",
        "artifact_id": ARTIFACT_ID,
        "form": "undecoded",
    }


@pytest.mark.parametrize(
    "change",
    [
        failed_authentication,
        unknown_outcome,
        restarted_without_response,
        restarted_with_saved_response,
        undecoded_capture,
    ],
)
def test_attempt_record_accepts_other_endings(change: Change) -> None:
    AttemptRecord.model_validate_json(json.dumps(changed(attempt_record, change)))


ATTEMPT_CHANGES: dict[str, Change] = {
    "succeeded with an error": lambda d: d.update(
        error={"code": "internal.unexpected", "message": "x"}
    ),
    "failed without an error": lambda d: (failed_authentication(d), d.update(error=None)),
    "succeeded without a response": lambda d: d.update(response=None),
    "sent but not possibly charged": lambda d: d.update(possibly_charged=False),
    "authentication only, possibly charged": lambda d: (
        failed_authentication(d),
        d.update(possibly_charged=True),
    ),
    "not_connected with a status": lambda d: d["exchanges"][1].update(result="not_connected"),
    "response without a status": lambda d: d["exchanges"][1].update(status=None),
    "ended before it started": lambda d: d.update(ended_at="2026-10-02T15:00:00Z"),
    "not in UTC": lambda d: d.update(started_at="2026-10-02T15:04:05+01:00"),
    "no time zone": lambda d: d.update(started_at="2026-10-02T15:04:05"),
    "not a version 4 UUID": lambda d: d.update(attempt_id="1b4e28ba-2fa1-11d2-883f-0016d3cca427"),
    "absolute path": lambda d: d["request"].update(path="/tmp/request.json"),
    "path leaving the run": lambda d: d["request"].update(path="cases/../../request.json"),
    "running is not an ending": lambda d: d.update(outcome="running"),
    "decoded saved as response.raw": lambda d: (
        undecoded_capture(d),
        d["response"].update(form="decoded"),
    ),
    "undecoded saved as response.json": lambda d: d["response"].update(form="undecoded"),
    "request not request.json": lambda d: d["request"].update(path="cases/request.yaml"),
    "succeeded without a 200": lambda d: d["exchanges"][1].update(status=204),
    "note on a 401": lambda d: (
        failed_authentication(d),
        d["exchanges"][0].update(note="completed_from_saved_response"),
    ),
    "attempt id without hyphens": lambda d: d.update(attempt_id=ATTEMPT_ID.replace("-", "")),
}


@pytest.mark.parametrize("change", ATTEMPT_CHANGES.values(), ids=ATTEMPT_CHANGES.keys())
def test_attempt_record_rejects(change: Change) -> None:
    rejects(AttemptRecord, changed(attempt_record, change))


def test_start_record_exchanges_carry_no_note() -> None:
    document = start_record()
    document["exchanges"][0]["note"] = "completed_from_saved_response"

    rejects(StartRecord, document)


def demo(document: Document) -> None:
    document["command"]["name"] = "demo"
    document.update(synthetic=True, approval="not_required")


def test_manifest_accepts_the_demo_run() -> None:
    RunManifest.model_validate_json(json.dumps(changed(manifest, demo)))


MANIFEST_CHANGES: dict[str, Change] = {
    "synthetic run approved by option": lambda d: (demo(d), d.update(approval="option")),
    "real run not approved": lambda d: d.update(approval="not_required"),
    "completed with an error": lambda d: d.update(
        error={"code": "internal.unexpected", "message": "x"}
    ),
    "failed without an error": lambda d: d.update(outcome="failed"),
    "logs listed": lambda d: d["artifacts"][0].update(path="logs/trialfolio.jsonl"),
    "a path twice": lambda d: d["artifacts"].append(d["artifacts"][0]),
    "source without its record": lambda d: d["artifacts"][1].update(source=None),
    "record on a derived file": lambda d: d["artifacts"][0].update(
        source=d["artifacts"][1]["source"]
    ),
    "complete despite a reference not snapshotted": lambda d: d["reproducibility"].update(
        status="complete"
    ),
    "assessed": lambda d: d["capabilities"].update(trading_readiness="ready"),
    "partial with another code": lambda d: d.update(
        outcome="partial", error={"code": "provider.auth_failed", "message": "x"}
    ),
    "failed with execution.partial": lambda d: d.update(
        outcome="failed", error={"code": "execution.partial", "message": "x"}
    ),
}


@pytest.mark.parametrize("change", MANIFEST_CHANGES.values(), ids=MANIFEST_CHANGES.keys())
def test_manifest_rejects(change: Change) -> None:
    rejects(RunManifest, changed(manifest, change))


def test_table_columns_are_in_the_documented_order() -> None:
    assert METRICS_COLUMNS == (
        "label",
        "subject",
        "metric_id",
        "source_label",
        "value",
        "unit",
        "source_decimals",
        "availability",
        "unavailable_reason",
        "origin",
        "provenance",
        "period_start",
        "period_end",
        "benchmark",
        "source_artifact",
        "source_location",
    )
    assert SETTINGS_COLUMNS == (
        "label",
        "setting",
        "category",
        "critical",
        "value",
        "unit",
        "interpretation",
        "provenance",
        "inference_rule",
        "original_key",
        "original_value",
        "source_artifact",
        "flags",
    )


def unavailable(document: Document) -> None:
    document.update(
        value=None,
        source_decimals=None,
        availability="unavailable",
        unavailable_reason="blank_in_source",
    )


def coverage_start(document: Document) -> None:
    document.update(
        metric_id="coverage_start",
        source_label=None,
        value="2016-01-04",
        unit="date",
        source_decimals=None,
        origin="calculated",
        provenance="inferred",
        source_location=None,
    )


@pytest.mark.parametrize(
    "change",
    [unavailable, coverage_start, lambda d: d.update(value="-7", source_decimals=0)],
    ids=["unavailable", "coverage date", "whole negative number"],
)
def test_metrics_row_accepts(change: Change) -> None:
    MetricsRow.model_validate_json(json.dumps(changed(metrics_row, change)))


METRICS_CHANGES: dict[str, Change] = {
    "zero for a missing value": lambda d: (unavailable(d), d.update(value="0")),
    "unavailable without a reason": lambda d: (unavailable(d), d.update(unavailable_reason=None)),
    "available with a reason": lambda d: d.update(unavailable_reason="blank_in_source"),
    "padded precision": lambda d: d.update(source_decimals=4),
    "exponent": lambda d: d.update(value="1.23e1"),
    "decimals on a date": lambda d: (coverage_start(d), d.update(source_decimals=0)),
    "calculated with a location": lambda d: (
        coverage_start(d),
        d.update(source_location="results.rows"),
    ),
    "unknown unit": lambda d: d.update(unit="basis_points"),
    "bad label": lambda d: d.update(label="Baseline"),
    "reported without a location": lambda d: d.update(source_location=None),
    "reported without a label": lambda d: d.update(source_label=None),
    "period reversed": lambda d: d.update(period_start="2026-01-01"),
}


@pytest.mark.parametrize("change", METRICS_CHANGES.values(), ids=METRICS_CHANGES.keys())
def test_metrics_row_rejects(change: Change) -> None:
    rejects(MetricsRow, changed(metrics_row, change))


SETTINGS_CHANGES: dict[str, Change] = {
    "empty value": lambda d: d.update(value=""),
    "unknown setting": lambda d: d.update(setting="leverage"),
    "wrong category": lambda d: d.update(category="other", critical=False),
    "not critical": lambda d: d.update(critical=False),
    "decimal not normalized": lambda d: d.update(value="0.250"),
    "key without a value": lambda d: d.update(original_value=None),
    "inferred without a rule": lambda d: d.update(provenance="inferred"),
    "flag twice": lambda d: d.update(flags=["coverage_mismatch", "coverage_mismatch"]),
    "unknown flag": lambda d: d.update(flags=["looks_fine"]),
    "ranking not JSON": lambda d: d.update(
        setting="ranking", category="strategy", unit=None, value="EarnYield"
    ),
    "ranking with wrong types": lambda d: d.update(
        setting="ranking",
        category="strategy",
        unit=None,
        value='{"formula": 5, "lower_is_better": "x"}',
    ),
    "impossible date": lambda d: d.update(
        setting="start_date", category="dates", unit=None, value="2016-13-45"
    ),
    "too many decimals": lambda d: d.update(value="0.123456"),
    "blank": lambda d: d.update(value=" "),
    "not sent but interpreted": lambda d: d.update(
        setting="max_pos_pct", category="strategy", unit=None, value="not_sent"
    ),
}


@pytest.mark.parametrize("change", SETTINGS_CHANGES.values(), ids=SETTINGS_CHANGES.keys())
def test_settings_row_rejects(change: Change) -> None:
    rejects(SettingsRow, changed(settings_row, change))


def failed_run(document: Document) -> None:
    document.update(
        outcome="failed",
        exit_code=3,
        ids={},
        output_dir=None,
        outputs={},
        counts={
            "attempts": 0,
            "provider_requests": 0,
            "metrics_unavailable": 0,
            "warnings": 0,
            "cost": None,
        },
        error={"code": "config.invalid", "message": "screen.yaml isn't valid."},
    )


def license_command(document: Document) -> None:
    document.update(command="license", ids={}, output_dir=None, outputs={}, counts={})


def approval_required(document: Document) -> None:
    failed_run(document)
    document.update(
        exit_code=2,
        ids={"plan_hash": PLAN_HASH, "case_id": CASE_ID},
        error={"code": "plan.approval_required", "message": "Approve with --approve."},
    )


@pytest.mark.parametrize("change", [failed_run, license_command, approval_required])
def test_summary_accepts(change: Change) -> None:
    JsonSummary.model_validate_json(json.dumps(changed(summary, change)))


SUMMARY_CHANGES: dict[str, Change] = {
    "exit code not the error's": lambda d: (failed_run(d), d.update(exit_code=5)),
    "completed with an error": lambda d: d.update(
        error={"code": "internal.unexpected", "message": "x"}
    ),
    "completed with a nonzero exit": lambda d: d.update(exit_code=6),
    "failed without an error": lambda d: d.update(outcome="failed", exit_code=1),
    "partial with another code": lambda d: (failed_run(d), d.update(outcome="partial")),
    "exit code false": lambda d: d.update(exit_code=False),
    "run without counts": lambda d: d.update(counts={}),
    "license with counts": lambda d: (license_command(d), d.update(counts=summary()["counts"])),
    "outputs without a directory": lambda d: d.update(output_dir=None),
    "unknown id": lambda d: d["ids"].update(review_id=ATTEMPT_ID),
    "unknown output role": lambda d: d["outputs"].update(log="logs/x.jsonl"),
    "quota in counts": lambda d: d["counts"].update(quota_remaining=1000),
    "assessed": lambda d: d.update(statistical_validation="passed"),
    "attempt id without hyphens": lambda d: d["ids"].update(attempt_id=ATTEMPT_ID.replace("-", "")),
}


@pytest.mark.parametrize("change", SUMMARY_CHANGES.values(), ids=SUMMARY_CHANGES.keys())
def test_summary_rejects(change: Change) -> None:
    rejects(JsonSummary, changed(summary, change))


ACKNOWLEDGMENT_CHANGES: dict[str, Change] = {
    "an identity field": lambda d: d.update(email="someone@example.invalid"),
    "another method": lambda d: d.update(method="environment"),
    "not in UTC": lambda d: d.update(acknowledged_at="2026-10-02T10:00:00-05:00"),
    "not a license reference": lambda d: d.update(license_id="MIT"),
}


@pytest.mark.parametrize(
    "change", ACKNOWLEDGMENT_CHANGES.values(), ids=ACKNOWLEDGMENT_CHANGES.keys()
)
def test_acknowledgment_holds_only_its_four_fields(change: Change) -> None:
    rejects(AcknowledgmentRecord, changed(acknowledgment, change))
