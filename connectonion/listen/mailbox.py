"""
Purpose: One directory per chat platform where every inbound message becomes a file any program can consume
LLM-Note:
  Dependencies: imports from [dataclasses, json, os, re, subprocess, sys, time, pathlib, environment.py, cli/browser_agent/transport.py (the singleton lock)] | imported by [listen/feishu.py, cli/commands/listen_commands.py] | tested by [tests/unit/test_listen_mailbox.py]
  Data flow: provider → Mailbox.deliver(Message) → one line appended to inbox.jsonl + one file in new/ | consumer → Mailbox.receive() → rename new/X → cur/X → Message | reply → Mailbox.record_sent() → one line in outbox.jsonl, cur/X removed
  State/Effects: creates ~/.co/<provider>/ (or $CO_<PROVIDER>_HOME) mode 0700 with inbox.jsonl, outbox.jsonl, tmp/, new/, cur/, bad/, log, listen.lock | every write is an append or an atomic rename | inbox.jsonl is never rewritten or truncated
  Integration: exposes Message, Mailbox | the directory is the interface: `ls new/` is the unread count, `tail -f inbox.jsonl` is a live view, `mv new/X cur/X` is a claim | receive() starts a listener when none is running, the gpg-agent convention
  Performance: deliver() is two small writes; receive() polls new/ four times a second; lookup() and already_replied() scan a JSONL file linearly, which is fine for the sizes one bot sees
  Errors: a torn last line in inbox.jsonl is skipped, never raised | a rename lost to another consumer moves on to the next file | a queue file that is not a message is set aside in bad/ with a log line | the listener lock is held by the kernel, so a dead listener holds nothing

Messages stay inspectable as files. Built-in mutations use a short kernel lock
because the visibility timestamp, rename and completion record must agree. A
raw filesystem consumer still owns its claim lifetime; use receive/done for
the coordinated lease and durable completion behavior. DD-063 has the interface.
"""

import json
import hashlib
from contextlib import contextmanager
from functools import wraps
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..environment import explicit_env_file

# One hour: a consumer that took a message and has not replied in an hour is
# assumed dead, and the message goes back to new/ for the next receive().
# The same idea as SQS's visibility timeout, with a directory.
STALE_AFTER_SECONDS = 3600

_UNSAFE = re.compile(r"[^A-Za-z0-9._:@+=-]")

# Our queue files are `<arrival ms>-<message id>`. Anything else in new/ or
# cur/ (.DS_Store, an editor's swap file, a note someone left) is not ours
# and is neither claimed, swept, nor deleted.
_QUEUE_NAME = re.compile(r"^\d+-.+")


def iso_utc(seconds: Optional[float] = None) -> str:
    """A UTC timestamp with second precision, `2026-09-02T10:31:07Z`. The one
    spelling every provider and the outbox use."""
    stamp = datetime.now(timezone.utc) if seconds is None else datetime.fromtimestamp(seconds, timezone.utc)
    return stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _now_iso() -> str:
    return iso_utc()


def _safe(message_id: str) -> str:
    """A message id as a file-name fragment. Feishu's om_…, Telegram's
    chat.msg and WhatsApp's wamid.…== all survive unchanged."""
    cleaned = _UNSAFE.sub("_", message_id).replace(":", "_")
    if cleaned != message_id:
        return cleaned[:100] + "-" + hashlib.sha256(message_id.encode()).hexdigest()
    return cleaned


@contextmanager
def _locked(path: Path):
    """Coordinate short mailbox mutations across threads and CLI processes."""
    from ..cli.browser_agent.transport import acquire_singleton_lock

    deadline = time.monotonic() + 30
    while True:
        handle = acquire_singleton_lock(str(path))
        if handle is not None:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError("Mailbox is busy; retry after the active operation completes")
        time.sleep(0.01)
    try:
        yield
    finally:
        handle.close()  # Keep the inode: unlinking allows two independent locks.


def _serialized(function):
    @wraps(function)
    def run(self, *args, **kwargs):
        with _locked(self.root / "queue.lock"):
            return function(self, *args, **kwargs)
    return run


def _sync_directory(path: Path) -> None:
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


@dataclass
class Message:
    """One inbound message. Identical fields on every provider.

    `chat` is the conversation key: reply there and the answer lands where
    the question was asked. `thread` narrows it when the platform has
    threads. `raw` is the provider payload; it is stored only when the
    listener was started with --raw and is never part of the printed form,
    so contact names and group titles do not reach a prompt by accident.
    """

    id: str
    chat: str
    sender: str
    text: str
    at: str
    thread: Optional[str] = None
    mentioned: bool = True
    raw: Optional[dict] = None

    def to_dict(self, *, raw: bool = False) -> dict:
        record = {
            "id": self.id,
            "chat": self.chat,
            "thread": self.thread,
            "sender": self.sender,
            "text": self.text,
            "mentioned": self.mentioned,
            "at": self.at,
        }
        if raw and self.raw is not None:
            record["raw"] = self.raw
        return record

    def to_json(self, *, raw: bool = False) -> str:
        return json.dumps(self.to_dict(raw=raw), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_dict(cls, record: dict) -> "Message":
        if not isinstance(record, dict) or any(
            not isinstance(record.get(key), str) or not record[key] for key in ("id", "chat")
        ):
            raise ValueError("A mailbox message needs nonempty string id and chat fields")
        return cls(
            id=str(record["id"]),
            chat=str(record["chat"]),
            sender=str(record.get("sender", "")),
            text=str(record.get("text", "")),
            at=str(record.get("at", "")),
            thread=record.get("thread"),
            mentioned=bool(record.get("mentioned", True)),
            raw=record.get("raw"),
        )


def default_home(provider: str) -> Path:
    """~/.co/<provider>, unless $CO_<PROVIDER>_HOME points elsewhere. The env
    var is how a second application of the same provider gets its own
    directory, the way GNUPGHOME does."""
    override = os.environ.get(f"CO_{provider.upper()}_HOME")
    return Path(override).expanduser() if override else Path.home() / ".co" / provider


class Mailbox:
    """The directory. See the module docstring for why it is one."""

    def __init__(self, provider: str, home: Optional[Path] = None):
        self.provider = provider
        self.root = Path(home) if home else default_home(provider)
        self.inbox = self.root / "inbox.jsonl"
        self.outbox = self.root / "outbox.jsonl"
        self.completed = self.root / "done.jsonl"
        self.tmp = self.root / "tmp"
        self.new = self.root / "new"
        self.cur = self.root / "cur"
        self.bad = self.root / "bad"
        self.logfile = self.root / "log"
        self.lock = self.root / "listen.lock"
        for directory in (self.root, self.tmp, self.new, self.cur, self.bad):
            directory.mkdir(parents=True, exist_ok=True)
        # Messages are private. Whoever can read the home directory can read
        # them, and nobody else.
        if os.name == "posix":
            os.chmod(self.root, 0o700)
        self._seen: Optional[set] = None
        self._lock_handle = None

    # ---- inbound -----------------------------------------------------------

    @_serialized
    def deliver(self, message: Message, *, raw: bool = False) -> bool:
        """Record one inbound message. Returns False for a duplicate id.

        The log line is written before the queue file, so a crash between
        the two leaves a message that is findable and can be re-queued, and
        never a queue entry the log has never heard of.

        An id the log already has is a duplicate only while the message is
        somewhere: queued, taken, or answered. If it is in none of those
        places the earlier attempt died between the two writes, and this
        delivery, Feishu's redelivery in practice, is the recovery: the
        queue file is written and the log is left as it is.
        """
        self._seen = self._ids_in(self.inbox)
        if message.id in self._ids_in(self.completed):
            return False
        if message.id in self._seen:
            if self._queued(message.id) or self.already_replied(message.id):
                return False
            original = self.lookup(message.id)
            if original is not None:
                message = original
            self.log(f"re-queued {message.id}: logged earlier but never queued")
        else:
            self._append(self.inbox, message.to_json(raw=raw))
            self._seen.add(message.id)
        name = f"{int(time.time() * 1000)}-{_safe(message.id)}"
        staging = self.tmp / name
        with staging.open("w", encoding="utf-8") as handle:
            handle.write(message.to_json() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, self.new / name)
        _sync_directory(self.new)
        return True

    # ---- consuming ---------------------------------------------------------

    def unread(self) -> list:
        """Our files in new/, oldest first. Names start with arrival time so
        sort order is arrival order."""
        return sorted(p for p in self.new.iterdir() if not p.is_symlink() and p.is_file() and _QUEUE_NAME.match(p.name))

    def receive(self, timeout: Optional[float] = None, poll: float = 0.25) -> Optional[Message]:
        """Block until a message is available, take it, return it.

        timeout=None waits forever; timeout=0 looks once. Taking is a rename
        into cur/, so two consumers on one directory never get the same
        message: the one whose rename fails just tries the next file.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            for path in self.unread():
                message = self._claim(path)
                if message is not None:
                    return message
            if deadline is not None and time.monotonic() >= deadline:
                return None
            time.sleep(poll)

    @_serialized
    def _claim(self, path: Path) -> Optional[Message]:
        target = self.cur / path.name
        try:
            os.rename(path, target)
            # rename keeps the delivery-time mtime; the stale clock starts at
            # the claim, not at the delivery, or an old message is "stale" at
            # once. The sweep can move the file back between these two calls,
            # which is the same as losing the rename: try the next file.
            os.utime(target, None)
        except FileNotFoundError:
            return None
        return self._read_queue_file(target)

    def _read_queue_file(self, path: Path) -> Optional[Message]:
        try:
            return Message.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return None
        except (ValueError, KeyError, TypeError):
            try:
                os.replace(path, self.bad / path.name)
            except FileNotFoundError:
                return None
            self.log(f"{path.name} is not a message; moved to bad/")
            return None

    @_serialized
    def list_messages(self) -> list:
        """Inspect the queue without claiming messages; quarantine malformed files."""
        return [message for path in self.unread()
                if (message := self._read_queue_file(path)) is not None]

    @_serialized
    def done(self, message_id: str) -> None:
        """Forget a message: the reply went out, or the consumer decided there
        is nothing to say. Clears the queue as well as cur/, so a reply made
        straight from `ls` without a `receive` does not leave the message
        waiting to be handed out again."""
        # Persist completion before removal; silence is an outcome, not a send.
        self._append(self.completed, json.dumps({"id": message_id, "at": _now_iso()}))
        wanted = _safe(message_id)
        for directory in (self.cur, self.new):
            for path in directory.iterdir():
                # Exact match after the arrival stamp: Telegram ids can carry a
                # leading "-", so a suffix test would let 123.55 delete -123.55.
                if path.name.split("-", 1)[1:] == [wanted]:
                    path.unlink(missing_ok=True)

    def _queued(self, message_id: str) -> bool:
        wanted = _safe(message_id)
        for directory in (self.new, self.cur):
            for path in directory.iterdir():
                if path.name.split("-", 1)[1:] == [wanted]:
                    return True
        return False

    @_serialized
    def release_stale(self, max_age: float = STALE_AFTER_SECONDS) -> int:
        """Return taken-but-never-replied messages to new/. Returns how many."""
        cutoff = time.time() - max_age
        released = 0
        for path in self.cur.iterdir():
            if not _QUEUE_NAME.match(path.name):
                continue
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    os.rename(path, self.new / path.name)
                    released += 1
            except FileNotFoundError:
                continue  # a consumer finished it between the listing and here
        return released

    # ---- outbound ----------------------------------------------------------

    def record_sent(
        self,
        *,
        chat: str,
        text: str,
        reply_to: Optional[str] = None,
        provider_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        record = {
            "at": _now_iso(),
            "chat": chat,
            "reply_to": reply_to,
            "text": text,
            "id": provider_id,
            "ok": error is None,
            "error": error,
        }
        self._append(self.outbox, json.dumps(record, ensure_ascii=False, separators=(",", ":")))

    def already_replied(self, message_id: str) -> bool:
        for record in self._records(self.outbox):
            if record.get("reply_to") == message_id and record.get("ok"):
                return True
        return False

    def lookup(self, message_id: str) -> Optional[Message]:
        """The message with this id, from the log. Lets `reply ID` find the
        chat and thread so an agent only has to carry one string."""
        found = None
        for record in self._records(self.inbox):
            if record.get("id") == message_id and "chat" in record:
                found = Message.from_dict(record)
        return found

    # ---- the tool's own log --------------------------------------------------

    def log(self, line: str) -> None:
        self._append(self.logfile, f"{_now_iso()} {line}")

    def last_log_lines(self, count: int = 3) -> list:
        try:
            lines = self.logfile.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        return [line for line in lines if line.strip()][-count:]

    # ---- the listener lock -----------------------------------------------------
    #
    # The kernel holds the lock, not the file. flock(2) (msvcrt.locking on
    # Windows) is released when the holder exits, SIGKILL and reboot
    # included, so a listener that died holds nothing and a pid the OS has
    # since reused is not a phantom. The pid inside the file is for people
    # (`check` prints it) and is never what decides whether a listener runs.
    # The bare-pid scheme this replaced failed in both directions: the file
    # existed empty for an instant before the pid was written, so a second
    # starter read "" and unlinked the winner's lock (two listeners, every
    # message delivered twice), and after a reboot a live pid of someone
    # else's process blocked every `receive` forever.

    def listener_pid(self) -> Optional[int]:
        """The pid in listen.lock if a process holds the lock, else None."""
        try:
            text = self.lock.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        if not _held(self.lock):
            return None
        try:
            return int(text)
        except ValueError:
            return -1  # held, but the holder has not written its pid yet

    def hold_lock(self) -> bool:
        """Claim the listener role for this process. False if another
        listener holds the lock."""
        from ..cli.browser_agent.transport import acquire_singleton_lock

        handle = acquire_singleton_lock(str(self.lock))
        if handle is None:
            return False
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        self._lock_handle = handle
        return True

    def release_lock(self) -> None:
        if self._lock_handle is None:
            return
        self._lock_handle.close()
        self._lock_handle = None

    def ensure_listener(self) -> Optional[int]:
        """Start `co <provider> listen` in the background if none is running.
        Returns the pid of the listener that is now running, or None if the
        one we started died within a second (its reason is in the log)."""
        pid = self.listener_pid()
        if pid is not None:
            return pid
        # The child is a fresh `co`: it reads ~/.co/keys.env on its own, and
        # a CO_<PROVIDER>_HOME there would send it to a different directory
        # than the one waiting for it. Pin the directory, and pass on the
        # --env-file the parent was started with for the same reason.
        argv = [sys.executable, "-m", "connectonion.cli.main"]
        env_file = explicit_env_file()
        if env_file is not None:
            argv += ["--env-file", str(env_file)]
        argv += [self.provider, "listen"]
        env = dict(os.environ, **{f"CO_{self.provider.upper()}_HOME": str(self.root)})
        kwargs = {"stdin": subprocess.DEVNULL, "stderr": subprocess.STDOUT, "env": env}
        if os.name == "posix":
            kwargs["start_new_session"] = True
        else:  # pragma: no cover - Windows only
            kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
        # The child inherits the descriptor; our copy is closed at once so a
        # long-lived `serve` does not hold one open log handle per restart.
        with self.logfile.open("ab") as log_handle:
            process = subprocess.Popen(argv, stdout=log_handle, **kwargs)
        # Wait for the child to take the lock, for it to exit, or for a few
        # seconds of interpreter start-up, whichever comes first.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            if self.listener_pid() == process.pid:
                self.log(f"listener started pid {process.pid}")
                return process.pid
            time.sleep(0.1)
        if process.poll() is None:
            self.log(f"listener started pid {process.pid} (lock not yet seen)")
            return process.pid
        # It exited. Another receive may have started a listener in the same
        # instant and won the lock; then ours losing is the right outcome.
        pid = self.listener_pid()
        if pid is not None:
            return pid
        self.log(f"listener exited at once with {process.returncode}; see the lines above")
        return None

    # ---- internals ----------------------------------------------------------

    @staticmethod
    def _append(path: Path, line: str) -> None:
        with _locked(path.with_name(path.name + ".lock")):
            with path.open("a+b") as handle:
                handle.seek(0, os.SEEK_END)
                if handle.tell():
                    handle.seek(-1, os.SEEK_END)
                    if handle.read(1) != b"\n":
                        handle.write(b"\n")  # Isolate a torn record before appending.
                handle.write((line + "\n").encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            _sync_directory(path.parent)

    @staticmethod
    def _records(path: Path):
        """Every well-formed JSON line. A torn last line, from a crash mid
        write, is skipped: it is a line that never finished, not an error."""
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict):
                    yield record

    def _ids_in(self, path: Path) -> set:
        return {str(record["id"]) for record in self._records(path) if "id" in record}


def _held(lock: Path) -> bool:
    """Whether some process, this one included, holds the lock right now.
    Asks the kernel by trying to take it; a refusal is the answer."""
    from ..cli.browser_agent.transport import acquire_singleton_lock

    probe = acquire_singleton_lock(str(lock))
    if probe is None:
        return True
    probe.close()
    return False
