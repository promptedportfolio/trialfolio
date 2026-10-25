"""An experiment's plan compiler (docs/contracts.md, experiment plans and revisions, and plans
with a ranking definition).

- `build_experiment_plan` compiles an experiment configuration into a plan 1.1.0: the baseline's
  case, then a case for each variant, the default included, in the order of cases.
- `build_experiment_plan_v1_1` compiles what release 0.4.0's reader read, the definition
  included, so it reads no file: 1.3.0 when its baseline's ranking is a definition, each case
  writing its definition, the baseline's or its ranking variant's, and 1.1.0 otherwise, as
  `build_experiment_plan` compiles it, whichever version the file is.

The plans' models check the consistency of what these build, a ranking variant's definition
included.
"""

from collections.abc import Mapping, Sequence

from trialfolio.canonical import CANONICALIZATION_VERSION
from trialfolio.configuration import ExperimentConfigurationRead
from trialfolio.contracts.common import BASELINE_CASE_KEY, TransportVersions, WrapperVersions
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
from trialfolio.contracts.plan_parts import (
    CREDITS_PER_REQUEST,
    CREDITS_PER_REQUEST_SOURCE,
    PlanSettingV1_2,
    RankingSource,
    ranking_credits,
)
from trialfolio.contracts.screen_configuration import ScreenFields, ScreenFieldsV1_1
from trialfolio.contracts.screen_settings import DefinitionRankingSetting
from trialfolio.planning.cases import (
    DATA_SENT,
    DATA_SENT_V1_2,
    RANKING_COSTS,
    RETRY_POLICY,
    case_id,
    definition_setting,
    ranking_requests,
    ranking_settings,
    ranking_source,
    resolve_settings,
    screen_requests,
)
from trialfolio.planning.hashing import UNHASHED, hashed
from trialfolio.planning.versions import Versions, require_verified
from trialfolio.ranking_definitions import RankingCase, RankingDefinition


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
        requests=screen_requests(settings),
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
    require_verified(versions)
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
    return hashed(
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
            plan_hash=UNHASHED,
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
    require_verified(versions)
    configuration = read.configuration
    if isinstance(configuration, ExperimentConfiguration):
        return _experiment_plan(
            configuration, configured_variants(configuration), versions, revises
        )
    variants = configured_variants_v1_1(configuration)
    ranking = definition_setting(configuration.baseline.ranking, read.definition, read.snapshot)
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
        requests=ranking_requests(settings, definition),
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


def _ranking_variant_case(
    baseline: ScreenFieldsV1_1,
    variant: ConfiguredVariantV1_1,
    ranked: tuple[DefinitionRankingSetting, RankingDefinition],
    by_place: Mapping[str, RankingCase],
) -> ExperimentPlanCaseV1_3:
    """A variant's case in an experiment's plan 1.3.0, whose baseline's settings are `baseline`
    and its ranking `ranked`: its `ranking` setting and its definition. A ranking variant's case
    has the definition `by_place` gives it, by its place; any other variant's has the baseline's
    definition."""
    ranking, definition = ranked
    if variant.setting != "ranking":
        settings = ranking_settings(_case_screen(variant), ranking, definition)
        change = PlanVariantV1_3.model_validate(
            _variant_change(variant) | {"set": None, "remove": None}
        )
        return _ranking_case(variant.key, variant.description, change, settings, definition)
    case = by_place.get(variant.place or "")
    if case is None:  # the reader gives every ranking variant's case
        raise ValueError("each ranking variant's case is read with its configuration")
    own = ranking.model_copy(update={"definition": case.definition.hash})
    settings = ranking_settings(baseline, own, case.definition)
    return _ranking_case(
        variant.key, variant.description, _ranking_variant(case), settings, case.definition
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
    settings = ranking_settings(configuration.baseline, ranking, definition)
    by_place = {case.place: case for case in ranking_cases}
    cases = [
        _ranking_case(BASELINE_CASE_KEY, None, None, settings, definition),
        *(
            _ranking_variant_case(configuration.baseline, variant, (ranking, definition), by_place)
            for variant in variants
        ),
    ]
    return hashed(
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
            plan_hash=UNHASHED,
        )
    )
