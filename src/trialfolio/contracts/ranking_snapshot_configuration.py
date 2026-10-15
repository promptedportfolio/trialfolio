"""The ranking snapshot configuration, `kind: ranking-snapshot`, schema version 1.0.0
(docs/contracts.md, ranking snapshot configuration).

It names a ranking system saved in the user's Portfolio123 account, which `trialfolio run` reads
with one `rank_get`, under a plan and approval of its own, into a ranking snapshot. A screen's or
an experiment's ranking can then name the snapshot. It writes nothing to the account.
`trialfolio.configuration` reads it from YAML, applying the rules for every configuration file,
and checks that `system`, which Portfolio123 receives, is quoted.
"""

from typing import Final, Literal, get_args

from trialfolio.contracts.common import ContractModel, NonEmptyText

RankingSnapshotSchemaVersion = Literal["1.0.0"]

RANKING_SNAPSHOT_SCHEMA_VERSIONS: Final = get_args(RankingSnapshotSchemaVersion)
"""The ranking snapshot configuration versions this release reads."""


class RankingSnapshotConfiguration(ContractModel):
    """A ranking snapshot configuration, `kind: ranking-snapshot`: the ranking system saved in the
    account that a snapshot reads, by name. It has no title or purpose: the snapshot records what
    Portfolio123 returns, and the configuration that uses it declares the research."""

    kind: Literal["ranking-snapshot"]
    schema_version: RankingSnapshotSchemaVersion
    system: NonEmptyText
    """The name of a ranking system saved in the account, as the website shows it, sent as
    `rank_get`'s `name`. An ID isn't offered."""
