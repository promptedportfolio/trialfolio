"""The experiment manifest, `sessions/<s>/manifest.json` with `artifact_type: experiment`, schema
version 1.0.0 (docs/contracts.md, the experiment manifest). Each run that reaches its end writes
one, last. It records the experiment as the run left it: a run's manifest, with the experiment,
the session, the plan, and the experiment's counts.
"""

import re
from collections import Counter
from typing import Annotated, Final, Literal, Self, TypedDict

from pydantic import ConfigDict, Field, model_validator, with_config

from trialfolio.contracts.common import (
    Approval,
    CommandOutcome,
    ContractModel,
    Count,
    ErrorDetail,
    ExperimentKey,
    IntegerOnly,
    LicenseId,
    NonEmptyText,
    Ordinal,
    RelativePath,
    SemanticVersion,
    Sha256Digest,
    UtcDatetime,
    check_outcome,
    require_unique,
)
from trialfolio.contracts.manifest import (
    AttemptCounts,
    Capabilities,
    ParserVersion,
    Reproducibility,
    SourceRecord,
)

ExperimentArtifactRole = Literal[
    "configuration",
    "plan",
    "experiment_record",
    "authentication_record",
    "start_record",
    "attempt_record",
    "provider_request",
    "provider_response",
    "provider_response_undecoded",
    "metrics",
    "settings",
    "session_record",
    "report",
]

SOURCE_ROLES: Final[frozenset[ExperimentArtifactRole]] = frozenset(
    {"configuration", "provider_request", "provider_response", "provider_response_undecoded"}
)
"""The roles of source artifacts, which carry a source record (INV-04, source artifacts)."""

EXPERIMENT_CONFIGURATION_FORMAT: Final = "experiment-configuration"
"""The format the source record of a plan's `configuration.yaml` gives."""

_PLAN = r"plans/(?P<plan>[1-9][0-9]*)/"
_ATTEMPT = r"cases/case-[0-9a-f]{16}/attempts/[0-9a-f-]{36}/"
_TABLES = r"cases/(?P<case>case-[0-9a-f]{16})/normalized/"
_SESSION = r"sessions/(?P<session>[1-9][0-9]*)/"

_ROLE_PATTERNS: Final[dict[ExperimentArtifactRole, str]] = {
    "configuration": rf"{_PLAN}configuration\.yaml",
    "plan": rf"{_PLAN}plan\.json",
    "experiment_record": rf"{_PLAN}experiment\.json",
    "authentication_record": rf"{_ATTEMPT}authenticating\.json",
    "start_record": rf"{_ATTEMPT}started\.json",
    "attempt_record": rf"{_ATTEMPT}attempt\.json",
    "provider_request": rf"{_ATTEMPT}request\.json",
    "provider_response": rf"{_ATTEMPT}response\.json",
    "provider_response_undecoded": rf"{_ATTEMPT}response\.raw",
    "metrics": rf"{_TABLES}metrics\.csv",
    "settings": rf"{_TABLES}settings\.csv",
    "session_record": rf"{_SESSION}session\.json",
    "report": rf"{_SESSION}report\.html",
}

ROLE_PATHS: Final = {role: re.compile(pattern) for role, pattern in _ROLE_PATTERNS.items()}
"""Where the file of each role is in the experiment's output directory (experiment output)."""

_PLAN_ROLES: Final[frozenset[ExperimentArtifactRole]] = frozenset(
    {"configuration", "plan", "experiment_record"}
)


class ExperimentArtifact(ContractModel):
    """One file of the experiment's records, by path, content address, and role."""

    path: RelativePath
    artifact_id: Sha256Digest
    size: Count
    role: ExperimentArtifactRole
    schema_version: SemanticVersion | None
    """The file's schema version, for files that have one."""
    source: SourceRecord | None
    """Given exactly for source artifacts."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.source is None) == (self.role in SOURCE_ROLES):
            raise ValueError("source must be given exactly for source artifacts")
        if not ROLE_PATHS[self.role].fullmatch(self.path):
            raise ValueError(f"a file of the role {self.role} isn't at this path")
        if (
            self.role == "configuration"
            and self.source is not None
            and (
                self.source.format != EXPERIMENT_CONFIGURATION_FORMAT
                or self.source.parser_version is not None
                or self.source.provenance != "user_supplied"
                or self.source.operation is not None
            )
        ):
            raise ValueError(
                "a configuration's source record gives the experiment-configuration format, "
                "user_supplied provenance, and no parser version or provider operation"
            )
        return self


@with_config(ConfigDict(strict=True, extra="forbid"))
class ExperimentOptions(TypedDict):
    """The run's options. Neither the configuration's path nor `--out` is recorded, because a
    path can name the user. The reason's text is in `experiment.json`, and the repeats are in
    the attempts' `repeat_of`."""

    approve: Sha256Digest | None
    """`--approve`, as given."""
    json: bool
    revision_reason: bool
    """Whether `--revision-reason` was given."""
    repeat: bool
    """Whether `--repeat` was given."""


class ExperimentCommandRecord(ContractModel):
    """The command that ran the session, its non-secret options, and when it started."""

    name: Literal["run"]
    options: ExperimentOptions
    started_at: UtcDatetime


class CaseCounts(ContractModel):
    """The current plan's cases, by outcome. They add up to `planned` (R03-AC08)."""

    planned: Annotated[int, Field(ge=2)]
    succeeded: Count
    failed: Count
    skipped: Count
    """0.3.0 skips no planned case deliberately, so it's 0."""
    unknown: Count
    not_yet_run: Count

    @model_validator(mode="after")
    def _add_up(self) -> Self:
        total = self.succeeded + self.failed + self.skipped + self.unknown + self.not_yet_run
        if total != self.planned:
            raise ValueError(
                "planned must equal succeeded + failed + skipped + unknown + not_yet_run"
            )
        return self


class ExperimentAttemptCounts(AttemptCounts):
    """Every attempt of the experiment, retired cases' included, by outcome, and how many of them
    repeat a case."""

    repeats: Count
    """The attempts that `--repeat` started: those with a `repeat_of`."""

    @model_validator(mode="after")
    def _repeats_are_attempts(self) -> Self:
        if self.repeats > self.succeeded + self.failed + self.unknown + self.running:
            raise ValueError("repeats counts attempts, so it's at most their number")
        return self


class BudgetLimits(ContractModel):
    """The current plan's budget, which bounds the whole experiment."""

    provider_requests: Ordinal
    authentication_calls: Ordinal


class ExperimentManifestCounts(ContractModel):
    """The experiment's counts, across every run of it."""

    cases: CaseCounts
    retired_cases: Count
    """How many cases revisions retired. Their attempts are counted with the others."""
    attempts: ExperimentAttemptCounts
    retries: Annotated[Literal[0], IntegerOnly]
    """Trial Folio never resends a request on its own."""
    provider_requests: Count
    """The sends that may have reached Portfolio123, a `running` attempt counted as one, as the
    budget counts them. A revision may set a budget below them."""
    authentication_calls: Count
    """Trial Folio's own authentication calls, whatever their result, as the budget counts them."""
    budget: BudgetLimits
    cost: Count | None
    """The credits Portfolio123 reported charging; null when it reported none."""


class ExperimentManifest(ContractModel):
    """The manifest a session of an experiment writes last, when it reaches its end."""

    schema_version: Literal["1.0.0"]
    artifact_type: Literal["experiment"]
    trialfolio_version: SemanticVersion
    created_at: UtcDatetime
    experiment_id: ExperimentKey
    session: Ordinal
    """The number of the session that wrote it, in whose directory it is."""
    command: ExperimentCommandRecord | None
    """Null when no `trialfolio` command ran the session, as when the core runs it for another
    interface, or writes a synthetic experiment."""
    synthetic: bool
    """True exactly for an experiment executed with the demo's client, which sends nothing. Its
    values, attempts, and counts are invented."""
    plan: Ordinal
    """The current plan's number."""
    plan_hash: Sha256Digest
    approval: Approval
    """How this run approved the current plan: `not_required` exactly for a synthetic
    experiment."""
    outcome: Literal["completed", "partial"]
    """`completed` when every planned case succeeded, and `partial` otherwise."""
    error: ErrorDetail | None
    """Null when completed, and `execution.partial` when partial."""
    artifacts: tuple[ExperimentArtifact, ...]
    """Every file of the experiment's records: each plan's three files, each attempt's files,
    each case's tables, and this session's record and report. Not `experiment.lock`, `logs/`,
    other sessions' files, or a plan's directory without `experiment.json`."""
    parsers: Annotated[tuple[ParserVersion, ...], Field(min_length=1)]
    """Each parser version that normalized a case's response, or the installed one's when none
    did."""
    license_id: LicenseId
    notice_version: NonEmptyText
    capabilities: Capabilities
    reproducibility: Reproducibility
    """Over the current plan's cases."""
    counts: ExperimentManifestCounts

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        outcome: CommandOutcome = self.outcome
        check_outcome(outcome, self.error)
        cases = self.counts.cases
        if (outcome == "completed") != (cases.succeeded == cases.planned):
            raise ValueError("the outcome is completed exactly when every planned case succeeded")
        if (self.approval == "not_required") != self.synthetic:
            raise ValueError("approval is not_required exactly for a synthetic experiment")
        if self.synthetic and self.command is not None:
            raise ValueError("no trialfolio command writes a synthetic experiment")
        require_unique(tuple(artifact.path for artifact in self.artifacts), "artifact paths")
        require_unique(
            tuple(
                (parser.layout, parser.layout_version, parser.parser_version)
                for parser in self.parsers
            ),
            "parsers",
        )
        self._check_layout()
        return self

    def _check_layout(self) -> None:
        plans: Counter[tuple[str, ExperimentArtifactRole]] = Counter()
        sessions: Counter[ExperimentArtifactRole] = Counter()
        tables: Counter[tuple[str, ExperimentArtifactRole]] = Counter()
        for artifact in self.artifacts:
            # Each artifact checked its path against its role, so each is found.
            found = ROLE_PATHS[artifact.role].fullmatch(artifact.path)
            groups = found.groupdict() if found is not None else {}
            if "plan" in groups:
                if int(groups["plan"]) > self.plan:
                    raise ValueError("no plan is newer than the current plan")
                plans[(groups["plan"], artifact.role)] += 1
            elif "session" in groups:
                if int(groups["session"]) != self.session:
                    raise ValueError("the manifest lists its own session's files, no other's")
                sessions[artifact.role] += 1
            elif "case" in groups:
                tables[(groups["case"], artifact.role)] += 1
        # The first plan is always recorded: a directory without it can't be resumed.
        numbers = {number for number, _ in plans} | {"1", str(self.plan)}
        if any(plans[(number, role)] != 1 for number in numbers for role in _PLAN_ROLES):
            raise ValueError(
                "each plan listed, the first and the current one included, has its "
                "configuration, plan, and experiment record"
            )
        if sessions != Counter({"session_record": 1, "report": 1}):
            raise ValueError("the manifest lists its session's record and report")
        cases = {case for case, _ in tables}
        if any(tables[(case, role)] != 1 for case in cases for role in ("metrics", "settings")):
            raise ValueError("a case has both of its normalized tables, or neither")
