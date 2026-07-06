"""Test the Outlook tool functionality."""
"""
LLM-Note: Tests for outlook

What it tests:
- Outlook functionality

Components under test:
- Module: outlook
"""


import os
import pytest
from unittest.mock import patch, MagicMock


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

    def test_get_access_token_requires_credentials(self):
        """Test that getting token requires credentials."""
        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "",
            "MICROSOFT_REFRESH_TOKEN": ""
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            with pytest.raises(ValueError) as exc_info:
                outlook._get_access_token()
            assert "credentials not found" in str(exc_info.value)

    def test_get_access_token_returns_valid_token(self):
        """Test that valid token is returned."""
        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            token = outlook._get_access_token()
            assert token == "test-token"


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
            assert payload["comment"] == "See you then"
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
            assert mock_httpx.request.call_args.kwargs["json"] == {"comment": "Thanks!"}


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
