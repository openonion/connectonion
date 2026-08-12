"""Canonical approval-mode vocabulary and bounded legacy normalization.

The product and ACP surfaces use ``default``, ``auto_approve``, and
``full_access``.  Older persisted sessions and rolling-upgrade clients may
still contain ``safe``, ``accept_edits``, or ``ulw``; those spellings are
accepted only through :func:`legacy_approval_mode_id` and are normalized
before they reach runtime state.
"""

from __future__ import annotations

from typing import Any


DEFAULT_MODE = "default"
AUTO_APPROVE_MODE = "auto_approve"
FULL_ACCESS_MODE = "full_access"

APPROVAL_MODE_IDS = frozenset({
    DEFAULT_MODE,
    AUTO_APPROVE_MODE,
    FULL_ACCESS_MODE,
})

# This is intentionally private: primary code must never emit these values.
_LEGACY_MODE_ALIASES = {
    "safe": DEFAULT_MODE,
    "accept_edits": AUTO_APPROVE_MODE,
    "ulw": FULL_ACCESS_MODE,
}


def approval_mode_id(value: Any) -> str:
    """Return one canonical mode ID or reject it without coercion."""

    if not isinstance(value, str) or value not in APPROVAL_MODE_IDS:
        raise ValueError(f"Unsupported approval mode: {value!r}")
    return value


def legacy_approval_mode_id(value: Any) -> str:
    """Normalize a canonical or legacy boundary value to a canonical ID."""

    if isinstance(value, str):
        value = _LEGACY_MODE_ALIASES.get(value, value)
    return approval_mode_id(value)


def migrate_legacy_full_access_fields(session: dict) -> dict:
    """Rename legacy autonomous-run fields in one detached session copy.

    The caller is responsible for copying the session before invoking this
    helper.  A canonical field always wins if a malformed snapshot contains
    both forms; policy validation still decides whether the resulting grant is
    authorized.
    """

    field_aliases = {
        "ulw_turns": "full_access_turns",
        "ulw_turns_used": "full_access_turns_used",
        "ulw_prompt": "full_access_prompt",
    }
    for legacy, canonical in field_aliases.items():
        if canonical not in session and legacy in session:
            session[canonical] = session[legacy]
        session.pop(legacy, None)
    return session


__all__ = [
    "APPROVAL_MODE_IDS",
    "AUTO_APPROVE_MODE",
    "DEFAULT_MODE",
    "FULL_ACCESS_MODE",
    "approval_mode_id",
    "legacy_approval_mode_id",
    "migrate_legacy_full_access_fields",
]
