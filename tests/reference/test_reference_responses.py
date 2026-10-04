"""Conformance against the local reference responses: each response Portfolio123 returned to
R01-T01's and R01-T05's live calls normalizes without error, with all 20 metrics available, no
value with more than 4 decimal places, coverage equal to the requested dates, and the settings
rows as documented.

Traces to release 0.1.0's verification commands, `TRIALFOLIO_REFERENCE_DIR=reference uv run
pytest -m reference`. The responses are the owner's, in the git-ignored `payloads/` folders
(REQ-11), so the marker keeps this module out of the default suite. Without the variable, or
without a response, each test skips and says why.

Each response's screen configuration is built from the request beside it, by the documented
mapping (docs/contracts.md, screen configuration) in reverse, and planning it must give that
request back exactly. For R01-T01, that's the committed `request.json`, the request that
succeeded; for the weekly check, the committed `request-weekly.json`; for the ranking checks, the
exact requests in `payloads/`, never the committed placeholders. Then `trialfolio run`, through the
CLI's entry function in the test process, sends the request to the fake server, which answers
with the reference response. So the response is saved as `response.json` saves any response, and
normalized from there.

Portfolio123's values, and the ranking system's name and ID, are account information. No
assertion here shows one: each names only the metric or setting that failed. The run is written in
a temporary directory that's removed afterwards, never under the reference directory.
"""

import json
import os
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from tests.interface.conftest import AUTHENTICATED, Cli
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from trialfolio.configuration import read_screen_configuration
from trialfolio.planning import build_plan, installed_versions
from trialfolio.tables import read_metrics_csv, read_settings_csv

pytestmark = pytest.mark.reference

REFERENCE_DIR_VARIABLE = "TRIALFOLIO_REFERENCE_DIR"


@dataclass(frozen=True)
class ReferenceCall:
    """One live call's request and response, by their paths under the reference directory."""

    request: str
    response: str


CALLS = {
    "R01-T01": ReferenceCall(
        "p123api-screen-backtest/request.json",
        "p123api-screen-backtest/payloads/response.json",
    ),
    "R01-T05 weekly": ReferenceCall(
        "p123api-screen-backtest-values/request-weekly.json",
        "p123api-screen-backtest-values/payloads/response-weekly.json",
    ),
    "R01-T05 ranking by name": ReferenceCall(
        "p123api-screen-backtest-values/payloads/request-ranking-name.json",
        "p123api-screen-backtest-values/payloads/response-ranking-name.json",
    ),
    "R01-T05 ranking by ID": ReferenceCall(
        "p123api-screen-backtest-values/payloads/request-ranking-id.json",
        "p123api-screen-backtest-values/payloads/response-ranking-id.json",
    ),
}

# The "Sent as" column of docs/contracts.md's screen configuration, read backwards.
REBALANCE_WEEKS = {"Every Week": 1, "Every 4 Weeks": 4}
TRANSACTION_PRICES = {1: "open"}
PIT_METHODS = {"Complete": "complete"}
FIXED = {"type": "stock", "method": "long", "currency": "USD"}
"""The values Trial Folio sends on every request, which a configuration can't change."""

# `metrics.csv`'s rows, in order, as `p123api-screen-backtest` version 1 gives them.
DOCUMENTED_METRICS = (
    ("strategy", "coverage_start"),
    ("strategy", "coverage_end"),
    ("strategy", "coverage_periods"),
    *(
        ("strategy", metric)
        for metric in (
            "total_return",
            "annualized_return",
            "max_drawdown",
            "standard_deviation",
            "sharpe_ratio",
            "sortino_ratio",
            "correlation",
            "r_squared",
            "beta",
            "alpha",
            "risk_samples",
        )
    ),
    *(
        ("benchmark", metric)
        for metric in (
            "total_return",
            "annualized_return",
            "max_drawdown",
            "standard_deviation",
            "sharpe_ratio",
            "sortino_ratio",
        )
    ),
)
PRECISION = 4
"""The decimal places every reference request asked for, and the most any value may have."""


@pytest.fixture
def reference_dir() -> Path:
    given = os.environ.get(REFERENCE_DIR_VARIABLE, "")
    if not given:
        pytest.skip(
            f"{REFERENCE_DIR_VARIABLE} isn't set: these tests read the owner's local reference "
            f"responses, as `{REFERENCE_DIR_VARIABLE}=reference uv run pytest -m reference`"
        )
    directory = Path(given).resolve()
    if not directory.is_dir():
        pytest.skip(f"{REFERENCE_DIR_VARIABLE} names no directory: {given}")
    return directory


@pytest.fixture
def server() -> Iterator[FakePortfolio123]:
    fake = FakePortfolio123()
    yield fake
    fake.close()


def quoted(text: object) -> str:
    """`text` as a single-quoted YAML scalar, which processes no escapes."""
    # Checked into a name of its own, so a failure doesn't show the text.
    printable = isinstance(text, str) and text.isprintable()
    assert printable, "a request value isn't printable text"
    return "'" + str(text).replace("'", "''") + "'"


def screen_configuration(request: Mapping[str, Any], title: str) -> str:
    """The screen configuration that sends `request`, by the documented mapping in reverse."""
    screen = request["screen"]
    assert {name: screen[name] for name in FIXED} == FIXED
    ranking = screen["ranking"]
    if isinstance(ranking, dict):
        assert set(ranking) == {"formula", "lowerIsBetter"}
        assert isinstance(ranking["lowerIsBetter"], bool)
        lower_is_better = "true" if ranking["lowerIsBetter"] else "false"
        ranking_lines = [
            f"  formula: {quoted(ranking['formula'])}",
            f"  lower_is_better: {lower_is_better}",
        ]
    elif isinstance(ranking, str):
        ranking_lines = [f"  name: {quoted(ranking)}"]
    else:
        assert type(ranking) is int
        ranking_lines = [f"  id: {ranking}"]
    rules = screen["rules"]
    assert all(set(rule) == {"formula"} for rule in rules)
    slippage = request["slippage"]
    assert type(slippage) is float
    lines = [
        "kind: screen",
        "schema_version: 1.0.0",
        f"title: {quoted(title)}",
        f"universe: {quoted(screen['universe'])}",
        "rules:",
        *(f"  - {quoted(rule['formula'])}" for rule in rules),
        "ranking:",
        *ranking_lines,
        f"max_holdings: {screen['maxNumHoldings']}",
        f"benchmark: {quoted(screen['benchmark'])}",
        f"start_date: {request['startDt']}",
        f"end_date: {request['endDt']}",
        f"rebalance_weeks: {REBALANCE_WEEKS[request['rebalFreq']]}",
        f"transaction_price: {TRANSACTION_PRICES[request['transPrice']]}",
        # A float's shortest round-trip form; the decimals rules keep it in plain notation.
        f"slippage_percent: {slippage!r}",
        f"pit_method: {PIT_METHODS[request['pitMethod']]}",
        f"precision: {request['precision']}",
    ]
    return "".join(f"{line}\n" for line in lines)


def json_text(value: object) -> str:
    """A list or a ranking as `settings.csv` writes it."""
    return json.dumps(value, ensure_ascii=False)


def documented_settings(request: Mapping[str, Any]) -> tuple[tuple[object, ...], ...]:
    """`settings.csv`'s rows for `request`, as docs/contracts.md's screen settings give them:
    setting, category, critical, value, unit, interpretation, provenance, and flags."""
    screen = request["screen"]
    ranking = screen["ranking"]
    if isinstance(ranking, dict):
        ranking_value = json_text(
            {"formula": ranking["formula"], "lower_is_better": ranking["lowerIsBetter"]}
        )
        ranking_flags: tuple[str, ...] = ()
    else:
        ranking_value = json_text({"name" if isinstance(ranking, str) else "id": ranking})
        ranking_flags = ("not_snapshotted",)
    slippage = format(Decimal(repr(request["slippage"])).normalize(), "f")
    rows: tuple[tuple[str, str, str, str | None, str, tuple[str, ...]], ...] = (
        ("universe", "universe", screen["universe"], None, "verified", ("not_snapshotted",)),
        ("screen_type", "universe", "stock", None, "verified", ()),
        ("rules", "strategy", json_text([r["formula"] for r in screen["rules"]]), None,
         "verified", ()),
        ("ranking", "strategy", ranking_value, None, "verified", ranking_flags),
        ("max_holdings", "strategy", str(screen["maxNumHoldings"]), "count", "verified", ()),
        ("position_method", "strategy", "long", None, "verified", ()),
        ("benchmark", "benchmark", screen["benchmark"], None, "verified", ()),
        ("currency", "currency", "USD", None, "verified", ()),
        ("start_date", "dates", request["startDt"], None, "verified", ()),
        ("end_date", "dates", request["endDt"], None, "verified", ()),
        ("rebalance_weeks", "execution", str(REBALANCE_WEEKS[request["rebalFreq"]]), "weeks",
         "verified", ()),
        ("transaction_price", "execution", "open", None, "verified", ()),
        ("slippage_percent", "costs", slippage, "percent", "verified", ()),
        ("commission", "costs", "not_modeled", None, "inferred", ()),
        ("pit_method", "data_source", "complete", None, "verified", ()),
        ("data_vendor", "data_source", "FactSet", None, "inferred", ("inferred_default",)),
        ("precision", "other", str(request["precision"]), None, "verified", ()),
        ("risk_stats_period", "other", "monthly", None, "inferred", ("inferred_default",)),
        ("max_pos_pct", "strategy", "not_sent", None, "unknown", ()),
        ("rank_tolerance", "strategy", "not_sent", None, "unknown", ()),
        ("carry_cost", "costs", "not_sent", None, "unknown", ()),
        ("long_weight", "strategy", "not_sent", None, "unknown", ()),
        ("short_weight", "strategy", "not_sent", None, "unknown", ()),
    )  # fmt: skip
    # Every category but `other` is critical, and only the unsent parameters aren't interpreted.
    return tuple(
        (
            setting,
            category,
            category != "other",
            value,
            unit,
            "not_interpreted" if provenance == "unknown" else "interpreted",
            provenance,
            flags,
        )
        for setting, category, value, unit, provenance, flags in rows
    )


def same_json(first: object, second: object) -> bool:
    """Whether two JSON values are equal as JSON text, so a float and an integer differ."""
    return json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


@pytest.mark.parametrize("call", CALLS.values(), ids=CALLS.keys())
def test_a_reference_response_normalizes_as_documented(
    call: ReferenceCall,
    reference_dir: Path,
    server: FakePortfolio123,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_path = reference_dir / call.request
    response_path = reference_dir / call.response
    for path in (request_path, response_path):
        if not path.is_file():
            pytest.skip(f"no local reference file at {path.relative_to(reference_dir)}")
    request: dict[str, Any] = json.loads(request_path.read_bytes())

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        configuration_path = root / "screen.yaml"
        configuration_path.write_text(
            screen_configuration(request, "Reference conformance"), encoding="utf-8"
        )
        configuration = read_screen_configuration(
            configuration_path.read_bytes(), str(configuration_path)
        )
        plan = build_plan(configuration, installed_versions())
        (planned,) = plan.cases[0].requests
        round_trip = same_json(planned.params.model_dump(mode="json"), request)
        assert round_trip, "the configuration doesn't plan the reference request"

        cli = Cli(monkeypatch, root, server)
        cli.ready()
        server.reply("/auth", AUTHENTICATED)
        server.reply("/screen/backtest", Reply(200, response_path.read_bytes()))
        out = root / "run"
        outcome = cli(
            "run", configuration_path, "--out", out, "--approve", plan.plan_hash, "--json"
        )

        # Only the error code: a message could hold a value.
        error = outcome.summary["error"]
        code = error["code"] if isinstance(error, dict) else None
        exit_code = outcome.exit_code
        assert exit_code == 0, code
        sends = [r for r in server.received if r.path == "/screen/backtest"]
        assert len(sends) == 1
        sent = same_json(json.loads(sends[0].body), request)
        assert sent, "the request sent isn't the reference request"

        metrics = read_metrics_csv((out / "normalized/metrics.csv").read_bytes(), "metrics.csv")
        settings = read_settings_csv((out / "normalized/settings.csv").read_bytes(), "settings.csv")

    assert tuple((row.subject, row.metric_id) for row in metrics) == DOCUMENTED_METRICS
    unavailable = [f"{r.subject} {r.metric_id}" for r in metrics if r.availability != "available"]
    assert not unavailable
    too_precise = [
        f"{row.subject} {row.metric_id}"
        for row in metrics
        if len((row.value or "").partition(".")[2]) > PRECISION
        or (row.source_decimals or 0) > PRECISION
    ]
    assert not too_precise
    rows = {row.metric_id: row for row in metrics if row.subject == "strategy"}
    covered = (rows["coverage_start"].value, rows["coverage_end"].value) == (
        request["startDt"],
        request["endDt"],
    )
    assert covered, "the coverage differs from the requested dates"
    assert int(rows["coverage_periods"].value or "0") > 0

    observed = tuple(
        (
            row.setting,
            row.category,
            row.critical,
            row.value,
            row.unit,
            row.interpretation,
            row.provenance,
            row.flags,
        )
        for row in settings
    )
    expected = documented_settings(request)
    assert [row[0] for row in observed] == [row[0] for row in expected]
    differing = [ours[0] for ours, documented in zip(observed, expected) if ours != documented]
    assert not differing
    case_id = plan.cases[0].case_id
    assert all(row.label == case_id for row in (*metrics, *settings))
    # Only the inferred rows cite a rule.
    cited = [row.setting for row in settings if row.inference_rule is not None]
    assert cited == [row.setting for row in settings if row.provenance == "inferred"]
