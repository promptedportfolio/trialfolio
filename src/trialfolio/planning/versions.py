"""The versions a plan records, and the check that refuses an environment no release has verified
(docs/contracts.md, plan contents).

`installed_versions` reads the versions a plan records, and refuses an environment no release has
verified, with `environment.unsupported`. `require_verified` refuses versions no release has
verified, which every builder of a plan checks first. `Versions.of` gives the versions a plan
records.
"""

import importlib
import importlib.metadata
import importlib.util
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType, ModuleType
from typing import Final, Literal, Self

from trialfolio.errors import TrialFolioError
from trialfolio.planning.hashing import AnyPlan

type ProviderPackage = Literal["p123api", "requests", "urllib3"]

VERIFIED_VERSIONS: Final[Mapping[ProviderPackage, tuple[str, ...]]] = MappingProxyType(
    {"p123api": ("3.1.0",), "requests": ("2.34.2",), "urllib3": ("2.8.0",)}
)
"""The versions of `p123api`, `requests`, and `urllib3` that a release has verified, which are
the only ones Trial Folio plans with. The package pins each one exactly (plan contents)."""


@dataclass(frozen=True)
class Versions:
    """The versions a plan records: Trial Folio's own, and those of the packages that will send
    its requests."""

    trialfolio: str
    p123api: str
    requests: str
    urllib3: str

    @classmethod
    def of(cls, plan: AnyPlan) -> Self:
        """The versions `plan` records, with which it was built."""
        return cls(
            trialfolio=plan.trialfolio_version,
            p123api=plan.provider_wrapper.p123api,
            requests=plan.transport.requests,
            urllib3=plan.transport.urllib3,
        )


def _verified_list() -> str:
    names = [f"{name} {' or '.join(found)}" for name, found in VERIFIED_VERSIONS.items()]
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def _unsupported(problem: str, remedy: str | None = None) -> TrialFolioError:
    if remedy is None:
        remedy = (
            "Reinstall Trial Folio, whose package pins those versions exactly, for example in a "
            "new virtual environment. If you run it from a copy of its repository, run uv sync "
            "there instead."
        )
    return TrialFolioError(
        "environment.unsupported",
        f"Trial Folio plans only with the versions of p123api, requests, and urllib3 that a "
        f"release has verified: {_verified_list()}. {problem} Nothing was sent, and no output "
        f"was created. {remedy}",
    )


def _metadata_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        raise _unsupported(f"{name} isn't installed.") from None


def _imported(name: str) -> ModuleType:
    # Imported only once their metadata shows a verified version, so a missing package is
    # reported as one, never as an ImportError.
    try:
        return importlib.import_module(name)
    except ImportError:
        raise _unsupported(
            f"{name} is installed, but it can't be imported: its files, or a package it needs, "
            "are missing or broken."
        ) from None


def require_verified(versions: Versions) -> None:
    for name, verified in VERIFIED_VERSIONS.items():
        installed: str = getattr(versions, name)
        if installed not in verified:
            raise _unsupported(f"The installed {name} is {installed}.")


def _simplejson_importable() -> bool:
    try:
        return importlib.util.find_spec("simplejson") is not None
    except (ImportError, ValueError):
        # A module imported without a spec, for example: it's importable.
        return True


def installed_versions() -> Versions:
    """Reads the installed versions from package metadata (plan contents).

    Raises `TrialFolioError` with `environment.unsupported` when `p123api`, `requests`, or
    `urllib3` is missing, isn't a verified version, or can't be imported; when the imported `requests` or `urllib3` reports a `__version__` other than its
    metadata's, as a stale `.dist-info` would; or when `requests` would write request bodies with
    `simplejson` rather than the standard library's `json`, which happens whenever `simplejson` is
    importable.
    """
    versions = Versions(
        trialfolio=_metadata_version("trialfolio"),
        p123api=_metadata_version("p123api"),
        requests=_metadata_version("requests"),
        urllib3=_metadata_version("urllib3"),
    )
    require_verified(versions)
    # urllib3 first: requests imports it, so a broken urllib3 is named as itself.
    for name in ("urllib3", "requests"):
        reported: object = getattr(_imported(name), "__version__", None)
        if reported != getattr(versions, name):
            raise _unsupported(
                f"The imported {name} reports another version than its package metadata, "
                f"{getattr(versions, name)}, so other code may be installed under its name."
            )
    # requests.compat chooses the module requests writes bodies with; it doesn't export the name.
    body_writer: object = getattr(_imported("requests.compat"), "json", None)
    if body_writer is not json or _simplejson_importable():
        raise _unsupported(
            "simplejson is importable here, so requests would write request bodies with it "
            "instead of Python's json, and Trial Folio's rules for decimals are verified only "
            "with json.",
            "Uninstall simplejson from this environment, or run Trial Folio in its own virtual "
            "environment.",
        )
    # Last, because it imports requests and urllib3: a failure here is p123api's own.
    _imported("p123api")
    return versions
