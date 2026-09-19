"""1.8.6a7's capture: what `check` says now, in all three states.

The connected block is run live against the listener on the owner's real
account. The other two are produced by pointing the same command at inboxes
whose connection record says what it says — still the real command, still its
own stdout.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path("/Users/changxing/projects/connectonion/.claude/worktrees/inbox-1.8.5")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page, shoot          # a2's renderer


def check(home=None) -> str:
    env = dict(os.environ, NO_COLOR="1", COLUMNS="96")
    if home:
        env["CO_INBOX_HOME"] = str(home)
    result = subprocess.run(
        [sys.executable, "-m", "connectonion.cli.main", "whatsapp", "check"],
        cwd=ROOT, capture_output=True, text=True, timeout=120, env=env)
    return (result.stdout or "") + (result.stderr or "")


def inbox_saying(state: dict) -> Path:
    """A scratch inbox whose listener record says `state`, and nothing else."""
    home = Path(tempfile.mkdtemp(prefix="a7-check-"))
    box = home / "whatsapp"
    box.mkdir(parents=True)
    # A session with a device row, so the only thing left to report is the socket.
    import sqlite3
    real = Path.home() / ".co" / "inbox" / "whatsapp" / "session.db"
    (box / "session.db").write_bytes(real.read_bytes())
    (box / "connection.json").write_text(json.dumps(state), encoding="utf-8")
    (box / "listen.lock").write_text(str(state.get("pid", 1)), encoding="utf-8")
    return home


if __name__ == "__main__":
    live = check()
    stale = check(inbox_saying({"state": "connected", "at": "2026-09-19T00:16:26Z",
                                "pid": 999999, "account": "61410724095"}))
    out = ROOT / "docs/releases/assets/v1.8.6a7"
    shoot(page("", [("co whatsapp check   # the live listener", live),
                    ("co whatsapp check   # a record from a process that has exited", stale)]),
          out / "check-stops-claiming-the-network.png")
    print("wrote 1 capture into", out)
