"""A reply in an inbox says which message it answers, next to its text (#3226).

In a group, "yes please" or "the first one" means nothing without the message
it quotes. The reference was always stored in `quoted`, but an agent reads
`text` and guessed: a reply about one video was taken for another.
"""
import json

import pytest

from connectonion.cli.commands import listen_commands
from connectonion.inbox import Inbox, Message
from connectonion.inbox.store import reply_line

QUOTE = {"id": "3EB0COVER", "sender": "6591234567@s.whatsapp.net", "text": "Cover for the launch video, v2",
         "kind": "text", "from_me": True}


@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
    monkeypatch.setattr(listen_commands, "_configured", lambda name, **_: None)
    monkeypatch.setattr(listen_commands, "_saved_names", lambda name: (lambda jid: ""))
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self, **_: None)
    return Inbox("whatsapp")


def reply(**quoted):
    return Message(id="3EB0YES", chat="120363@g.us", sender="6597654321@s.whatsapp.net",
                   text="Yes please", at="2026-11-17T09:00:00Z", quoted={**QUOTE, **quoted})


def test_receive_shows_the_quoted_message_right_after_the_text(box, capsys):
    box.deliver(reply())

    listen_commands.handle_receive("whatsapp", timeout=0)

    line = capsys.readouterr().out
    record = json.loads(line)
    assert record["reply_to"] == '↩ replying to you: "Cover for the launch video, v2" (id 3EB0COVER)'
    assert list(record)[list(record).index("text") + 1] == "reply_to"
    assert record["quoted"] == QUOTE  # the full object stays for --json readers


def test_a_message_that_quotes_nothing_is_unchanged(box, capsys):
    plain = Message(id="m1", chat="c", sender="s", text="hi", at="2026-11-17T09:00:00Z")
    box.deliver(plain)

    listen_commands.handle_receive("whatsapp", timeout=0)

    record = json.loads(capsys.readouterr().out)
    assert "reply_to" not in record
    assert list(record) == ["id", "chat", "thread", "sender", "sender_name", "text", "kind",
                            "quoted", "mentioned", "at"]


def test_someone_elses_message_a_photo_and_a_long_text_still_read(box):
    assert reply_line({**QUOTE, "from_me": False}).startswith('↩ replying to 6591234567: "Cover')
    assert reply_line({**QUOTE, "text": "", "kind": "image"}) == "↩ replying to you: (image) (id 3EB0COVER)"
    long = reply_line({**QUOTE, "text": "word " * 60})
    assert '…"' in long and len(long.split('"')[1]) == 120
    assert reply_line(None) == "" and reply_line({"text": "no id"}) == ""


def test_the_log_adds_it_to_a_reply_stored_before_it_existed(box, capsys):
    record = {**reply().to_dict()}
    record.pop("reply_to")
    box.received.parent.mkdir(parents=True, exist_ok=True)
    box.received.write_text(json.dumps(record) + "\n", encoding="utf-8")

    listen_commands.handle_log("whatsapp")

    shown = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert shown["reply_to"].startswith("↩ replying to you:")
