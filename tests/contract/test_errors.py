"""Trial Folio's errors keep their code and message (docs/contracts.md, errors)."""

import copy
import pickle
import typing

from trialfolio.errors import EXIT_CODES, ErrorCode, TrialFolioError


def test_every_error_code_has_an_exit_code() -> None:
    assert set(EXIT_CODES) == set(typing.get_args(ErrorCode))


def test_error_survives_pickling_and_copying() -> None:
    error = TrialFolioError("config.invalid", "screen.yaml isn't a valid configuration.")

    for clone in (pickle.loads(pickle.dumps(error)), copy.copy(error), copy.deepcopy(error)):
        assert isinstance(clone, TrialFolioError)
        assert (clone.code, clone.message, str(clone)) == (
            "config.invalid",
            "screen.yaml isn't a valid configuration.",
            "screen.yaml isn't a valid configuration.",
        )
