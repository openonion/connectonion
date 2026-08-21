"""Canonical permission-mode state for ConnectOnion 1.7.

Purpose: define the public mode vocabulary and keep every state transition in
one place. Host/OIP, provider adapters, plugins, React, and O Chat use these
same three IDs; provider-private permission values are translated only at the
provider boundary.

There is deliberately no legacy alias reader. Unknown stored values degrade
to ``auto`` and a malformed Full access grant never skips approval.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping

Mode = Literal["read-only", "auto", "full-access"]

READ_ONLY: Mode = "read-only"
AUTO: Mode = "auto"
FULL_ACCESS: Mode = "full-access"
MODES: tuple[Mode, ...] = (READ_ONLY, AUTO, FULL_ACCESS)
DEFAULT_MODE: Mode = AUTO


def mode_id(value: Any) -> Mode:
    """Return one exact public mode ID or reject it."""

    if value in MODES and isinstance(value, str):
        return value  # type: ignore[return-value]
    raise ValueError(f"Unsupported mode: {value!r}")


def full_access_turns_left(session: Mapping[str, Any]) -> int:
    """Return a valid remaining Full access budget, otherwise zero."""

    value = session.get("turns_left")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return 0
    return value


def mode_of(session: Mapping[str, Any]) -> Mode:
    """Read canonical state, degrading unknown or incomplete state to Auto."""

    try:
        mode = mode_id(session.get("mode", DEFAULT_MODE))
    except ValueError:
        return DEFAULT_MODE
    if mode == FULL_ACCESS and full_access_turns_left(session) == 0:
        return DEFAULT_MODE
    return mode


def set_mode(
    session: dict[str, Any],
    mode: Mode | str,
    *,
    turns_left: int | None = None,
) -> Mode:
    """Write one canonical state.

    This is the only function allowed to assign ``mode`` or ``turns_left``.
    Full access requires a positive bounded budget; the other modes reject a
    budget and remove any stale countdown.
    """

    canonical = mode_id(mode)
    if canonical == FULL_ACCESS:
        if (
            isinstance(turns_left, bool)
            or not isinstance(turns_left, int)
            or turns_left <= 0
        ):
            raise ValueError("full-access requires a positive turns_left budget")
        session["turns_left"] = turns_left
    else:
        if turns_left is not None:
            raise ValueError("turns_left is only valid for full-access")
        session.pop("turns_left", None)
    session["mode"] = canonical
    return canonical


def skips_approval(session: Mapping[str, Any]) -> bool:
    """Return whether the current bounded mode bypasses routine approval."""

    return mode_of(session) == FULL_ACCESS


def consume_full_access_turn(session: dict[str, Any]) -> Mode:
    """Consume one completed user-driven turn and atomically apply expiry.

    Non-Full-access modes are unchanged. A malformed stored Full access value
    is repaired to Auto. A valid countdown either remains Full access with one
    fewer turn or expires to Auto at zero.
    """

    current = mode_of(session)
    if current != FULL_ACCESS:
        if session.get("mode") == FULL_ACCESS:
            return set_mode(session, AUTO)
        return current

    remaining = full_access_turns_left(session) - 1
    if remaining == 0:
        return set_mode(session, AUTO)
    return set_mode(session, FULL_ACCESS, turns_left=remaining)


__all__ = [
    "AUTO",
    "DEFAULT_MODE",
    "FULL_ACCESS",
    "MODES",
    "Mode",
    "READ_ONLY",
    "consume_full_access_turn",
    "full_access_turns_left",
    "mode_id",
    "mode_of",
    "set_mode",
    "skips_approval",
]
