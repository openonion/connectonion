"""
Purpose: Persistent session storage for hosted agent requests with TTL expiry
LLM-Note:
  Dependencies: imports from [pydantic, pathlib, json, time] | imported by [host/http_router.py, host/server.py, host/ws_router/agent_io.py, host/session/__init__.py] | tested by [tests/unit/test_session_storage.py]
  Data flow: save(session) appends to JSONL → get(session_id) reads backwards, returns latest if not expired → list() loads all, filters expired
  State/Effects: writes to .co/session_results.jsonl (append-only) | creates .co/ directory if missing
  Integration: exposes Session (Pydantic model), SessionStorage class with save/get/list | used by http_router.input_handler and ws_router agent execution paths
  Performance: append-only writes O(1) | linear scan on read O(n) - acceptable for thousands of sessions
  Errors: returns None if session not found or expired | creates parent directory if missing
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from ....project import project_co_dir


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


def session_owner(record) -> str | None:
    """The address that started this session, or None if nobody owns it.

    Written by input_handler on every turn, from the signature-verified
    address, and kept in SERVER_OWNED_SESSION_KEYS so a client carries it but
    does not get to author it. It was recorded and never read back, so naming
    someone else's session id handed you their conversation (#696).

    None for a session stored before this was read -- nobody inherits those.
    """
    if not record or not record.session:
        return None
    requester = record.session.get("requester") or {}
    return requester.get("address")


def _exclusive(path: Path, wait: bool = True, attempts: int = 3000,
               pause: float = 0.01):
    """Hold this file against other writers.

    Appends and compaction have to exclude each other. The guard compact() uses
    -- read the size, build the replacement, read it again, replace -- still
    leaves a window between the second read and the replace, and an append that
    lands in it is in the file being thrown away. compact() says what that
    costs: "A lost session record is a turn that happened and left no trace."

    At startup, where compact() has only ever run, that window is small and
    nothing is serving. It is why an agent left running never compacts at all
    (#625), and why the fix is this rather than calling it more often.

    Same shape as schedule.py's lock, for the same reasons: POSIX flock,
    Windows msvcrt, imported inside so a module-level `fcntl` does not stop
    this importing on Windows.

    `wait=False` for compaction: it is housekeeping, and skipping costs one
    cycle. An append waits instead -- giving up and writing anyway is exactly
    the lost turn this exists to prevent, which is what the first version of
    this did, and its test stayed red.

    Waiting cannot hang on a dead holder: the OS releases a flock when the
    process holding it dies. The cap is a backstop for a live process wedged
    forever, not for a crashed one.
    """
    import time as _time

    for _ in range(attempts if wait else 1):
        handle = open(path, "a+", encoding="utf-8")
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except OSError:
            handle.close()
            _time.sleep(pause)
    return None


def _release(handle) -> None:
    if handle is None:
        return
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


class SessionStorage:
    """JSONL file storage. Append-only, last entry wins."""

    def __init__(self, path=None):
        # The project's `.co/`, not a bare relative path. `host()` builds this
        # with no argument, so an agent hosted from a subdirectory wrote its
        # sessions to `sub/.co/` -- invisible to any later run, and the `.co/`
        # created here is a decoy that the walk-up in #660/#661/#663 stops at,
        # so the project's own host.yaml and trust lists stop being found.
        # Absolute, because a relative path is re-resolved on every use and a
        # tool calling os.chdir would move the history mid-run.
        self.path = Path(path) if path else project_co_dir() / "session_results.jsonl"
        self.path.parent.mkdir(exist_ok=True)

    @property
    def _lock_path(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".lock")

    def save(self, session: Session):
        # Excludes compact(), which replaces this file wholesale.
        handle = _exclusive(self._lock_path)
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(session.model_dump_json() + "\n")
        finally:
            _release(handle)

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

    def compact(self) -> None:
        """Drop what no reader can see any more, and rewrite the file.

        `save()` appends and nothing removed. `expires` was honoured on read —
        list() and get() skip records past their TTL — but they stayed in the
        file and list() parsed all of them to answer. Measured on a live agent:
        17 MB for 222 sessions. One running a schedule every fifteen minutes
        writes 96 a day, so about 7 MB a day and 2.5 GB a year, and a dashboard
        that reparses the lot each time it is opened.

        Safe for one specific reason: it removes only what list() and get()
        already refuse to return — superseded records for a session, and
        sessions past their TTL that are not `running`. Every one of those was
        invisible to every reader before it was removed, so nothing observable
        changes except the size.

        Written to a temporary file and moved into place, so a crash in the
        middle leaves the old file rather than half a new one.
        """
        if not self.path.exists():
            return

        handle = _exclusive(self._lock_path, wait=False)
        if handle is None:
            return          # someone is writing; the next cycle compacts
        try:
            self._compact_locked()
        finally:
            _release(handle)

    def _compact_locked(self) -> None:
        now = time.time()
        size_when_read = self.path.stat().st_size
        keep = [s for s in self._latest_by_id().values()
                if s.status == "running" or not s.expires or s.expires > now]

        tmp = self.path.with_suffix(f"{self.path.suffix}.compact.{os.getpid()}")
        with open(tmp, "w", encoding="utf-8") as f:
            for session in sorted(keep, key=lambda s: s.created or 0):
                f.write(session.model_dump_json() + "\n")

        # Someone appended while we were reading and writing, and their record
        # is only in the file we are about to replace. A lost session record is
        # a turn that happened and left no trace — absent from the dashboard,
        # uncounted by `co status`, with nothing anywhere saying one was
        # dropped.
        #
        # The window is small: this runs at startup, before this process serves
        # anything. Not zero — `host()` can run workers > 1, so another process
        # may already be serving, and the relay announce and the schedule's
        # first tick both begin within milliseconds.
        #
        # Skipping costs nothing; the next startup compacts. So notice, and
        # leave the file alone.
        # A missing file counts as changed. Compaction is housekeeping and must
        # not be able to stop the agent — the same rule _records already states
        # for a torn line: refusing to boot over it costs the agent.
        try:
            unchanged = self.path.stat().st_size == size_when_read
        except OSError:
            unchanged = False
        if not unchanged:
            tmp.unlink(missing_ok=True)
            return

        tmp.replace(self.path)

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
