"""What a report says about each code it shows: the tables from the codes in a run's, a review's,
or an experiment's records to the report's names and meanings for them.

Each kind of report keeps its own wording (DSC-04), so a table belongs to the kind of report that
shows it, unless more than one shows it the same way: the run report's tables come first, since the
review and the experiment report share most of them, then the review's, then the experiment's.
"""

from typing import Final

from trialfolio.contracts.common import Approval, PriorResearchStatus, UnavailableReason
from trialfolio.contracts.experiment_manifest import ExperimentArtifactRole
from trialfolio.contracts.manifest import ArtifactRole
from trialfolio.contracts.review_manifest import ReviewArtifactRole
from trialfolio.contracts.tables import DifferenceReason

# Every report

METRIC_DEFINITIONS: Final[dict[str, tuple[str, str]]] = {
    "coverage_start": ("Coverage start", "The first transaction date in the response's periods."),
    "coverage_end": ("Coverage end", "The end of the response's last period."),
    "coverage_periods": ("Coverage periods", "The number of rebalance periods."),
    "total_return": ("Total return", "Cumulative return over the backtest."),
    "annualized_return": (
        "Annualized return",
        (
            "Compound annual growth rate over the calendar days from the first to the last date of"
            " the daily series, with 365.25-day years."
        ),
    ),
    "max_drawdown": (
        "Maximum drawdown",
        "The largest peak-to-trough decline in the daily series, as a negative number.",
    ),
    "standard_deviation": (
        "Standard deviation",
        "Annualized standard deviation of monthly returns.",
    ),
    "sharpe_ratio": (
        "Sharpe ratio",
        "Portfolio123's Sharpe ratio. Its risk-free rate isn't documented.",
    ),
    "sortino_ratio": (
        "Sortino ratio",
        "Portfolio123's Sortino ratio. Its risk-free rate and target aren't documented.",
    ),
    "correlation": ("Correlation", "Correlation with the benchmark."),
    "r_squared": ("R squared", "The square of the correlation."),
    "beta": ("Beta", "Beta against the benchmark."),
    "alpha": (
        "Alpha",
        (
            "Portfolio123's alpha against the benchmark. Its unit is inferred from the value's"
            " magnitude, and its method isn't documented."
        ),
    ),
    "risk_samples": ("Risk samples", "The number of returns behind the risk statistics."),
}
"""Each metric's name and definition, from `p123api-screen-backtest` version 1's metrics."""

UNAVAILABLE_REASONS: Final[dict[UnavailableReason, str]] = {
    "absent_from_layout": "The response layout has no such metric.",
    "blank_in_source": "The response gives no value for it.",
    "unparseable_in_source": (
        "Its value couldn't be interpreted. The saved response keeps it as it came."
    ),
    "not_applicable": "The metric has no meaning here.",
    "not_supported": "Trial Folio doesn't interpret this field.",
    "input_unavailable": "A value it's calculated from is unavailable.",
}

FLAGS: Final[dict[str, str]] = {
    "critical_unexplained_mismatch": "A critical setting differs, and no change was declared.",
    "critical_unknown": "A critical setting is missing or can't be interpreted.",
    "intended_change_not_observed": "A declared change isn't present.",
    "inferred_default": (
        "A default the provider applies, inferred from its documentation or an owner decision,"
        " not reported by the provider."
    ),
    "time_dependent_default": "A default that depends on when the tool ran.",
    "unsupported_value": "Recorded, but unsupported and unverified.",
    "not_snapshotted": (
        "Names an object in the Portfolio123 account whose definition wasn't captured, so"
        " reproducibility is incomplete."
    ),
    "coverage_mismatch": "The response's coverage differs from this date.",
    "identical_source": "Two results have byte-identical saved responses.",
}

TOKENS: Final[dict[str, str]] = {
    "not_sent": "Not sent. Portfolio123's default applies, and it isn't documented.",
    "not_modeled": (
        "Not modeled by this provider path: the API documents no commission parameter, and"
        " slippage is its only trading-cost input."
    ),
}

PROVENANCE: Final[dict[str, str]] = {
    "verified": "Sent in the request, or captured from Portfolio123's response, by this run.",
    "user_supplied": "Provided by the user as a description, not as a request setting.",
    "inferred": "Derived under a documented rule, which the setting or metric records.",
    "unknown": "Not available from any source.",
}

SYNTHETIC_VERIFIED: Final = (
    "Where a real run's value is sent to Portfolio123 or captured from its response. Here it comes"
    " from the run's configuration or its invented response: nothing was sent, and no value came"
    " from Portfolio123."
)
"""What `verified` means in a synthetic run's report, which never calls its values Portfolio123's
(DSC-04)."""

ATTEMPT_OUTCOMES: Final[dict[str, str]] = {
    "succeeded": (
        "Portfolio123 returned a response, which was saved. That says nothing about the strategy."
    ),
    "failed": "The attempt ended with a recorded error.",
    "unknown": (
        "A request may have been sent, and no response was durably recorded. It's never retried"
        " automatically."
    ),
    "running": (
        "The attempt has a start record and no attempt record: the request may have been sent,"
        " and how the attempt ended wasn't recorded."
    ),
}

EXCHANGE_RESULTS: Final[dict[str, str]] = {
    "response": "Response",
    "not_connected": "Not connected: nothing was sent",
    "interrupted": "Interrupted: no complete response arrived",
}

APPROVALS: Final[dict[str, str]] = {
    "interactive": "Approved interactively: the plan was shown, and <code>approve</code> typed.",
    "option": "Approved with <code>--approve</code> and the plan's full hash.",
    "not_required": "Not required: the synthetic run sends nothing.",
}
"""How the plan was approved, as HTML."""

ROLES: Final[dict[ArtifactRole, str]] = {
    "plan": "Plan",
    "configuration": "Screen configuration, byte for byte",
    "start_record": "Start record",
    "attempt_record": "Attempt record",
    "provider_request": "Request, redacted",
    "provider_response": "Response, decoded",
    "provider_response_undecoded": "Response, undecoded",
    "metrics": "Normalized metrics",
    "settings": "Normalized settings",
    "report": "Report",
}


# The review report

SETTING_CLASSES: Final = (
    ("same", "The two values read the same."),
    ("intended_change", "The values differ, and the result declares the change."),
    ("unexplained_mismatch", "The values differ, and the result doesn't declare the change."),
    ("unknown", "The setting is missing from one of the two runs, so it can't be compared."),
)

METRIC_CLASSES: Final = (
    ("differenced", "Both values are available and comparable, so their difference is given."),
    (
        "not_comparable",
        (
            "Both values are available, but their contexts differ, so both are shown, without a"
            " difference."
        ),
    ),
    ("unavailable", "A value is unavailable, so there's no difference."),
)

DIFFERENCE_REASONS: Final[dict[DifferenceReason, str]] = {
    "input_unavailable": "A value is unavailable.",
    "different_unit": "The two values are in different units.",
    "different_benchmark": "The runs' benchmarks differ.",
    "unknown_period": "A run's period couldn't be established, so it isn't shown as matching.",
    "different_period": "The runs' periods differ.",
}
"""Why a metric isn't differenced, as `differences.csv`'s `reason` gives it, in the order the
comparison applies them."""

REVIEW_ROLES: Final[dict[ReviewArtifactRole, str]] = {
    "configuration": "Review configuration, byte for byte",
    "run_manifest": "Run manifest, copied",
    "plan": "Plan, copied",
    "metrics": "Normalized metrics, copied",
    "settings": "Normalized settings, copied",
    "differences": "Differences from the baseline",
    "report": "Report",
}

LAYOUT_METRICS: Final[dict[str, str]] = {
    "total_return": "Cumulative return over the response's periods.",
    "sharpe_ratio": (
        "The Sharpe ratio, as the response layout defines it. Its risk-free rate isn't documented."
    ),
    "sortino_ratio": (
        "The Sortino ratio, as the response layout defines it. Its risk-free rate and target"
        " aren't documented."
    ),
    "alpha": (
        "Alpha against the benchmark, as the response layout defines it. Its unit is inferred from"
        " the value's magnitude, and its method isn't documented."
    ),
}
"""A review with a synthetic result gives these definitions in place of a run report's, which call
a value Portfolio123's or a backtest's. They hold for a synthetic result's values and a backtested
one's alike (DSC-04)."""

SYNTHETIC_NOT_SENT: Final = (
    "Not sent: where a real run leaves it to Portfolio123's default, which isn't documented. Here"
    " nothing was sent, and no value came from Portfolio123."
)
"""What `not_sent` means in a review whose results are all synthetic, whose runs sent nothing."""


# The experiment report

PRIOR_RESEARCH: Final[dict[PriorResearchStatus, str]] = {
    "complete": (
        "the description accounts for all the earlier outcome-informed work on this idea, or"
        " says there was none"
    ),
    "partial": (
        "the description accounts for some of the earlier outcome-informed work on this idea,"
        " and there was more that it doesn't describe"
    ),
    "unknown": "the user can't say what earlier outcome-informed work on this idea there was",
}
"""What each prior-research status declares (docs/contracts.md, prior research)."""

EXPERIMENT_APPROVALS: Final[dict[Approval, str]] = {
    "interactive": "Approved interactively: the plan was shown, and <code>approve</code> typed.",
    "option": "Approved with the plan's full hash, as <code>--approve</code> gives it.",
    "not_required": "Not required: the synthetic experiment sends nothing.",
}
"""How a plan was approved, as HTML."""

EXPERIMENT_ROLES: Final[dict[ExperimentArtifactRole, str]] = {
    "configuration": "Experiment configuration, byte for byte",
    "plan": "Plan",
    "experiment_record": "Experiment record",
    "authentication_record": "Authentication record",
    "start_record": "Start record",
    "attempt_record": "Attempt record",
    "provider_request": "Request, redacted",
    "provider_response": "Response, decoded",
    "provider_response_undecoded": "Response, undecoded",
    "metrics": "Normalized metrics",
    "settings": "Normalized settings",
    "session_record": "Session record",
    "report": "Report",
}

EXPERIMENT_VERIFIED: Final = (
    "Sent in the case's request, or captured from Portfolio123's response, by the case's attempt."
)

SYNTHETIC_EXPERIMENT_VERIFIED: Final = (
    "Where a real experiment's value is sent to Portfolio123 or captured from its response. Here"
    " it comes from the experiment's configuration or its invented responses: nothing was sent,"
    " and no value came from Portfolio123."
)
"""What `verified` means in a synthetic experiment's report, which never calls its values
Portfolio123's (DSC-04)."""
