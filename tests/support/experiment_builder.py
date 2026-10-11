"""The experiment builder (release 0.3.0, test pairing): writes an experiment with `trialfolio run`,
through the CLI's entry function in the test process, with `--approve` and the hash of the plan
the run builds, the fixed clock, and the fake Portfolio123 server answering each exchange from a
script: Trial Folio's authentication call, then each case's request, with a response from
`responses/` or a failure. It runs the same command, or another, again, so a test can build
several sessions and plans.

It isn't a double: the experiment is real `trialfolio run` output, in the test's temporary
directory. Its values are invented, but nothing labels them synthetic, so it's never committed
(DSC-04). A test stops a run with a `KeyboardInterrupt` from the storage faults by giving the
command its `store_factory`.

R03-T13 wrote it for the command's tests. R03-T11 adds stopping a run with `SIGKILL` under the
test launcher, while the fake server holds a reply.
"""

from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Final, Protocol

from tests.support import canaries
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from trialfolio.configuration import read_experiment_configuration
from trialfolio.experiment_records import read_experiment
from trialfolio.planning import build_experiment_plan, installed_versions, plan_revision
from trialfolio.storage import ArtifactStore, LocalArtifactStore

FIXTURES: Final = Path(__file__).resolve().parents[1] / "fixtures"
EXPERIMENT_CONFIGS: Final = FIXTURES / "experiment-configs"
RESPONSES: Final = FIXTURES / "responses"

AUTHENTICATED: Final = Reply(200, canaries.TOKEN.encode())
"""Portfolio123's answer to a successful authentication: the token."""

UNAVAILABLE: Final = Reply(503, b"")
"""A 5xx to a case's request, which leaves the case `unknown`, possibly charged."""

REJECTED: Final = Reply(400, b"Unsupported value")
"""A 400 to a case's request: `failed`, possibly charged, with
`provider.unsupported_capability`."""

REFUSED: Final = Reply(401, b"")
"""A 401 to Trial Folio's authentication call: `provider.auth_failed`, nothing sent."""


def experiment_config(name: str) -> Path:
    """The experiment configuration `name` in `experiment-configs/`."""
    return EXPERIMENT_CONFIGS / name


def returns(name: str = "complete.json") -> Reply:
    """A 200 whose body is the response fixture `name`."""
    return Reply(200, (RESPONSES / name).read_bytes())


def plan_hash(config: Path, out: Path) -> str:
    """The hash of the plan `trialfolio run` builds from `config` into `out`, with the installed
    versions: a new experiment's, or, when `out` holds an experiment, its current plan's, or the
    revision's. It reads the records without taking the lock."""
    configuration = read_experiment_configuration(config.read_bytes(), str(config))
    versions = installed_versions()
    if not (out / "experiment.lock").is_file():
        return build_experiment_plan(configuration, versions).plan_hash
    saved = read_experiment(LocalArtifactStore(out))
    revision = plan_revision(configuration, versions, saved.plan)
    return saved.plan.plan_hash if revision is None else revision.plan.plan_hash


class Ran(Protocol):
    """What one command did."""

    @property
    def exit_code(self) -> int: ...

    @property
    def stdout(self) -> str: ...

    @property
    def stderr(self) -> str: ...


class Command[R: Ran](Protocol):
    """Runs `trialfolio` with `argv` through its entry function, as the interface tests' `Cli`
    does."""

    def __call__(
        self,
        *argv: str | Path,
        store_factory: Callable[[str], ArtifactStore] = ...,
        clock: Callable[[], datetime] | None = ...,
    ) -> R: ...


class ExperimentBuilder[R: Ran]:
    """Runs `trialfolio run` for an experiment, with the server's replies scripted first."""

    def __init__(self, server: FakePortfolio123, command: Command[R]) -> None:
        self.server = server
        self._command = command

    def run(
        self,
        config: Path,
        out: Path,
        *options: str,
        sends: Sequence[Reply] = (),
        authenticates: Sequence[Reply] | None = None,
        approve: bool = True,
        store_factory: Callable[[str], ArtifactStore] = LocalArtifactStore,
        clock: Callable[[], datetime] | None = None,
    ) -> R:
        """Runs `config` into `out` with `--json` and `options`, and with `--approve` and the hash
        of the plan the run builds, unless `approve` is false. The server first gets `sends`, the
        replies to the cases' requests, in order, and `authenticates`, the replies to Trial
        Folio's authentication calls: one success when it isn't given and a case is sent."""
        if authenticates is None:
            authenticates = (AUTHENTICATED,) if sends else ()
        self.server.reply("/auth", *authenticates)
        self.server.reply("/screen/backtest", *sends)
        argv: list[str | Path] = ["run", config, "--out", out, "--json", *options]
        if approve:
            argv += ["--approve", plan_hash(config, out)]
        return self._command(*argv, store_factory=store_factory, clock=clock)
