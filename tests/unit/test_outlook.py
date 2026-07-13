"""Test the Outlook tool functionality."""
"""
LLM-Note: Tests for outlook

What it tests:
- Outlook functionality: init scope checks, token management, formatting, read/search, send (attachments, send_at scheduling), reply (plain-text→HTML paragraph conversion, scheduled), get_scheduled (paging), mark read, unread count

Components under test:
- Module: outlook
"""


import os
from hashlib import sha256
import httpx
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def _stub_token_fetch(request, monkeypatch):
    """Keep Graph-operation tests isolated from the oo-api token endpoint."""
    if "token_fetch" in request.keywords:
        return
    from connectonion.useful_tools.outlook import Outlook
    monkeypatch.setattr(
        Outlook,
        "_fetch_access_token",
        lambda self, rejected_access_token=None: "test-token",
    )


class TestOutlookInit:
    """Test Outlook initialization."""

    def test_outlook_requires_microsoft_scopes(self):
        """Test that Outlook raises error when Microsoft scopes are missing."""
        with patch.dict(os.environ, {"MICROSOFT_SCOPES": ""}, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            with pytest.raises(ValueError) as exc_info:
                Outlook()
            assert "Missing Microsoft Mail scopes" in str(exc_info.value)
            assert "co auth microsoft" in str(exc_info.value)

    def test_outlook_init_with_valid_scopes(self):
        """Test that Outlook initializes with valid scopes."""
        with patch.dict(os.environ, {"MICROSOFT_SCOPES": "Mail.Read,Mail.Send"}, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            assert outlook._access_token is None


class TestOutlookTokenManagement:
    """Test Outlook token management."""

    @pytest.mark.token_fetch
    def test_get_access_token_requires_openonion_auth(self):
        """The client needs only an OpenOnion API key, not Microsoft tokens."""
        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "OPENONION_API_KEY": "",
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            with pytest.raises(ValueError) as exc_info:
                outlook._get_access_token()
            assert "co auth" in str(exc_info.value)

    @pytest.mark.token_fetch
    @patch('connectonion.useful_tools.outlook.httpx')
    def test_first_use_fetches_once_without_a_request_body(self, mock_httpx):
        """First use asks oo-api once; later uses reuse only instance memory."""
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "access_token": "server-access",
            "expires_in": 3600,
        }
        mock_httpx.post.return_value = response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "OPENONION_API_KEY": "api-key",
            "OPENONION_API_URL": "https://oo.example",
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            assert outlook._get_access_token() == "server-access"
            assert outlook._get_access_token() == "server-access"

        mock_httpx.post.assert_called_once_with(
            "https://oo.example/api/v1/oauth/microsoft/refresh",
            headers={"Authorization": "Bearer api-key"},
        )

    @pytest.mark.token_fetch
    @patch('connectonion.useful_tools.outlook.httpx')
    def test_access_token_is_refetched_five_minutes_before_expiry(self, mock_httpx):
        first = MagicMock(status_code=200)
        first.json.return_value = {
            "access_token": "first-access",
            "expires_in": 3600,
        }
        second = MagicMock(status_code=200)
        second.json.return_value = {
            "access_token": "second-access",
            "expires_in": 3600,
        }
        mock_httpx.post.side_effect = [first, second]

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "OPENONION_API_KEY": "api-key",
        }, clear=False), patch(
            "connectonion.useful_tools.outlook.time.monotonic",
            side_effect=[1000, 4299, 4300, 4300],
        ):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            assert outlook._get_access_token() == "first-access"
            assert outlook._get_access_token() == "first-access"
            assert outlook._get_access_token() == "second-access"

        assert mock_httpx.post.call_count == 2

    @pytest.mark.token_fetch
    @patch('connectonion.useful_tools.outlook.httpx')
    def test_graph_401_reports_rejected_token_and_retries_once(self, mock_httpx):
        """A Graph 401 triggers one server refresh tied to the rejected token."""
        first_graph = MagicMock(status_code=401, text="expired")
        second_graph = MagicMock(status_code=200, text='{"value": []}')
        second_graph.json.return_value = {"value": []}
        mock_httpx.request.side_effect = [first_graph, second_graph]

        token_response = MagicMock(status_code=200)
        token_response.json.return_value = {
            "access_token": "fresh-access",
            "expires_in": 3600,
        }
        mock_httpx.post.return_value = token_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "OPENONION_API_KEY": "api-key",
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            outlook._access_token = "rejected-access"
            assert outlook._request("GET", "/me/messages") == {"value": []}

        assert mock_httpx.request.call_count == 2
        mock_httpx.post.assert_called_once_with(
            "https://oo.openonion.ai/api/v1/oauth/microsoft/refresh",
            headers={"Authorization": "Bearer api-key"},
            json={
                "rejected_access_token_hash": sha256(
                    b"rejected-access"
                ).hexdigest()
            },
        )

    @pytest.mark.token_fetch
    @patch('connectonion.useful_tools.outlook.httpx')
    def test_second_graph_401_is_not_retried(self, mock_httpx):
        """The retry budget is exactly one Graph request."""
        graph_401 = MagicMock(status_code=401, text="expired")
        mock_httpx.request.side_effect = [graph_401, graph_401]
        token_response = MagicMock(status_code=200)
        token_response.json.return_value = {
            "access_token": "fresh-access",
            "expires_in": 3600,
        }
        mock_httpx.post.return_value = token_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "OPENONION_API_KEY": "api-key",
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            outlook._access_token = "rejected-access"
            with pytest.raises(ValueError, match="Microsoft Graph API error: 401"):
                outlook._request("GET", "/me/messages")

        assert mock_httpx.request.call_count == 2
        assert mock_httpx.post.call_count == 1

    @pytest.mark.token_fetch
    @pytest.mark.parametrize(
        ("status_code", "message"),
        [
            (404, "Reconnect with: co auth microsoft"),
            (409, "Reconnect with: co auth microsoft"),
            (401, "Run: co auth"),
            (403, "Run: co auth"),
            (503, "token service unavailable"),
        ],
    )
    @patch('connectonion.useful_tools.outlook.httpx')
    def test_token_service_error_mapping(self, mock_httpx, status_code, message):
        response = MagicMock(status_code=status_code)
        mock_httpx.post.return_value = response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read",
            "OPENONION_API_KEY": "api-key",
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            with pytest.raises(ValueError, match=message):
                Outlook()._get_access_token()

    @pytest.mark.token_fetch
    @patch('connectonion.useful_tools.outlook.httpx.post')
    def test_token_service_network_failure_is_sanitized(self, post):
        request = httpx.Request("POST", "https://oo.example/refresh")
        post.side_effect = httpx.ConnectError("offline", request=request)

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read",
            "OPENONION_API_KEY": "api-key",
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            with pytest.raises(ValueError, match="token service unavailable"):
                Outlook()._get_access_token()

    @pytest.mark.token_fetch
    @patch('connectonion.useful_tools.outlook.httpx')
    def test_malformed_token_response_is_rejected(self, mock_httpx):
        response = MagicMock(status_code=200)
        response.json.return_value = {"expires_in": 3600}
        mock_httpx.post.return_value = response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read",
            "OPENONION_API_KEY": "api-key",
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            with pytest.raises(ValueError, match="invalid Microsoft token response"):
                Outlook()._get_access_token()


class TestOutlookEmailFormatting:
    """Test Outlook email formatting."""

    def test_format_emails_empty_list(self):
        """Test formatting empty email list."""
        with patch.dict(os.environ, {"MICROSOFT_SCOPES": "Mail.Read,Mail.Send"}, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            result = outlook._format_emails([])
            assert "No emails found" in result

    def test_format_emails_with_messages(self):
        """Test formatting email list with messages."""
        with patch.dict(os.environ, {"MICROSOFT_SCOPES": "Mail.Read,Mail.Send"}, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()

            messages = [
                {
                    'id': 'msg-123',
                    'from': {'emailAddress': {'address': 'alice@example.com', 'name': 'Alice'}},
                    'subject': 'Test Email',
                    'receivedDateTime': '2024-01-15T10:00:00Z',
                    'bodyPreview': 'This is a test preview',
                    'isRead': False
                }
            ]

            result = outlook._format_emails(messages)
            assert "alice@example.com" in result
            assert "Test Email" in result
            assert "[UNREAD]" in result
            assert "msg-123" in result


class TestOutlookReadOperations:
    """Test Outlook read operations with mocked API."""

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_read_inbox(self, mock_httpx):
        """Test reading inbox."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'value': [
                {
                    'id': 'msg-1',
                    'from': {'emailAddress': {'address': 'test@example.com', 'name': 'Test'}},
                    'subject': 'Hello',
                    'receivedDateTime': '2024-01-15T10:00:00Z',
                    'bodyPreview': 'Preview text',
                    'isRead': True
                }
            ]
        }
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            result = outlook.read_inbox(last=5)

            assert "test@example.com" in result
            assert "Hello" in result

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_search_emails(self, mock_httpx):
        """Test searching emails."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'value': [
                {
                    'id': 'msg-search-1',
                    'from': {'emailAddress': {'address': 'found@example.com', 'name': 'Found'}},
                    'subject': 'Search Result',
                    'receivedDateTime': '2024-01-15T10:00:00Z',
                    'bodyPreview': 'Found content',
                    'isRead': True
                }
            ]
        }
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            result = outlook.search_emails("test query")

            assert "found@example.com" in result
            assert "Search Result" in result


class TestOutlookListInbox:
    """Test structured inbox listing (used by the CLI)."""

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_list_inbox_returns_dicts(self, mock_httpx):
        """Test list_inbox returns plain email dicts."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'value': [
                {
                    'id': 'msg-1',
                    'from': {'emailAddress': {'address': 'test@example.com', 'name': 'Test'}},
                    'subject': 'Hello',
                    'receivedDateTime': '2024-01-15T10:00:00Z',
                    'bodyPreview': 'Preview text',
                    'isRead': False
                }
            ]
        }
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            emails = outlook.list_inbox(last=5)

            assert emails == [{
                'id': 'msg-1',
                'from': 'test@example.com',
                'from_name': 'Test',
                'subject': 'Hello',
                'date': '2024-01-15T10:00:00Z',
                'snippet': 'Preview text',
                'unread': True
            }]


class TestOutlookSendOperations:
    """Test Outlook send operations with mocked API."""

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_send_email(self, mock_httpx):
        """Test sending email."""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.text = ""  # Graph sendMail returns 202 with an empty body
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            result = outlook.send(
                to="recipient@example.com",
                subject="Test Subject",
                body="Test Body"
            )

            assert "sent successfully" in result
            assert "recipient@example.com" in result

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_send_email_with_attachment(self, mock_httpx, tmp_path):
        """Test sending email with a file attachment."""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.text = ""  # Graph sendMail returns 202 with an empty body
        mock_httpx.request.return_value = mock_response

        screenshot = tmp_path / "screenshot.png"
        screenshot.write_bytes(b"\x89PNG fake image data")

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            result = outlook.send(
                to="recipient@example.com",
                subject="Test Subject",
                body="Test Body",
                attachments=[str(screenshot)]
            )

            assert "sent successfully" in result
            assert "screenshot.png" in result

            sent_message = mock_httpx.request.call_args.kwargs["json"]["message"]
            attachment = sent_message["attachments"][0]
            assert attachment["@odata.type"] == "#microsoft.graph.fileAttachment"
            assert attachment["name"] == "screenshot.png"
            assert attachment["contentType"] == "image/png"
            assert attachment["contentBytes"]

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_send_email_scheduled(self, mock_httpx):
        """Test scheduled send sets the deferred-send extended property."""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.text = ""  # Graph sendMail returns 202 with an empty body
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            result = outlook.send(
                to="recipient@example.com",
                subject="Test Subject",
                body="Test Body",
                send_at="2026-07-06T15:30:00Z"
            )

            assert "scheduled" in result.lower()
            assert "2026-07-06T15:30:00Z" in result
            assert "recipient@example.com" in result

            method, url = mock_httpx.request.call_args.args[:2]
            assert method == "POST"
            assert url.endswith("/me/sendMail")

            sent_message = mock_httpx.request.call_args.kwargs["json"]["message"]
            assert sent_message["singleValueExtendedProperties"] == [
                {"id": "SystemTime 0x3FEF", "value": "2026-07-06T15:30:00Z"}
            ]

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_send_email_missing_attachment(self, mock_httpx):
        """Test sending with a nonexistent attachment path raises."""
        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            import pytest
            outlook = Outlook()
            with pytest.raises(ValueError, match="Attachment not found"):
                outlook.send(
                    to="recipient@example.com",
                    subject="Test",
                    body="Test",
                    attachments=["/no/such/file.png"]
                )


class TestOutlookReply:
    """Test reply operations with mocked API."""

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_reply_scheduled(self, mock_httpx):
        """Test scheduled reply carries the deferred-send property."""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.text = ""
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            result = outlook.reply("msg-1", "See you then", send_at="2026-07-06T15:30:00Z")

            assert "scheduled" in result.lower()
            payload = mock_httpx.request.call_args.kwargs["json"]
            assert payload["comment"] == "<p>See you then</p>"
            prop = payload["message"]["singleValueExtendedProperties"][0]
            assert prop == {"id": "SystemTime 0x3FEF", "value": "2026-07-06T15:30:00Z"}

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_reply_immediate_has_no_message_block(self, mock_httpx):
        """Test immediate reply payload stays a bare comment."""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.text = ""
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            result = outlook.reply("msg-1", "Thanks!")

            assert "sent" in result.lower()
            assert mock_httpx.request.call_args.kwargs["json"] == {"comment": "<p>Thanks!</p>"}

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_reply_plain_text_paragraphs_become_html(self, mock_httpx):
        """Plain-text paragraphs convert to <p> blocks so Graph keeps line breaks."""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.text = ""
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            outlook.reply("msg-1", "Hi Tamara,\n\nFirst line\nsecond line\n\nBye")

            comment = mock_httpx.request.call_args.kwargs["json"]["comment"]
            assert comment == "<p>Hi Tamara,</p><p>First line<br>second line</p><p>Bye</p>"

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_reply_escapes_html_characters(self, mock_httpx):
        """User text is escaped so '<' and '&' can't inject markup or vanish."""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.text = ""
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            outlook.reply("msg-1", "cost < $10 & rising")

            comment = mock_httpx.request.call_args.kwargs["json"]["comment"]
            assert comment == "<p>cost &lt; $10 &amp; rising</p>"


class TestOutlookActions:
    """Test Outlook action operations with mocked API."""

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_mark_read(self, mock_httpx):
        """Test marking email as read."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            result = outlook.mark_read("msg-123")

            assert "Marked email as read" in result
            assert "msg-123" in result

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_count_unread(self, mock_httpx):
        """Test counting unread emails."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'unreadItemCount': 5}
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            result = outlook.count_unread()

            assert "5" in result
            assert "unread" in result.lower()

class TestOutlookScheduled:
    """Test scheduled-send listing and cancellation with mocked API."""

    ENV = {
        "MICROSOFT_SCOPES": "Mail.ReadWrite,Mail.Send",
        "MICROSOFT_ACCESS_TOKEN": "test-token",
        "MICROSOFT_REFRESH_TOKEN": "test-refresh",
        "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z",
    }

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_get_scheduled_filters_ordinary_drafts(self, mock_httpx):
        """Only drafts carrying the deferred-send property count as scheduled."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "ok"
        mock_response.json.return_value = {"value": [
            {
                "id": "sched-1",
                "subject": "RE: Access to the MCIC",
                "toRecipients": [{"emailAddress": {"address": "tamara@unsw.edu.au"}}],
                "singleValueExtendedProperties": [
                    {"id": "SystemTime 0x3fef", "value": "2026-07-06T22:00:00Z"}
                ],
            },
            {
                "id": "plain-draft",
                "subject": "unfinished thought",
                "toRecipients": [],
            },
        ]}
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, self.ENV, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            scheduled = Outlook().get_scheduled()

        assert scheduled == [{
            "id": "sched-1",
            "subject": "RE: Access to the MCIC",
            "to": "tamara@unsw.edu.au",
            "send_at": "2026-07-06T22:00:00Z",
        }]

        # The request must target the drafts folder and expand the
        # deferred-send property — a broken query would silently return [].
        url = mock_httpx.request.call_args.args[1]
        assert "/me/mailFolders/drafts/messages" in url
        assert "SystemTime 0x3FEF" in url

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_get_scheduled_follows_next_link(self, mock_httpx):
        """Scheduled drafts beyond the first page are still found."""
        def make_draft(i, scheduled):
            d = {"id": f"d-{i}", "subject": f"draft {i}", "toRecipients": []}
            if scheduled:
                d["singleValueExtendedProperties"] = [
                    {"id": "SystemTime 0x3fef", "value": "2026-07-06T22:00:00Z"}
                ]
            return d

        page1 = MagicMock(status_code=200, text="ok")
        page1.json.return_value = {
            "value": [make_draft(i, scheduled=False) for i in range(3)],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/mailFolders/drafts/messages?$skip=100",
        }
        page2 = MagicMock(status_code=200, text="ok")
        page2.json.return_value = {"value": [make_draft(99, scheduled=True)]}
        mock_httpx.request.side_effect = [page1, page2]

        with patch.dict(os.environ, self.ENV, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            scheduled = Outlook().get_scheduled()

        assert [e["id"] for e in scheduled] == ["d-99"]

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_cancel_scheduled_deletes_message(self, mock_httpx):
        """cancel_scheduled issues a DELETE for the pending message."""
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.text = ""
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, self.ENV, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            result = Outlook().cancel_scheduled("sched-1")

        assert "Canceled" in result
        method, url = mock_httpx.request.call_args.args[:2]
        assert method == "DELETE"
        assert url.endswith("/me/messages/sched-1")
