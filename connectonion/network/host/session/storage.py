"""
Purpose: Persistent session storage for hosted agent requests with TTL expiry
LLM-Note:
  Dependencies: imports from [pydantic, pathlib, json, time] | imported by [host/http_router.py, host/server.py, host/ws_router/agent_io.py, host/session/__init__.py] | tested by [tests/network/test_session_storage.py]
  Data flow: save(session) appends to JSONL → get(session_id) reads backwards, returns latest if not expired → list() loads all, filters expired
  State/Effects: writes to .co/session_results.jsonl (append-only) | creates .co/ directory if missing
  Integration: exposes Session (Pydantic model), SessionStorage class with save/get/list | used by http_router.input_handler and ws_router agent execution paths
  Performance: append-only writes O(1) | linear scan on read O(n) - acceptable for thousands of sessions
  Errors: returns None if session not found or expired | creates parent directory if missing
"""

import json
import math
import threading
import time
import weakref
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from ..auth import (
    MAX_REQUEST_ID_LENGTH,
    MAX_SESSION_ID_LENGTH,
    SIGNATURE_EXPIRY_SECONDS,
)


VALID_SESSION_MODES = frozenset({"safe", "plan", "accept_edits", "ulw"})
ULW_MAX_TURNS = 1000
REQUEST_CLAIM_TTL_SECONDS = SIGNATURE_EXPIRY_SECONDS
MAX_REQUEST_CLAIMS = 10_000


class _SessionLock:
    """Weak-referenceable holder for one reentrant session lock."""

    __slots__ = ("lock", "__weakref__")

    def __init__(self):
        self.lock = threading.RLock()


def _validated_session_id(value: str) -> str:
    if type(value) is not str or not value:
        raise ValueError("session_id must be a non-empty string")
    if len(value) > MAX_SESSION_ID_LENGTH:
        raise ValueError("session_id is too long")
    return value


def _normalized_generation(value):
    if type(value) is not str or not value:
        return None
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        return None
    if value not in (parsed.hex, str(parsed)):
        return None
    return parsed.hex


def _valid_ulw_lease(value):
    if not isinstance(value, dict):
        return None
    turns = value.get("turns")
    used = value.get("turns_used")
    if (type(turns) is not int or not 1 <= turns <= ULW_MAX_TURNS
            or type(used) is not int or not 0 <= used <= turns):
        return None
    lease = {"turns": turns, "turns_used": used}
    if "generation" in value:
        generation = _normalized_generation(value.get("generation"))
        if generation is None:
            return None
        lease["generation"] = generation
    if isinstance(value.get("prompt"), str):
        lease["prompt"] = value["prompt"]
    return lease


def _merge_ulw_leases(lease: dict | None, old_lease: dict | None) -> dict | None:
    """Merge progress only within one authorization generation."""
    if lease is None:
        return old_lease
    if old_lease is None:
        return lease

    generation = lease.get("generation")
    old_generation = old_lease.get("generation")
    if generation != old_generation:
        # A UUID generation is a fresh explicit authorization.  A legacy
        # generation-less writer may not roll a generated lease backwards.
        return lease if generation is not None else old_lease

    merged = {
        "turns": max(lease["turns"], old_lease["turns"]),
        "turns_used": max(lease["turns_used"], old_lease["turns_used"]),
    }
    if generation is not None:
        merged["generation"] = generation
    prompt = lease.get("prompt", old_lease.get("prompt"))
    if isinstance(prompt, str):
        merged["prompt"] = prompt
    return merged


def narrow_server_state(state: dict | None, previous: dict | None = None) -> dict:
    """Allowlist server controls and keep ULW usage monotonic."""
    state = state if isinstance(state, dict) else {}
    previous = previous if isinstance(previous, dict) else {}

    mode = state.get("mode")
    if not isinstance(mode, str) or mode not in VALID_SESSION_MODES:
        return {}

    narrowed = {"mode": mode}
    if mode != "ulw":
        return narrowed

    lease = _valid_ulw_lease(state.get("ulw"))
    old_lease = (
        _valid_ulw_lease(previous.get("ulw"))
        if previous.get("mode") == "ulw"
        else None
    )
    if lease is None and old_lease is None:
        return {"mode": "safe"}

    narrowed["ulw"] = _merge_ulw_leases(lease, old_lease)
    return narrowed


class Session(BaseModel):
    """Session record for agent requests."""
    session_id: str
    owner_address: Optional[str] = None
    status: str
    prompt: str
    result: Optional[str] = None
    session: Optional[dict] = None  # Full context: messages, trace, iteration, updated
    # Security-sensitive, server-validated controls.  This is persisted beside
    # the ordinary round-trip session, but HTTP/WS responses must never expose it.
    server_state: dict = Field(default_factory=dict)
    created: Optional[float] = None
    expires: Optional[float] = None
    duration_ms: Optional[int] = None


class SessionStorage:
    """JSONL file storage. Append-only, last entry wins."""

    def __init__(self, path: str = ".co/session_results.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(exist_ok=True)
        self._session_locks = weakref.WeakValueDictionary()
        self._session_locks_guard = threading.Lock()
        self._file_lock = threading.RLock()
        self._request_claims: dict[tuple[str, str], tuple[str, float]] = {}
        self._request_claims_lock = threading.Lock()
        self._request_claim_limit = MAX_REQUEST_CLAIMS

    @contextmanager
    def session_lock(self, session_id: str):
        """Serialize one session lifecycle; reentrant for in-run checkpoints."""
        session_id = _validated_session_id(session_id)
        with self._session_locks_guard:
            holder = self._session_locks.get(session_id)
            if holder is None:
                holder = _SessionLock()
                self._session_locks[session_id] = holder
        with holder.lock:
            yield

    def claim_request(
        self,
        owner_address: str,
        session_id: str,
        request_id: str,
        timestamp: float | None = None,
        *,
        now: float | None = None,
    ) -> bool:
        """Atomically claim a signed request ID for one owner/session.

        A request ID is unique per owner during the TTL.  Reusing it for the
        same session is a replay; reusing it for another session is a binding
        violation.  Both return ``False`` without changing the original claim.
        """
        session_id = _validated_session_id(session_id)
        values = (owner_address, request_id)
        if any(type(value) is not str or not value for value in values):
            raise ValueError("owner_address and request_id are required")
        if len(request_id) > MAX_REQUEST_ID_LENGTH:
            raise ValueError("request_id is too long")
        current = time.time() if now is None else now
        if (not isinstance(current, (int, float)) or isinstance(current, bool)
                or not math.isfinite(current)):
            raise ValueError("now must be a finite number")
        signed_at = current if timestamp is None else timestamp
        if (not isinstance(signed_at, (int, float)) or isinstance(signed_at, bool)
                or not math.isfinite(signed_at)):
            raise ValueError("timestamp must be a finite number")

        key = (owner_address, request_id)
        with self._request_claims_lock:
            expired = [
                claim_key for claim_key, (_, expires) in self._request_claims.items()
                if expires < current
            ]
            for claim_key in expired:
                del self._request_claims[claim_key]

            if key in self._request_claims:
                return False
            if len(self._request_claims) >= self._request_claim_limit:
                raise ValueError("request replay cache is full")
            expires = max(current, signed_at) + REQUEST_CLAIM_TTL_SECONDS
            self._request_claims[key] = (session_id, expires)
            return True

    def save(self, session: Session):
        _validated_session_id(session.session_id)
        with self.session_lock(session.session_id), self._file_lock:
            with open(self.path, "a") as f:
                f.write(session.model_dump_json() + "\n")

    def get(self, session_id: str) -> Session | None:
        session_id = _validated_session_id(session_id)
        with self.session_lock(session_id), self._file_lock:
            if not self.path.exists():
                return None
            now = time.time()
            with open(self.path) as f:
                lines = f.readlines()
            for line in reversed(lines):
                data = json.loads(line)
                if data["session_id"] == session_id:
                    session = Session(**data)
                    if not session.expires or session.expires > now:
                        return session
                    return None  # Expired
        return None

    def list(self) -> list[Session]:
        with self._file_lock:
            if not self.path.exists():
                return []
            sessions = {}
            now = time.time()
            with open(self.path) as f:
                for line in f:
                    data = json.loads(line)
                    sessions[data["session_id"]] = Session(**data)
        valid = [s for s in sessions.values()
                 if not s.expires or s.expires > now]
        return sorted(valid, key=lambda s: s.created or 0, reverse=True)

    def checkpoint(
        self,
        session: dict,
        *,
        owner_address: str | None = None,
        server_state: dict | None = None,
        status: str = "waiting_approval",
    ) -> None:
        """Save a checkpoint before a blocking operation.

        ``owner_address`` and ``server_state`` are deliberately explicit.  The
        ordinary session may have come from a client, so neither value may be
        inferred from keys inside it.
        """
        session_id = session.get('session_id')
        if not session_id:
            return
        with self.session_lock(session_id):
            previous = self.get(session_id)
            if (previous and previous.owner_address is not None
                    and previous.owner_address != owner_address):
                raise PermissionError("session owner mismatch")

            prior_state = previous.server_state if previous else {}
            if server_state is None and previous and previous.owner_address == owner_address:
                checkpoint_state = deepcopy(prior_state)
            else:
                checkpoint_state = narrow_server_state(server_state, prior_state)

            record = Session(
                session_id=session_id,
                owner_address=owner_address,
                status=status,
                prompt="",
                session=deepcopy(session),
                server_state=checkpoint_state,
                created=time.time(),
                expires=(
                    previous.expires
                    if status == "running" and previous and previous.expires
                    else time.time() + 86400
                ),
            )
            self.save(record)
