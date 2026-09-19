"""1.8.6a8's capture: a message being fixed after it went out.

Both blocks are the real command's own stdout, run against a scratch inbox
whose provider is the real WhatsApp one with its socket replaced — the
rendering and the record are the real code paths, and nothing is sent.
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

DRIVER = r'''
import json, sys
from connectonion.cli.commands import listen_commands
from connectonion.inbox.whatsapp import WhatsApp

# The real provider, with only the socket taken out: render(), the record and
# every handler below are the shipped code.
box = WhatsApp.__new__(WhatsApp)
box.name = "whatsapp"
box.missing = lambda: []
box.check = lambda: []
box._queue = lambda payload: "3EB0D0D948BC23918C0ADD" if "kind" not in payload else "3EB09D56F2E332347BA586"
listen_commands.provider = lambda name: box

listen_commands.handle_send("whatsapp", "120363411567190840@g.us",
                            "Deploy **finished** at 14:02 — [the run](https://ci/42)")
'''

SHOW_RECORD = r'''
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
print(rows[-1]["text"])
'''


def run(code: str, home: Path, *args) -> str:
    env = dict(os.environ, NO_COLOR="1", COLUMNS="96", CO_INBOX_HOME=str(home))
    out = subprocess.run([sys.executable, "-c", code, *args], cwd=ROOT,
                         capture_output=True, text=True, timeout=120, env=env)
    return (out.stdout or "") + (out.stderr or "")


if __name__ == "__main__":
    home = Path(tempfile.mkdtemp(prefix="a8-"))
    sent_id = run(DRIVER, home).strip().splitlines()[0]
    record = run(SHOW_RECORD, home, str(home / "whatsapp" / "sent.jsonl"))

    # The shared renderer prints the command line through Rich, whose markup
    # eats `[the run]` — the picture would then show a command nobody ran, and
    # the one thing it is meant to demonstrate is the link.
    from rich.markup import escape

    blocks = [
        (escape("co whatsapp send 1203…@g.us "
                "'Deploy **finished** at 14:02 — [the run](https://ci/42)'"),
         f"{sent_id}\n"),
        ("# what the group actually received, read back out of sent.jsonl",
         record),
    ]
    out = ROOT / "docs/releases/assets/v1.8.6a8"
    out.mkdir(parents=True, exist_ok=True)
    shoot(page("", blocks), out / "markdown-becomes-what-whatsapp-draws.png")
    print("wrote 1 capture into", out)
