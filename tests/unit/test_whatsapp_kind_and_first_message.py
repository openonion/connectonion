"""Group text is `text`, and a sender's first group message is not lost (#1858, #1837).

On the owner's real inbox 154 of 334 records were `kind: "messagecontextinfo"`:
ordinary group messages named after the delivery metadata WhatsApp attaches to
them. The older fakes in test_inbox_whatsapp.py gave `conversation` a message
type; the real protobuf field is a string, which is how this passed. These use
the real field types.

And a person's first message in a group arrived twice under one id: an empty
sender-key frame, then the text. Dedup kept the first, so the text was lost.
"""

from types import SimpleNamespace

import pytest

from connectonion.inbox.store import Inbox
from connectonion.inbox.whatsapp import WhatsApp, _kind
from tests.unit.test_inbox_whatsapp import OWN, event, linked, sdk  # noqa: F401  (sdk is a fixture)

STRING, MESSAGE = 9, 11


def field(name, kind, value):
    descriptor = SimpleNamespace(name=name, label=1, LABEL_REPEATED=3, type=kind, TYPE_MESSAGE=MESSAGE,
                                 is_repeated=False)
    return descriptor, value


def carrier():
    return SimpleNamespace(HasField=lambda f: False)


def message(text, *fields):
    return SimpleNamespace(text=text, ListFields=lambda: list(fields))


GROUP_TEXT = lambda text: message(text, field("conversation", STRING, text),  # noqa: E731
                                  field("messageContextInfo", MESSAGE, carrier()))
SENDER_KEY_ONLY = message("", field("senderKeyDistributionMessage", MESSAGE, carrier()),
                          field("messageContextInfo", MESSAGE, carrier()))


def test_a_group_text_with_delivery_metadata_is_text():
    assert _kind(GROUP_TEXT("dinner at 7?")) == "text"


def test_metadata_never_names_an_image_either():
    image = SimpleNamespace(contextInfo=SimpleNamespace(mentionedJID=[], participant=""), HasField=lambda f: True)
    assert _kind(message("", field("senderKeyDistributionMessage", MESSAGE, carrier()),
                         field("imageMessage", MESSAGE, image))) == "image"


def test_a_frame_of_only_metadata_is_not_a_message(sdk):
    frame = event(text="")
    frame.Message = SENDER_KEY_ONLY
    assert linked(WhatsApp(), ids=(OWN,)).to_message(frame) is None


def test_a_senders_first_group_message_survives_its_sender_key_frame(sdk):
    """#1837: the frame and the text share an id; the text must be what is kept."""
    bot = linked(WhatsApp(), ids=(OWN,))
    inbox = Inbox("whatsapp")
    frame, first = event(text="", message_id="AC8956"), event(text="hi all, I'm Mia", message_id="AC8956")
    frame.Message, first.Message = SENDER_KEY_ONLY, GROUP_TEXT("hi all, I'm Mia")
    for arriving in (frame, first):
        found = bot.to_message(arriving)
        if found is not None:
            inbox.deliver(found)
    [kept] = inbox.list_messages()
    assert (kept.id, kept.kind, kept.text) == ("AC8956", "text", "hi all, I'm Mia")


def test_the_real_protobuf_shapes_where_neonize_is_installed():
    """The fakes hid #1858; this runs _kind on neonize's own Message type.
    In a subprocess: importing neonize starts its runtime thread."""
    import importlib.util
    import subprocess
    import sys
    if importlib.util.find_spec("neonize") is None:
        pytest.skip("the WhatsApp extra (neonize) is not installed")
    check = """
from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import Message
from connectonion.inbox.whatsapp import PROTOCOL_ONLY, _kind
text = Message(conversation="dinner at 7?"); text.messageContextInfo.messageSecret = b"x" * 32
frame = Message(); frame.senderKeyDistributionMessage.groupID = "1@g.us"
frame.messageContextInfo.messageSecret = b"y" * 32
image = Message(); image.senderKeyDistributionMessage.groupID = "1@g.us"; image.imageMessage.mimetype = "image/jpeg"
assert (_kind(text), _kind(frame), _kind(image)) == ("text", PROTOCOL_ONLY, "image"), (_kind(text), _kind(frame), _kind(image))
"""
    result = subprocess.run([sys.executable, "-c", check], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr[-2000:]
