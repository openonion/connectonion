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
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class Session(BaseModel):
    """Session record for agent requests."""
    session_id: str
    status: str
    prompt: str
    result: Optional[str] = None
    session: Optional[dict] = None  # Full context: messages, trace, iteration, updated
    created: Optional[float] = None
    expires: Optional[float] = None
    duration_ms: Optional[int] = None


class SessionStorage:
    """JSONL file storage. Append-only, last entry wins."""

    def __init__(self, path: str = ".co/session_results.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(exist_ok=True)

    def save(self, session: Session):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(session.model_dump_json() + "\n")

    def get(self, session_id: str) -> Session | None:
        if not self.path.exists():
            return None
        now = time.time()
        with open(self.path, encoding="utf-8") as f:
            lines = f.readlines()
        for line in reversed(lines):
            data = json.loads(line)
            if data["session_id"] == session_id:
                session = Session(**data)
                if session.status == "running" or not session.expires or session.expires > now:
                    return session
                return None  # Expired
        return None

    # A turn that is still owed something by this process. Both are equally dead
    # once the process is gone: `running` had work in flight, `waiting_approval`
    # had a question outstanding, and the thread that would have finished either
    # one no longer exists.
    UNFINISHED = ('running', 'waiting_approval')

    def reconcile_interrupted(self):
        """Close out sessions this process cannot possibly finish.

        Call at startup. That is the one moment the answer is certain: this
        process has just begun and owns no sessions, so anything still marked
        running belongs to a process that died between the two records a turn
        writes — one when it starts, one when it returns.

        Nothing corrected this before, and `running` is exempt from TTL
        (see get/list), so the rows were not merely wrong but permanent. On a
        deployed agent four of the five most recent rows on Home were turns
        killed by a restart, all claiming to be running. Restarting mid-turn is
        not an edge case; it is what deploying does.

        `interrupted` rather than `failed`: the turn may well have finished its
        work before the process went away, and for a scheduled entry that
        writes to a shared ledger, "failed" invites a rerun that duplicates.
        This says what is known — it stopped, and how far it got is not
        recorded anywhere.

        `waiting_approval` was missed the first time this shipped, and it is the
        worse of the two. A run that stopped mid-work at least looks unfinished;
        a session that asked a question renders as *waiting for you*, so the
        reader is invited to answer something no thread is listening for. Nine
        hours after the first version deployed, that agent held five of them —
        the oldest 52 hours old.
        """
        for session in self._latest_by_id().values():
            if session.status in self.UNFINISHED:
                session.status = "interrupted"
                self.save(session)

    def _latest_by_id(self) -> dict:
        """The newest record for each session, whatever its status or age."""
        if not self.path.exists():
            return {}
        out = {}
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                out[data["session_id"]] = Session(**data)
        return out

    def list(self) -> list[Session]:
        if not self.path.exists():
            return []
        sessions = {}
        now = time.time()
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                sessions[data["session_id"]] = Session(**data)
        valid = [s for s in sessions.values()
                 if s.status == "running" or not s.expires or s.expires > now]
        return sorted(valid, key=lambda s: s.created or 0, reverse=True)

    def checkpoint(self, session: dict) -> None:
        """Save session checkpoint before blocking operation (approval, ask_user)."""
        session_id = session.get('session_id')
        if not session_id:
            return
        record = Session(
            session_id=session_id,
            status="waiting_approval",
            prompt="",
            session=session,
            created=time.time(),
            expires=time.time() + 86400,
        )
        self.save(record)
