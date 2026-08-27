"""Immutable release coordinates for the ConnectOnion 1.9 browser preview."""

from __future__ import annotations

import os
from urllib.parse import urlparse

RELEASE_CHANNEL = "preview"
ONIONWRIGHT_VERSION = "0.0.13.dev2"
ONIONWRIGHT_ARTIFACT = (
    "onionwright/0.0.13.dev2/onionwright-0.0.13.dev2-py3-none-any.whl"
)
DEFAULT_API_URL = "https://browser-preview.oo.openonion.ai"
API_URL_ENV = "CONNECTONION_BROWSER_PREVIEW_API_URL"


class BrowserPreviewConfigError(ValueError):
    """The explicit preview trust boundary is absent or unsafe."""


def api_url() -> str:
    """Return one HTTPS origin (or loopback HTTP origin for local testing)."""
    value = os.getenv(API_URL_ENV, DEFAULT_API_URL).strip().rstrip("/")
    parsed = urlparse(value)
    loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    allowed_scheme = parsed.scheme == "https" or (parsed.scheme == "http" and loopback)
    if (
        not allowed_scheme
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise BrowserPreviewConfigError(
            f"{API_URL_ENV} must be an HTTPS origin (loopback HTTP is allowed "
            "for local tests)"
        )
    return value
