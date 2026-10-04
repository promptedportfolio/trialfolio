"""The planner builds the plan docs/contracts.md specifies, and its hash identifies it.

Traces to R01-AC11 (an omitted and an explicit FactSet resolve to the same case, which sends no
vendor) and R01-AC25 (the plan hash: files written differently give the same hash; a setting, the
title, or the purpose changes it; a saved plan recomputes to it; a whole-number slippage is sent
as a float, and its body text equals its text in `params`) in release 0.1.0's test pairing. Also
to docs/contracts.md, plans and approval: plan contents, budget and retries, data sent, plan
hashing, and approval, which never trusts a stored `plan_hash`. A run executed through
`Execution`, as `trialfolio run` executes one, over the fake server, saves a `plan.json` that
recomputes to its hash, and its start record, attempt record, and manifest name that hash.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.core.conftest import execute_run
from tests.support import canaries
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from trialfolio.canonical import canonical_json, sha256_hex
from trialfolio.configuration import read_screen_configuration
from trialfolio.contracts.attempt import AttemptRecord, StartRecord
from trialfolio.contracts.manifest import RunManifest
from trialfolio.contracts.plan import Plan
from trialfolio.contracts.screen_configuration import ScreenConfiguration
from trialfolio.errors import TrialFolioError
from trialfolio.planning import (
    VERIFIED_VERSIONS,
    Versions,
    build_plan,
    case_id,
    check_approval,
    plan_hash,
)
from trialfolio.provider import Credentials, DecodedResponse, P123ScreenBacktestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "screen-configs"
RESPONSES = REPO_ROOT / "tests" / "fixtures" / "responses"

VERIFIED = Versions(
    trialfolio="0.1.0",
    p123api=VERIFIED_VERSIONS["p123api"][0],
    requests=VERIFIED_VERSIONS["requests"][0],
    urllib3=VERIFIED_VERSIONS["urllib3"][0],
)


def read_fixture(name: str) -> ScreenConfiguration:
    path = FIXTURES / name
    return read_screen_configuration(path.read_bytes(), path.name)


def plan_for(name: str) -> Plan:
    return build_plan(read_fixture(name), VERIFIED)


def plan_from_text(text: str) -> Plan:
    return build_plan(read_screen_configuration(text.encode(), "screen.yaml"), VERIFIED)


def params_of(plan: Plan) -> dict[str, object]:
    return plan.cases[0].requests[0].params.model_dump(mode="json")


def setting(plan: Plan, name: str) -> dict[str, object]:
    (row,) = (row for row in plan.cases[0].settings if row.setting == name)
    return row.model_dump(mode="json")


# The screen settings for the documented example, as docs/contracts.md's table gives them:
# setting, value, unit, expected provenance, and flags.
EXAMPLE_SETTINGS = [
    ("universe", "SP500", None, "verified", ["not_snapshotted"]),
    ("screen_type", "stock", None, "verified", []),
    ("rules", ["AvgDailyTot(30) > 1000000"], None, "verified", []),
    ("ranking", {"formula": "EarnYield", "lower_is_better": False}, None, "verified", []),
    ("max_holdings", 25, "count", "verified", []),
    ("position_method", "long", None, "verified", []),
    ("benchmark", "SPY", None, "verified", []),
    ("currency", "USD", None, "verified", []),
    ("start_date", "2016-01-01", None, "verified", []),
    ("end_date", "2025-12-31", None, "verified", []),
    ("rebalance_weeks", 4, "weeks", "verified", []),
    ("transaction_price", "open", None, "verified", []),
    ("slippage_percent", "0.25", "percent", "verified", []),
    ("commission", "not_modeled", None, "inferred", []),
    ("pit_method", "complete", None, "verified", []),
    ("data_vendor", "FactSet", None, "inferred", ["inferred_default"]),
    ("precision", 4, None, "verified", []),
    ("risk_stats_period", "monthly", None, "inferred", ["inferred_default"]),
    ("max_pos_pct", "not_sent", None, "unknown", []),
    ("rank_tolerance", "not_sent", None, "unknown", []),
    ("carry_cost", "not_sent", None, "unknown", []),
    ("long_weight", "not_sent", None, "unknown", []),
    ("short_weight", "not_sent", None, "unknown", []),
]


def test_the_plan_holds_every_screen_setting_in_order_with_its_expected_provenance() -> None:
    rows = [row.model_dump(mode="json") for row in plan_for("formula.yaml").cases[0].settings]

    assert [
        (row["setting"], row["value"], row["unit"], row["expected_provenance"], row["flags"])
        for row in rows
    ] == EXAMPLE_SETTINGS
    for row in rows:
        inferred = row["expected_provenance"] == "inferred"
        assert (row["inference_rule"] is not None) == inferred
        assert row["interpretation"] == (
            "not_interpreted" if row["value"] == "not_sent" else "interpreted"
        )
        assert row["critical"] == (row["setting"] not in ("precision", "risk_stats_period"))


def test_the_plan_records_its_versions_budget_retry_policy_and_data_sent() -> None:
    plan = plan_for("formula.yaml").model_dump(mode="json")

    assert plan["schema_version"] == "1.0.0"
    assert plan["trialfolio_version"] == "0.1.0"
    assert plan["canonicalization_version"] == 1
    assert plan["provider_wrapper"] == {"p123api": "3.1.0"}
    assert plan["transport"] == {"requests": "2.34.2", "urllib3": "2.8.0"}
    assert plan["title"] == "Earnings yield with a liquidity floor"
    assert plan["purpose"] == "Reference backtest for the 0.1.0 response layout."
    assert plan["budget"] == {
        "provider_requests": 1,
        "credits_per_request": 5,
        "credits_per_request_source": {
            "title": "API: Screen",
            "url": "https://portfolio123.customerly.help/en/articles/43324-api-screen",
            "checked": "2026-10-01",
        },
        "credits": 5,
        "authentication_calls": 1,
    }
    assert plan["retry_policy"] == {
        "automatic_retries": 0,
        "wrapper_attempts_per_call": 1,
        "exchanges_per_call": 1,
    }
    # The entries in data sent's order, and each one's settings in the screen settings' order,
    # which the hash covers.
    assert [(entry["category"], entry["settings"]) for entry in plan["data_sent"]] == [
        ("credentials", []),
        ("strategy_definition", ["universe", "rules", "ranking"]),
        (
            "backtest_settings",
            [
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
        ),
    ]
    assert {(entry["recipient"], entry["via"]) for entry in plan["data_sent"]} == {
        ("Portfolio123", "p123api")
    }


def test_an_omitted_and_an_explicit_factset_resolve_to_the_same_case_and_send_no_vendor() -> None:
    omitted = plan_for("formula.yaml")
    explicit = plan_for("vendor-factset.yaml")

    for plan in (omitted, explicit):
        assert "vendor" not in json.dumps(params_of(plan)).lower()
        vendor = setting(plan, "data_vendor")
        assert (vendor["value"], vendor["expected_provenance"], vendor["flags"]) == (
            "FactSet",
            "inferred",
            ["inferred_default"],
        )
    assert omitted.cases[0].case_id == explicit.cases[0].case_id


def test_a_ranking_by_name_or_id_is_sent_as_text_or_an_integer_and_not_snapshotted() -> None:
    by_name = plan_for("ranking-name.yaml")
    by_id = plan_for("ranking-id.yaml")

    assert isinstance(by_name.cases[0].requests[0].params.screen.ranking, str)
    assert type(by_id.cases[0].requests[0].params.screen.ranking) is int
    for plan in (by_name, by_id):
        assert setting(plan, "ranking")["flags"] == ["not_snapshotted"]
    assert setting(plan_for("formula.yaml"), "ranking")["flags"] == []


def test_files_written_differently_give_the_same_plan() -> None:
    plans = [
        plan_for(name)
        for name in ("formula.yaml", "written-differently.yaml", "vendor-factset.yaml")
    ]

    assert plans[0] == plans[1] == plans[2]
    assert len({plan.plan_hash for plan in plans}) == 1


def test_the_plan_hash_is_the_hash_of_the_canonical_plan_without_it() -> None:
    plan = plan_for("formula.yaml")
    content = plan.model_dump(mode="json", exclude={"plan_hash"})

    assert plan.plan_hash == "sha256:" + sha256_hex(canonical_json(content))
    rows = [
        {"setting": row.setting, "value": row.model_dump(mode="json")["value"], "unit": row.unit}
        for row in plan.cases[0].settings
    ]
    assert plan.cases[0].case_id == "case-" + sha256_hex(canonical_json(rows))[:16]


def example_text() -> str:
    return (FIXTURES / "formula.yaml").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("old", "new", "changes_case"),
    [
        ("slippage_percent: 0.25", "slippage_percent: 0.3", True),
        ("max_holdings: 25", "max_holdings: 26", True),
        ("end_date: 2025-12-31", "end_date: 2025-12-30", True),
        ("title: Earnings yield with a liquidity floor", "title: Earnings yield", False),
        ("purpose: Reference backtest", "purpose: Another backtest", False),
        ("purpose: Reference backtest for the 0.1.0 response layout.\n", "", False),
    ],
)
def test_a_setting_the_title_or_the_purpose_changes_the_hash(
    old: str, new: str, changes_case: bool
) -> None:
    original = plan_from_text(example_text())
    assert old in example_text()

    changed = plan_from_text(example_text().replace(old, new, 1))

    assert changed.plan_hash != original.plan_hash
    assert (changed.cases[0].case_id != original.cases[0].case_id) == changes_case


def test_a_version_change_changes_the_hash() -> None:
    plan = plan_for("formula.yaml")
    upgraded = plan.model_copy(update={"trialfolio_version": "0.1.1"})

    assert plan_hash(upgraded) != plan.plan_hash


def test_the_plan_hash_is_the_same_in_another_process() -> None:
    # Two hash seeds, so an order taken from a set would show.
    script = (
        "from tests.core.test_plan import plan_for\nprint(plan_for('formula.yaml').plan_hash)\n"
    )
    hashes = {
        subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
            env=os.environ | {"PYTHONHASHSEED": seed},
        ).stdout.strip()
        for seed in ("1", "2")
    }

    assert hashes == {plan_for("formula.yaml").plan_hash}


@pytest.mark.parametrize("indent", [None, 2])
def test_a_saved_plan_recomputes_to_its_hash(indent: int | None) -> None:
    plan = plan_for("title-non-ascii.yaml")
    saved = Plan.model_validate_json(plan.model_dump_json(indent=indent))

    assert plan_hash(saved) == saved.plan_hash == plan.plan_hash
    assert case_id(saved.cases[0].settings) == saved.cases[0].case_id


@pytest.mark.parametrize("fixture", ["formula.yaml", "slippage-whole.yaml", "title-non-ascii.yaml"])
def test_a_run_saves_a_plan_that_recomputes_to_its_hash_and_its_records_name_it(
    tmp_path: Path, fixture: str
) -> None:
    out = tmp_path / "out"
    plan = execute_run(
        (FIXTURES / fixture).read_bytes(), out, (RESPONSES / "complete.json").read_bytes()
    )

    saved = Plan.model_validate_json((out / "plan.json").read_bytes())
    assert plan_hash(saved) == saved.plan_hash == plan.plan_hash
    (attempt,) = (out / "cases" / plan.cases[0].case_id / "attempts").iterdir()
    start = StartRecord.model_validate_json((attempt / "started.json").read_bytes())
    record = AttemptRecord.model_validate_json((attempt / "attempt.json").read_bytes())
    manifest = RunManifest.model_validate_json((out / "manifest.json").read_bytes())
    assert start.plan_hash == record.plan_hash == manifest.plan_hash == plan.plan_hash


def test_a_saved_plan_whose_contents_changed_doesnt_recompute_to_its_hash() -> None:
    plan = plan_for("formula.yaml")
    document = plan.model_dump(mode="json")
    document["title"] = "Another title"

    edited = Plan.model_validate_json(json.dumps(document))

    assert plan_hash(edited) != edited.plan_hash


def test_a_non_ascii_title_hashes_as_its_utf8() -> None:
    plan = plan_for("title-non-ascii.yaml")
    canonical = canonical_json(plan.model_dump(mode="json", exclude={"plan_hash"}))

    assert "Café".encode() in canonical
    assert b"\\u00e9" not in canonical
    assert plan.plan_hash == "sha256:" + sha256_hex(canonical)


def test_a_whole_number_slippage_is_planned_and_sent_as_a_float() -> None:
    whole = plan_for("slippage-whole.yaml")
    params = whole.cases[0].requests[0].params

    assert setting(whole, "slippage_percent")["value"] == "1"
    assert type(params.slippage) is float
    assert '"slippage": 1.0' in json.dumps(params_of(whole))
    assert b'"slippage":1,' in canonical_json(whole.model_dump(mode="json"))


@pytest.mark.parametrize(
    ("fixture", "text"), [("slippage-whole.yaml", b"1.0"), ("formula.yaml", b"0.25")]
)
def test_the_request_body_writes_slippage_as_params_does(fixture: str, text: bytes) -> None:
    params = params_of(plan_for(fixture))
    assert b'"slippage": ' + text in json.dumps(params).encode()
    server = FakePortfolio123()
    server.reply("/auth", Reply(200, canaries.TOKEN.encode()))
    server.reply("/screen/backtest", Reply(200, b"{}"))
    try:
        with P123ScreenBacktestClient(
            Credentials(canaries.API_ID, canaries.API_KEY), endpoint=server.endpoint
        ) as client:
            client.authenticate()
            assert isinstance(client.screen_backtest(params), DecodedResponse)
    finally:
        server.close()

    body = server.received[-1].body
    assert b'"slippage": ' + text in body
    assert json.loads(body) == params


def test_a_version_no_release_verified_isnt_planned() -> None:
    configuration = read_fixture("formula.yaml")

    with pytest.raises(TrialFolioError) as raised:
        build_plan(configuration, Versions("0.1.0", "3.2.0", "2.34.2", "2.8.0"))

    assert raised.value.code == "environment.unsupported"
    assert "p123api 3.1.0, requests 2.34.2, and urllib3 2.8.0" in raised.value.message
    assert "The installed p123api is 3.2.0." in raised.value.message


def test_approval_takes_exactly_the_recomputed_hash() -> None:
    plan = plan_for("formula.yaml")

    assert check_approval(plan, plan.plan_hash) == plan.plan_hash


@pytest.mark.parametrize(
    "given",
    [
        None,
        "",
        "abbreviated",
        "uppercase",
        "without prefix",
        "trailing space",
        "another plan",
    ],
)
def test_approval_refuses_anything_but_the_full_hash(given: str | None) -> None:
    plan = plan_for("formula.yaml")
    variants: dict[str | None, str | None] = {
        None: None,
        "": "",
        "abbreviated": plan.plan_hash[:20],
        "uppercase": "sha256:" + plan.plan_hash.removeprefix("sha256:").upper(),
        "without prefix": plan.plan_hash.removeprefix("sha256:"),
        "trailing space": plan.plan_hash + " ",
        "another plan": plan_for("slippage-whole.yaml").plan_hash,
    }

    with pytest.raises(TrialFolioError) as raised:
        check_approval(plan, variants[given])

    assert raised.value.code == "plan.approval_required"
    assert plan.plan_hash in raised.value.message


def test_approval_never_trusts_a_stored_plan_hash() -> None:
    plan = plan_for("formula.yaml")
    forged_hash = plan_for("slippage-whole.yaml").plan_hash
    forged = plan.model_copy(update={"plan_hash": forged_hash})

    with pytest.raises(TrialFolioError) as raised:
        check_approval(forged, forged_hash)

    assert raised.value.code == "plan.approval_required"
    assert check_approval(forged, plan.plan_hash) == plan.plan_hash
