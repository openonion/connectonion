"""Nothing is not a message. #1602.

`co whatsapp send <chat>` with no text read stdin, got EOF, and delivered an
empty bubble — id printed, exit 0, a row in `sent.jsonl` with `"text": ""`.
Everything that normally catches a bad send reported success, because it *was*
a successful send of nothing.

Measured on 2026-09-19: two blanks reached real groups that way, one of them a
client's.

The read-back habit cannot catch this one, so the command has to.
"""

import io
import json
import sys

import pytest

from connectonion.cli.commands import listen_commands
from connectonion.inbox import Inbox, Message


class FakeProvider:
    def __init__(self):
        self.sent = []
        self.edited = []

    def missing(self):
        return []

    def check(self):
        return []

    def render(self, text):
        from connectonion.inbox.formatting import to_whatsapp

        return to_whatsapp(text)

    def send(self, chat, text, *, reply_to=None, fresh=False, plain=False):
        self.sent.append((chat, text))
        return "om_sent"

    def edit(self, chat, message_id, text, *, plain=False):
        self.edited.append((chat, message_id, text))
        return "om_edit"


@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
    return Inbox("whatsapp")


@pytest.fixture
def fake(monkeypatch):
    p = FakeProvider()
    monkeypatch.setattr(listen_commands, "provider", lambda name: p)
    return p


def empty_stdin(monkeypatch, text=""):
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))


class TestSend:
    def test_no_argument_and_empty_stdin_sends_nothing(self, box, fake, monkeypatch, capsys):
        empty_stdin(monkeypatch)

        with pytest.raises(SystemExit) as exit_:
            listen_commands.handle_send("whatsapp", "oc_ops")

        assert exit_.value.code == 2, "a usage error, the same as no text on a terminal"
        assert fake.sent == []
        assert "nothing to send" in capsys.readouterr().err

    def test_whitespace_only_is_also_nothing(self, box, fake, monkeypatch):
        empty_stdin(monkeypatch, "   \n\n  \t\n")

        with pytest.raises(SystemExit) as exit_:
            listen_commands.handle_send("whatsapp", "oc_ops")

        assert exit_.value.code == 2
        assert fake.sent == []

    def test_an_empty_argument_is_refused_too(self, box, fake):
        # `send <chat> ""` — the shell's way of producing the same blank.
        with pytest.raises(SystemExit) as exit_:
            listen_commands.handle_send("whatsapp", "oc_ops", "")

        assert exit_.value.code == 2
        assert fake.sent == []

    def test_nothing_is_written_to_the_send_log(self, box, fake, monkeypatch):
        # A refusal is not an attempt. A row here would make the log claim a
        # send happened, which is the reporting failure this whole release is
        # about.
        empty_stdin(monkeypatch)

        with pytest.raises(SystemExit):
            listen_commands.handle_send("whatsapp", "oc_ops")

        assert not box.sent.exists() or box.sent.read_text().strip() == ""

    def test_a_real_message_still_goes(self, box, fake, monkeypatch, capsys):
        empty_stdin(monkeypatch, "all green\n")

        listen_commands.handle_send("whatsapp", "oc_ops")

        assert fake.sent == [("oc_ops", "all green")]
        assert capsys.readouterr().out.strip().endswith("om_sent")

    def test_text_that_is_only_formatting_still_goes(self, box, fake):
        # `**bold**` renders to `*bold*` — not empty, and not the caller's
        # mistake. The check is on what the caller wrote, not on what is left
        # after stripping marks.
        listen_commands.handle_send("whatsapp", "oc_ops", "**!**")

        assert fake.sent == [("oc_ops", "*!*")]


class TestReply:
    """The issue asked for `reply` to be audited for the same shape."""

    def test_an_empty_reply_is_refused(self, box, fake, monkeypatch):
        box.deliver(Message(id="om_q", chat="oc_ops", sender="on_x", text="?",
                            at="2026-09-19T01:00:00Z"))
        empty_stdin(monkeypatch)

        with pytest.raises(SystemExit) as exit_:
            listen_commands.handle_reply("whatsapp", "om_q")

        assert exit_.value.code == 2
        assert fake.sent == []

    def test_an_empty_reply_does_not_consume_the_message(self, box, fake, monkeypatch):
        # Worse than the blank itself would be losing the question: `reply`
        # marks a message done, and a refused reply must leave it to be
        # answered properly.
        box.deliver(Message(id="om_q", chat="oc_ops", sender="on_x", text="?",
                            at="2026-09-19T01:00:00Z"))
        empty_stdin(monkeypatch)

        with pytest.raises(SystemExit):
            listen_commands.handle_reply("whatsapp", "om_q")

        assert not box.already_replied("om_q")


class TestEdit:
    def test_an_empty_edit_is_refused(self, box, fake, monkeypatch):
        # An edit to nothing is a delete that does not say so, and `delete` is
        # right there.
        box.record_sent(chat="oc_ops", text="something", provider_id="om_1", by="send")
        empty_stdin(monkeypatch)

        with pytest.raises(SystemExit) as exit_:
            listen_commands.handle_edit("whatsapp", "om_1")

        assert exit_.value.code == 2
        assert fake.edited == []
