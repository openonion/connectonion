"""Scoped Claude Code Hook settings for one ConnectOnion-owned process."""

import hashlib
import json
import os
import secrets
import sys
import time
from collections import deque
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock, Thread
from typing import Callable
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

_MAX_HOOK_INPUT = 64 * 1024
_OBSERVED_EVENTS = (
    "SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse",
    "PostToolUse", "PostToolUseFailure", "PermissionRequest", "SubagentStart",
    "SubagentStop", "Stop", "StopFailure", "PostCompact",
)
_EVENT_FIELDS = (
    "hook_event_name", "session_id", "transcript_path", "cwd", "source",
    "tool_name", "tool_use_id", "agent_id",
)
_MAX_EVENTS = 4096
_MAX_EVENT_RATE = 128
_MAX_TRANSCRIPT_LINE = 1024 * 1024
_MAX_TRANSCRIPT_RECORDS = 512
_MAX_TRANSCRIPT_BYTES = 2 * 1024 * 1024


@contextmanager
def exclusive_workspace_writer(cwd: Path):
    """Allow one owned Claude writer per workspace across CLI processes.

    Claude's session ID is unknown until SessionStart for a fresh TUI. A
    workspace lock also covers that interval and prevents a browser worker
    from resuming the same transcript while the native TUI owns it.
    """
    directory = Path.home() / ".co" / "claude-writers"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = hashlib.sha256(str(cwd.resolve()).encode()).hexdigest()
    path = directory / f"{name}.lock"
    with path.open("a+b") as handle:
        path.chmod(0o600)
        if os.name == "nt":
            import msvcrt

            if path.stat().st_size == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ValueError("Claude Code already owns this workspace.") from exc
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("Claude Code already owns this workspace.") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class _HookReceiver(BaseHTTPRequestHandler):
    """Accept one wrapper's bounded Hook facts over authenticated loopback."""

    def do_POST(self):
        server = self.server
        authorization = self.headers.get("Authorization", "")
        if self.path != "/hook" or not secrets.compare_digest(
            authorization, f"Bearer {server.token}"
        ):
            self.send_error(403)
            return
        length = self.headers.get("Content-Length", "")
        if len(length) > 6 or not length.isdecimal() or not 0 < int(length) <= _MAX_HOOK_INPUT:
            self.send_error(413)
            return
        self.connection.settimeout(5)
        raw = self.rfile.read(int(length))
        try:
            event = json.loads(raw)
            record = _event_record(event)
        except (ValueError, UnicodeDecodeError):
            self.send_error(400)
            return
        with server.event_lock:
            if server.event_count >= _MAX_EVENTS:
                self.send_error(429)
                return
            now = time.monotonic()
            while server.recent_events and now - server.recent_events[0] >= 1:
                server.recent_events.popleft()
            if len(server.recent_events) >= _MAX_EVENT_RATE:
                self.send_error(429)
                return
            with server.events.open("a", encoding="utf-8") as output:
                output.write(json.dumps(record) + "\n")
            server.event_count += 1
            server.recent_events.append(now)
        handler = getattr(server, "permission_handler", None)
        if event["hook_event_name"] == "PermissionRequest" and handler is not None:
            approved = bool(handler(event))
            response = json.dumps({"hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "allow" if approved else "deny"},
            }}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        self.send_response(204)
        self.end_headers()

    def log_message(self, format, *args):
        return


def _event_record(event: object) -> dict:
    if not isinstance(event, dict) or event.get("hook_event_name") not in _OBSERVED_EVENTS:
        raise ValueError("Unexpected Claude Hook event.")
    record = {key: event[key] for key in _EVENT_FIELDS if key in event}
    if any(not isinstance(value, str) or len(value) > 4096 for value in record.values()):
        raise ValueError("Claude Hook identity field is too long.")
    return record


def forward_hook(url: str, token: str) -> None:
    """Command Hook entry point; no prompt, tool input, or credential is saved."""
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
        or parsed.port is None or parsed.path != "/hook"
        or parsed.username or parsed.password or parsed.query or parsed.fragment
    ):
        raise ValueError("Claude Hook receiver must be on loopback.")
    raw = sys.stdin.buffer.read(_MAX_HOOK_INPUT + 1)
    if len(raw) > _MAX_HOOK_INPUT:
        raise ValueError("Claude Hook input exceeds the allowed size.")
    request = Request(url, data=raw, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
    })
    with build_opener(ProxyHandler({})).open(request, timeout=180) as response:
        output = response.read(_MAX_HOOK_INPUT)
        if output:
            sys.stdout.write(output.decode("utf-8"))


@contextmanager
def scoped_bridge_settings(permission_handler: Callable[[dict], bool] | None = None):
    """Install per-process Hooks with a private authenticated loopback receiver."""
    with TemporaryDirectory(prefix="co-claude-") as directory:
        root = Path(directory)
        events = root / "events.jsonl"
        events.touch(mode=0o600)
        settings = root / "settings.json"
        receiver = ThreadingHTTPServer(("127.0.0.1", 0), _HookReceiver)
        receiver.daemon_threads = True
        receiver.token = secrets.token_urlsafe(32)
        receiver.events = events
        receiver.event_lock = Lock()
        receiver.event_count = 0
        receiver.recent_events = deque()
        receiver.permission_handler = permission_handler
        url = f"http://127.0.0.1:{receiver.server_port}/hook"
        hook = {
            "type": "command", "command": sys.executable,
            "args": [str(Path(__file__).resolve()), url, receiver.token],
            "timeout": 5,
        }
        permission_hook = {**hook, "timeout": 180}
        settings.write_text(json.dumps({
            "hooks": {event: [{"hooks": [permission_hook if event == "PermissionRequest" else hook]}]
                      for event in _OBSERVED_EVENTS},
        }))
        os.chmod(settings, 0o600)
        thread = Thread(target=receiver.serve_forever, name="co-claude-hooks", daemon=True)
        thread.start()
        try:
            yield settings, events
        finally:
            receiver.shutdown()
            receiver.server_close()
            thread.join(timeout=2)


def session_start(
    events: Path, *, cwd: Path, requested_session: str, latest: bool = False
) -> dict:
    """Read only the scoped Hook's exact session and transcript identity."""
    lines = events.read_text().splitlines()
    for line in reversed(lines) if latest else lines:
        event = json.loads(line)
        if event.get("hook_event_name") != "SessionStart":
            continue
        return _validate_session_start(event, cwd, requested_session)
    raise ValueError("Claude SessionStart Hook did not run.")


def _validate_session_start(event: dict, cwd: Path, requested_session: str) -> dict:
    session_id = event.get("session_id")
    transcript_path = event.get("transcript_path")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Claude SessionStart did not identify a session.")
    if requested_session and session_id != requested_session:
        raise ValueError("Claude SessionStart changed the requested session.")
    if Path(event.get("cwd", "")).resolve() != cwd.resolve():
        raise ValueError("Claude SessionStart changed the workspace.")
    if not isinstance(transcript_path, str) or not Path(transcript_path).is_absolute():
        raise ValueError("Claude SessionStart did not provide an absolute transcript path.")
    return event


def poll_bridge(
    events: Path, offset: int, cwd: Path, tailer: "ClaudeTranscriptTailer | None",
    *, skip_existing_messages: bool = False,
) -> tuple[int, "ClaudeTranscriptTailer | None", list[dict], list[dict]]:
    """Consume bounded Hook facts, then mirror only the current exact transcript."""
    facts = []
    messages = []
    with events.open("rb") as spool:
        spool.seek(offset)
        for _ in range(128):
            line = spool.readline(_MAX_HOOK_INPUT + 1)
            if not line or not line.endswith(b"\n"):
                break
            if len(line) > _MAX_HOOK_INPUT:
                raise ValueError("Claude Hook spool line is too long.")
            event = json.loads(line)
            if event.get("hook_event_name") == "SessionStart":
                hook = _validate_session_start(event, cwd, "")
                path = Path(hook["transcript_path"])
                if tailer is None:
                    tailer = ClaudeTranscriptTailer(path, hook["session_id"])
                    if skip_existing_messages:
                        tailer.skip_existing()
                elif tailer.path != path or tailer.session_id != hook["session_id"]:
                    messages.extend(tailer.read_available())
                    tailer.follow(path, hook["session_id"])
            elif (
                tailer is None
                or event.get("session_id") != tailer.session_id
                or Path(event.get("cwd", "")).resolve() != cwd.resolve()
                or event.get("transcript_path") != str(tailer.path)
            ):
                raise ValueError("Claude Hook changed the owned session identity.")
            facts.append(event)
            offset = spool.tell()
    if tailer is not None:
        messages.extend(tailer.read_available())
    return offset, tailer, facts, messages


class ClaudeTranscriptTailer:
    """Read bounded, tested conversation records from an exact Hook path."""

    def __init__(self, path: Path, session_id: str = ""):
        if not path.is_absolute():
            raise ValueError("Claude transcript path must be absolute.")
        self.path = path
        self.session_id = session_id
        self.offset = 0
        self.identity = None
        self.skip_long_line = False
        self.seen: set[str] = set()
        self.recent = deque(maxlen=2048)
        self.unknown_records = 0

    def skip_existing(self) -> None:
        """A returning TUI watches new text; OIP already holds earlier turns."""
        if self.path.is_file():
            stat = self.path.stat()
            self.identity = (stat.st_dev, stat.st_ino)
            self.offset = stat.st_size

    def follow(self, path: Path, session_id: str = "") -> None:
        """Follow a new SessionStart transcript after resume, compact, or fork."""
        if not path.is_absolute():
            raise ValueError("Claude transcript path must be absolute.")
        self.path = path
        self.session_id = session_id
        self.offset = 0
        self.identity = None
        self.skip_long_line = False

    def read_available(self) -> list[dict]:
        if not self.path.is_file():
            return []
        stat = self.path.stat()
        identity = (stat.st_dev, stat.st_ino)
        if identity != self.identity or stat.st_size < self.offset:
            self.offset = 0
            self.identity = identity
            self.skip_long_line = False
        messages = []
        consumed = 0
        with self.path.open("rb") as transcript:
            transcript.seek(self.offset)
            for _ in range(_MAX_TRANSCRIPT_RECORDS):
                if consumed >= _MAX_TRANSCRIPT_BYTES:
                    break
                start = transcript.tell()
                line = transcript.readline(_MAX_TRANSCRIPT_LINE + 1)
                if not line:
                    break
                consumed += len(line)
                if self.skip_long_line:
                    self.offset = transcript.tell()
                    if line.endswith(b"\n"):
                        self.skip_long_line = False
                    continue
                if len(line) > _MAX_TRANSCRIPT_LINE:
                    self.offset = transcript.tell()
                    self.skip_long_line = not line.endswith(b"\n")
                    self.unknown_records += 1
                    continue
                if not line.endswith(b"\n"):
                    self.offset = start
                    break
                self.offset = transcript.tell()
                message = self._message(line)
                if message is not None:
                    messages.append(message)
        return messages

    def _message(self, line: bytes) -> dict | None:
        try:
            record = json.loads(line)
        except (UnicodeDecodeError, ValueError):
            self.unknown_records += 1
            return None
        if not isinstance(record, dict) or record.get("type") not in ("user", "assistant"):
            self.unknown_records += 1
            return None
        if self.session_id and record.get("sessionId") != self.session_id:
            self.unknown_records += 1
            return None
        if record.get("isSidechain"):
            return None
        identifier = record.get("uuid")
        message = record.get("message")
        if (
            not isinstance(identifier, str)
            or len(identifier) > 128
            or not identifier.isascii()
            or not all(character.isalnum() or character in "._:-" for character in identifier)
            or not isinstance(message, dict)
        ):
            self.unknown_records += 1
            return None
        role = record["type"]
        content = message.get("content")
        if role == "assistant" and isinstance(content, list):
            text = "\n".join(
                block["text"] for block in content
                if isinstance(block, dict) and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            )
        elif role == "user" and isinstance(content, str):
            text = content
        else:
            return None
        if not text.strip() or identifier in self.seen:
            return None
        if len(self.recent) == self.recent.maxlen:
            self.seen.remove(self.recent.popleft())
        self.recent.append(identifier)
        self.seen.add(identifier)
        return {"message_id": identifier, "role": role, "text": text[:16000]}


if __name__ == "__main__":
    forward_hook(sys.argv[1], sys.argv[2])
