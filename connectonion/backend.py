"""One source of truth for the ConnectOnion service origin.

Every network client must use :func:`backend_url`.  Previously three email
modules honoured ``CONNECTONION_BACKEND_URL`` while auth, models, deploys and
the other clients silently kept talking to production (#733).
"""

from __future__ import annotations

import os


DEFAULT_BACKEND_URL = "https://oo.openonion.ai"
_LEGACY_ENV_VARS = ("OPENONION_API_URL", "OPENONION_BASE_URL")


def backend_url() -> str:
    """Return the common HTTP origin, without a trailing slash.

    ``CONNECTONION_BACKEND_URL`` is canonical.  The two older variable names
    remain aliases, but because every caller resolves them here they can no
    longer redirect only Drive/Calendar or only trust checks.  An explicit URL
    wins over the development shortcut.
    """
    configured = os.getenv("CONNECTONION_BACKEND_URL")
    if not configured:
        for name in _LEGACY_ENV_VARS:
            configured = os.getenv(name)
            if configured:
                break
    if configured:
        return configured.rstrip("/")
    if os.getenv("OPENONION_DEV") or os.getenv("ENVIRONMENT") == "development":
        return "http://localhost:8000"
    return DEFAULT_BACKEND_URL


def backend_ws_url() -> str:
    """Return the configured origin as a WebSocket base URL."""
    return backend_url().replace("https://", "wss://", 1).replace("http://", "ws://", 1)
