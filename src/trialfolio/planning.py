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

An experiment's plan compiler and revision rules (docs/contracts.md, experiment plans and
revisions):

- `build_experiment_plan` compiles an experiment configuration into a plan 1.1.0: the baseline's
  case, then a case for each variant, the default included, in the order of cases.
- `plan_revision` builds an experiment's plan again for a run into its own output directory, and
  gives the revision of its current plan, with what changed, or None when the configuration and
  the versions give the current plan, which the run resumes.
- `first_experiment_record` and `revised_experiment_record` give the `experiment.json` of a
  plan: the experiment as the plan declares it, its retired cases, and the history of its plans.
"""

import importlib
import importlib.metadata
import importlib.util
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType, ModuleType
from typing import Final, Literal, cast

from trialfolio.canonical import CANONICALIZATION_VERSION, canonical_json, sha256_hex
from trialfolio.contracts.common import (
    BASELINE_CASE_KEY,
    CRITICAL_CATEGORIES,
    Approval,
    TransportVersions,
    WrapperVersions,
)
from trialfolio.contracts.experiment_configuration import (
    ConfiguredVariant,
    ExperimentConfiguration,
    HoldingsVariant,
    RebalanceVariant,
    RuleVariant,
    SlippageVariant,
    configured_variants,
)
from trialfolio.contracts.experiment_plan import (
    DeclaredPriorResearch,
    ExperimentPlanCase,
    PlanBudgetV1_1,
    PlanV1_1,
    PlanVariant,
)
from trialfolio.contracts.experiment_record import (
    REVISED_PARTS,
    VERSIONED_PACKAGES,
    CaseChange,
    ExperimentRecord,
    PlanChanges,
    PlanEntry,
    RecordedCase,
    RetiredCase,
    RevisedPart,
    VersionChange,
    VersionedPackage,
)
from trialfolio.contracts.plan import (
    DATA_SENT_SETTINGS,
    Budget,
    DataSent,
    DocumentedSource,
    Plan,
    PlanCase,
    PlanFlag,
    PlanRequest,
    PlanSetting,
    RetryPolicy,
    SettingValue,
    screen_backtest_params,
)
from trialfolio.contracts.screen_configuration import (
    IdRanking,
    NameRanking,
    ScreenConfiguration,
    ScreenFields,
)
from trialfolio.contracts.screen_settings import SCREEN_SETTINGS, ScreenSetting
from trialfolio.errors import TrialFolioError

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


CREDITS_PER_REQUEST: Final = 5
"""Portfolio123's documented cost of one screen backtest, in credits (budget and retries)."""

CREDITS_PER_REQUEST_SOURCE: Final = DocumentedSource(
    title="API: Screen",
    url="https://portfolio123.customerly.help/en/articles/43324-api-screen",
    checked=date(2026, 10, 1),
)

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


def _configured_values(configuration: ScreenFields) -> dict[str, SettingValue]:
    """The settings the configuration gives, in their JSON types as a plan holds them: dates as
    `YYYY-MM-DD`, and decimals as normalized text."""
    return {
        "universe": configuration.universe,
        "rules": configuration.rules,
        "ranking": configuration.ranking,
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


def resolve_settings(configuration: ScreenFields) -> tuple[PlanSetting, ...]:
    """Every screen setting, in order, resolved from the configuration, or from an experiment's
    case (settings in the plan).

    A setting the configuration doesn't give takes the one value its row allows: a fixed value,
    an inferred default, `not_modeled`, or `not_sent`. So `data_vendor` is FactSet, inferred,
    whether the configuration omits it or gives it, and how the file is written leaves no trace.
    """
    configured = _configured_values(configuration)
    resolved: list[PlanSetting] = []
    for setting in SCREEN_SETTINGS:
        value = configured.get(setting.name)
        if value is None:
            (value,) = setting.allowed
        resolved.append(_plan_setting(setting, value))
    return tuple(resolved)


def case_id(settings: Sequence[PlanSetting]) -> str:
    """`case-` and the first 16 hex digits of the SHA-256 of the canonical form of `settings`,
    each row reduced to its `setting`, `value`, and `unit` (plan hashing)."""
    rows = [row.model_dump(mode="json", include={"setting", "value", "unit"}) for row in settings]
    return "case-" + sha256_hex(canonical_json(rows))[:16]


def plan_hash(plan: Plan | PlanV1_1) -> str:
    """`sha256:` and the SHA-256 of the canonical form of `plan` without its `plan_hash` field
    (plan hashing). It's computed from the contents, so a stored `plan_hash` is never trusted."""
    content = plan.model_dump(mode="json", exclude={"plan_hash"})
    return "sha256:" + sha256_hex(canonical_json(content))


_UNHASHED: Final = "sha256:" + "0" * 64
"""A placeholder, replaced by the plan's hash before the plan leaves `build_plan` or
`build_experiment_plan`."""


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
    settings = resolve_settings(configuration)
    draft = Plan(
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
    # The draft was validated whole. Its hash is well formed, so the copy needs no validation.
    return draft.model_copy(update={"plan_hash": plan_hash(draft)})


def check_approval(plan: Plan, approved_hash: str | None) -> str:
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


def _plan_variant(variant: ConfiguredVariant) -> PlanVariant:
    """A case's `variant`: the setting it changes, and its change as the configuration gives it,
    with a decimal as its normalized text. Every key is written, null where it doesn't apply."""
    given = variant.variant
    change: dict[str, object] = {"value": None, "add": None, "replace": None, "with": None}
    if isinstance(given, RuleVariant):
        change |= {"add": given.add, "replace": given.replace, "with": given.with_}
    elif isinstance(given, SlippageVariant):
        # The model normalized it, so its text is the normalized form, in plain notation.
        change["value"] = str(given.value)
    elif isinstance(given, HoldingsVariant | RebalanceVariant):
        change["value"] = given.value
    else:  # The default, which the file doesn't write: the frequency the baseline doesn't use.
        change["value"] = variant.screen.rebalance_weeks
    # `with` is a Python keyword, so the model takes it by its alias.
    return PlanVariant.model_validate(
        {"setting": variant.setting, **change, "default": variant.default}
    )


def _experiment_case(
    key: str, description: str | None, variant: PlanVariant | None, screen: ScreenFields
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
    cases = [_experiment_case(BASELINE_CASE_KEY, None, None, configuration.baseline)]
    cases.extend(
        _experiment_case(variant.key, variant.description, _plan_variant(variant), variant.screen)
        for variant in configured_variants(configuration)
    )
    declared = configuration.prior_research
    draft = PlanV1_1(
        schema_version="1.1.0",
        trialfolio_version=versions.trialfolio,
        canonicalization_version=CANONICALIZATION_VERSION,
        provider_wrapper=WrapperVersions(p123api=versions.p123api),
        transport=TransportVersions(requests=versions.requests, urllib3=versions.urllib3),
        experiment_id=configuration.experiment_id,
        title=configuration.title,
        purpose=configuration.purpose,
        prior_research=DeclaredPriorResearch(
            status=declared.status, description=declared.description
        ),
        revises=revises,
        cases=tuple(cases),
        budget=_experiment_budget(configuration.budget.provider_requests),
        retry_policy=RETRY_POLICY,
        data_sent=DATA_SENT,
        plan_hash=_UNHASHED,
    )
    # The draft was validated whole. Its hash is well formed, so the copy needs no validation.
    return draft.model_copy(update={"plan_hash": plan_hash(draft)})


@dataclass(frozen=True)
class PlanRevision:
    """A revision of an experiment's current plan: the plan a run approves in its place, and what
    changed from the current plan, which the revision's `experiment.json` records."""

    plan: PlanV1_1
    """Its `revises` is the current plan's hash."""
    changes: PlanChanges


def _another_experiment(problem: str) -> TrialFolioError:
    return TrialFolioError(
        "output.not_empty",
        f"{problem} The directory's records stay as they are, and nothing was sent. Run the "
        "configuration into a new output directory.",
    )


def _universe(plan: PlanV1_1) -> SettingValue:
    """The baseline's universe, which every case of the plan uses."""
    (universe,) = (row.value for row in plan.cases[0].settings if row.setting == "universe")
    return universe


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
    current_hash = plan_hash(current)
    if build_experiment_plan(configuration, versions, current.revises).plan_hash == current_hash:
        return None
    revision = build_experiment_plan(configuration, versions, current_hash)
    return PlanRevision(revision, _changes(current, revision))


def _versions_of(plan: PlanV1_1) -> dict[VersionedPackage, str]:
    return {
        "trialfolio": plan.trialfolio_version,
        "p123api": plan.provider_wrapper.p123api,
        "requests": plan.transport.requests,
        "urllib3": plan.transport.urllib3,
    }


def _changes(previous: PlanV1_1, revision: PlanV1_1) -> PlanChanges:
    """What the revision changed from the plan before it: each version that changed, with both
    values; the cases it added, in its order, and those it retired, in the previous plan's; and
    which other parts changed.

    A case is its `case_id`, so a case whose settings didn't change is kept. `case_keys`,
    `case_descriptions`, and `case_variants` are changes to a kept case, and `case_order` a new
    order of the kept cases. An added or retired case is recorded as that alone, even when it has
    a retired case's key.
    """
    before, after = _versions_of(previous), _versions_of(revision)
    earlier = {case.case_id: case for case in previous.cases}
    later = {case.case_id: case for case in revision.cases}
    kept = [(earlier[case.case_id], case) for case in revision.cases if case.case_id in earlier]
    changed: dict[RevisedPart, bool] = {
        "title": previous.title != revision.title,
        "purpose": previous.purpose != revision.purpose,
        "prior_research": previous.prior_research != revision.prior_research,
        "budget": previous.budget != revision.budget,
        "case_keys": any(old.case_key != new.case_key for old, new in kept),
        "case_descriptions": any(old.description != new.description for old, new in kept),
        "case_variants": any(old.variant != new.variant for old, new in kept),
        "case_order": [case.case_id for case in previous.cases if case.case_id in later]
        != [new.case_id for _, new in kept],
    }
    # Everything else a plan holds follows from these and Trial Folio's own code, so a plan that
    # differs in none of them was built by other code under the same version: the model refuses
    # a revision that records no change.
    return PlanChanges(
        versions=tuple(
            VersionChange(package=package, previous=before[package], current=after[package])
            for package in VERSIONED_PACKAGES
            if before[package] != after[package]
        ),
        cases_added=tuple(
            CaseChange(case_id=case.case_id, case_key=case.case_key)
            for case in revision.cases
            if case.case_id not in earlier
        ),
        cases_retired=tuple(
            CaseChange(case_id=case.case_id, case_key=case.case_key)
            for case in previous.cases
            if case.case_id not in later
        ),
        parts=tuple(part for part in REVISED_PARTS if changed[part]),
    )


def _recorded(case: ExperimentPlanCase | RecordedCase) -> dict[str, object]:
    return {
        "case_key": case.case_key,
        "case_id": case.case_id,
        "description": case.description,
        "variant": case.variant,
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
    planned = {case.case_id for case in revision.plan.cases}
    current = previous.plans[-1].plan
    retired = (
        *(case for case in previous.retired_cases if case.case_id not in planned),
        *(
            RetiredCase.model_validate({**_recorded(case), "plan": current})
            for case in previous.planned_cases
            if case.case_id not in planned
        ),
    )
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
