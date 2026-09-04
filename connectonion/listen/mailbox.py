"""
Purpose: One directory per chat platform where every inbound message becomes a file any program can consume
LLM-Note:
  Dependencies: imports from [dataclasses, json, os, re, subprocess, sys, time, pathlib] | imported by [listen/feishu.py, cli/commands/listen_commands.py] | tested by [tests/unit/test_listen_mailbox.py]
  Data flow: provider → Mailbox.deliver(Message) → one line appended to inbox.jsonl + one file in new/ | consumer → Mailbox.receive() → rename new/X → cur/X → Message | reply → Mailbox.record_sent() → one line in outbox.jsonl, cur/X removed
  State/Effects: creates ~/.co/<provider>/ (or $CO_<PROVIDER>_HOME) mode 0700 with inbox.jsonl, outbox.jsonl, tmp/, new/, cur/, log, listen.lock | every write is an append or an atomic rename | inbox.jsonl is never rewritten or truncated
  Integration: exposes Message, Mailbox | the directory is the interface: `ls new/` is the unread count, `tail -f inbox.jsonl` is a live view, `mv new/X cur/X` is a claim | receive() starts a listener when none is running, the gpg-agent convention
  Performance: deliver() is two small writes; receive() polls new/ four times a second; lookup() and already_replied() scan a JSONL file linearly, which is fine for the sizes one bot sees
  Errors: a torn last line in inbox.jsonl is skipped, never raised | a rename lost to another consumer moves on to the next file | a lock whose pid is dead counts as no listener

Why files and not a database: Maildir solved "many writers, many readers, no
locks, crash-safe" for mail in 1995 with three directories and rename(2). A
message is a file; taking it is a rename, which is atomic, so two consumers
can never take the same one; the log beside the queue means a consumer that
crashes loses nothing that cannot be found again. Nothing here needs a
library, and nothing that reads it needs one either. DD-063 has the argument.
"""

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# One hour: a consumer that took a message and has not replied in an hour is
# assumed dead, and the message goes back to new/ for the next receive().
# The same idea as SQS's visibility timeout, with a directory.
STALE_AFTER_SECONDS = 3600

_UNSAFE = re.compile(r"[^A-Za-z0-9._:@+=-]")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe(message_id: str) -> str:
    """A message id as a file-name fragment. Feishu's om_…, Telegram's
    chat.msg and WhatsApp's wamid.…== all survive unchanged."""
    return _UNSAFE.sub("_", message_id)


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
        self.tmp = self.root / "tmp"
        self.new = self.root / "new"
        self.cur = self.root / "cur"
        self.logfile = self.root / "log"
        self.lock = self.root / "listen.lock"
        for directory in (self.root, self.tmp, self.new, self.cur):
            directory.mkdir(parents=True, exist_ok=True)
        # Messages are private. Whoever can read the home directory can read
        # them, and nobody else.
        if os.name == "posix":
            os.chmod(self.root, 0o700)
        self._seen: Optional[set] = None

    # ---- inbound -----------------------------------------------------------

    def deliver(self, message: Message, *, raw: bool = False) -> bool:
        """Record one inbound message. Returns False for a duplicate id.

        The log line is written before the queue file, so a crash between
        the two leaves a message that is findable and can be re-queued, and
        never a queue entry the log has never heard of.
        """
        if self._seen is None:
            self._seen = self._ids_in(self.inbox)
        if message.id in self._seen:
            return False
        self._append(self.inbox, message.to_json(raw=raw))
        self._seen.add(message.id)
        name = f"{int(time.time() * 1000)}-{_safe(message.id)}"
        staging = self.tmp / name
        staging.write_text(message.to_json() + "\n", encoding="utf-8")
        os.replace(staging, self.new / name)
        return True

    # ---- consuming ---------------------------------------------------------

    def unread(self) -> list:
        """Files in new/, oldest first. Names start with arrival time so sort
        order is arrival order."""
        return sorted(p for p in self.new.iterdir() if p.is_file())

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

    def _claim(self, path: Path) -> Optional[Message]:
        target = self.cur / path.name
        try:
            os.rename(path, target)
        except FileNotFoundError:
            return None
        # rename keeps the delivery-time mtime; the stale clock starts at the
        # claim, not at the delivery, or an old message is "stale" at once.
        os.utime(target, None)
        return Message.from_dict(json.loads(target.read_text(encoding="utf-8")))

    def done(self, message_id: str) -> None:
        """Forget a taken message: the reply went out, or the consumer decided
        there is nothing to say."""
        suffix = f"-{_safe(message_id)}"
        for path in self.cur.iterdir():
            if path.name.endswith(suffix):
                path.unlink(missing_ok=True)

    def release_stale(self, max_age: float = STALE_AFTER_SECONDS) -> int:
        """Return taken-but-never-replied messages to new/. Returns how many."""
        cutoff = time.time() - max_age
        released = 0
        for path in self.cur.iterdir():
            if path.is_file() and path.stat().st_mtime < cutoff:
                os.rename(path, self.new / path.name)
                released += 1
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
            if record.get("id") == message_id:
                found = Message.from_dict(record)
        return found

    # ---- the tool's own log --------------------------------------------------

    def log(self, line: str) -> None:
        self._append(self.logfile, f"{_now_iso()} {line}")

    # ---- the listener lock -----------------------------------------------------

    def listener_pid(self) -> Optional[int]:
        """The pid in listen.lock if that process is alive, else None."""
        try:
            pid = int(self.lock.read_text(encoding="utf-8").strip())
        except (FileNotFoundError, ValueError):
            return None
        return pid if _alive(pid) else None

    def hold_lock(self) -> bool:
        """Claim the listener role for this process. False if another
        listener is alive."""
        if self.listener_pid() is not None:
            return False
        self.lock.write_text(f"{os.getpid()}\n", encoding="utf-8")
        return True

    def release_lock(self) -> None:
        if self.listener_pid() == os.getpid():
            self.lock.unlink(missing_ok=True)

    def ensure_listener(self) -> Optional[int]:
        """Start `co <provider> listen` in the background if none is running.
        Returns the pid of the listener that is now running, or None if the
        one we started died within a second (its reason is in the log)."""
        pid = self.listener_pid()
        if pid is not None:
            return pid
        argv = [sys.executable, "-m", "connectonion.cli.main", self.provider, "listen"]
        kwargs = {"stdin": subprocess.DEVNULL, "stdout": self.logfile.open("ab"), "stderr": subprocess.STDOUT}
        if os.name == "posix":
            kwargs["start_new_session"] = True
        else:  # pragma: no cover - Windows only
            kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
        process = subprocess.Popen(argv, **kwargs)
        time.sleep(1.0)
        if process.poll() is not None:
            self.log(f"listener exited at once with {process.returncode}; see the lines above")
            return None
        self.log(f"listener started pid {process.pid}")
        return process.pid

    # ---- internals ----------------------------------------------------------

    @staticmethod
    def _append(path: Path, line: str) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

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
                    yield json.loads(line)
                except ValueError:
                    continue

    def _ids_in(self, path: Path) -> set:
        return {str(record["id"]) for record in self._records(path) if "id" in record}


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "posix":  # pragma: no cover - Windows only
        # os.kill(pid, 0) on Windows calls TerminateProcess. Ask, do not shoot.
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
