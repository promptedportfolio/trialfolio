"""What an ending's message says of an attempt with a ranking definition that a second interrupt
stopped before its attempt record (docs/contracts.md, sending a definition): `RAN_UPDATE`, once its
start record, `started.json`, was written, and `UPDATING`, once only its update record,
`updating.json`, was. A test formats each part with `of`, the words that name the attempt, and
`record`, those that name its record.

TS-T07 moved them here from tests/core/test_ranking_execution.py, when it separated a screen run's
tests into tests/core/test_ranking_screen_run.py, so that the screen run's test and the experiment's
of a second interrupt at the attempt record check the same words (docs/test-refactoring.md, modules
to separate).
"""

RAN_UPDATE: tuple[str, ...] = (
    (
        "The rank_update request{of}, which writes the case's ranking definition into"
        " ApiRankingSystem, reached Portfolio123, and may have been charged."
    ),
    (
        "screen backtest request may have been sent, and may have been charged: {record} start"
        " record reads as running."
    ),
)
"""What an ending's message says of an attempt with a definition whose start record,
`started.json`, was written, and its attempt record wasn't: its `rank_update` reached
Portfolio123, since that start record follows only its 200, and its backtest may have been sent."""

UPDATING: tuple[str, ...] = (
    (
        "The rank_update request{of}, which writes the case's ranking definition into"
        " ApiRankingSystem, may have been sent, and may have been charged: {record} update record"
        " was written, and its screen backtest request wasn't sent."
    ),
)
"""The same, for an attempt whose latest record is its update record, `updating.json`."""
