"""Canonical approval-mode vocabulary and bounded legacy normalization.

The product and ACP surfaces use ``default``, ``auto_approve``, and
``full_access``.  Older persisted sessions and rolling-upgrade clients may
still contain ``safe``, ``accept_edits``, or ``ulw``; those spellings are
accepted only through :func:`legacy_approval_mode_id` and are normalized
before they reach runtime state.
"""

from __future__ import annotations

from typing import Any, Mapping

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


def has_valid_full_access_grant(session: Mapping[str, Any]) -> bool:
    """Return whether one session carries a complete bounded bypass grant."""

    turns = session.get("full_access_turns")
    used = session.get("full_access_turns_used")
    return (
        session.get("mode") == FULL_ACCESS_MODE
        and not isinstance(turns, bool)
        and isinstance(turns, int)
        and turns > 0
        and not isinstance(used, bool)
        and isinstance(used, int)
        and 0 <= used < turns
        and session.get("skip_tool_approval") is True
    )


def normalize_runtime_approval_session(session: dict) -> dict:
    """Return canonical local Agent state, removing malformed authority.

    Host and ACP persistence use their stricter policy validators and reject a
    corrupt snapshot.  A direct ``Agent.input(session=...)`` restoration has no
    transaction to reject, so it takes the fail-closed local behavior: legacy
    fields migrate, while unknown modes or inconsistent Full access state are
    reduced to Default before any hook, model call, or tool can run.
    """

    normalized = dict(session)
    migrate_legacy_full_access_fields(normalized)
    raw_mode = normalized.get("mode", DEFAULT_MODE)
    if raw_mode == "plan":
        mode = DEFAULT_MODE
    else:
        try:
            mode = legacy_approval_mode_id(raw_mode)
        except ValueError:
            mode = DEFAULT_MODE

    full_access_fields = (
        "skip_tool_approval",
        "full_access_turns",
        "full_access_turns_used",
        "full_access_prompt",
    )
    normalized["mode"] = mode
    if mode == FULL_ACCESS_MODE:
        if not has_valid_full_access_grant(normalized):
            mode = DEFAULT_MODE

    if mode != FULL_ACCESS_MODE:
        for field in full_access_fields:
            normalized.pop(field, None)
    normalized["mode"] = mode
    return normalized


__all__ = [
    "APPROVAL_MODE_IDS",
    "AUTO_APPROVE_MODE",
    "DEFAULT_MODE",
    "FULL_ACCESS_MODE",
    "approval_mode_id",
    "has_valid_full_access_grant",
    "legacy_approval_mode_id",
    "migrate_legacy_full_access_fields",
    "normalize_runtime_approval_session",
]
