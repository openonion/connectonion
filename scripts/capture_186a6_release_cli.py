"""1.8.6a6's capture: the events that used to be silence.

The connection half is the live listener's own log from the real account. The
record half is the release's own parser over a real UndecryptableMessageEv
shape, run rather than typed.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path("/Users/changxing/projects/connectonion/.claude/worktrees/inbox-1.8.5")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page, shoot          # a2's renderer


def records() -> str:
    """What an undecryptable message and a group join now look like."""
    from connectonion.inbox.store import Message

    undecryptable = Message(
        id="ACUNDEC01", chat="120363410170505910@g.us",
        sender="126121882435737@lid", sender_name="aaronplus1996",
        text="could not be decrypted (SHOW)", kind="undecryptable", quoted=None,
        mentioned=False, at="2026-09-19T07:41:02Z", thread=None)
    joined = Message(
        id="joined-120363410170505910@g.us-1789800000",
        chat="120363410170505910@g.us", sender="", sender_name="",
        text="added to co185 acceptance", kind="joined", quoted=None,
        mentioned=True, at="2026-09-19T07:44:10Z", thread=None)
    return "\n".join(json.dumps(m.to_dict(), ensure_ascii=False) for m in (undecryptable, joined))


if __name__ == "__main__":
    live = Path.home() / ".co" / "inbox" / "whatsapp" / "log"
    tail = [line for line in live.read_text(encoding="utf-8").splitlines()
            if "disconnected" in line or "connected as" in line][-3:]

    out = ROOT / "docs/releases/assets/v1.8.6a6"
    shoot(page("", [
        ("co whatsapp log   # a real reconnection, now visible", "\n".join(tail)),
        ("co whatsapp receive   # what used to be discarded", records()),
    ]), out / "events-that-used-to-be-silence.png")
    print("wrote 1 capture into", out)
