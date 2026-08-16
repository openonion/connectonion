"""
Purpose: Durable, authority-bounded Host session mode transactions
LLM-Note:
  Dependencies: imports from [core.approval_modes, .storage, copy, dataclasses, time] | imported by [host/ws_router/connect.py, host/ws_router/session.py, host/http_router.py]
  Data flow: CONNECT -> ensure_host_mode_session() appends an owned :read-only snapshot when needed -> CONNECTED advertises policy.state() | OIP mode setter -> commit_host_session_mode() checks process-local busy state -> storage.atomic_update() rechecks durable owner/status and appends a detached policy copy -> caller acknowledges and updates conn
  State/Effects: appends Session records through SessionStorage.atomic_update; never mutates caller or stored dictionaries before commit
  Integration: HostModePolicy captures the launch-time Full access ceiling and derives identity-bounded mode lists; ModeTransactionError carries owned JSON-RPC errors
  Errors: missing/wrong owner=-32002, busy=-32000 retryable, invalid/unavailable=-32602; storage exceptions deliberately propagate for -32603 mapping at the carrier boundary
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from typing import Any

from ....core.approval_modes import (
    DANGER_FULL_ACCESS_PERMISSION_PROFILE,
    READ_ONLY_PERMISSION_PROFILE,
    WORKSPACE_PERMISSION_PROFILE,
    legacy_permission_profile_id,
    migrate_legacy_full_access_fields,
)
from .storage import Session, SessionStorage, session_owner

_FULL_ACCESS_FIELDS = (
    "skip_tool_approval",
    "full_access_turns",
    "full_access_turns_used",
)
SERVER_OWNED_SESSION_KEYS = (
    "mode",
    *_FULL_ACCESS_FIELDS,
    "permissions",
    "approval",
    # A 1.6.11 rolling-build policy field.  The OIP mode transaction does not
    # read it, but it must not be client-authored while older adapters can
    # still restore it.
    "approval_profile",
    # Obsolete rolling-build marker.  It is deliberately dropped rather than
    # restored so a browser can never choose its authorization default.
    "_new_session",
    "requester",
)


class ModeTransactionError(Exception):
    """A client-owned policy failure safe to expose through JSON-RPC."""

    def __init__(
        self,
        code: int,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


@dataclass(frozen=True)
class HostPermissionPolicy:
    """Available Codex-style profiles below Host launch authority."""

    full_access_turns: int | None = None

    def __post_init__(self) -> None:
        if self.full_access_turns is not None and (
            isinstance(self.full_access_turns, bool)
            or not isinstance(self.full_access_turns, int)
            or self.full_access_turns <= 0
        ):
            raise ValueError("Full access launch ceiling must be a positive integer")

    def available_profile_ids(self, *, is_admin: bool) -> tuple[str, ...]:
        if not is_admin:
            return (READ_ONLY_PERMISSION_PROFILE,)
        if self.full_access_turns is None:
            return (READ_ONLY_PERMISSION_PROFILE, WORKSPACE_PERMISSION_PROFILE)
        return (
            READ_ONLY_PERMISSION_PROFILE,
            WORKSPACE_PERMISSION_PROFILE,
            DANGER_FULL_ACCESS_PERMISSION_PROFILE,
        )

    # Compatibility for callers compiled against the previous draft API.
    def available_mode_ids(self, *, is_admin: bool) -> tuple[str, ...]:
        return self.available_profile_ids(is_admin=is_admin)

    def state(self, session: dict, *, is_admin: bool) -> dict[str, Any]:
        normalized = self.normalized(session, is_admin=is_admin)
        available = self.available_profile_ids(is_admin=is_admin)
        names = {
            READ_ONLY_PERMISSION_PROFILE: "Read only",
            WORKSPACE_PERMISSION_PROFILE: "Auto",
            DANGER_FULL_ACCESS_PERMISSION_PROFILE: "Full access",
        }
        return {
            "currentModeId": normalized["mode"],
            "availableModes": [
                {"id": mode_id, "name": names[mode_id]} for mode_id in available
            ],
        }

    def normalized(self, session: dict, *, is_admin: bool) -> dict:
        """Return a detached validated snapshot or fail closed."""
        normalized = copy.deepcopy(session)
        migrate_legacy_full_access_fields(normalized)
        raw_profile = normalized.get(
            "permission_profile", normalized.get("mode", READ_ONLY_PERMISSION_PROFILE)
        )
        try:
            profile = legacy_permission_profile_id(raw_profile)
        except ValueError as exc:
            raise ModeTransactionError(-32602, str(exc)) from None
        if profile not in self.available_profile_ids(is_admin=is_admin):
            raise ModeTransactionError(
                -32602, "Permission profile is not available"
            )
        if profile == DANGER_FULL_ACCESS_PERMISSION_PROFILE:
            self._validate_full_access(normalized)
        elif any(field in normalized for field in _FULL_ACCESS_FIELDS):
            raise ModeTransactionError(
                -32602,
                "Session has Full access authority outside the Full access profile",
            )
        normalized["mode"] = profile
        normalized.pop("permission_profile", None)
        return normalized

    def apply(self, session: dict, profile_id: Any, *, is_admin: bool) -> dict:
        """Apply one validated permission profile to a detached copy."""
        try:
            profile = legacy_permission_profile_id(profile_id)
        except ValueError as exc:
            raise ModeTransactionError(-32602, str(exc)) from None
        if profile not in self.available_profile_ids(is_admin=is_admin):
            raise ModeTransactionError(
                -32602, "Permission profile is not available"
            )
        changed = copy.deepcopy(session)
        for field in _FULL_ACCESS_FIELDS:
            changed.pop(field, None)
        changed["mode"] = profile
        changed.pop("permission_profile", None)
        if profile == DANGER_FULL_ACCESS_PERMISSION_PROFILE:
            changed["full_access_turns"] = self.full_access_turns
            changed["full_access_turns_used"] = 0
            changed["skip_tool_approval"] = True
        return self.normalized(changed, is_admin=is_admin)

    def _validate_full_access(self, session: dict) -> None:
        turns = session.get("full_access_turns")
        used = session.get("full_access_turns_used")
        if (
            self.full_access_turns is None
            or isinstance(turns, bool)
            or not isinstance(turns, int)
            or turns <= 0
            or isinstance(used, bool)
            or not isinstance(used, int)
            or used < 0
            or used >= turns
            or turns - used > self.full_access_turns
            or session.get("skip_tool_approval") is not True
        ):
            raise ModeTransactionError(-32602, "Session has invalid Full access state")


def ensure_host_mode_session(
    storage: SessionStorage,
    session_id: str,
    *,
    requester: dict,
    result_ttl: int,
    policy: HostPermissionPolicy,
    is_admin: bool,
) -> Session:
    """Persist an owned read-only snapshot before a Host session's first prompt."""
    owner = requester.get("address")
    if not isinstance(owner, str) or not owner:
        raise ValueError("requester address is required")

    def ensure(current: Session | None) -> Session:
        if current is None:
            now = time.time()
            return Session(
                session_id=session_id,
                status="connected",
                prompt="",
                session=_fresh_session(session_id, requester),
                created=now,
                expires=now + result_ttl,
            )
        existing_owner = session_owner(current)
        if existing_owner and existing_owner != owner:
            raise _not_found()
        session = policy.normalized(
            current.session or _fresh_session(session_id, requester),
            is_admin=is_admin,
        )
        session["session_id"] = session_id
        if not existing_owner:
            session["requester"] = copy.deepcopy(requester)
        return current.model_copy(update={"session": session})

    return storage.atomic_update(session_id, ensure)


def commit_host_session_mode(
    storage: SessionStorage,
    registry,
    session_id: str,
    owner: str,
    mode_id: Any,
    policy: HostPermissionPolicy,
    is_admin: bool,
) -> Session:
    """Commit one idle policy change under the cross-worker storage lock."""
    active = registry.get(session_id) if registry is not None else None
    if active is not None and getattr(active, "owner", None) not in (None, owner):
        raise _not_found()
    if active is not None and getattr(active, "status", None) == "running":
        raise _busy()

    def commit(current: Session | None) -> Session:
        if current is None or session_owner(current) != owner:
            raise _not_found()
        if current.status in SessionStorage.UNFINISHED:
            raise _busy()
        session = policy.normalized(current.session or {}, is_admin=is_admin)
        session = policy.apply(session, mode_id, is_admin=is_admin)
        return current.model_copy(update={"session": session})

    return storage.atomic_update(session_id, commit)


def session_with_durable_policy(client_session: dict | None, durable: dict) -> dict:
    """Keep client conversation fields but replace every server policy field."""
    merged = copy.deepcopy(client_session or {})
    for field in SERVER_OWNED_SESSION_KEYS:
        merged.pop(field, None)
        if field in durable:
            merged[field] = copy.deepcopy(durable[field])
    # ``_new_session`` belonged only to the pre-OIP draft policy and must not
    # survive either a client round-trip or an old durable snapshot.
    merged.pop("_new_session", None)
    if durable.get("session_id"):
        merged["session_id"] = durable["session_id"]
    return merged


def claim_host_prompt(
    storage: SessionStorage,
    session_id: str,
    prompt: str,
    result_ttl: int,
    client_session: dict,
    *,
    requester: dict | None,
    policy: HostPermissionPolicy | None,
    is_admin: bool,
) -> tuple[Session, bool]:
    """Atomically claim an idle session and return its prepared prompt state."""
    server_newer = False

    def claim(current: Session | None) -> Session:
        nonlocal server_newer
        owner = session_owner(current)
        address = requester.get("address") if requester else None
        if owner and owner != address:
            raise _not_found()
        if current is not None and current.status in SessionStorage.UNFINISHED:
            raise _busy()

        session = copy.deepcopy(client_session)
        durable = current.session if current and current.session else {}
        if durable:
            from .merge import merge_sessions

            session, server_newer = merge_sessions(
                client_session=session,
                server_session=durable,
            )
        session = session_with_durable_policy(session, durable)
        session["session_id"] = session_id
        session.setdefault("messages", [])
        session.setdefault("trace", [])
        session.setdefault("turn", 0)
        if requester is not None:
            session["requester"] = copy.deepcopy(requester)
        else:
            session.pop("requester", None)
        if policy is not None:
            session = policy.normalized(session, is_admin=is_admin)

        now = time.time()
        return Session(
            session_id=session_id,
            status="running",
            prompt=prompt,
            session=session,
            created=now,
            expires=now + result_ttl,
        )

    return storage.atomic_update(session_id, claim), server_newer


def _fresh_session(session_id: str, requester: dict) -> dict:
    return {
        "session_id": session_id,
        "messages": [],
        "trace": [],
        "turn": 0,
        "mode": READ_ONLY_PERMISSION_PROFILE,
        "requester": copy.deepcopy(requester),
    }


# One release-window source alias.  New code should use HostPermissionPolicy.
HostModePolicy = HostPermissionPolicy


def _not_found() -> ModeTransactionError:
    return ModeTransactionError(-32002, "Session not found")


def _busy() -> ModeTransactionError:
    return ModeTransactionError(
        -32000, "Session is busy", {"retryable": True}
    )
