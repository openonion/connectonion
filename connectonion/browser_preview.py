"""Immutable release coordinates for the ConnectOnion 1.8 browser preview."""

from __future__ import annotations

RELEASE_CHANNEL = "preview"
ONIONWRIGHT_VERSION = "0.0.13.dev3"
ONIONWRIGHT_ARTIFACT = (
    "onionwright/0.0.13.dev3/onionwright-0.0.13.dev3-py3-none-any.whl"
)
DEFAULT_API_URL = "https://browser-preview.oo.openonion.ai"


def api_url() -> str:
    """Return the one origin trusted by these immutable preview bytes.

    ConnectOnion loads project ``.env`` files before this module is imported.
    Any environment override, including a loopback-only one, would therefore
    let an untrusted repository receive the user's ambient bearer token.  Local
    integration tests replace this function explicitly instead of widening the
    shipped credential boundary.
    """
    return DEFAULT_API_URL
