"""A plain-text body keeps its paragraphs and line breaks once the mail service sends it as HTML (#2395)."""
from unittest.mock import MagicMock, patch

from connectonion.useful_tools.send_email import send_email
from tests.utils.config_helpers import TEST_ACCOUNT, TEST_JWT_TOKEN


def _sent_body(message: str) -> str:
    reply = MagicMock(status_code=200)
    reply.json.return_value = {"message_id": "m"}
    with patch.dict("os.environ", {"OPENONION_API_KEY": TEST_JWT_TOKEN, "AGENT_EMAIL": TEST_ACCOUNT["email"]}), \
            patch("requests.post", return_value=reply) as post:
        assert send_email("someone@example.com", "s", message)["success"] is True
    return post.call_args.kwargs["json"]["body"]


def test_blank_lines_become_paragraphs_and_newlines_become_breaks():
    body = _sent_body("Line one.\nLine two.\n\nSecond paragraph.\n\n\nThird.")
    assert body == "<p>Line one.<br>\nLine two.</p>\n<p>Second paragraph.</p>\n<p>Third.</p>"


def test_plain_text_is_escaped_so_angle_brackets_show_as_written():
    assert _sent_body("1 < 2 & 3 > 2") == "<p>1 &lt; 2 &amp; 3 &gt; 2</p>"


def test_a_body_that_is_already_html_goes_as_is():
    html = "<pre>keep\n\nme</pre>"
    assert _sent_body(html) == html
