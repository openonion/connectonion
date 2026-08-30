"""Immutable release coordinates for the ConnectOnion 1.8 browser preview."""

from __future__ import annotations

import os
from urllib.parse import urlparse

RELEASE_CHANNEL = "preview"
ONIONWRIGHT_VERSION = "0.0.13.dev3"
ONIONWRIGHT_ARTIFACT = (
    "onionwright/0.0.13.dev3/onionwright-0.0.13.dev3-py3-none-any.whl"
)
DEFAULT_API_URL = "https://browser-preview.oo.openonion.ai"
API_URL_ENV = "CONNECTONION_BROWSER_PREVIEW_API_URL"


class BrowserPreviewConfigError(ValueError):
    """The explicit preview trust boundary is absent or unsafe."""


def api_url() -> str:
    """Return the fixed preview origin, or a loopback origin for local testing.

    The CLI loads project ``.env`` files, so permitting an arbitrary remote
    override here would let repository configuration redirect the ambient
    bearer token.  A different hosted origin therefore requires a new
    ConnectOnion release; the environment override is deliberately loopback
    only.
    """
    value = os.getenv(API_URL_ENV, DEFAULT_API_URL).strip().rstrip("/")
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise BrowserPreviewConfigError(
            f"{API_URL_ENV} must be the fixed preview HTTPS origin or a "
            "loopback origin for local tests"
        ) from exc

    default = urlparse(DEFAULT_API_URL)
    loopback = hostname in {"localhost", "127.0.0.1", "::1"}
    fixed_preview = (
        parsed.scheme == "https"
        and hostname == default.hostname
        and (port or 443) == (default.port or 443)
    )
    allowed_origin = fixed_preview or (
        loopback and parsed.scheme in {"http", "https"}
    )
    if (
        not allowed_origin
        or not parsed.netloc
        or hostname is None
        or port == 0
        or parsed.netloc.endswith(":")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise BrowserPreviewConfigError(
            f"{API_URL_ENV} must be the fixed preview HTTPS origin or a "
            "loopback origin for local tests"
        )
    return value
