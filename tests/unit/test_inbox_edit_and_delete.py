"""Changing a message after it has been sent, and taking one back.

An agent that answers in a group gets things wrong in public. Until now the
only repair was a second message saying "sorry, I meant", which leaves the
wrong one sitting above it forever.
"""

import json

import pytest

from connectonion.cli.commands import listen_commands
from connectonion.inbox import Inbox, Message


class FakeProvider:
    def __init__(self):
        self.edited = []
        self.revoked = []
        self.fail = None

    def missing(self):
        return []

    def check(self):
        return []

    def render(self, text):
        # The real WhatsApp provider's own renderer, not a stand-in: a fake
        # that "renders" by returning the input would let a handler that never
        # calls it pass.
        from connectonion.inbox.formatting import to_whatsapp

        return to_whatsapp(text)

    def send(self, chat, text, *, reply_to=None, fresh=False, plain=False):
        return "om_sent"

    def edit(self, chat, message_id, text, *, plain=False):
        if self.fail:
            raise RuntimeError(self.fail)
        self.edited.append((chat, message_id, text))
        return f"om_edit{len(self.edited)}"

    def revoke(self, chat, message_id, *, sender=""):
        if self.fail:
            raise RuntimeError(self.fail)
        self.revoked.append((chat, message_id, sender))
        return f"om_revoke{len(self.revoked)}"


@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
    return Inbox("whatsapp")


@pytest.fixture
def fake(monkeypatch):
    p = FakeProvider()
    monkeypatch.setattr(listen_commands, "provider", lambda name: p)
    return p


class TestEdit:
    def test_the_chat_comes_from_the_send_record_so_the_id_is_enough(self, box, fake, capsys):
        box.record_sent(chat="oc_ops", text="the buidl failed", provider_id="om_1", by="send")

        listen_commands.handle_edit("whatsapp", "om_1", "the build failed")

        assert fake.edited == [("oc_ops", "om_1", "the build failed")]
        assert capsys.readouterr().out.strip() == "om_edit1"

    def test_the_edit_is_recorded_so_the_log_shows_what_was_said_last(self, box, fake):
        box.record_sent(chat="oc_ops", text="wrong", provider_id="om_1", by="send")

        listen_commands.handle_edit("whatsapp", "om_1", "right")

        last = [json.loads(line) for line in box.sent.read_text().splitlines()][-1]
        assert last["text"] == "right" and last["by"] == "edit of om_1"

    def test_editing_a_message_we_did_not_send_says_that_and_not_no_such_id(
            self, box, fake, capsys):
        # Someone else's message is in received.jsonl, and WhatsApp will not
        # let us rewrite it. "No such message" would send the reader looking
        # for a typo in an id that is perfectly correct.
        box.deliver(Message(id="om_theirs", chat="oc_ops", sender="on_x", text="hi",
                            at="2026-09-19T01:00:00Z"))

        with pytest.raises(SystemExit) as exit_:
            listen_commands.handle_edit("whatsapp", "om_theirs", "no")

        assert exit_.value.code == 1
        assert "no record of sending" in capsys.readouterr().err
        assert fake.edited == []

    def test_a_send_that_failed_is_not_offered_as_editable(self, box, fake):
        # It has no id on the platform, so an edit would go nowhere.
        box.record_sent(chat="oc_ops", text="x", provider_id="om_1", error="refused", by="send")

        with pytest.raises(SystemExit):
            listen_commands.handle_edit("whatsapp", "om_1", "y")

    def test_the_text_is_rendered_before_it_is_handed_over(self, box, fake):
        # Rendered once, in the handler, so the string that reaches the
        # platform is the string written to sent.jsonl. `--plain` is the only
        # way to get the characters through untouched.
        box.record_sent(chat="oc_ops", text="x", provider_id="om_1", by="send")

        listen_commands.handle_edit("whatsapp", "om_1", "**done**")
        listen_commands.handle_edit("whatsapp", "om_1", "**done**", plain=True)

        assert [text for _, _, text in fake.edited] == ["*done*", "**done**"]

    def test_the_record_says_what_was_sent_not_what_was_typed(self, box, fake):
        # `log` showing Markdown that nobody in the chat ever saw is the same
        # defect as a `check` that reports a network it never touched.
        box.record_sent(chat="oc_ops", text="x", provider_id="om_1", by="send")

        listen_commands.handle_edit("whatsapp", "om_1", "**done**")

        last = [json.loads(line) for line in box.sent.read_text().splitlines()][-1]
        assert last["text"] == "*done*"

    def test_a_refusal_from_the_platform_exits_1(self, box, fake, capsys):
        box.record_sent(chat="oc_ops", text="x", provider_id="om_1", by="send")
        fake.fail = "message is too old to edit"

        with pytest.raises(SystemExit) as exit_:
            listen_commands.handle_edit("whatsapp", "om_1", "y")

        assert exit_.value.code == 1
        assert "too old to edit" in capsys.readouterr().err


class TestDelete:
    def test_deleting_our_own_message_sends_no_sender(self, box, fake, capsys):
        # An empty sender is what tells the provider "this one is ours", which
        # is what makes WhatsApp stamp fromMe.
        box.record_sent(chat="oc_ops", text="oops", provider_id="om_1", by="send")

        listen_commands.handle_delete("whatsapp", "om_1")

        assert fake.revoked == [("oc_ops", "om_1", "")]
        assert capsys.readouterr().out.strip() == "om_revoke1"

    def test_deleting_someone_elses_message_names_who_sent_it(self, box, fake):
        # A group admin can delete another member's message, and the platform
        # has to be told whose it was.
        box.deliver(Message(id="om_theirs", chat="oc_ops", sender="on_x", text="spam",
                            at="2026-09-19T01:00:00Z"))

        listen_commands.handle_delete("whatsapp", "om_theirs")

        assert fake.revoked == [("oc_ops", "om_theirs", "on_x")]

    def test_an_unknown_id_names_both_places_that_were_searched(self, box, fake, capsys):
        with pytest.raises(SystemExit) as exit_:
            listen_commands.handle_delete("whatsapp", "om_nope")

        assert exit_.value.code == 1
        err = capsys.readouterr().err
        assert "received.jsonl" in err and "sent.jsonl" in err

    def test_a_refusal_from_the_platform_exits_1(self, box, fake, capsys):
        box.record_sent(chat="oc_ops", text="x", provider_id="om_1", by="send")
        fake.fail = "not an admin of this group"

        with pytest.raises(SystemExit) as exit_:
            listen_commands.handle_delete("whatsapp", "om_1")

        assert exit_.value.code == 1
        assert "not an admin" in capsys.readouterr().err


class TestAProviderWithoutThem:
    """Feishu and Lark have the endpoints and nobody has wired them up."""

    def test_edit_says_which_provider_has_it_rather_than_failing_blankly(
            self, box, monkeypatch, capsys):
        class NoEdit:
            def missing(self):
                return []

            def check(self):
                return []

        monkeypatch.setattr(listen_commands, "provider", lambda name: NoEdit())

        with pytest.raises(SystemExit) as exit_:
            listen_commands.handle_edit("lark", "om_1", "x")

        assert exit_.value.code == 1
        err = capsys.readouterr().err
        assert "not implemented" in err and "WhatsApp" in err
