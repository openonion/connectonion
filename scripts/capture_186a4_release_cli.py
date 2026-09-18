"""1.8.6a4's captures, produced by running the release's own code.

The record comes from the real parser over a real protobuf message with the real
contact store behind it; the logged-out transcript is the listener's own log
line and refusal. Nothing here is typed out to look right.
"""
import json
import sys
from pathlib import Path

ROOT = Path("/Users/changxing/projects/connectonion/.claude/worktrees/inbox-1.8.5")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page, shoot          # a2's renderer


def a_message_that_says_who_and_what(out: Path) -> None:
    import os
    from types import SimpleNamespace

    os.environ["WHATSAPP_SESSION"] = str(Path.home() / ".co/inbox/whatsapp/session.db")
    from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import (
        Message as Body, ExtendedTextMessage, ContextInfo)
    from connectonion.inbox.whatsapp import WhatsApp, GROUP_SERVER

    bot = WhatsApp()
    bot._own_user, bot._own_ids = "61410724095", frozenset({"61410724095", "132754033377342"})

    reply = Body()
    reply.extendedTextMessage.CopyFrom(ExtendedTextMessage(
        text="这条不对",
        contextInfo=ContextInfo(stanzaID="3EB0C796D27ADACFDFE66A",
                                participant="132754033377342@lid",
                                quotedMessage=Body(conversation="deploy 41 is live"))))
    event = SimpleNamespace(
        Info=SimpleNamespace(ID="ACQUOTE01", Timestamp=SimpleNamespace(seconds=1789704000),
            MessageSource=SimpleNamespace(
                Chat=SimpleNamespace(User="120363410170505910", Server=GROUP_SERVER, Device=0),
                Sender=SimpleNamespace(User="126121882435737", Server="lid", Device=0),
                IsFromMe=False, IsGroup=True)),
        Message=reply)

    record = bot.to_message(event).to_dict()
    record["context"] = [
        {"at": "2026-09-18T03:58:00Z", "from": "them", "sender": "126121882435737@lid",
         "text": "the price sheet is still wrong", "kind": "text"},
        {"at": "2026-09-18T03:59:10Z", "from": "us", "sender": "",
         "text": "looking now", "kind": "text"},
    ]
    shoot(page("", [("co whatsapp receive --context 20",
                     json.dumps(record, ensure_ascii=False, indent=1))]), out)


def a_listener_that_was_unlinked(out: Path) -> None:
    log = ("2026-09-18T05:12:03Z connected as 61410724095 (also 132754033377342)\n"
           "2026-09-18T06:41:55Z listener stopped: logged out by the phone (reason 401). "
           "This device was unlinked under Settings > Linked devices. "
           "Next: co whatsapp listen — scan the QR again\n")
    refusal = ("logged out by the phone (reason 401). This device was unlinked under\n"
               "Settings > Linked devices. Next: co whatsapp listen — scan the QR again\n"
               "# exit 3 — a person has to act; no restart helps\n")
    shoot(page("", [("co whatsapp log", log), ("co whatsapp listen", refusal)]), out)


if __name__ == "__main__":
    out = ROOT / "docs/releases/assets/v1.8.6a4"
    a_message_that_says_who_and_what(out / "who-is-talking-and-what-they-mean.png")
    a_listener_that_was_unlinked(out / "a-listener-that-stopped-says-why.png")
    print("wrote 2 captures into", out)
