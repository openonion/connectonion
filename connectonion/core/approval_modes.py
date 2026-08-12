"""Codex-aligned collaboration and permission-profile vocabulary.

Codex keeps collaboration intent (``default`` / ``plan``) separate from the
permission profile that bounds tool execution.  ConnectOnion mirrors that
shape while retaining one compatibility reader for snapshots written with the
older ``safe`` / ``accept_edits`` / ``ulw`` approval-mode vocabulary.

The module name remains ``approval_modes`` for one import-compatibility window;
new code should use the collaboration/profile names exported below.
"""

from __future__ import annotations

from typing import Any, Mapping

DEFAULT_COLLABORATION_MODE = "default"
PLAN_COLLABORATION_MODE = "plan"
COLLABORATION_MODE_IDS = frozenset({
    DEFAULT_COLLABORATION_MODE,
    PLAN_COLLABORATION_MODE,
})

READ_ONLY_PERMISSION_PROFILE = ":read-only"
WORKSPACE_PERMISSION_PROFILE = ":workspace"
DANGER_FULL_ACCESS_PERMISSION_PROFILE = ":danger-full-access"
PERMISSION_PROFILE_IDS = frozenset({
    READ_ONLY_PERMISSION_PROFILE,
    WORKSPACE_PERMISSION_PROFILE,
    DANGER_FULL_ACCESS_PERMISSION_PROFILE,
})

# Primary code never emits these values.  ``default`` / ``auto_approve`` /
# ``full_access`` were prepared in an unreleased migration branch, so accepting
# them here also makes rolling draft builds fail closed during review.
_LEGACY_PERMISSION_PROFILE_ALIASES = {
    "safe": READ_ONLY_PERMISSION_PROFILE,
    "default": READ_ONLY_PERMISSION_PROFILE,
    "accept_edits": WORKSPACE_PERMISSION_PROFILE,
    "auto_approve": WORKSPACE_PERMISSION_PROFILE,
    "ulw": DANGER_FULL_ACCESS_PERMISSION_PROFILE,
    "full_access": DANGER_FULL_ACCESS_PERMISSION_PROFILE,
}


def collaboration_mode_id(value: Any) -> str:
    """Return one canonical collaboration mode or reject it."""

    if not isinstance(value, str) or value not in COLLABORATION_MODE_IDS:
        raise ValueError(f"Unsupported collaboration mode: {value!r}")
    return value


def permission_profile_id(value: Any) -> str:
    """Return one canonical Codex-compatible permission profile or reject it."""

    if not isinstance(value, str) or value not in PERMISSION_PROFILE_IDS:
        raise ValueError(f"Unsupported permission profile: {value!r}")
    return value


def legacy_permission_profile_id(value: Any) -> str:
    """Normalize one canonical or previous boundary value."""

    if isinstance(value, str):
        value = _LEGACY_PERMISSION_PROFILE_ALIASES.get(value, value)
    return permission_profile_id(value)


def migrate_legacy_full_access_fields(session: dict) -> dict:
    """Rename previous autonomous-run fields in one detached session copy."""

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
        session.get("mode") == DANGER_FULL_ACCESS_PERMISSION_PROFILE
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

    Direct ``Agent.input(session=...)`` restoration has no transaction to
    reject.  Previous fields are therefore normalized, while unknown or
    inconsistent authority falls back to the read-only profile before any
    hook, model call, or tool can run.
    """

    normalized = dict(session)
    migrate_legacy_full_access_fields(normalized)

    raw_profile = normalized.get(
        "permission_profile", normalized.get("mode", READ_ONLY_PERMISSION_PROFILE)
    )
    if raw_profile == PLAN_COLLABORATION_MODE:
        raw_profile = READ_ONLY_PERMISSION_PROFILE
    try:
        profile = legacy_permission_profile_id(raw_profile)
    except ValueError:
        profile = READ_ONLY_PERMISSION_PROFILE

    full_access_fields = (
        "skip_tool_approval",
        "full_access_turns",
        "full_access_turns_used",
        "full_access_prompt",
    )
    normalized["mode"] = profile
    normalized.pop("permission_profile", None)
    if (
        profile == DANGER_FULL_ACCESS_PERMISSION_PROFILE
        and not has_valid_full_access_grant(normalized)
    ):
        profile = READ_ONLY_PERMISSION_PROFILE

    if profile != DANGER_FULL_ACCESS_PERMISSION_PROFILE:
        for field in full_access_fields:
            normalized.pop(field, None)
    normalized["mode"] = profile
    return normalized


# Deprecated source aliases.  Compatibility callers may still import these,
# but primary protocol/runtime code uses the names above.
DEFAULT_MODE = READ_ONLY_PERMISSION_PROFILE
AUTO_APPROVE_MODE = WORKSPACE_PERMISSION_PROFILE
FULL_ACCESS_MODE = DANGER_FULL_ACCESS_PERMISSION_PROFILE
APPROVAL_MODE_IDS = PERMISSION_PROFILE_IDS
approval_mode_id = permission_profile_id
legacy_approval_mode_id = legacy_permission_profile_id


__all__ = [
    "COLLABORATION_MODE_IDS",
    "DANGER_FULL_ACCESS_PERMISSION_PROFILE",
    "DEFAULT_COLLABORATION_MODE",
    "PERMISSION_PROFILE_IDS",
    "PLAN_COLLABORATION_MODE",
    "READ_ONLY_PERMISSION_PROFILE",
    "WORKSPACE_PERMISSION_PROFILE",
    "collaboration_mode_id",
    "has_valid_full_access_grant",
    "legacy_permission_profile_id",
    "migrate_legacy_full_access_fields",
    "normalize_runtime_approval_session",
    "permission_profile_id",
]
