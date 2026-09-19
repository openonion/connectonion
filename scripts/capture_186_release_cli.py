"""1.8.6 stable: the twelve verbs, and the account they are pointed at.

Both blocks are the real command's own stdout. `check` runs against the
listener on the owner's real linked number, so the connected line is a live
reading rather than a fixture.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Users/changxing/projects/connectonion/.claude/worktrees/inbox-1.8.5")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page, shoot          # a2's renderer


def co(*args) -> str:
    env = dict(os.environ, NO_COLOR="1", COLUMNS="92")
    out = subprocess.run([sys.executable, "-m", "connectonion.cli.main", *args],
                         cwd=ROOT, capture_output=True, text=True, timeout=120, env=env)
    return (out.stdout or "") + (out.stderr or "")


def verbs(text: str) -> str:
    """The command table only — the options box and the borders carry nothing."""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("│") and not stripped.startswith("│ --"):
            body = stripped.strip("│").rstrip()
            if body.strip():
                lines.append(body)
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    out = ROOT / "docs/releases/assets/v1.8.6"
    out.mkdir(parents=True, exist_ok=True)
    shoot(page("", [("co whatsapp --help", verbs(co("whatsapp", "--help"))),
                    ("co whatsapp check", co("whatsapp", "check"))]),
          out / "whatsapp-is-an-inbox-with-an-undo.png")
    print("wrote 1 capture into", out)
