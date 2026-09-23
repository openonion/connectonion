"""Scoped Claude Code Hook settings for one ConnectOnion-owned process."""

import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

_MAX_HOOK_INPUT = 64 * 1024
_SESSION_FIELDS = ("hook_event_name", "session_id", "transcript_path", "cwd", "source")


@contextmanager
def scoped_bridge_settings():
    """Install a private SessionStart recorder without changing user settings."""
    with TemporaryDirectory(prefix="co-claude-") as directory:
        root = Path(directory)
        events = root / "events.jsonl"
        events.touch(mode=0o600)
        settings = root / "settings.json"
        settings.write_text(json.dumps({
            "hooks": {
                "SessionStart": [{"hooks": [{
                    "type": "command",
                    "command": sys.executable,
                    "args": [str(Path(__file__).resolve()), str(events)],
                    "timeout": 5,
                }]}],
            },
        }))
        os.chmod(settings, 0o600)
        yield settings, events


def session_start(events: Path, *, cwd: Path, requested_session: str) -> dict:
    """Read only the scoped Hook's exact session and transcript identity."""
    for line in events.read_text().splitlines():
        event = json.loads(line)
        if event.get("hook_event_name") != "SessionStart":
            continue
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
    raise ValueError("Claude SessionStart Hook did not run.")


def record_session_start(events: Path) -> None:
    """Command Hook entry point; keep raw prompts and credentials out of the spool."""
    raw = sys.stdin.read(_MAX_HOOK_INPUT + 1)
    if len(raw) > _MAX_HOOK_INPUT:
        raise ValueError("Claude Hook input exceeds the allowed size.")
    event = json.loads(raw)
    if event.get("hook_event_name") != "SessionStart":
        raise ValueError("Unexpected Claude Hook event.")
    record = {key: event.get(key) for key in _SESSION_FIELDS}
    with events.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    record_session_start(Path(sys.argv[1]))
