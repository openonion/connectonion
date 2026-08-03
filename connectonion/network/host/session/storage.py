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

    def _records(self) -> list:
        """Every parseable record, oldest first. A torn line costs itself, nothing more.

        This file is appended from more than one thread, so a crash, a full disk
        or an interleaved write can leave a partial line. `json.loads` on that
        line used to raise out of get(), list() *and* reconcile_interrupted() —
        and since reconcile runs at startup, one torn line stopped the agent from
        booting at all.

        The schedule's own state file settled this long ago: "Refusing to boot
        over it costs the agent, so a truncated write or a hand edit is not
        allowed to be fatal." Same file shape, same rule, applied late.
        """
        if not self.path.exists():
            return []
        out = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(Session(**json.loads(line)))
                except Exception:
                    continue      # one unreadable record, not an unreadable file
        return out

    def _lines_from_the_end(self, chunk: int = 65536):
        """Yield whole lines newest-first, reading backwards in chunks.

        get() answers "what is the latest record for this one session", and the
        answer is almost always near the end — a turn asks about the session it
        is in. Parsing forwards meant every lookup cost the whole file.

        That file is append-only and never shrinks: 17 MB and 222 sessions on an
        agent up for thirteen hours, each record carrying its full message list.
        get() runs on every turn and inside every checkpoint(), so a full parse
        there is a cost that grows for as long as the agent stays alive.
        """
        with open(self.path, "rb") as f:
            f.seek(0, 2)
            end = f.tell()
            tail = b""
            while end > 0:
                size = min(chunk, end)
                end -= size
                f.seek(end)
                block = f.read(size) + tail
                lines = block.split(b"\n")
                tail = lines.pop(0)          # may be half a line; carry it back
                for raw in reversed(lines):
                    if raw.strip():
                        yield raw
            if tail.strip():
                yield tail

    def get(self, session_id: str) -> Session | None:
        if not self.path.exists():
            return None
        now = time.time()
        for raw in self._lines_from_the_end():
            try:
                data = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue          # one torn record, not an unreadable file
            if not isinstance(data, dict) or data.get("session_id") != session_id:
                continue
            try:
                session = Session(**data)
            except Exception:
                continue
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
        return {s.session_id: s for s in self._records()}

    def list(self) -> list[Session]:
        now = time.time()
        sessions = self._latest_by_id()
        valid = [s for s in sessions.values()
                 if s.status == "running" or not s.expires or s.expires > now]
        return sorted(valid, key=lambda s: s.created or 0, reverse=True)

    def checkpoint(self, session: dict) -> None:
        """Save session checkpoint before blocking operation (approval, ask_user)."""
        session_id = session.get('session_id')
        if not session_id:
            return
        # The prompt, from the session this checkpoint is *of*. It used to be
        # hardcoded empty, which is what Home renders as the row's label — so a
        # deployed agent showed five rows reading only "interrupted · 13h ago",
        # with nothing saying what had been interrupted. The dict in hand has
        # had `user_prompt` all along.
        #
        # `created` from the earlier record for the same reason: it is what
        # Recent turns into "13h ago", and stamping it at pause time makes a turn
        # that began this morning look like it began when it stopped.
        earlier = self.get(session_id)
        record = Session(
            session_id=session_id,
            status="waiting_approval",
            prompt=str(session.get('user_prompt') or (earlier.prompt if earlier else '') or ''),
            session=session,
            created=(earlier.created if earlier and earlier.created else time.time()),
            expires=time.time() + 86400,
        )
        self.save(record)
