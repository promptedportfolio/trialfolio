"""docs/contracts.md's experiment example, and the readers the experiment configuration's contract
tests give it: `example`, the example as it's documented, and `documented_examples`, which gives it
with the second example as a whole file; `with_line`, which changes one line of it, or of another
text; `read`, which reads with the 1.0.0 reader; and `rejection`, a `Rejection` of the 1.0.0 reader,
from tests/support/contract_checks.py.

TS-T07 moved them here from tests/contract/test_experiment_configuration.py, when it separated
experiment configuration 1.1.0's tests into tests/contract/test_ranking_configuration.py, which uses
them too (docs/test-refactoring.md, modules to separate).
"""

import re

from tests.support.contract_checks import Rejection
from tests.support.paths import ROOT
from trialfolio.configuration import read_experiment_configuration
from trialfolio.contracts.experiment_configuration import ExperimentConfiguration


def documented_examples() -> tuple[str, str]:
    """The experiment example in docs/contracts.md, and the second example as a whole file: the
    first, with the universe `'Easy to Trade US'` and the second's `variants`."""
    contracts = (ROOT / "docs" / "contracts.md").read_text(encoding="utf-8")
    section = contracts[contracts.index("#### Experiment example") :]
    first, second = re.findall(r"```yaml\n(.*?)```", section, re.DOTALL)[:2]
    whole = first.replace("  universe: 'SP500'\n", "  universe: 'Easy to Trade US'\n")
    whole = whole[: whole.index("variants:\n")] + second + whole[whole.index("budget:\n") :]
    return first, whole


def example() -> str:
    return documented_examples()[0]


rejection = Rejection(read_experiment_configuration, "experiment.yaml")


def with_line(old: str, new: str, text: str | None = None) -> str:
    """The documented example, or `text`, with one line replaced."""
    text = example() if text is None else text
    assert text.count(old) == 1, old
    return text.replace(old, new)


def read(content: str) -> ExperimentConfiguration:
    return read_experiment_configuration(content.encode(), "experiment.yaml")
