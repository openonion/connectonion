"""Durable, authority-bounded Host permission-mode transactions."""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from typing import Any

from ....core.mode import (
    AUTO,
    FULL_ACCESS,
    READ_ONLY,
    full_access_turns_left,
    mode_id,
    mode_of,
    set_mode,
)
from ....core.provider_permissions import reconcile_provider_permission_events
from .storage import Session, SessionStorage, session_owner

_DISCARDED_MODE_KEYS = {
    "_new_session",
    "approval_profile",
    "full_access_prompt",
    "full_access_turns",
    "full_access_turns_used",
    "permission_profile",
    "skip_tool_approval",
    "ulw_prompt",
    "ulw_turns",
    "ulw_turns_used",
    "workflow_mode",
}
SERVER_OWNED_SESSION_KEYS = (
    "mode",
    "turns_left",
    "permissions",
    "approval",
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
    """Available public modes below the Host Full access ceiling."""

    full_access_turns: int | None = None

    def __post_init__(self) -> None:
        if self.full_access_turns is not None and (
            isinstance(self.full_access_turns, bool)
            or not isinstance(self.full_access_turns, int)
            or self.full_access_turns <= 0
        ):
            raise ValueError("Full access launch ceiling must be a positive integer")

    def available_mode_ids(self, *, is_admin: bool) -> tuple[str, ...]:
        """Return ordinary modes equally for every authenticated participant."""

        del is_admin
        if self.full_access_turns is None:
            return (READ_ONLY, AUTO)
        return (READ_ONLY, AUTO, FULL_ACCESS)

    def state(self, session: dict, *, is_admin: bool) -> dict[str, Any]:
        normalized = self.normalized(session, is_admin=is_admin)
        available = self.available_mode_ids(is_admin=is_admin)
        names = {
            READ_ONLY: "Read only",
            AUTO: "Auto",
            FULL_ACCESS: "Full access",
        }
        return {
            "currentModeId": normalized["mode"],
            "turnsLeft": normalized.get("turns_left"),
            "availableModes": [
                {"id": current, "name": names[current]} for current in available
            ],
        }

    def normalized(
        self,
        session: dict,
        *,
        is_admin: bool,
        reconcile_provider_permissions: bool = True,
    ) -> dict:
        """Return a detached 1.7 snapshot; old/invalid authority becomes Auto."""

        del is_admin
        normalized = copy.deepcopy(session)
        canonical = mode_of(normalized)
        remaining = full_access_turns_left(normalized)
        for key in _DISCARDED_MODE_KEYS:
            normalized.pop(key, None)

        if (
            canonical == FULL_ACCESS
            and self.full_access_turns is not None
            and remaining <= self.full_access_turns
        ):
            set_mode(normalized, FULL_ACCESS, turns_left=remaining)
        else:
            set_mode(normalized, canonical if canonical != FULL_ACCESS else AUTO)
        if reconcile_provider_permissions:
            reconcile_provider_permission_events(normalized, mode_of(normalized))
        return normalized

    def apply(self, session: dict, requested_mode: Any, *, is_admin: bool) -> dict:
        """Apply one exact client request to a detached canonical snapshot."""

        try:
            canonical = mode_id(requested_mode)
        except ValueError as exc:
            raise ModeTransactionError(-32602, str(exc)) from None
        if canonical not in self.available_mode_ids(is_admin=is_admin):
            raise ModeTransactionError(-32602, "Permission mode is not available")

        # A mode write is one authority transaction. Reconciling against the
        # old ceiling first would append an intermediate provider snapshot and
        # stream it before the final, narrower snapshot. Normalize the rest of
        # the durable policy without publishing provider authority, commit the
        # requested mode, then reconcile exactly once against that final mode.
        changed = self.normalized(
            session,
            is_admin=is_admin,
            reconcile_provider_permissions=False,
        )
        if canonical == FULL_ACCESS:
            set_mode(
                changed,
                FULL_ACCESS,
                turns_left=self.full_access_turns,
            )
        else:
            set_mode(changed, canonical)
        reconcile_provider_permission_events(changed, mode_of(changed))
        return changed


def ensure_host_mode_session(
    storage: SessionStorage,
    session_id: str,
    *,
    requester: dict,
    result_ttl: int,
    policy: HostPermissionPolicy,
    is_admin: bool,
) -> Session:
    """Persist an owned Auto snapshot before a Host session's first prompt."""

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
    """Commit one idle mode change under the cross-worker storage lock."""

    record, _ = commit_host_session_mode_with_events(
        storage,
        registry,
        session_id,
        owner,
        mode_id,
        policy,
        is_admin,
    )
    return record


def commit_host_session_mode_with_events(
    storage: SessionStorage,
    registry,
    session_id: str,
    owner: str,
    mode_id: Any,
    policy: HostPermissionPolicy,
    is_admin: bool,
) -> tuple[Session, tuple[dict[str, Any], ...]]:
    """Commit a mode change and return provider revisions it appended."""

    active = registry.get(session_id) if registry is not None else None
    if active is not None and getattr(active, "owner", None) not in (None, owner):
        raise _not_found()
    if active is not None and getattr(active, "status", None) == "running":
        raise _busy()

    appended_provider_events: tuple[dict[str, Any], ...] = ()

    def commit(current: Session | None) -> Session:
        nonlocal appended_provider_events
        if current is None or session_owner(current) != owner:
            raise _not_found()
        if current.status in SessionStorage.UNFINISHED:
            raise _busy()
        current_session = current.session or {}
        current_trace = current_session.get("trace")
        trace_length = len(current_trace) if isinstance(current_trace, list) else 0
        session = policy.apply(current_session, mode_id, is_admin=is_admin)
        trace = session.get("trace")
        appended_provider_events = tuple(
            copy.deepcopy(event)
            for event in (trace[trace_length:] if isinstance(trace, list) else [])
            if isinstance(event, dict)
            and event.get("type") == "provider_invocation"
            and isinstance(event.get("providerPermission"), dict)
        )
        return current.model_copy(update={"session": session})

    record = storage.atomic_update(session_id, commit)
    return record, appended_provider_events


def session_with_durable_policy(client_session: dict | None, durable: dict) -> dict:
    """Keep conversation fields but replace every server-owned policy field."""

    merged = copy.deepcopy(client_session or {})
    for key in _DISCARDED_MODE_KEYS:
        merged.pop(key, None)
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
        metadata = dict(current.metadata) if current is not None else {}
        if not metadata.get("title") and prompt.strip():
            metadata["title"] = " ".join(prompt.split())[:120]
        # Sending a new turn makes an archived conversation active again.
        metadata["archived_at"] = None
        return Session(
            session_id=session_id,
            status="running",
            prompt=prompt,
            session=session,
            created=(current.created if current and current.created else now),
            expires=now + result_ttl,
            metadata=metadata,
        )

    return storage.atomic_update(session_id, claim), server_newer


def _fresh_session(session_id: str, requester: dict) -> dict:
    session = {
        "session_id": session_id,
        "messages": [],
        "trace": [],
        "turn": 0,
        "requester": copy.deepcopy(requester),
    }
    set_mode(session, AUTO)
    return session


HostModePolicy = HostPermissionPolicy


def _not_found() -> ModeTransactionError:
    return ModeTransactionError(-32002, "Session not found")


def _busy() -> ModeTransactionError:
    return ModeTransactionError(
        -32000, "Session is busy", {"retryable": True}
    )
