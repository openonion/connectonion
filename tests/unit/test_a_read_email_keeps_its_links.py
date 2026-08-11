"""`co outlook read` used to drop every URL in an HTML mail.

`get_email_body()` renders HTML by deleting every tag:

    body_content = re.sub(r'<[^>]+>', '', body_content)

For `<a href="https://…">Complete the questionnaire</a>` that keeps the words
and throws away the address. The reader is left with an instruction to click
something that is no longer there.

On 2026-08-11 that cost two reference-check questionnaires. Their links carried
a per-recipient token:

    https://forms.example.com/r/AbC123?t=9f2c…

which is not a URL anyone can reconstruct from the anchor text, the sender, or
the subject — unlike a bare marketing link, where you can just visit the site.
The mail was readable, looked complete, and the one thing it existed to deliver
was gone.

So: the words stay where they are, and the address follows in angle brackets —
the convention plain-text mail has used for decades, and one an agent reading
the output can pick up without being taught a new format.
"""

import os
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _stub_token_refresh(monkeypatch):
    from connectonion.useful_tools.outlook import Outlook
    monkeypatch.setattr(Outlook, "_refresh_via_backend", lambda self, rt: "test-token")


def body_rendered_from(html: str) -> str:
    """Whatever `co outlook read` would print for this HTML mail."""
    from connectonion.useful_tools.outlook import Outlook

    with patch.dict(os.environ, {"MICROSOFT_SCOPES": "Mail.Read,Mail.Send"}, clear=False):
        outlook = Outlook()
        with patch.object(outlook, "_request", return_value={
            "from": {"emailAddress": {"name": "HR", "address": "hr@example.com"}},
            "toRecipients": [{"emailAddress": {"address": "me@example.com"}}],
            "subject": "Reference check",
            "receivedDateTime": "2026-08-11T00:00:00Z",
            "body": {"contentType": "html", "content": html},
        }):
            return outlook.get_email_body("msg-id")


class TestALinkSurvives:

    def test_the_url_is_kept(self):
        url = "https://forms.example.com/r/AbC123?t=9f2c"
        out = body_rendered_from(f'<p>Please <a href="{url}">complete it</a>.</p>')

        assert url in out, (
            "the anchor's href was dropped; this URL carries a per-recipient "
            "token and cannot be reconstructed from the text around it"
        )

    def test_the_link_text_is_kept_too(self):
        url = "https://forms.example.com/r/AbC123?t=9f2c"
        out = body_rendered_from(f'<p>Please <a href="{url}">complete it</a>.</p>')

        assert "complete it" in out, "the sentence lost its words"

    def test_several_links_each_keep_their_own_url(self):
        out = body_rendered_from(
            '<a href="https://a.example/1">first</a> and '
            '<a href="https://b.example/2">second</a>'
        )

        assert "https://a.example/1" in out
        assert "https://b.example/2" in out

    def test_single_quoted_href_works(self):
        out = body_rendered_from("<a href='https://a.example/1'>x</a>")

        assert "https://a.example/1" in out

    def test_other_attributes_do_not_hide_the_href(self):
        out = body_rendered_from(
            '<a class="btn" href="https://a.example/1" target="_blank">x</a>'
        )

        assert "https://a.example/1" in out


class TestNothingElseChanges:

    def test_a_bare_url_as_link_text_is_not_printed_twice(self):
        """Mail clients often render the URL as its own anchor text."""
        url = "https://a.example/1"
        out = body_rendered_from(f'<a href="{url}">{url}</a>')

        assert out.count(url) == 1, f"printed twice: {out!r}"

    def test_plain_text_mail_is_untouched(self):
        from connectonion.useful_tools.outlook import Outlook

        with patch.dict(os.environ, {"MICROSOFT_SCOPES": "Mail.Read"}, clear=False):
            outlook = Outlook()
            with patch.object(outlook, "_request", return_value={
                "from": {"emailAddress": {"name": "A", "address": "a@example.com"}},
                "toRecipients": [],
                "subject": "s",
                "receivedDateTime": "2026-08-11T00:00:00Z",
                "body": {"contentType": "text",
                         "content": "see <https://a.example/1>"},
            }):
                out = outlook.get_email_body("id")

        assert "see <https://a.example/1>" in out

    def test_styles_are_still_stripped(self):
        out = body_rendered_from("<style>a {color: red}</style><p>hello</p>")

        assert "color: red" not in out
        assert "hello" in out

    def test_markup_is_still_stripped(self):
        out = body_rendered_from('<p class="x">hello <b>there</b></p>')

        assert "<p" not in out and "<b>" not in out
        assert "hello" in out and "there" in out
