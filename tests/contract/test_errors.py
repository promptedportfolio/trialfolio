"""Trial Folio's errors keep their code and message, and a loggable message that is also their
string form (docs/contracts.md, errors: offending values reach the terminal, never the logs)."""

import copy
import pickle
import traceback
import typing

from trialfolio.errors import EXIT_CODES, ErrorCode, TrialFolioError


def test_every_error_code_has_an_exit_code() -> None:
    assert set(EXIT_CODES) == set(typing.get_args(ErrorCode))


def test_error_survives_pickling_and_copying() -> None:
    error = TrialFolioError("config.invalid", "screen.yaml isn't a valid configuration.")

    for clone in (pickle.loads(pickle.dumps(error)), copy.copy(error), copy.deepcopy(error)):
        assert isinstance(clone, TrialFolioError)
        assert (clone.code, clone.message, clone.log_message, str(clone)) == (
            "config.invalid",
            "screen.yaml isn't a valid configuration.",
            "screen.yaml isn't a valid configuration.",
            "screen.yaml isn't a valid configuration.",
        )


def test_an_errors_string_form_is_its_loggable_message() -> None:
    error = TrialFolioError("config.invalid", "Rejected: canary-value.", "Rejected.")

    for clone in (error, pickle.loads(pickle.dumps(error)), copy.deepcopy(error)):
        assert (clone.message, clone.log_message, str(clone)) == (
            "Rejected: canary-value.",
            "Rejected.",
            "Rejected.",
        )
        # So a logged traceback leaves the terminal's text out too.
        assert "canary-value" not in "".join(traceback.format_exception(clone))
