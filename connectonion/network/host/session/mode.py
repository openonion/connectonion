"""
Purpose: Durable, authority-bounded Host session mode transactions
LLM-Note:
  Dependencies: imports from [core.acp_wire, .storage, copy, dataclasses, time] | imported by [host/ws_router/connect.py, host/ws_router/session.py, host/http_router.py] | tested by [tests/unit/test_acp_host_set_mode.py]
  Data flow: CONNECT -> ensure_host_mode_session() appends an owned Safe snapshot when needed -> CONNECTED advertises policy.state() | ACP/legacy setter -> commit_host_session_mode() checks process-local busy state -> storage.atomic_update() rechecks durable owner/status and appends a detached policy copy -> caller acknowledges and updates conn
  State/Effects: appends Session records through SessionStorage.atomic_update; never mutates caller or stored dictionaries before commit
  Integration: HostModePolicy captures the launch-time ULW ceiling and derives identity-bounded mode lists; ModeTransactionError carries owned JSON-RPC errors
  Errors: missing/wrong owner=-32002, busy=-32000 retryable, invalid/unavailable=-32602; storage exceptions deliberately propagate for -32603 mapping at the carrier boundary
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from typing import Any

from ....core.acp_wire import acp_session_mode_state, session_mode_id
from .storage import Session, SessionStorage, session_owner

_ULW_FIELDS = ("skip_tool_approval", "ulw_turns", "ulw_turns_used")
SERVER_OWNED_SESSION_KEYS = (
    "mode", *_ULW_FIELDS, "permissions", "approval", "requester"
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
class HostModePolicy:
    """Available Host modes below identity and Agent launch authority."""

    ulw_turns: int | None = None

    def __post_init__(self) -> None:
        if self.ulw_turns is not None and (
            isinstance(self.ulw_turns, bool)
            or not isinstance(self.ulw_turns, int)
            or self.ulw_turns <= 0
        ):
            raise ValueError("ULW launch ceiling must be a positive integer")

    def available_mode_ids(self, *, is_admin: bool) -> tuple[str, ...]:
        if not is_admin:
            return ("safe",)
        if self.ulw_turns is None:
            return ("safe", "accept_edits")
        return ("safe", "accept_edits", "ulw")

    def state(self, session: dict, *, is_admin: bool) -> dict[str, Any]:
        normalized = self.normalized(session, is_admin=is_admin)
        return acp_session_mode_state(
            normalized["mode"], self.available_mode_ids(is_admin=is_admin)
        )

    def normalized(self, session: dict, *, is_admin: bool) -> dict:
        """Return a detached validated snapshot or fail closed."""
        normalized = copy.deepcopy(session)
        mode = normalized.get("mode", "safe")
        try:
            mode = session_mode_id(mode)
        except ValueError as exc:
            raise ModeTransactionError(-32602, str(exc)) from None
        if mode not in self.available_mode_ids(is_admin=is_admin):
            raise ModeTransactionError(-32602, "Session mode is not available")
        if mode == "ulw":
            self._validate_ulw(normalized)
        elif any(field in normalized for field in _ULW_FIELDS):
            raise ModeTransactionError(
                -32602, "Session has ULW authority outside ULW mode"
            )
        normalized["mode"] = mode
        return normalized

    def apply(self, session: dict, mode_id: Any, *, is_admin: bool) -> dict:
        """Apply one validated mode to a detached copy."""
        try:
            mode = session_mode_id(mode_id)
        except ValueError as exc:
            raise ModeTransactionError(-32602, str(exc)) from None
        if mode not in self.available_mode_ids(is_admin=is_admin):
            raise ModeTransactionError(-32602, "Session mode is not available")
        changed = copy.deepcopy(session)
        for field in _ULW_FIELDS:
            changed.pop(field, None)
        changed["mode"] = mode
        if mode == "ulw":
            changed["ulw_turns"] = self.ulw_turns
            changed["ulw_turns_used"] = 0
            changed["skip_tool_approval"] = True
        return self.normalized(changed, is_admin=is_admin)

    def _validate_ulw(self, session: dict) -> None:
        turns = session.get("ulw_turns")
        used = session.get("ulw_turns_used")
        if (
            self.ulw_turns is None
            or isinstance(turns, bool)
            or not isinstance(turns, int)
            or turns <= 0
            or isinstance(used, bool)
            or not isinstance(used, int)
            or used < 0
            or used >= turns
            or turns - used > self.ulw_turns
            or session.get("skip_tool_approval") is not True
        ):
            raise ModeTransactionError(-32602, "Session has invalid ULW state")


def ensure_host_mode_session(
    storage: SessionStorage,
    session_id: str,
    *,
    requester: dict,
    result_ttl: int,
    policy: HostModePolicy,
    is_admin: bool,
) -> Session:
    """Persist an owned Safe snapshot before a Host session's first prompt."""
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
    policy: HostModePolicy,
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
    policy: HostModePolicy | None,
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
        "mode": "safe",
        "requester": copy.deepcopy(requester),
    }


def _not_found() -> ModeTransactionError:
    return ModeTransactionError(-32002, "Session not found")


def _busy() -> ModeTransactionError:
    return ModeTransactionError(
        -32000, "Session is busy", {"retryable": True}
    )
