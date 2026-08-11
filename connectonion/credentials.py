"""Non-mutating validation for ambient OpenOnion credentials.

Ambient credentials are convenient, but their source is implicit: package
startup may load a project ``.env`` and then the global ``~/.co/keys.env``.
Before a library call spends credit or reads mail, make sure the selected token
names the identity this project acts as. Explicit ``api_key=`` arguments remain
caller-owned dependency injection and do not pass through this resolver.

This module never authenticates, searches for dotenv files, writes credentials,
or makes a network request. CLI reauthentication is a separate policy layer.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from typing import Any, Mapping

from .project import project_identity


class AmbientCredentialError(ValueError):
    """Base error for an unusable ambient OpenOnion credential."""


class MissingAmbientAPIKey(AmbientCredentialError):
    """No OpenOnion token is available in the process environment."""

    def __init__(self) -> None:
        super().__init__(
            "OpenOnion API key required: OPENONION_API_KEY not found in "
            "environment. Run 'co init' or 'co auth' to authenticate."
        )


class AmbientAPIKeyAccountMismatch(AmbientCredentialError):
    """The ambient token names a different account than the current project."""

    def __init__(self, *, claimed: str, expected: str) -> None:
        self.claimed = claimed
        self.expected = expected
        super().__init__(
            "OPENONION_API_KEY belongs to account "
            f"{_short_address(claimed)}, but this project acts as "
            f"{_short_address(expected)}. Run 'co auth' from this project or "
            "pass an explicit api_key when another account is intentional."
        )


def account_in_token(token: str) -> str | None:
    """Return the public-key claim from a JWT-shaped token, if inspectable.

    This is not authentication. The server still verifies the token signature.
    Local inspection only prevents an implicit credential from silently billing
    or reading mail for a different local project identity.
    """

    if not isinstance(token, str):
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        decoded = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return None
    if not isinstance(decoded, dict):
        return None
    public_key = decoded.get("public_key")
    return public_key if isinstance(public_key, str) and public_key else None


def require_ambient_api_key() -> str:
    """Return the ambient token after checking its local account claim.

    A token with no inspectable account claim is returned unchanged; rejecting
    token formats locally would duplicate server authentication and break
    opaque future formats. A valid claim that conflicts with the canonical
    project identity fails closed before any billed or mailbox request.
    """

    token = os.getenv("OPENONION_API_KEY")
    if not token:
        raise MissingAmbientAPIKey()

    mismatch = api_key_account_mismatch(token, project_identity())
    if mismatch is not None:
        claimed, expected = mismatch
        raise AmbientAPIKeyAccountMismatch(
            claimed=claimed,
            expected=expected,
        )
    return token


def api_key_account_mismatch(
    token: str,
    identity: Any,
) -> tuple[str, str] | None:
    """Return ``(claimed, expected)`` when an inspectable token is foreign.

    Diagnostics use the same comparison as the runtime guard without loading,
    authenticating, or rewriting credentials. Opaque tokens and an unavailable
    local identity cannot be classified here; the server remains authoritative.
    """

    claimed = account_in_token(token)
    expected = _identity_address(identity)
    if (
        claimed is not None
        and expected is not None
        and claimed.casefold() != expected.casefold()
    ):
        return claimed, expected
    return None


def _identity_address(identity: Any) -> str | None:
    if not isinstance(identity, Mapping):
        return None
    value = identity.get("address")
    return value if isinstance(value, str) and value else None


def _short_address(address: str) -> str:
    return f"{address[:16]}…" if len(address) > 16 else address
