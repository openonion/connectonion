"""1.8.6a3's captures: a message that says what it is and what it answers.

The two records are produced by running the real parser over a real protobuf
reply — not typed out — so the picture cannot drift from the behaviour.
"""
import io
import json
import sys
from pathlib import Path

ROOT = Path("/Users/changxing/projects/connectonion/.claude/worktrees/inbox-1.8.5")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from rich.console import Console
from rich.text import Text

from capture_186a2_release_cli import page, shoot  # same renderer as a2


def records():
    """Run the parser over a real protobuf reply and a real image message."""
    from types import SimpleNamespace
    from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import (
        Message as Body, ExtendedTextMessage, ContextInfo, ImageMessage)
    from connectonion.inbox.whatsapp import WhatsApp, GROUP_SERVER, USER_SERVER

    bot = WhatsApp()
    bot._own_user = "61410724095"
    bot._own_ids = frozenset({"61410724095", "132754033377342"})

    def event(body, message_id):
        return SimpleNamespace(
            Info=SimpleNamespace(
                ID=message_id, Timestamp=SimpleNamespace(seconds=1789704000),
                MessageSource=SimpleNamespace(
                    Chat=SimpleNamespace(User="120363410170505910", Server=GROUP_SERVER, Device=0),
                    Sender=SimpleNamespace(User="126121882435737", Server="lid", Device=0),
                    IsFromMe=False, IsGroup=True)),
            Message=body)

    reply = Body()
    reply.extendedTextMessage.CopyFrom(ExtendedTextMessage(
        text="这条不对",
        contextInfo=ContextInfo(
            stanzaID="3EB0C796D27ADACFDFE66A",
            participant="132754033377342@lid",
            quotedMessage=Body(conversation="收到：LID @提及现在能识别了"))))

    photo = Body()
    photo.imageMessage.CopyFrom(ImageMessage(caption=""))

    return (bot.to_message(event(reply, "ACQUOTE01")),
            bot.to_message(event(photo, "ACPHOTO01")))


def shaped(message):
    return json.dumps(message.to_dict(), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    quoted, photo = records()
    out = ROOT / "docs/releases/assets/v1.8.6a3"
    shoot(page("", [("co whatsapp receive   # a reply, quoting the bot", shaped(quoted))]),
          out / "a-reply-carries-what-it-answers.png")
    shoot(page("", [("co whatsapp receive   # a photo with no caption", shaped(photo))]),
          out / "a-photo-is-not-an-empty-message.png")
    print("wrote 2 captures into", out)
