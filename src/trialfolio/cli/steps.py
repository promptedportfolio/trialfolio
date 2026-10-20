"""The steps the commands share (docs/contracts.md, CLI behavior and credentials).

`run`, `demo`, and `review` open the same way: the license acknowledgment, then the time the
command started, `opened`; and each command that writes an output directory checks it's absent or
empty first, `empty_store`. The commands that send read the credentials, make Portfolio123's
client, and give the core the ranking lock's file and a definition's bytes; `run` first removes
`SSLKEYLOGFILE` from its environment. `run` and `demo` log each plan they build and approve here.

The modules that import `p123api`, `requests`, or `urllib3` are imported only within the steps
that need them, which run once `installed_versions` has checked them.
"""

import logging
from collections.abc import MutableMapping
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

from trialfolio.cli.invocation import Context, Invocation, event, shown
from trialfolio.cli.license import require_acknowledgment
from trialfolio.configuration import ExperimentConfigurationRead, ScreenConfigurationRead
from trialfolio.contracts.experiment_plan import PlanV1_1, PlanV1_3
from trialfolio.contracts.plan import Plan, PlanV1_2
from trialfolio.errors import TrialFolioError, reason_of
from trialfolio.ranking_lock import ranking_lock_path
from trialfolio.storage import ArtifactStore

if TYPE_CHECKING:
    from trialfolio.provider import Credentials, P123ScreenBacktestClient
    from trialfolio.snapshots import SnapshotFiles

_logger = logging.getLogger("trialfolio.cli")

API_ID_VARIABLE: Final = "TRIALFOLIO_P123_API_ID"
API_KEY_VARIABLE: Final = "TRIALFOLIO_P123_API_KEY"
KEY_LOG_VARIABLE: Final = "SSLKEYLOGFILE"
"""`urllib3` writes TLS session keys to the file it names, so the CLI removes it (credentials)."""


def opened(invocation: Invocation) -> datetime:
    """How `run`, `demo`, and `review` open: the license acknowledgment, which they require before
    they process any data, then when the command started, as the manifest records it, and when it
    acquired the configuration: once the license is acknowledged, before the configuration is
    read, so a run's duration includes planning and any wait for approval."""
    require_acknowledgment(invocation)
    return invocation.context.clock()


def empty_store(context: Context, path: str) -> ArtifactStore:
    """The store of the output directory at `path`, as given, once it's checked absent or empty:
    `output.not_empty` otherwise."""
    store = context.store_factory(path)
    store.check_empty()
    return store


def read_input(path: str) -> bytes:
    """The bytes of the configuration file at `path`: `input.not_found` when it can't be read."""
    try:
        return Path(path).read_bytes()
    except OSError as error:
        reason = reason_of(error)
        raise TrialFolioError(
            "input.not_found",
            f"Couldn't read the configuration file {shown(path)}: {reason}. Check the path."
            " Nothing was sent, and no output was created.",
        ) from None


def plan_built(invocation: Invocation) -> None:
    """Logs `plan.created`, with the command's IDs, which hold the plan's hash."""
    _logger.info("Built the plan.", extra={**event("plan.created", False), **invocation.ids})


def plan_approved(invocation: Invocation, method: str) -> None:
    """Logs `plan.approved`, with how the plan was approved."""
    _logger.info(
        "Plan approved (%s).",
        method,
        extra={**event("plan.approved", False), **invocation.ids},
    )


def ignore_key_log(environ: MutableMapping[str, str]) -> None:
    """Removes `SSLKEYLOGFILE` from the process environment before any request, with a warning,
    so `urllib3` writes no TLS session keys (credentials)."""
    if environ.pop(KEY_LOG_VARIABLE, None) is not None:
        _logger.warning(
            "%s is set, so TLS session keys could be written to a file; Trial Folio ignores it,"
            " and removed it from its own environment. Your shell is unaffected.",
            KEY_LOG_VARIABLE,
            extra={"event": "cli.environment.ignored"},
        )


def read_credentials(environ: MutableMapping[str, str]) -> "Credentials":
    """The credentials, from `TRIALFOLIO_P123_API_ID` and `TRIALFOLIO_P123_API_KEY`:
    `provider.auth_failed` when either is missing or blank."""
    from trialfolio.provider import Credentials

    api_id = environ.get(API_ID_VARIABLE, "")
    api_key = environ.get(API_KEY_VARIABLE, "")
    missing = [
        (name, credential)
        for name, credential, value in (
            (API_ID_VARIABLE, "API ID", api_id),
            (API_KEY_VARIABLE, "API key", api_key),
        )
        if not value.strip()
    ]
    if missing:
        names = " and ".join(name for name, _ in missing)
        credentials = " and ".join(credential for _, credential in missing)
        listed = "lists it" if len(missing) == 1 else "lists both"
        raise TrialFolioError(
            "provider.auth_failed",
            f"Portfolio123 credentials are missing: set {names} to your {credentials}."
            f" Portfolio123's website {listed} under DataMiner & API. Nothing was sent, and no"
            " output was created.",
        )
    return Credentials(api_id, api_key)


def provider_client(
    context: Context, credentials: "Credentials", *, snapshot: bool = False
) -> "P123ScreenBacktestClient":
    """Portfolio123's client, with the credentials, and the endpoint and the timeout tests give.
    `snapshot` is for a ranking snapshot's, whose authentication's messages name its `rank_get`."""
    from trialfolio.provider import REQUEST_TIMEOUT_SECONDS, P123ScreenBacktestClient

    return P123ScreenBacktestClient(
        credentials,
        endpoint=context.endpoint,
        timeout=REQUEST_TIMEOUT_SECONDS if context.timeout is None else context.timeout,
        snapshot=snapshot,
    )


def ranking_lock(context: Context, plan: Plan | PlanV1_2 | PlanV1_1 | PlanV1_3) -> Path | None:
    """The ranking lock's file, which the CLI gives the core for a plan with a ranking
    definition, and only for one: `trialfolio-ranking.lock`, in `TRIALFOLIO_LOCK_DIR` when it's
    set and not empty, and otherwise in `/tmp`, or in `%ProgramData%` on Windows (the ranking
    lock). The core takes it, and gives `experiment.locked` or `storage.write_failed` when it
    can't."""
    if not isinstance(plan, PlanV1_2 | PlanV1_3):
        return None
    return ranking_lock_path(context.environ)


def definition_bytes(
    read: ScreenConfigurationRead | ExperimentConfigurationRead,
) -> tuple[bytes | None, "SnapshotFiles | None"]:
    """The bytes the core copies, as `definition.xml`, and `snapshot.json` for a snapshot, beside
    the plan's `configuration.yaml`: the definition file's that the reader read in step 2, or
    the two files' of the snapshot it read; neither for a ranking given another way. They're the
    bytes the configuration was validated with, never read again (ranking definitions)."""
    if read.snapshot is not None:
        return None, read.snapshot.files
    if read.definition is not None:
        return read.definition.content, None
    return None, None
