"""Canary values for the credentials and for the token the fake server issues (release 0.1.0,
test pairing). Each is distinct, so a test can show that none of them appears where it mustn't.
"""

from typing import Final

API_ID: Final = "canary-api-id-5b1e9c"
API_KEY: Final = "canary-api-key-0f7d2a6e"
TOKEN: Final = "canary-token-93c4be71"
"""The bearer token the fake server issues for a successful authentication."""
