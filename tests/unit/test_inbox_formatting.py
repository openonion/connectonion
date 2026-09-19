"""Markdown in, WhatsApp's own formatting out.

An agent writes Markdown because that is what agents write. WhatsApp does not
read Markdown: `**bold**` arrives as four literal asterisks around a word, and
a `[label](url)` arrives as punctuation nobody can tap. The conversion is the
difference between a message that looks written and one that looks leaked.
"""

from connectonion.inbox.formatting import to_whatsapp


def test_bold_loses_one_asterisk_on_each_side():
    assert to_whatsapp("**ready**") == "*ready*"
    assert to_whatsapp("__ready__") == "*ready*"


def test_single_asterisk_is_italic_in_markdown_and_underscore_on_whatsapp():
    # The trap: `*x*` means italic in Markdown and bold on WhatsApp. Passing it
    # through unchanged silently changes what the sentence emphasises.
    assert to_whatsapp("*maybe*") == "_maybe_"


def test_strikethrough_loses_one_tilde():
    assert to_whatsapp("~~cancelled~~") == "~cancelled~"


def test_headings_become_bold_because_whatsapp_has_no_headings():
    assert to_whatsapp("# Deploy failed") == "*Deploy failed*"
    assert to_whatsapp("### Deploy failed") == "*Deploy failed*"


def test_links_keep_the_url_a_reader_can_tap():
    assert to_whatsapp("[the run](https://example.com/x)") == "the run: https://example.com/x"


def test_a_link_whose_label_is_its_url_is_not_written_twice():
    assert to_whatsapp("[https://e.com](https://e.com)") == "https://e.com"


def test_bullets_become_the_bullet_character():
    assert to_whatsapp("- one\n- two") == "• one\n• two"
    assert to_whatsapp("* one\n* two") == "• one\n• two"


def test_numbered_lists_are_left_alone_because_whatsapp_renders_them():
    assert to_whatsapp("1. one\n2. two") == "1. one\n2. two"


def test_a_fenced_block_keeps_its_fence_and_drops_the_language():
    assert to_whatsapp("```python\nx = 1\n```") == "```\nx = 1\n```"


def test_nothing_inside_a_fence_is_converted():
    # The whole point of a code block is that its characters are literal.
    assert to_whatsapp("```\n**x** and [a](b)\n```") == "```\n**x** and [a](b)\n```"


def test_nothing_inside_inline_code_is_converted():
    assert to_whatsapp("run `git commit -m **now**`") == "run `git commit -m **now**`"


def test_plain_text_is_returned_unchanged():
    assert to_whatsapp("just a sentence") == "just a sentence"


def test_an_empty_string_stays_empty():
    assert to_whatsapp("") == ""


def test_a_horizontal_rule_becomes_a_line_you_can_see():
    assert to_whatsapp("a\n\n---\n\nb") == "a\n\n──────\n\nb"


def test_a_bare_asterisk_is_not_treated_as_emphasis():
    # `2 * 3 = 6` must not become `2 _ 3 = 6_`.
    assert to_whatsapp("2 * 3 = 6") == "2 * 3 = 6"


def test_bold_inside_a_sentence_keeps_its_neighbours():
    assert to_whatsapp("the **build** failed") == "the *build* failed"


class TestTheProviderUsesIt:
    """The conversion has to sit where every sender passes, not in one verb.

    `consume` replies without going through `handle_reply`, so a conversion
    done in the CLI would prettify a message typed by a person and leave the
    agent's own answers — the ones actually written in Markdown — untouched.
    """

    @staticmethod
    def _whatsapp(monkeypatch):
        from connectonion.inbox.whatsapp import WhatsApp

        box = WhatsApp.__new__(WhatsApp)
        queued = []
        monkeypatch.setattr(WhatsApp, "_queue",
                            lambda self, payload: queued.append(payload) or "om_1")
        return box, queued

    def test_send_reads_its_text_as_markdown(self, monkeypatch):
        box, queued = self._whatsapp(monkeypatch)

        box.send("oc_a", "the **build** failed")

        assert queued[0]["text"] == "the *build* failed"

    def test_send_plain_leaves_the_text_exactly_as_typed(self, monkeypatch):
        box, queued = self._whatsapp(monkeypatch)

        box.send("oc_a", "the **build** failed", plain=True)

        assert queued[0]["text"] == "the **build** failed"

    def test_edit_reads_its_text_as_markdown_too(self, monkeypatch):
        box, queued = self._whatsapp(monkeypatch)

        box.edit("oc_a", "om_1", "# Fixed")

        assert queued[0] == {"kind": "edit", "chat": "oc_a", "message_id": "om_1",
                             "text": "*Fixed*"}

    def test_revoke_carries_the_sender_that_decides_whose_message_it_is(self, monkeypatch):
        box, queued = self._whatsapp(monkeypatch)

        box.revoke("oc_a", "om_1", sender="on_x")

        assert queued[0] == {"kind": "revoke", "chat": "oc_a", "message_id": "om_1",
                             "sender": "on_x"}
