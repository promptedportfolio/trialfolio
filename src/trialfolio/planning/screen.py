"""A screen's plans, and a ranking snapshot's (docs/contracts.md, plan contents, plans with a
ranking definition, and ranking snapshot output).

- `build_plan` resolves a screen configuration into a plan 1.0.0, with its `case_id` and
  `plan_hash`. Nothing in a plan varies between invocations: it holds no timestamps, output
  directory, file paths, attempt IDs, credentials, or account information.
- `build_plan_v1_1` builds the plan of a screen configuration that release 0.4.0's reader read,
  from what it read, the definition included, so it reads no file: 1.2.0 when its ranking is a
  definition, with the case's `rank_update` and backtest, its weight rows, and `ranking_source`,
  and 1.0.0 otherwise, as `build_plan` builds it.
- `build_snapshot_plan` builds a ranking snapshot configuration's plan: the system it names, its
  one `rank_get`, the budget, and the data sent.
"""

from typing import Final

from trialfolio.canonical import CANONICALIZATION_VERSION
from trialfolio.configuration import ScreenConfigurationRead
from trialfolio.contracts.common import TransportVersions, WrapperVersions
from trialfolio.contracts.plan import Plan, PlanBudgetV1_2, PlanCase, PlanCaseV1_2, PlanV1_2
from trialfolio.contracts.plan_parts import (
    CREDITS_PER_REQUEST,
    CREDITS_PER_REQUEST_SOURCE,
    Budget,
    ranking_credits,
)
from trialfolio.contracts.ranking_snapshot import (
    SNAPSHOT_BUDGET,
    RankGetParams,
    RankGetRequest,
    RankingSnapshotPlan,
    SnapshotDataSent,
)
from trialfolio.contracts.ranking_snapshot_configuration import RankingSnapshotConfiguration
from trialfolio.contracts.screen_configuration import ScreenConfiguration, ScreenConfigurationV1_1
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

BUDGET: Final = Budget(
    provider_requests=1,
    credits_per_request=CREDITS_PER_REQUEST,
    credits_per_request_source=CREDITS_PER_REQUEST_SOURCE,
    credits=CREDITS_PER_REQUEST,
    authentication_calls=1,
)
"""A 1.0.0 plan's budget: one request, sent at most once, and one authentication call."""


def build_plan(configuration: ScreenConfiguration, versions: Versions) -> Plan:
    """Builds the plan for a screen configuration: its one case, with its request and every
    resolved setting, the budget, the retry policy, and the data sent (plan contents).

    Raises `TrialFolioError` with `environment.unsupported` when `versions` names a version of
    `p123api`, `requests`, or `urllib3` that no release has verified.
    """
    require_verified(versions)
    return _screen_plan(configuration, versions)


def _screen_plan(
    configuration: ScreenConfiguration | ScreenConfigurationV1_1, versions: Versions
) -> Plan:
    """A screen's plan 1.0.0, whose ranking is by formula, name, or ID."""
    settings = resolve_settings(configuration)
    return hashed(
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
                    requests=screen_requests(settings),
                    settings=settings,
                ),
            ),
            budget=BUDGET,
            retry_policy=RETRY_POLICY,
            data_sent=DATA_SENT,
            plan_hash=UNHASHED,
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
    require_verified(versions)
    return hashed(
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
            plan_hash=UNHASHED,
        )
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
    require_verified(versions)
    configuration = read.configuration
    ranking = definition_setting(configuration.ranking, read.definition, read.snapshot)
    if ranking is None or read.definition is None:
        return _screen_plan(configuration, versions)
    settings = ranking_settings(configuration, ranking, read.definition)
    budget = PlanBudgetV1_2(
        provider_requests=2,
        costs=RANKING_COSTS,
        credits=ranking_credits(2, RANKING_COSTS),
        authentication_calls=1,
    )
    return hashed(
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
                    requests=ranking_requests(settings, read.definition),
                    settings=settings,
                ),
            ),
            budget=budget,
            retry_policy=RETRY_POLICY,
            data_sent=DATA_SENT_V1_2,
            plan_hash=UNHASHED,
        )
    )
