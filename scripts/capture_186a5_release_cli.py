"""1.8.6a5's capture: finding a conversation and reading it back.

Both blocks are the real commands run against the inbox the WhatsApp acceptance
left behind — 11 records, 5 of them addressed to nobody — captured from their
own stdout rather than typed.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Users/changxing/projects/connectonion/.claude/worktrees/inbox-1.8.5")
INBOX = Path("/private/tmp/claude-501/-Users-changxing-projects/"
             "585412e9-f9ca-4ba8-b15c-627e474f92b2/scratchpad/wa-inbox")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page, shoot          # a2's renderer


def run(*args: str) -> str:
    """One real invocation against the acceptance inbox, colour off."""
    result = subprocess.run(
        [sys.executable, "-m", "connectonion.cli.main", *args],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
        env=dict(os.environ, CO_INBOX_HOME=str(INBOX), NO_COLOR="1", COLUMNS="96"))
    return (result.stdout or "") + (result.stderr or "")


if __name__ == "__main__":
    chats = run("whatsapp", "chats")
    group = next((line.split("\t")[0] for line in chats.splitlines() if "\tgroup\t" in line), "")
    history = run("whatsapp", "log", "--chat", group, "-n", "4")

    out = ROOT / "docs/releases/assets/v1.8.6a5"
    shoot(page("", [("co whatsapp chats", chats),
                    (f"co whatsapp log --chat {group} -n 4", history)]),
          out / "find-a-conversation-and-read-it-back.png")
    print("wrote 1 capture into", out)
