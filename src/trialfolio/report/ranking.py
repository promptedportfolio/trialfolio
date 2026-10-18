"""What a ranking given as a definition adds to a run's and an experiment session's report
(release 0.4.0, R04-T11; docs/contracts.md, a ranking definition in a report): its weights, in
section 2; where the definition came from, in section 3; each attempt's costs, its `rank_update`'s
beside its backtest's, in section 5; and the limitations of writing it into `ApiRankingSystem`, in
section 10.

The weights are shown by their nodes' canonical paths, and the definition's text never is: the plan
holds it, and the report links the plan. An experiment's table of weights aligns each case's
weights by the baseline's nodes, which a ranking variant keeps, apart from the factor it removes,
not by their paths, which a removal can change. Like the metrics, it orders, ranks, and marks no
case by a value.
"""

from collections.abc import Sequence
from typing import Final

from trialfolio.contracts.attempt import (
    AttemptRecord,
    AttemptRecordV1_1,
    AttemptRecordV1_2,
    AttemptRecordV1_3,
)
from trialfolio.contracts.experiment_plan import ExperimentPlanCaseV1_3, PlanVariantV1_3
from trialfolio.contracts.plan import RankingSource
from trialfolio.contracts.ranking_snapshot import RankingSnapshotRecord
from trialfolio.contracts.screen_settings import SCREEN_SETTINGS_BY_NAME, DefinitionRankingSetting
from trialfolio.report.evidence import CaseView
from trialfolio.report.fragments import Setting, reported_cost, resolved_settings
from trialfolio.report.page import code, facts, moment, table
from trialfolio.report.vocabulary import RANKING_METHODS

REMOVED: Final = "Removed"
"""The cell of the factor a case's ranking variant removes, in an experiment's table of
weights."""

_RANKING: Final = SCREEN_SETTINGS_BY_NAME["ranking"]

_SYSTEM: Final = "<code>ApiRankingSystem</code>"


# 2. Definitions


def run_weights(settings: Sequence[Setting]) -> list[str]:
    """A run's ranking definition, in section 2: its `ranking` row, the definition's hash and
    ranking method, and each weight row, by its node's canonical path, in the definition's order.
    Empty for a run whose ranking isn't a definition."""
    weights = [setting for setting in settings if setting.node is not None]
    if not weights:
        return []
    # Weight rows follow a ranking given as a definition, whose `ranking` row is its hash and
    # its ranking method.
    ranking = next(setting for setting in settings if setting.name == _RANKING.name)
    value = DefinitionRankingSetting.model_validate_json(ranking.value)
    rows = [
        f"<tr><td>{code(setting.node or '')}</td><td>{code(setting.value)}</td></tr>"
        for setting in weights
    ]
    expected = any(setting.expected for setting in weights)
    held = "the plan resolves them" if expected else "settings.csv records them"
    return [
        "<h3>The ranking definition</h3>",
        (
            "<p>The ranking is a ranking system's definition, given by its hash, its ranking"
            " method, and each node's weight, which the <code>ranking</code> row and its weight"
            " rows give. The definition's text isn't shown: the plan holds it, and the artifacts"
            " below link the plan.</p>"
        ),
        *facts(
            [
                ("Definition", code(value.definition)),
                ("Ranking method", _method(value)),
            ]
        ),
        *table(
            ("Node", "Weight"),
            rows,
            caption=(
                f"Each node's weight, by its canonical path, in the definition's order, as {held}."
            ),
        ),
    ]


def experiment_weights(cases: Sequence[CaseView]) -> list[str]:
    """An experiment's table of weights, in section 2: a row for each node of the baseline's
    definition, in its order, by its canonical path, and a column for each planned case, in the
    plan's order, each cell the weight that case's definition gives the node, or `Removed` for
    the factor its ranking variant removes. Empty for an experiment whose current plan has no
    ranking definition."""
    baseline, *_ = cases
    if not isinstance(baseline.case, ExperimentPlanCaseV1_3):
        return []
    nodes = [setting.node for setting in _weights(baseline) if setting.node is not None]
    columns = [_aligned(nodes, view) for view in cases]
    rows = [
        f"<tr><td>{code(node)}</td>"
        + "".join(f"<td>{_cell(column[index])}</td>" for column in columns)
        + "</tr>"
        for index, node in enumerate(nodes)
    ]
    return [
        "<h3>The ranking's weights</h3>",
        (
            "<p>Each case's ranking is a ranking system's definition: the baseline's, or the"
            " baseline's with exactly its ranking variant's change, which its change above"
            " gives. A row for each node of the baseline's definition, in its order, by its"
            " canonical path, and a column for each planned case, in the plan's order. Each cell"
            " is the weight the case's definition gives the node, as the case's settings.csv"
            " holds it, or, for a case without one, its plan; <code>Removed</code> is the factor"
            " its variant removes. Each case's weights are aligned by the baseline's nodes, not"
            " by their paths, which a removal can change. The table orders, ranks, and marks no"
            " case by a weight. The definitions' text isn't shown: the plan holds each case's,"
            " and the artifacts below link the plan.</p>"
        ),
        *table(("Node", *(code(view.case.case_key) for view in cases)), rows),
    ]


def _weights(view: CaseView) -> list[Setting]:
    """A case's weight rows: its `settings.csv`'s, or its plan's without one."""
    settings = resolved_settings(view.settings, view.case.settings)
    return [setting for setting in settings if setting.node is not None]


def _aligned(nodes: Sequence[str], view: CaseView) -> list[Setting | None]:
    """The case's weight of each of the baseline's `nodes`, in order, None for the factor its
    ranking variant removes. A case's definition has the baseline's nodes, in its order, but the
    one its variant removes, so its weight rows follow the baseline's nodes but that one, though
    the removal can change their canonical paths."""
    variant = view.case.variant
    removed = (
        variant.remove
        if isinstance(variant, PlanVariantV1_3) and variant.setting == "ranking"
        else None
    )
    kept = iter(_weights(view))
    return [None if node == removed else next(kept) for node in nodes]


def _cell(weight: Setting | None) -> str:
    return REMOVED if weight is None else code(weight.value)


def _method(value: DefinitionRankingSetting) -> str:
    return f"{code(value.ranking_method)}: {RANKING_METHODS[value.ranking_method]}"


# 3. Data sources


def definition_source(ranking: RankingSource | None, snapshot: RankingSnapshotRecord | None) -> str:
    """Where a plan's ranking definition came from: a file, by the definition's hash, or a
    snapshot, by its system's name and ID, and when it was read, from its record."""
    if ranking is None:
        return "None: the ranking isn't a definition."
    if snapshot is None:
        # A file's: a snapshot's ranking_source always comes with its record.
        return f"A file, by the definition's hash, {code(ranking.definition)}."
    system = snapshot.system
    return (
        f"A ranking snapshot of the system {code(system.name)}, ID {code(str(system.id))}, read"
        f" {moment(snapshot.taken_at)}, as its record, <code>snapshot.json</code>, gives it. The"
        f" definition's hash: {code(ranking.definition)}."
    )


def run_source(ranking: RankingSource, snapshot: RankingSnapshotRecord | None) -> list[str]:
    """A run's ranking definition's source, in section 3."""
    copy = (
        "<code>definition.xml</code> is the run's copy of the file, byte for byte"
        if snapshot is None
        else "<code>definition.xml</code> and <code>snapshot.json</code> are the run's copies of"
        " the snapshot's files, byte for byte"
    )
    return [
        "<h3>The ranking definition's source</h3>",
        f"<p>{definition_source(ranking, snapshot)} {copy}.</p>",
    ]


def experiment_sources(rankings: Sequence[tuple[int, str]]) -> list[str]:
    """Each plan's ranking definition's source, in section 3, by its number, oldest first, as
    `definition_source` gives it."""
    rows = [f"<tr><td>{number}</td><td>{shown}</td></tr>" for number, shown in rankings]
    return [
        "<h3>The ranking definition's source</h3>",
        (
            "<p>Where each plan's ranking definition came from, oldest plan first. Each plan's"
            " <code>plans/&lt;n&gt;/definition.xml</code> is its copy of the definition, byte for"
            " byte, and, for a snapshot, its <code>snapshot.json</code> the copy of the"
            " snapshot's record.</p>"
        ),
        *table(("Plan", "Source"), rows),
    ]


# 5. Cases and attempts


def costs(record: AttemptRecord | AttemptRecordV1_1 | AttemptRecordV1_2 | AttemptRecordV1_3) -> str:
    """The credits Portfolio123 reported charging for an attempt's requests: its `rank_update`'s
    beside its backtest's, for an attempt that sends a definition."""
    backtest = reported_cost(record.provider_metadata.cost)
    update = (
        record.ranking_update if isinstance(record, AttemptRecordV1_2 | AttemptRecordV1_3) else None
    )
    if update is None:
        return backtest
    return (
        f"<code>rank_update</code>: {reported_cost(update.provider_metadata.cost)}."
        f" <code>screen_backtest</code>: {backtest}."
    )


# 10. Conclusion


def limitations(*, synthetic: bool, each: str, kind: str) -> list[str]:
    """The limitations of a ranking given as a definition: that `each`, such as "The run's
    definition", is written into `ApiRankingSystem` just before its backtest, which ranks by that
    system's name; and what the ranking lock can't exclude. A synthetic `kind`, such as "run",
    sent nothing, so wrote nothing."""
    if synthetic:
        return [
            (
                f"This {kind} is synthetic, and sent nothing, so nothing was written into the"
                f" account's {_SYSTEM}. A definition that's sent is written into it just before"
                " its backtest, which ranks by that system's name, and the ranking lock keeps"
                " only other Trial Folio processes on the machine from writing it between the"
                " two."
            )
        ]
    return [
        (
            f"{each} is written into the account's {_SYSTEM}, with its"
            " <code>rank_update</code>, just before its backtest, which ranks by that system's"
            " name."
        ),
        (
            "The ranking lock kept only other Trial Folio processes on the machine from writing"
            f" {_SYSTEM} between a definition's write and its backtest: Portfolio123's website,"
            " or another machine, could have changed it between the two, and no record would"
            " show it."
        ),
    ]
