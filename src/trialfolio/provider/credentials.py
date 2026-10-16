"""The Portfolio123 credentials the client authenticates with (docs/contracts.md, credentials;
REQ-09, INV-11)."""

from trialfolio.errors import TrialFolioError


class Credentials:
    """A Portfolio123 API ID and API key (docs/contracts.md, credentials; REQ-09, INV-11).

    A credential object is never serialized, hashed, logged, or written to an artifact. Its repr
    shows neither value, and pickling or copying it raises `TypeError`.
    """

    __slots__ = ("_api_id", "_api_key")

    def __init__(self, api_id: str, api_key: str) -> None:
        """Raises `TrialFolioError` with `provider.auth_failed` if either value is blank."""
        if not api_id.strip() or not api_key.strip():
            raise TrialFolioError(
                "provider.auth_failed",
                "Portfolio123 credentials are missing: Trial Folio needs both an API ID and an "
                "API key. Portfolio123's website lists them under DataMiner & API.",
            )
        self._api_id = api_id
        self._api_key = api_key

    @property
    def api_id(self) -> str:
        return self._api_id

    @property
    def api_key(self) -> str:
        return self._api_key

    def __repr__(self) -> str:
        return "Credentials(api_id=<redacted>, api_key=<redacted>)"

    def __reduce__(self) -> tuple[object, ...]:
        raise TypeError("credentials are never serialized or copied")
