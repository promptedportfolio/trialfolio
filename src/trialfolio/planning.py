"""Plans and approval, the core's side (docs/contracts.md, plans and approval).

The core builds plans and checks approvals, and never prompts. `trialfolio.approval` is the
CLI's side: it shows the plan and obtains the approved hash.

- `installed_versions` reads the versions a plan records, and refuses an environment no release
  has verified, with `environment.unsupported`.
- `build_plan` resolves a screen configuration into a plan 1.0.0, with its `case_id` and
  `plan_hash`. Nothing in a plan varies between invocations: it holds no timestamps, output
  directory, file paths, attempt IDs, credentials, or account information.
- `plan_hash` recomputes a plan's hash from its contents, never from its stored `plan_hash`, and
  `check_approval` passes only exactly that hash.
- `build_snapshot_plan` builds a ranking snapshot configuration's plan (release 0.4.0; ranking
  snapshot output): the system it names, its one `rank_get`, the budget, and the data sent.

An experiment's plan compiler and revision rules (docs/contracts.md, experiment plans and
revisions):

- `build_experiment_plan` compiles an experiment configuration into a plan 1.1.0: the baseline's
  case, then a case for each variant, the default included, in the order of cases.
- `plan_revision` builds an experiment's plan again for a run into its own output directory, and
  gives the revision of its current plan, with what changed, or None when the configuration and
  the versions give the current plan, which the run resumes. `plan_changes` gives what a
  revision changed, which the executor records when it's given the revision's plan.
- `first_experiment_record` and `revised_experiment_record` give the `experiment.json` of a
  plan: the experiment as the plan declares it, its retired cases, and the history of its plans.

Release 0.4.0's plans with a ranking definition (docs/contracts.md, plans with a ranking
definition), which `trialfolio run` builds once its path for them is built (R04-T10 and R04-T12).
Each takes what 0.4.0's configuration readers read, the definition included, so it reads no file:

- `build_plan_v1_1` builds a screen's plan: 1.2.0 when its ranking is a definition, with the
  case's `rank_update` and backtest, its weight rows, and `ranking_source`, and 1.0.0 otherwise,
  as `build_plan` builds it.
- `build_experiment_plan_v1_1` compiles an experiment's: 1.3.0 when its baseline's ranking is a
  definition, each case writing its definition, the baseline's or its ranking variant's, and
  1.1.0 otherwise, as `build_experiment_plan` compiles it, whichever version the file is.
- `plan_revision_v1_1`, `plan_changes_v1_1`, and `retired_cases_v1_1` revise an experiment's
  plan 1.1.0 or 1.3.0 by 0.3.0's rules, so a changed definition or ranking method is a changed
  setting, and a plan 1.1.0 can be revised into a 1.3.0, or back; and `first_experiment_record_v1_1`
  and `revised_experiment_record_v1_1` give its `experiment.json`, 1.1.0 once a plan of the
  experiment is 1.3.0, and 1.0.0 otherwise.

The plans' models check the consistency of what these build, a ranking variant's definition
included.
"""

import importlib
import importlib.metadata
import importlib.util
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType, ModuleType
from typing import Final, Literal, cast

from trialfolio.canonical import CANONICALIZATION_VERSION, canonical_json, sha256_hex
from trialfolio.configuration import ExperimentConfigurationRead, ScreenConfigurationRead
from trialfolio.contracts.common import (
    BASELINE_CASE_KEY,
    CRITICAL_CATEGORIES,
    RANKING_METHOD_NUMBERS,
    Approval,
    TransportVersions,
    WrapperVersions,
)
from trialfolio.contracts.experiment_configuration import (
    ConfiguredVariant,
    ConfiguredVariantV1_1,
    ExperimentConfiguration,
    ExperimentConfigurationV1_1,
    HoldingsVariant,
    RebalanceVariant,
    RuleVariant,
    SlippageVariant,
    configured_variants,
    configured_variants_v1_1,
)
from trialfolio.contracts.experiment_plan import (
    DeclaredPriorResearch,
    ExperimentPlanCase,
    ExperimentPlanCaseV1_3,
    PlanBudgetV1_1,
    PlanBudgetV1_3,
    PlanV1_1,
    PlanV1_3,
    PlanVariant,
    PlanVariantV1_3,
    WeightChange,
)
from trialfolio.contracts.experiment_record import (
    REVISED_PARTS,
    REVISED_PARTS_V1_1,
    VERSIONED_PACKAGES,
    CaseChange,
    ExperimentRecord,
    ExperimentRecordV1_1,
    PlanChanges,
    PlanChangesV1_1,
    PlanEntry,
    PlanEntryV1_1,
    RecordedCase,
    RecordedCaseV1_1,
    RetiredCase,
    RetiredCaseV1_1,
    RevisedPartV1_1,
    VersionChange,
    VersionedPackage,
)
from trialfolio.contracts.plan import (
    CREDITS_PER_REQUEST,
    CREDITS_PER_REQUEST_SOURCE,
    DATA_SENT_SETTINGS,
    DATA_SENT_SETTINGS_V1_2,
    Budget,
    DataSent,
    DataSentV1_2,
    OperationCost,
    Plan,
    PlanBudgetV1_2,
    PlanCase,
    PlanCaseV1_2,
    PlanFlag,
    PlanRequest,
    PlanSetting,
    PlanSettingV1_2,
    PlanV1_2,
    RankingSource,
    RankUpdateRequest,
    RetryPolicy,
    SettingValue,
    SettingValueV1_2,
    ranking_credits,
    screen_backtest_params,
)
from trialfolio.contracts.ranking_snapshot import (
    RANK_GET_COST_SOURCE,
    SNAPSHOT_BUDGET,
    RankGetParams,
    RankGetRequest,
    RankingSnapshotPlan,
    SnapshotDataSent,
)
from trialfolio.contracts.ranking_snapshot_configuration import RankingSnapshotConfiguration
from trialfolio.contracts.screen_configuration import (
    DefinitionRanking,
    IdRanking,
    NameRanking,
    Ranking,
    RankingV1_1,
    ScreenConfiguration,
    ScreenConfigurationV1_1,
    ScreenFields,
    ScreenFieldsV1_1,
    SnapshotRanking,
)
from trialfolio.contracts.screen_settings import (
    RANKING_WEIGHT,
    SCREEN_SETTINGS,
    DefinitionRankingSetting,
    ScreenSetting,
)
from trialfolio.errors import TrialFolioError
from trialfolio.ranking_definitions import RankingCase, RankingDefinition
from trialfolio.snapshots import SnapshotRead

type ProviderPackage = Literal["p123api", "requests", "urllib3"]

VERIFIED_VERSIONS: Final[Mapping[ProviderPackage, tuple[str, ...]]] = MappingProxyType(
    {"p123api": ("3.1.0",), "requests": ("2.34.2",), "urllib3": ("2.8.0",)}
)
"""The versions of `p123api`, `requests`, and `urllib3` that a release has verified, which are
the only ones Trial Folio plans with. The package pins each one exactly (plan contents)."""


@dataclass(frozen=True)
class Versions:
    """The versions a plan records: Trial Folio's own, and those of the packages that will send
    its requests."""

    trialfolio: str
    p123api: str
    requests: str
    urllib3: str


def _verified_list() -> str:
    names = [f"{name} {' or '.join(found)}" for name, found in VERIFIED_VERSIONS.items()]
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def _unsupported(problem: str, remedy: str | None = None) -> TrialFolioError:
    if remedy is None:
        remedy = (
            "Reinstall Trial Folio, whose package pins those versions exactly, for example in a "
            "new virtual environment. If you run it from a copy of its repository, run uv sync "
            "there instead."
        )
    return TrialFolioError(
        "environment.unsupported",
        f"Trial Folio plans only with the versions of p123api, requests, and urllib3 that a "
        f"release has verified: {_verified_list()}. {problem} Nothing was sent, and no output "
        f"was created. {remedy}",
    )


def _metadata_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        raise _unsupported(f"{name} isn't installed.") from None


def _imported(name: str) -> ModuleType:
    # Imported only once their metadata shows a verified version, so a missing package is
    # reported as one, never as an ImportError.
    try:
        return importlib.import_module(name)
    except ImportError:
        raise _unsupported(
            f"{name} is installed, but it can't be imported: its files, or a package it needs, "
            "are missing or broken."
        ) from None


def _require_verified(versions: Versions) -> None:
    for name, verified in VERIFIED_VERSIONS.items():
        installed: str = getattr(versions, name)
        if installed not in verified:
            raise _unsupported(f"The installed {name} is {installed}.")


def _simplejson_importable() -> bool:
    try:
        return importlib.util.find_spec("simplejson") is not None
    except (ImportError, ValueError):
        # A module imported without a spec, for example: it's importable.
        return True


def installed_versions() -> Versions:
    """Reads the installed versions from package metadata (plan contents).

    Raises `TrialFolioError` with `environment.unsupported` when `p123api`, `requests`, or
    `urllib3` is missing, isn't a verified version, or can't be imported; when the imported `requests` or `urllib3` reports a `__version__` other than its
    metadata's, as a stale `.dist-info` would; or when `requests` would write request bodies with
    `simplejson` rather than the standard library's `json`, which happens whenever `simplejson` is
    importable.
    """
    versions = Versions(
        trialfolio=_metadata_version("trialfolio"),
        p123api=_metadata_version("p123api"),
        requests=_metadata_version("requests"),
        urllib3=_metadata_version("urllib3"),
    )
    _require_verified(versions)
    # urllib3 first: requests imports it, so a broken urllib3 is named as itself.
    for name in ("urllib3", "requests"):
        reported: object = getattr(_imported(name), "__version__", None)
        if reported != getattr(versions, name):
            raise _unsupported(
                f"The imported {name} reports another version than its package metadata, "
                f"{getattr(versions, name)}, so other code may be installed under its name."
            )
    # requests.compat chooses the module requests writes bodies with; it doesn't export the name.
    body_writer: object = getattr(_imported("requests.compat"), "json", None)
    if body_writer is not json or _simplejson_importable():
        raise _unsupported(
            "simplejson is importable here, so requests would write request bodies with it "
            "instead of Python's json, and Trial Folio's rules for decimals are verified only "
            "with json.",
            "Uninstall simplejson from this environment, or run Trial Folio in its own virtual "
            "environment.",
        )
    # Last, because it imports requests and urllib3: a failure here is p123api's own.
    _imported("p123api")
    return versions


BUDGET: Final = Budget(
    provider_requests=1,
    credits_per_request=CREDITS_PER_REQUEST,
    credits_per_request_source=CREDITS_PER_REQUEST_SOURCE,
    credits=CREDITS_PER_REQUEST,
    authentication_calls=1,
)
"""A 1.0.0 plan's budget: one request, sent at most once, and one authentication call."""

RETRY_POLICY: Final = RetryPolicy(
    automatic_retries=0, wrapper_attempts_per_call=1, exchanges_per_call=1
)

DATA_SENT: Final = tuple(
    DataSent(
        category=category,
        recipient="Portfolio123",
        via="p123api",
        # In the screen settings' order, never a set's, which varies between processes.
        settings=tuple(setting.name for setting in SCREEN_SETTINGS if setting.name in carried),
    )
    for category, carried in DATA_SENT_SETTINGS.items()
)
"""The three categories of data that leave the machine, in the order data sent lists them."""

RANKING_COSTS: Final = (
    # The Rank page documents rank_update's cost beside rank_get's, and was checked for both.
    OperationCost(operation="rank_update", credits_per_request=1, source=RANK_GET_COST_SOURCE),
    OperationCost(
        operation="screen_backtest",
        credits_per_request=CREDITS_PER_REQUEST,
        source=CREDITS_PER_REQUEST_SOURCE,
    ),
)
"""The documented cost of each operation a plan with a ranking definition sends, `rank_update`
and then the backtest, with the one date each source was checked, which the plan hash covers
(plans with a ranking definition)."""

_SETTINGS_WITH_WEIGHTS: Final = tuple(
    name
    for setting in SCREEN_SETTINGS
    for name in (
        (setting.name, RANKING_WEIGHT.name) if setting.name == "ranking" else (setting.name,)
    )
)
"""The screen settings' names, with the weight rows' right after `ranking`, as they come."""

DATA_SENT_V1_2: Final = tuple(
    DataSentV1_2(
        category=category,
        recipient="Portfolio123",
        via="p123api",
        settings=tuple(name for name in _SETTINGS_WITH_WEIGHTS if name in carried),
    )
    for category, carried in DATA_SENT_SETTINGS_V1_2.items()
)
"""The data sent of a plan with a ranking definition: 1.0.0's, with each `rank_update`'s weights
among the strategy's definition."""


def _screen_values(
    configuration: ScreenFields | ScreenFieldsV1_1,
) -> dict[str, int | str | tuple[str, ...]]:
    """The settings the configuration gives but its ranking, in their JSON types as a plan holds
    them: dates as `YYYY-MM-DD`, and decimals as normalized text."""
    return {
        "universe": configuration.universe,
        "rules": configuration.rules,
        "max_holdings": configuration.max_holdings,
        "benchmark": configuration.benchmark,
        "start_date": configuration.start_date.isoformat(),
        "end_date": configuration.end_date.isoformat(),
        "rebalance_weeks": configuration.rebalance_weeks,
        "transaction_price": configuration.transaction_price,
        # The model normalized it, so its text is the normalized form, in plain notation.
        "slippage_percent": str(configuration.slippage_percent),
        "pit_method": configuration.pit_method,
        "precision": configuration.precision,
    }


def _ranking_form(ranking: RankingV1_1) -> Ranking:
    """A ranking by formula, name, or ID, which a plan 1.0.0 or 1.1.0 holds as it's configured.
    Raises `TypeError` for a definition or a snapshot, which a plan holds by its definition."""
    if isinstance(ranking, DefinitionRanking | SnapshotRanking):
        raise TypeError(
            "a ranking given as a definition is planned with the definition read with it, and a "
            "snapshot with its definition and its record"
        )
    return ranking


def _configured_values(configuration: ScreenFields | ScreenFieldsV1_1) -> dict[str, SettingValue]:
    """The settings the configuration gives, in their JSON types as a plan holds them, its
    ranking by formula, name, or ID."""
    return {**_screen_values(configuration), "ranking": _ranking_form(configuration.ranking)}


def _plan_setting(setting: ScreenSetting, value: SettingValue) -> PlanSetting:
    # A row's own flags are known before execution; the model checks they're its documented ones.
    flags = cast("tuple[PlanFlag, ...]", setting.flags)
    if isinstance(value, NameRanking | IdRanking):
        flags = (*flags, "not_snapshotted")
    return PlanSetting(
        setting=setting.name,
        category=setting.category,
        critical=setting.category in CRITICAL_CATEGORIES,
        value=value,
        unit=setting.unit,
        interpretation=setting.interpretation,
        expected_provenance=setting.provenance,
        inference_rule=setting.inference_rule,
        flags=flags,
    )


def resolve_settings(configuration: ScreenFields | ScreenFieldsV1_1) -> tuple[PlanSetting, ...]:
    """Every screen setting, in order, resolved from the configuration, or from an experiment's
    case (settings in the plan), whose ranking is by formula, name, or ID.

    A setting the configuration doesn't give takes the one value its row allows: a fixed value,
    an inferred default, `not_modeled`, or `not_sent`. So `data_vendor` is FactSet, inferred,
    whether the configuration omits it or gives it, and how the file is written leaves no trace.
    Raises `TypeError` for a ranking given as a definition or a snapshot.
    """
    configured = _configured_values(configuration)
    resolved: list[PlanSetting] = []
    for setting in SCREEN_SETTINGS:
        value = configured.get(setting.name)
        if value is None:
            (value,) = setting.allowed
        resolved.append(_plan_setting(setting, value))
    return tuple(resolved)


def case_id(settings: Sequence[PlanSetting] | Sequence[PlanSettingV1_2]) -> str:
    """`case-` and the first 16 hex digits of the SHA-256 of the canonical form of `settings`,
    each row reduced to its `setting`, `value`, and `unit`, and a weight row's to its `node` too,
    which tells the weight rows apart, so a case without a ranking definition keeps the
    `case_id` 0.3.0 gave it (plan hashing)."""
    rows = [
        row.model_dump(
            mode="json",
            include={"setting", "node", "value", "unit"}
            if row.setting == RANKING_WEIGHT.name
            else {"setting", "value", "unit"},
        )
        for row in settings
    ]
    return "case-" + sha256_hex(canonical_json(rows))[:16]


type AnyPlan = Plan | PlanV1_1 | PlanV1_2 | PlanV1_3 | RankingSnapshotPlan
"""A screen's or an experiment's plan, of any version, or a ranking snapshot's."""


def plan_hash(plan: AnyPlan) -> str:
    """`sha256:` and the SHA-256 of the canonical form of `plan` without its `plan_hash` field
    (plan hashing). It's computed from the contents, so a stored `plan_hash` is never trusted."""
    content = plan.model_dump(mode="json", exclude={"plan_hash"})
    return "sha256:" + sha256_hex(canonical_json(content))


_UNHASHED: Final = "sha256:" + "0" * 64
"""A placeholder, replaced by the plan's hash before the plan leaves the function that builds
it."""


def _hashed[P: (Plan, PlanV1_1, PlanV1_2, PlanV1_3, RankingSnapshotPlan)](draft: P) -> P:
    # The draft was validated whole. Its hash is well formed, so the copy needs no validation.
    return draft.model_copy(update={"plan_hash": plan_hash(draft)})


def _screen_requests(settings: Sequence[PlanSetting]) -> tuple[PlanRequest]:
    """A case's one request: the screen backtest its settings send, by the "Sent as" mapping."""
    params = screen_backtest_params({row.setting: row.value for row in settings})
    return (PlanRequest(operation="screen_backtest", params=params),)


def build_plan(configuration: ScreenConfiguration, versions: Versions) -> Plan:
    """Builds the plan for a screen configuration: its one case, with its request and every
    resolved setting, the budget, the retry policy, and the data sent (plan contents).

    Raises `TrialFolioError` with `environment.unsupported` when `versions` names a version of
    `p123api`, `requests`, or `urllib3` that no release has verified.
    """
    _require_verified(versions)
    return _screen_plan(configuration, versions)


def _screen_plan(
    configuration: ScreenConfiguration | ScreenConfigurationV1_1, versions: Versions
) -> Plan:
    """A screen's plan 1.0.0, whose ranking is by formula, name, or ID."""
    settings = resolve_settings(configuration)
    return _hashed(
        Plan(
            schema_version="1.0.0",
            trialfolio_version=versions.trialfolio,
            canonicalization_version=CANONICALIZATION_VERSION,
            provider_wrapper=WrapperVersions(p123api=versions.p123api),
            transport=TransportVersions(requests=versions.requests, urllib3=versions.urllib3),
            title=configuration.title,
            purpose=configuration.purpose,
            cases=(
                PlanCase(
                    case_id=case_id(settings),
                    requests=_screen_requests(settings),
                    settings=settings,
                ),
            ),
            budget=BUDGET,
            retry_policy=RETRY_POLICY,
            data_sent=DATA_SENT,
            plan_hash=_UNHASHED,
        )
    )


_SNAPSHOT_DATA_SENT: Final = (
    SnapshotDataSent(category="credentials", recipient="Portfolio123", via="p123api", settings=()),
    SnapshotDataSent(
        category="strategy_definition",
        recipient="Portfolio123",
        via="p123api",
        settings=("system",),
    ),
)
"""A snapshot plan's data sent: the credentials, then the system's name, as the strategy's
definition (ranking snapshot output)."""


def build_snapshot_plan(
    configuration: RankingSnapshotConfiguration, versions: Versions
) -> RankingSnapshotPlan:
    """Builds a ranking snapshot configuration's plan (ranking snapshot output): the system it
    names, which is sent, its one `rank_get`, with the params `p123api`'s `rank_get` sends as the
    query of `GET /rank`, the budget of one request at `rank_get`'s documented cost, the retry
    policy, and the data sent, the credentials and the system's name. It has no title, purpose,
    or cases, and holds nothing that varies between invocations.

    Raises `TrialFolioError` with `environment.unsupported` as `build_plan` does.
    """
    _require_verified(versions)
    return _hashed(
        RankingSnapshotPlan(
            schema_version="1.0.0",
            trialfolio_version=versions.trialfolio,
            canonicalization_version=CANONICALIZATION_VERSION,
            provider_wrapper=WrapperVersions(p123api=versions.p123api),
            transport=TransportVersions(requests=versions.requests, urllib3=versions.urllib3),
            system=configuration.system,
            requests=(
                RankGetRequest(
                    operation="rank_get", params=RankGetParams(name=configuration.system)
                ),
            ),
            budget=SNAPSHOT_BUDGET,
            retry_policy=RETRY_POLICY,
            data_sent=_SNAPSHOT_DATA_SENT,
            plan_hash=_UNHASHED,
        )
    )


def check_approval(plan: AnyPlan, approved_hash: str | None) -> str:
    """Returns the plan's hash when `approved_hash` is exactly that hash, recomputed from the
    plan's contents: the full hash, `sha256:` and 64 lowercase hex digits (approval).

    Raises `TrialFolioError` with `plan.approval_required` otherwise, including for an
    abbreviated or uppercase hash, or none.
    """
    expected = plan_hash(plan)
    if approved_hash != expected:
        given = (
            "No approval was given."
            if approved_hash is None
            else "The hash given isn't this plan's hash."
        )
        raise TrialFolioError(
            "plan.approval_required",
            f"Running this plan needs its approval: its full hash, {expected}, exactly as "
            f"shown. {given} Nothing was sent.",
        )
    return expected


# Plans with a ranking definition: a screen's 1.2.0, and an experiment's 1.3.0.


def _definition_setting(
    ranking: RankingV1_1, definition: RankingDefinition | None, snapshot: SnapshotRead | None
) -> DefinitionRankingSetting | None:
    """The `ranking` setting of a ranking given as a definition, read with it, or named by a
    snapshot, read with it: the definition's hash, and its ranking method, the configuration's or
    the snapshot's system's. None for any other ranking, which `resolve_settings` plans as it's
    configured, or refuses with `TypeError`: a definition or a snapshot without what was read
    with it."""
    if isinstance(ranking, DefinitionRanking) and definition is not None:
        return DefinitionRankingSetting(
            definition=definition.hash, ranking_method=ranking.ranking_method
        )
    if isinstance(ranking, SnapshotRanking) and snapshot is not None:
        return DefinitionRankingSetting(
            definition=snapshot.definition.hash, ranking_method=snapshot.ranking_method
        )
    return None


def _plan_setting_v1_2(
    setting: ScreenSetting, node: str | None, value: SettingValueV1_2
) -> PlanSettingV1_2:
    return PlanSettingV1_2(
        setting=setting.name,
        node=node,
        category=setting.category,
        critical=setting.category in CRITICAL_CATEGORIES,
        value=value,
        unit=setting.unit,
        interpretation=setting.interpretation,
        expected_provenance=setting.provenance,
        inference_rule=setting.inference_rule,
        # A definition is captured whole, so its `ranking` row isn't flagged not_snapshotted.
        flags=cast("tuple[PlanFlag, ...]", setting.flags),
    )


def _ranking_settings(
    screen: ScreenFields | ScreenFieldsV1_1,
    ranking: DefinitionRankingSetting,
    definition: RankingDefinition,
) -> tuple[PlanSettingV1_2, ...]:
    """Every screen setting, in order, as `resolve_settings` resolves them, with `ranking`, the
    definition's hash and its ranking method, followed by a weight row for each of the
    definition's nodes, in its order, by its canonical path (weight rows)."""
    configured: dict[str, SettingValueV1_2] = {**_screen_values(screen), "ranking": ranking}
    resolved: list[PlanSettingV1_2] = []
    for setting in SCREEN_SETTINGS:
        value = configured.get(setting.name)
        if value is None:
            (value,) = setting.allowed
        resolved.append(_plan_setting_v1_2(setting, None, value))
        if setting.name == "ranking":
            resolved.extend(
                _plan_setting_v1_2(RANKING_WEIGHT, node.path, format(node.weight, "f"))
                for node in definition.nodes
            )
    return tuple(resolved)


def _ranking_requests(
    settings: Sequence[PlanSettingV1_2], definition: RankingDefinition
) -> tuple[RankUpdateRequest, PlanRequest]:
    """A case's two requests: the `rank_update` that writes its whole definition into
    `ApiRankingSystem`, with its ranking method, then the backtest its settings send, ranked by
    that system (sending a definition)."""
    values = {row.setting: row.value for row in settings if row.node is None}
    ranking = values["ranking"]
    if not isinstance(ranking, DefinitionRankingSetting):  # the settings give a definition
        raise TypeError("a case with a ranking definition holds its hash and its ranking method")
    update = RankUpdateRequest.model_validate(
        {
            "operation": "rank_update",
            "params": {
                "type": "stock",
                "nodes": definition.text,
                "rankingMethod": RANKING_METHOD_NUMBERS[ranking.ranking_method],
                "currency": "USD",
            },
        }
    )
    backtest = PlanRequest(operation="screen_backtest", params=screen_backtest_params(values))
    return update, backtest


def ranking_source(definition: RankingDefinition, snapshot: SnapshotRead | None) -> RankingSource:
    """Where the definition came from (ranking definitions, its source): a file, by the
    definition's hash, not the file's `artifact_id`, which its line endings would change; or a
    snapshot, by its system's name, as its record gives it, and the `artifact_id`s of its
    `snapshot.json` and `definition.xml`."""
    if snapshot is None:
        return RankingSource(
            form="definition",
            definition=definition.hash,
            system=None,
            snapshot_record=None,
            snapshot_definition=None,
        )
    return RankingSource(
        form="snapshot",
        definition=definition.hash,
        system=snapshot.record.system.name,
        snapshot_record=snapshot.record_id,
        snapshot_definition=snapshot.definition_id,
    )


def build_plan_v1_1(read: ScreenConfigurationRead, versions: Versions) -> Plan | PlanV1_2:
    """Builds the plan of a screen configuration that release 0.4.0's reader read, 1.0.0 or
    1.1.0, from what it read.

    A ranking given as a definition, or named by a snapshot, gives plan 1.2.0 (plans with a
    ranking definition): its one case's `rank_update`, which writes the whole definition into
    `ApiRankingSystem`, with its ranking method, then its backtest, ranked by that system; its
    settings, with the `ranking` row's definition hash and ranking method, and a weight row for
    each node; its `case_id`, which covers both, and so is the same for a file and for a
    snapshot of the same definition; `ranking_source`, the file's, by the definition's hash, or
    the snapshot's; and a budget of the two requests, with each operation's documented cost. Any
    other ranking gives plan 1.0.0, as `build_plan` builds it, whichever version the file is.

    Raises `TrialFolioError` with `environment.unsupported` as `build_plan` does.
    """
    _require_verified(versions)
    configuration = read.configuration
    ranking = _definition_setting(configuration.ranking, read.definition, read.snapshot)
    if ranking is None or read.definition is None:
        return _screen_plan(configuration, versions)
    settings = _ranking_settings(configuration, ranking, read.definition)
    budget = PlanBudgetV1_2(
        provider_requests=2,
        costs=RANKING_COSTS,
        credits=ranking_credits(2, RANKING_COSTS),
        authentication_calls=1,
    )
    return _hashed(
        PlanV1_2(
            schema_version="1.2.0",
            trialfolio_version=versions.trialfolio,
            canonicalization_version=CANONICALIZATION_VERSION,
            provider_wrapper=WrapperVersions(p123api=versions.p123api),
            transport=TransportVersions(requests=versions.requests, urllib3=versions.urllib3),
            title=configuration.title,
            purpose=configuration.purpose,
            ranking_source=ranking_source(read.definition, read.snapshot),
            cases=(
                PlanCaseV1_2(
                    case_id=case_id(settings),
                    requests=_ranking_requests(settings, read.definition),
                    settings=settings,
                ),
            ),
            budget=budget,
            retry_policy=RETRY_POLICY,
            data_sent=DATA_SENT_V1_2,
            plan_hash=_UNHASHED,
        )
    )


# An experiment's plans, 1.1.0 and 1.3.0


def _experiment_budget(provider_requests: int) -> PlanBudgetV1_1:
    """The budget across runs: the configuration's provider requests, as many authentication
    calls, and the credits the requests cost at the documented cost."""
    return PlanBudgetV1_1(
        provider_requests=provider_requests,
        credits_per_request=CREDITS_PER_REQUEST,
        credits_per_request_source=CREDITS_PER_REQUEST_SOURCE,
        credits=provider_requests * CREDITS_PER_REQUEST,
        authentication_calls=provider_requests,
    )


def _ranking_budget(provider_requests: int) -> PlanBudgetV1_3:
    """The budget across runs of an experiment with a ranking definition: the configuration's
    provider requests, as many authentication calls, each operation's documented cost, and the
    most the requests can cost at them, at most half of them backtests."""
    return PlanBudgetV1_3(
        provider_requests=provider_requests,
        costs=RANKING_COSTS,
        credits=ranking_credits(provider_requests, RANKING_COSTS),
        authentication_calls=provider_requests,
    )


def _case_screen(
    variant: ConfiguredVariant | ConfiguredVariantV1_1,
) -> ScreenFields | ScreenFieldsV1_1:
    """The settings of a variant's case, which every variant but a ranking variant has."""
    if variant.screen is None:  # a ranking variant's case is its definition
        raise ValueError("a ranking variant's case is planned by its definition")
    return variant.screen


def _variant_change(variant: ConfiguredVariant | ConfiguredVariantV1_1) -> dict[str, object]:
    """A case's `variant` but a ranking variant's: the setting it changes, and its change as the
    configuration gives it, with a decimal as its normalized text. Every key is written, null
    where it doesn't apply."""
    given = variant.variant
    change: dict[str, object] = {"value": None, "add": None, "replace": None, "with": None}
    if isinstance(given, RuleVariant):
        change |= {"add": given.add, "replace": given.replace, "with": given.with_}
    elif isinstance(given, SlippageVariant):
        # The model normalized it, so its text is the normalized form, in plain notation.
        change["value"] = str(given.value)
    elif isinstance(given, HoldingsVariant | RebalanceVariant):
        change["value"] = given.value
    elif given is None:
        # The default, which the file doesn't write: the frequency the baseline doesn't use.
        change["value"] = _case_screen(variant).rebalance_weeks
    else:
        raise ValueError("a ranking variant's change is its set and its remove")
    # `with` is a Python keyword, so the models take it by its alias.
    return {"setting": variant.setting, **change, "default": variant.default}


def _experiment_case(
    key: str,
    description: str | None,
    variant: PlanVariant | None,
    screen: ScreenFields | ScreenFieldsV1_1,
) -> ExperimentPlanCase:
    """A case of the experiment, resolved as a screen with its settings is: so its `case_id` and
    request are that screen's, whatever its key."""
    settings = resolve_settings(screen)
    return ExperimentPlanCase(
        case_key=key,
        case_id=case_id(settings),
        description=description,
        variant=variant,
        requests=_screen_requests(settings),
        settings=settings,
    )


def _declared(
    configuration: ExperimentConfiguration | ExperimentConfigurationV1_1,
) -> DeclaredPriorResearch:
    declared = configuration.prior_research
    return DeclaredPriorResearch(status=declared.status, description=declared.description)


def build_experiment_plan(
    configuration: ExperimentConfiguration, versions: Versions, revises: str | None = None
) -> PlanV1_1:
    """Compiles an experiment configuration into its plan 1.1.0 (docs/contracts.md, experiment
    plans and revisions): the baseline's case, then a case for each variant, P-13's default
    included, in the order of cases, each with its request and every resolved setting; the
    research context; the budget across runs; and `revises`, the hash of the plan this one
    revises, or None for the experiment's first plan.

    Nothing in the plan varies between invocations, so the same configuration, versions, and
    `revises` give the same plan and hash, however the file is written.

    Raises `TrialFolioError` with `environment.unsupported` when `versions` names a version of
    `p123api`, `requests`, or `urllib3` that no release has verified.
    """
    _require_verified(versions)
    return _experiment_plan(configuration, configured_variants(configuration), versions, revises)


def _experiment_plan(
    configuration: ExperimentConfiguration | ExperimentConfigurationV1_1,
    variants: Sequence[ConfiguredVariant | ConfiguredVariantV1_1],
    versions: Versions,
    revises: str | None,
) -> PlanV1_1:
    """An experiment's plan 1.1.0, whose baseline's ranking is by formula, name, or ID."""
    cases = [_experiment_case(BASELINE_CASE_KEY, None, None, configuration.baseline)]
    cases.extend(
        _experiment_case(
            variant.key,
            variant.description,
            PlanVariant.model_validate(_variant_change(variant)),
            _case_screen(variant),
        )
        for variant in variants
    )
    return _hashed(
        PlanV1_1(
            schema_version="1.1.0",
            trialfolio_version=versions.trialfolio,
            canonicalization_version=CANONICALIZATION_VERSION,
            provider_wrapper=WrapperVersions(p123api=versions.p123api),
            transport=TransportVersions(requests=versions.requests, urllib3=versions.urllib3),
            experiment_id=configuration.experiment_id,
            title=configuration.title,
            purpose=configuration.purpose,
            prior_research=_declared(configuration),
            revises=revises,
            cases=tuple(cases),
            budget=_experiment_budget(configuration.budget.provider_requests),
            retry_policy=RETRY_POLICY,
            data_sent=DATA_SENT,
            plan_hash=_UNHASHED,
        )
    )


def build_experiment_plan_v1_1(
    read: ExperimentConfigurationRead, versions: Versions, revises: str | None = None
) -> PlanV1_1 | PlanV1_3:
    """Compiles an experiment configuration that release 0.4.0's reader read, 1.0.0 or 1.1.0, from
    what it read, into its plan.

    A baseline ranked by a definition gives plan 1.3.0 (plans with a ranking definition): each
    case in the order of cases, with its `rank_update`, which writes its whole definition into
    `ApiRankingSystem`, then its backtest, ranked by that system; its settings with the weight
    rows of its definition; and its `case_id`, which covers them. A ranking variant's case has the
    definition its change of the baseline's gives, which the reader read, and its `variant` gives
    its `set` and `remove` by canonical paths in the baseline's definition; every other case has
    the baseline's definition. A baseline named by a snapshot is planned the same way, from the
    snapshot's definition and ranking method. The plan gives `ranking_source`, the baseline's
    file, by the definition's hash, or its snapshot, and the budget across runs, with each
    operation's documented cost. Any other ranking gives plan 1.1.0, as `build_experiment_plan`
    compiles it, whichever version the file is, so a case without a definition keeps the
    `case_id` 0.3.0 gave it.

    Raises `TrialFolioError` with `environment.unsupported` as `build_experiment_plan` does.
    """
    _require_verified(versions)
    configuration = read.configuration
    if isinstance(configuration, ExperimentConfiguration):
        return _experiment_plan(
            configuration, configured_variants(configuration), versions, revises
        )
    variants = configured_variants_v1_1(configuration)
    ranking = _definition_setting(configuration.baseline.ranking, read.definition, read.snapshot)
    if ranking is None or read.definition is None:
        return _experiment_plan(configuration, variants, versions, revises)
    return _ranking_plan(
        configuration,
        variants,
        (ranking, read.definition, ranking_source(read.definition, read.snapshot)),
        read.ranking_cases,
        versions,
        revises,
    )


def _ranking_case(
    key: str,
    description: str | None,
    variant: PlanVariantV1_3 | None,
    settings: tuple[PlanSettingV1_2, ...],
    definition: RankingDefinition,
) -> ExperimentPlanCaseV1_3:
    return ExperimentPlanCaseV1_3(
        case_key=key,
        case_id=case_id(settings),
        description=description,
        variant=variant,
        requests=_ranking_requests(settings, definition),
        settings=settings,
    )


def _ranking_variant(case: RankingCase) -> PlanVariantV1_3:
    """A ranking variant's `variant`: each node its `set` gives, by its canonical path in the
    baseline's definition, in that definition's order, with its weight as a normalized decimal's
    text, and the factor it removes, or None."""
    # `with` is a Python keyword, so the model takes it by its alias.
    return PlanVariantV1_3.model_validate(
        {
            "setting": "ranking",
            "value": None,
            "add": None,
            "replace": None,
            "with": None,
            "set": tuple(
                WeightChange(node=entry.node.path, weight=format(entry.weight, "f"))
                for entry in case.set
            ),
            "remove": None if case.remove is None else case.remove.path,
            "default": False,
        }
    )


def _ranking_plan(
    configuration: ExperimentConfigurationV1_1,
    variants: Sequence[ConfiguredVariantV1_1],
    baseline: tuple[DefinitionRankingSetting, RankingDefinition, RankingSource],
    ranking_cases: Sequence[RankingCase],
    versions: Versions,
    revises: str | None,
) -> PlanV1_3:
    """An experiment's plan 1.3.0, whose baseline's ranking is `baseline`: its `ranking` setting,
    its definition, and where that came from. `ranking_cases` gives each ranking variant's
    definition, by its place."""
    ranking, definition, source = baseline
    settings = _ranking_settings(configuration.baseline, ranking, definition)
    cases = [_ranking_case(BASELINE_CASE_KEY, None, None, settings, definition)]
    by_place = {case.place: case for case in ranking_cases}
    for variant in variants:
        if variant.setting != "ranking":
            settings = _ranking_settings(_case_screen(variant), ranking, definition)
            change = PlanVariantV1_3.model_validate(
                _variant_change(variant) | {"set": None, "remove": None}
            )
            cases.append(
                _ranking_case(variant.key, variant.description, change, settings, definition)
            )
            continue
        ranked = by_place.get(variant.place or "")
        if ranked is None:  # the reader gives every ranking variant's case
            raise ValueError("each ranking variant's case is read with its configuration")
        own = ranking.model_copy(update={"definition": ranked.definition.hash})
        settings = _ranking_settings(configuration.baseline, own, ranked.definition)
        cases.append(
            _ranking_case(
                variant.key,
                variant.description,
                _ranking_variant(ranked),
                settings,
                ranked.definition,
            )
        )
    return _hashed(
        PlanV1_3(
            schema_version="1.3.0",
            trialfolio_version=versions.trialfolio,
            canonicalization_version=CANONICALIZATION_VERSION,
            provider_wrapper=WrapperVersions(p123api=versions.p123api),
            transport=TransportVersions(requests=versions.requests, urllib3=versions.urllib3),
            experiment_id=configuration.experiment_id,
            title=configuration.title,
            purpose=configuration.purpose,
            prior_research=_declared(configuration),
            ranking_source=source,
            revises=revises,
            cases=tuple(cases),
            budget=_ranking_budget(configuration.budget.provider_requests),
            retry_policy=RETRY_POLICY,
            data_sent=DATA_SENT_V1_2,
            plan_hash=_UNHASHED,
        )
    )


# Revisions


@dataclass(frozen=True)
class PlanRevision:
    """A revision of an experiment's current plan: the plan a run approves in its place, and what
    changed from the current plan, which the revision's `experiment.json` records."""

    plan: PlanV1_1
    """Its `revises` is the current plan's hash."""
    changes: PlanChanges


@dataclass(frozen=True)
class PlanRevisionV1_1:
    """A revision of an experiment's current plan, 1.1.0 or 1.3.0, by release 0.4.0's rules: the
    plan a run approves in its place, 1.1.0 or 1.3.0, and what changed, as `experiment.json`
    1.1.0 records it, `ranking_source` among the parts."""

    plan: PlanV1_1 | PlanV1_3
    """Its `revises` is the current plan's hash."""
    changes: PlanChangesV1_1


def _another_experiment(problem: str) -> TrialFolioError:
    return TrialFolioError(
        "output.not_empty",
        f"{problem} The directory's records stay as they are, and nothing was sent. Run the "
        "configuration into a new output directory.",
    )


def _universe(plan: PlanV1_1 | PlanV1_3) -> object:
    """The baseline's universe, which every case of the plan uses."""
    (universe,) = (row.value for row in plan.cases[0].settings if row.setting == "universe")
    return universe


def _check_experiment(
    configuration: ExperimentConfiguration | ExperimentConfigurationV1_1,
    current: PlanV1_1 | PlanV1_3,
) -> None:
    """Raises `TrialFolioError` with `output.not_empty` when the configuration's `experiment_id`,
    or its baseline's universe, isn't the current plan's: either makes another experiment."""
    if configuration.experiment_id != current.experiment_id:
        raise _another_experiment(
            "The configuration's `experiment_id` isn't that of the experiment in the output "
            "directory, so it's another experiment, which can't run there."
        )
    if configuration.baseline.universe != _universe(current):
        raise _another_experiment(
            "The configuration's baseline has another universe than the experiment in the output "
            "directory. Another universe is another experiment, not a revision of this one, so "
            "it can't run there."
        )


def plan_revision(
    configuration: ExperimentConfiguration, versions: Versions, current: PlanV1_1
) -> PlanRevision | None:
    """Builds the experiment's plan again, for a run of its configuration into its own output
    directory, and compares it with `current`, the experiment's current plan (docs/contracts.md,
    experiment plans and revisions).

    Returns None when the configuration and the versions give the current plan, which the run
    then resumes. That's so even when the file is written differently, in a way no plan records.
    Anything else is a revision: that plan, with its `revises` set to the current plan's hash,
    recomputed from its contents, and what changed.

    Raises `TrialFolioError` with `output.not_empty` when the configuration's `experiment_id`, or
    its baseline's universe, isn't the current plan's: either makes another experiment, not a
    revision. Raises it with `environment.unsupported` as `build_experiment_plan` does.
    """
    _check_experiment(configuration, current)
    current_hash = plan_hash(current)
    if build_experiment_plan(configuration, versions, current.revises).plan_hash == current_hash:
        return None
    revision = build_experiment_plan(configuration, versions, current_hash)
    return PlanRevision(revision, plan_changes(current, revision))


def plan_revision_v1_1(
    read: ExperimentConfigurationRead, versions: Versions, current: PlanV1_1 | PlanV1_3
) -> PlanRevisionV1_1 | None:
    """Builds the experiment's plan again, as `build_experiment_plan_v1_1` builds it from what
    release 0.4.0's reader read, and compares it with `current`, the experiment's current plan,
    1.1.0 or 1.3.0, by the rules `plan_revision` follows (plans with a ranking definition,
    revisions).

    A changed definition, or ranking method, is a changed setting of the baseline, so its cases
    are new, and the cases it no longer gives are retired; a ranking variant whose definition
    stays the same, byte for byte, keeps its case. A ranking given another way, such as a
    definition in place of a formula, revises a plan 1.1.0 into a 1.3.0, or back.

    Returns None when the configuration and the versions give the current plan, and otherwise
    the revision, with what changed, as `experiment.json` 1.1.0 records it. Raises
    `TrialFolioError` as `plan_revision` does, and `TypeError` as `build_experiment_plan_v1_1`
    does.
    """
    _check_experiment(read.configuration, current)
    current_hash = plan_hash(current)
    if build_experiment_plan_v1_1(read, versions, current.revises).plan_hash == current_hash:
        return None
    revision = build_experiment_plan_v1_1(read, versions, current_hash)
    return PlanRevisionV1_1(revision, plan_changes_v1_1(current, revision))


def _versions_of(plan: PlanV1_1 | PlanV1_3) -> dict[VersionedPackage, str]:
    return {
        "trialfolio": plan.trialfolio_version,
        "p123api": plan.provider_wrapper.p123api,
        "requests": plan.transport.requests,
        "urllib3": plan.transport.urllib3,
    }


def _variant_v1_3(variant: PlanVariant | PlanVariantV1_3 | None) -> PlanVariantV1_3 | None:
    """A case's `variant` as plan 1.3.0 and `experiment.json` 1.1.0 hold it: a 1.1.0 plan's, or
    a 1.0.0 `experiment.json`'s, with `set` and `remove` null, and otherwise unchanged."""
    if variant is None or isinstance(variant, PlanVariantV1_3):
        return variant
    return PlanVariantV1_3.model_validate(
        variant.model_dump(mode="json") | {"set": None, "remove": None}
    )


def _source_changed(previous: PlanV1_1 | PlanV1_3, revision: PlanV1_1 | PlanV1_3) -> bool:
    """Whether the definition's source changed, other than by its definition, whose change the
    cases record: so a change of its form, such as a snapshot of the definition a file held. A
    ranking given another way, which one of the plans gives no source, changes the cases
    instead."""
    if not (isinstance(previous, PlanV1_3) and isinstance(revision, PlanV1_3)):
        return False
    before, after = previous.ranking_source, revision.ranking_source
    return before.model_dump(exclude={"definition"}) != after.model_dump(exclude={"definition"})


def _changes(
    previous: PlanV1_1 | PlanV1_3, revision: PlanV1_1 | PlanV1_3, parts: Sequence[RevisedPartV1_1]
) -> dict[str, object]:
    """What the revision changed from the plan before it, with the changed parts of `parts`, as
    `experiment.json` records them."""
    before, after = _versions_of(previous), _versions_of(revision)
    earlier = {case.case_id: case for case in previous.cases}
    later = {case.case_id: case for case in revision.cases}
    kept = [(earlier[case.case_id], case) for case in revision.cases if case.case_id in earlier]
    changed: dict[RevisedPartV1_1, bool] = {
        "title": previous.title != revision.title,
        "purpose": previous.purpose != revision.purpose,
        "prior_research": previous.prior_research != revision.prior_research,
        # Another version of the budget, with each operation's cost, is another budget too.
        "budget": previous.budget != revision.budget,
        "ranking_source": _source_changed(previous, revision),
        "case_keys": any(old.case_key != new.case_key for old, new in kept),
        "case_descriptions": any(old.description != new.description for old, new in kept),
        "case_variants": any(
            _variant_v1_3(old.variant) != _variant_v1_3(new.variant) for old, new in kept
        ),
        "case_order": [case.case_id for case in previous.cases if case.case_id in later]
        != [new.case_id for _, new in kept],
    }
    # Everything else a plan holds follows from these and Trial Folio's own code, so a plan that
    # differs in none of them was built by other code under the same version: the model refuses
    # a revision that records no change.
    return {
        "versions": tuple(
            VersionChange(package=package, previous=before[package], current=after[package])
            for package in VERSIONED_PACKAGES
            if before[package] != after[package]
        ),
        "cases_added": tuple(
            CaseChange(case_id=case.case_id, case_key=case.case_key)
            for case in revision.cases
            if case.case_id not in earlier
        ),
        "cases_retired": tuple(
            CaseChange(case_id=case.case_id, case_key=case.case_key)
            for case in previous.cases
            if case.case_id not in later
        ),
        "parts": tuple(part for part in parts if changed[part]),
    }


def plan_changes(previous: PlanV1_1, revision: PlanV1_1) -> PlanChanges:
    """What the revision changed from the plan before it: each version that changed, with both
    values; the cases it added, in its order, and those it retired, in the previous plan's; and
    which other parts changed.

    A case is its `case_id`, so a case whose settings didn't change is kept. `case_keys`,
    `case_descriptions`, and `case_variants` are changes to a kept case, and `case_order` a new
    order of the kept cases. An added or retired case is recorded as that alone, even when it has
    a retired case's key.
    """
    return PlanChanges.model_validate(_changes(previous, revision, REVISED_PARTS))


def plan_changes_v1_1(
    previous: PlanV1_1 | PlanV1_3, revision: PlanV1_1 | PlanV1_3
) -> PlanChangesV1_1:
    """What the revision changed from the plan before it, 1.1.0 or 1.3.0, as `plan_changes`
    gives it, and as `experiment.json` 1.1.0 records it: with `ranking_source` among the parts
    when the definition's source changed, other than by its definition, as when a snapshot of the
    definition a file held takes the file's place, which keeps every case. A changed definition,
    and a ranking given another way, change the cases instead (`experiment.json`)."""
    return PlanChangesV1_1.model_validate(_changes(previous, revision, REVISED_PARTS_V1_1))


# experiment.json


def _recorded(case: ExperimentPlanCase | RecordedCase) -> dict[str, object]:
    return {
        "case_key": case.case_key,
        "case_id": case.case_id,
        "description": case.description,
        "variant": case.variant,
    }


def _recorded_v1_1(
    case: ExperimentPlanCase | ExperimentPlanCaseV1_3 | RecordedCase | RecordedCaseV1_1,
) -> dict[str, object]:
    return {
        "case_key": case.case_key,
        "case_id": case.case_id,
        "description": case.description,
        "variant": _variant_v1_3(case.variant),
    }


def _record(
    plan: PlanV1_1, retired: tuple[RetiredCase, ...], plans: tuple[PlanEntry, ...], at: datetime
) -> ExperimentRecord:
    return ExperimentRecord(
        schema_version="1.0.0",
        # Written in the run that built the plan, so by the Trial Folio the plan records.
        trialfolio_version=plan.trialfolio_version,
        created_at=at,
        experiment_id=plan.experiment_id,
        title=plan.title,
        purpose=plan.purpose,
        prior_research=plan.prior_research,
        planned_cases=tuple(RecordedCase.model_validate(_recorded(case)) for case in plan.cases),
        retired_cases=retired,
        plans=plans,
    )


def _record_v1_1(
    plan: PlanV1_1 | PlanV1_3,
    retired: tuple[RetiredCaseV1_1, ...],
    plans: tuple[PlanEntryV1_1, ...],
    at: datetime,
) -> ExperimentRecordV1_1:
    return ExperimentRecordV1_1(
        schema_version="1.1.0",
        # Written in the run that built the plan, so by the Trial Folio the plan records.
        trialfolio_version=plan.trialfolio_version,
        created_at=at,
        experiment_id=plan.experiment_id,
        title=plan.title,
        purpose=plan.purpose,
        prior_research=plan.prior_research,
        planned_cases=tuple(
            RecordedCaseV1_1.model_validate(_recorded_v1_1(case)) for case in plan.cases
        ),
        retired_cases=retired,
        plans=plans,
    )


def first_experiment_record(
    plan: PlanV1_1,
    *,
    plan_artifact_id: str,
    configuration_artifact_id: str,
    approval: Approval,
    created_at: datetime,
) -> ExperimentRecord:
    """The `experiment.json` of an experiment's first plan, in `plans/1/` (docs/contracts.md,
    `experiment.json`): the experiment as the plan declares it, its planned cases, no retired
    case, and the plan's entry, with no reason or changes.

    `plan_artifact_id` and `configuration_artifact_id` are those of the plan's `plan.json` and
    `configuration.yaml`, and `approval` is how the plan was approved, `not_required` only for a
    synthetic experiment.

    Raises `ValueError` when `plan` revises another plan.
    """
    entry = PlanEntry(
        plan=1,
        plan_hash=plan_hash(plan),
        revises=plan.revises,
        plan_artifact_id=plan_artifact_id,
        configuration_artifact_id=configuration_artifact_id,
        approval=approval,
        reason=None,
        changes=None,
    )
    return _record(plan, (), (entry,), created_at)


def first_experiment_record_v1_1(
    plan: PlanV1_1 | PlanV1_3,
    *,
    plan_artifact_id: str,
    configuration_artifact_id: str,
    approval: Approval,
    created_at: datetime,
) -> ExperimentRecord | ExperimentRecordV1_1:
    """The `experiment.json` of an experiment's first plan, 1.1.0 or 1.3.0, as
    `first_experiment_record` gives it: version 1.1.0 for a plan 1.3.0, whose cases' variants
    hold `set` and `remove`, and 1.0.0 for a plan 1.1.0 (`experiment.json`).

    Raises `ValueError` when `plan` revises another plan.
    """
    if isinstance(plan, PlanV1_1):
        return first_experiment_record(
            plan,
            plan_artifact_id=plan_artifact_id,
            configuration_artifact_id=configuration_artifact_id,
            approval=approval,
            created_at=created_at,
        )
    entry = PlanEntryV1_1(
        plan=1,
        plan_hash=plan_hash(plan),
        revises=plan.revises,
        plan_artifact_id=plan_artifact_id,
        configuration_artifact_id=configuration_artifact_id,
        approval=approval,
        reason=None,
        changes=None,
    )
    return _record_v1_1(plan, (), (entry,), created_at)


def retired_cases(previous: ExperimentRecord, plan: PlanV1_1) -> tuple[RetiredCase, ...]:
    """The retired cases of the experiment once `plan` is its current plan, from `previous`, the
    current plan's `experiment.json`: `previous`'s retired cases, without each case `plan`
    includes again, followed by each case the current plan included and `plan` doesn't, as the
    current plan held it, with its number. With the current plan itself, they're `previous`'s."""
    planned = {case.case_id for case in plan.cases}
    current = previous.plans[-1].plan
    return (
        *(case for case in previous.retired_cases if case.case_id not in planned),
        *(
            RetiredCase.model_validate({**_recorded(case), "plan": current})
            for case in previous.planned_cases
            if case.case_id not in planned
        ),
    )


def retired_cases_v1_1(
    previous: ExperimentRecord | ExperimentRecordV1_1, plan: PlanV1_1 | PlanV1_3
) -> tuple[RetiredCaseV1_1, ...]:
    """The retired cases of the experiment once `plan`, 1.1.0 or 1.3.0, is its current plan, as
    `retired_cases` gives them, as `experiment.json` 1.1.0 holds them: an entry taken from a
    1.0.0 `experiment.json` with its variant's `set` and `remove` null."""
    planned = {case.case_id for case in plan.cases}
    current = previous.plans[-1].plan
    return (
        *(
            RetiredCaseV1_1.model_validate({**_recorded_v1_1(case), "plan": case.plan})
            for case in previous.retired_cases
            if case.case_id not in planned
        ),
        *(
            RetiredCaseV1_1.model_validate({**_recorded_v1_1(case), "plan": current})
            for case in previous.planned_cases
            if case.case_id not in planned
        ),
    )


def revised_experiment_record(
    previous: ExperimentRecord,
    revision: PlanRevision,
    *,
    number: int,
    reason: str,
    plan_artifact_id: str,
    configuration_artifact_id: str,
    approval: Approval,
    created_at: datetime,
) -> ExperimentRecord:
    """The `experiment.json` of a revision, in `plans/<number>/`, from the current plan's,
    `previous` (docs/contracts.md, `experiment.json`).

    It holds the experiment as the revision declares it, and its planned cases. Its retired cases
    are `previous`'s, without each case the revision includes again, followed by each case the
    current plan included and the revision doesn't, as the current plan held it, with its number.
    Its plans are `previous`'s, unchanged, followed by the revision's entry, with `reason`, the
    revision's `--revision-reason`, and what changed.

    Raises `ValueError` when the records don't fit together: when `number` isn't above the
    current plan's, the revision doesn't revise it, or `previous` isn't its record, as the
    revision's changes show; or when `reason` isn't a valid reason.
    """
    retired = retired_cases(previous, revision.plan)
    entry = PlanEntry(
        plan=number,
        plan_hash=plan_hash(revision.plan),
        revises=revision.plan.revises,
        plan_artifact_id=plan_artifact_id,
        configuration_artifact_id=configuration_artifact_id,
        approval=approval,
        reason=reason,
        changes=revision.changes,
    )
    return _record(revision.plan, retired, (*previous.plans, entry), created_at)


def revised_experiment_record_v1_1(
    previous: ExperimentRecord | ExperimentRecordV1_1,
    revision: PlanRevisionV1_1,
    *,
    number: int,
    reason: str,
    plan_artifact_id: str,
    configuration_artifact_id: str,
    approval: Approval,
    created_at: datetime,
) -> ExperimentRecord | ExperimentRecordV1_1:
    """The `experiment.json` of a revision, 1.1.0 or 1.3.0, as `revised_experiment_record` gives
    it, from the current plan's, `previous`, 1.0.0 or 1.1.0 (`experiment.json`).

    It's version 1.1.0 once the revision, or an earlier plan of the experiment, is plan 1.3.0,
    which `previous` being 1.1.0 shows: its cases' variants hold `set` and `remove`, null in a
    variant of another setting, and an entry taken from a 1.0.0 `experiment.json` is written with
    them null, and is otherwise unchanged, so the history can still be checked one plan at a
    time. Otherwise it's 1.0.0, as `revised_experiment_record` gives it.

    Raises `ValueError` as `revised_experiment_record` does.
    """
    plan = revision.plan
    if isinstance(previous, ExperimentRecord) and isinstance(plan, PlanV1_1):
        # No plan of the experiment is 1.3.0, so no part names the definition's source.
        changes = PlanChanges.model_validate_json(revision.changes.model_dump_json())
        return revised_experiment_record(
            previous,
            PlanRevision(plan, changes),
            number=number,
            reason=reason,
            plan_artifact_id=plan_artifact_id,
            configuration_artifact_id=configuration_artifact_id,
            approval=approval,
            created_at=created_at,
        )
    entry = PlanEntryV1_1(
        plan=number,
        plan_hash=plan_hash(plan),
        revises=plan.revises,
        plan_artifact_id=plan_artifact_id,
        configuration_artifact_id=configuration_artifact_id,
        approval=approval,
        reason=reason,
        changes=revision.changes,
    )
    plans = tuple(
        PlanEntryV1_1.model_validate_json(earlier.model_dump_json()) for earlier in previous.plans
    )
    return _record_v1_1(plan, retired_cases_v1_1(previous, plan), (*plans, entry), created_at)
