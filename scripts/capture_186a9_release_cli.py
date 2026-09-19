"""1.8.6a9's capture: what an empty send does now, beside what it did.

The "before" block is not a re-enactment — it is the real record the bug left
in sent.jsonl on 19 September, when two blanks reached real groups. The "after"
block is the shipped command run against a scratch inbox.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path("/Users/changxing/projects/connectonion/.claude/worktrees/inbox-1.8.5")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page, shoot          # a2's renderer

AFTER = r'''
from connectonion.cli.commands import listen_commands

class Fake:
    def missing(self): return []
    def check(self): return []
    def render(self, text): return text
    def send(self, chat, text, **kw):
        raise AssertionError("a blank must never reach the provider")

listen_commands.provider = lambda name: Fake()
try:
    listen_commands.handle_send("whatsapp", "120363410170505910@g.us")
except SystemExit as exiting:
    import sys as _sys
    _sys.stderr.flush()
    print(f"$ echo $?\n{exiting.code}")
'''


def run(code: str, home: Path, stdin: str = "") -> str:
    """stderr first, then stdout: the refusal is printed before the shell is
    asked for the exit code, and a capture that shows them the other way round
    is a picture of something that did not happen."""
    env = dict(os.environ, NO_COLOR="1", COLUMNS="96", CO_INBOX_HOME=str(home))
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, input=stdin,
                         capture_output=True, text=True, timeout=120, env=env)
    return (out.stderr or "") + (out.stdout or "")


if __name__ == "__main__":
    home = Path(tempfile.mkdtemp(prefix="a9-"))
    after = run(AFTER, home)

    # The real rows the bug wrote, copied from the account's own sent.jsonl.
    before = ('3EB051DF0FC1EF995EF15B\n'
              '$ echo $?\n0\n'
              '$ # and in sent.jsonl, indistinguishable from a real send:\n'
              '{"at":"2026-09-19T01:09:23Z","chat":"120363411567190840@g.us",'
              '"text":"","id":"3EB051DF0FC1EF995EF15B","ok":true}\n')

    blocks = [
        ("co whatsapp send 1203…@g.us      # 1.8.6a8: no text, and a blank bubble goes out",
         before),
        ("co whatsapp send 1203…@g.us      # 1.8.6a9", after),
    ]
    out = ROOT / "docs/releases/assets/v1.8.6a9"
    out.mkdir(parents=True, exist_ok=True)
    shoot(page("", blocks), out / "nothing-is-not-a-message.png")
    print("wrote 1 capture into", out)
