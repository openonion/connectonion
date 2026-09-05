"""Test the Outlook tool functionality."""
"""
LLM-Note: Tests for outlook

What it tests:
- Outlook functionality: init scope checks, token management, formatting, read/search, send (attachments, send_at scheduling), reply (plain-text→HTML paragraph conversion, attachments on the threaded reply action, scheduled, send_at still third positional with attachments keyword-only), get_scheduled (paging), mark read, unread count

Components under test:
- Module: outlook
"""


import base64
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture(autouse=True)
def _stub_token_refresh(request, monkeypatch):
    """Keep Graph-operation tests isolated from the refresh broker.

    Tests of the real refresh flow opt out with @pytest.mark.real_refresh.
    """
    if "real_refresh" in request.keywords:
        return
    from connectonion.useful_tools.outlook import Outlook
    monkeypatch.setattr(Outlook, "_refresh_via_backend", lambda self, rt: "test-token")


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

    def test_outlook_init_with_contacts_scope_only(self):
        """Contact-only Graph credentials can use the contact methods."""
        with patch.dict(
            os.environ,
            {"MICROSOFT_SCOPES": "User.Read,Contacts.ReadWrite"},
            clear=False,
        ):
            from connectonion.useful_tools.outlook import Outlook

            assert Outlook()._access_token is None


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
        """A token with a future expiry does not depend on the broker."""
        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            outlook._refresh_via_backend = MagicMock(return_value="unexpected")
            token = outlook._get_access_token()
            assert token == "test-token"
            outlook._refresh_via_backend.assert_not_called()

    def test_get_access_token_refreshes_near_expiry(self):
        """A parseable expiry inside the five-minute window refreshes early."""
        near_expiry = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "old-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": near_expiry,
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            outlook._refresh_via_backend = MagicMock(return_value="new-token")

            assert outlook._get_access_token() == "new-token"
            outlook._refresh_via_backend.assert_called_once_with("test-refresh")

    @pytest.mark.parametrize("expiry", ["", "not-an-iso-date"])
    def test_unknown_expiry_uses_existing_token(self, expiry):
        """Legacy or malformed expiry metadata does not force a refresh."""
        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": expiry,
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            outlook._refresh_via_backend = MagicMock(return_value="unexpected")

            assert outlook._get_access_token() == "test-token"
            outlook._refresh_via_backend.assert_not_called()

    def test_valid_access_token_does_not_require_refresh_credential(self):
        """A usable access token remains useful when its refresh token is absent."""
        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z",
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook

            assert Outlook()._get_access_token() == "test-token"

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_unknown_expiry_refreshes_after_graph_401(self, mock_httpx):
        """Graph remains the expiry authority when local metadata is malformed."""
        rejected = MagicMock(status_code=401, text="expired")
        accepted = MagicMock(status_code=200, text="ok")
        accepted.json.return_value = {"value": []}
        responses = iter([rejected, accepted])
        authorizations = []

        def request_with_auth(*args, **kwargs):
            authorizations.append(kwargs["headers"]["Authorization"])
            return next(responses)

        mock_httpx.request.side_effect = request_with_auth

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "old-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "unknown",
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            outlook._refresh_via_backend = MagicMock(return_value="new-token")

            assert outlook._request("GET", "/me/messages") == {"value": []}
            outlook._refresh_via_backend.assert_called_once_with("test-refresh")

        assert authorizations == ["Bearer old-token", "Bearer new-token"]

    @pytest.mark.real_refresh
    @patch('connectonion.useful_tools.outlook.httpx')
    def test_refresh_persists_rotated_refresh_token(self, mock_httpx, tmp_path):
        """An expired token refreshes and saves the rotated token to keys.env."""
        keys_env = tmp_path / "keys.env"
        keys_env.write_text(
            "MICROSOFT_ACCESS_TOKEN=old-access\n"
            "MICROSOFT_REFRESH_TOKEN=old-refresh\n"
            "MICROSOFT_TOKEN_EXPIRES_AT=2026-01-01T00:00:00Z\n"
        )

        refresh_response = MagicMock()
        refresh_response.status_code = 200
        refresh_response.json.return_value = {
            "access_token": "new-access",
            "expires_at": "2099-12-31T23:59:59Z",
            "refresh_token": "rotated-refresh",
        }
        mock_httpx.post.return_value = refresh_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "old-access",
            "MICROSOFT_REFRESH_TOKEN": "old-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2000-01-01T00:00:00Z",
            "OPENONION_API_KEY": "test-key",
            "AGENT_CONFIG_PATH": str(tmp_path),
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            token = Outlook()._get_access_token()

            assert token == "new-access"
            assert os.environ["MICROSOFT_REFRESH_TOKEN"] == "rotated-refresh"

        saved = keys_env.read_text()
        assert "MICROSOFT_REFRESH_TOKEN=rotated-refresh" in saved
        assert "MICROSOFT_ACCESS_TOKEN=new-access" in saved

    @pytest.mark.real_refresh
    @patch('connectonion.useful_tools.outlook.httpx')
    def test_refresh_without_rotated_token_keeps_current(self, mock_httpx, tmp_path):
        """Older backends omit refresh_token — the current one must survive."""
        keys_env = tmp_path / "keys.env"
        keys_env.write_text("MICROSOFT_REFRESH_TOKEN=old-refresh\n")

        refresh_response = MagicMock()
        refresh_response.status_code = 200
        refresh_response.json.return_value = {
            "access_token": "new-access",
            "expires_at": "2099-12-31T23:59:59Z",
        }
        mock_httpx.post.return_value = refresh_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "old-access",
            "MICROSOFT_REFRESH_TOKEN": "old-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2000-01-01T00:00:00Z",
            "OPENONION_API_KEY": "test-key",
            "AGENT_CONFIG_PATH": str(tmp_path),
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            assert Outlook()._get_access_token() == "new-access"
            assert os.environ["MICROSOFT_REFRESH_TOKEN"] == "old-refresh"

        assert "MICROSOFT_REFRESH_TOKEN=old-refresh" in keys_env.read_text()

    @pytest.mark.real_refresh
    @patch('connectonion.useful_tools.outlook.httpx')
    def test_refresh_updates_project_env_holding_the_tokens(self, mock_httpx, tmp_path, monkeypatch):
        """A project .env is loaded first and never overridden — it must rotate too."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text(
            "MICROSOFT_ACCESS_TOKEN=old-access\n"
            "MICROSOFT_REFRESH_TOKEN=old-refresh\n"
        )
        config_dir = tmp_path / "co"
        config_dir.mkdir()

        refresh_response = MagicMock()
        refresh_response.status_code = 200
        refresh_response.json.return_value = {
            "access_token": "new-access",
            "expires_at": "2099-12-31T23:59:59Z",
            "refresh_token": "rotated-refresh",
        }
        mock_httpx.post.return_value = refresh_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "old-access",
            "MICROSOFT_REFRESH_TOKEN": "old-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2000-01-01T00:00:00Z",
            "OPENONION_API_KEY": "test-key",
            "AGENT_CONFIG_PATH": str(config_dir),
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            assert Outlook()._get_access_token() == "new-access"

        saved = (tmp_path / ".env").read_text()
        assert "MICROSOFT_ACCESS_TOKEN=new-access" in saved
        assert "MICROSOFT_REFRESH_TOKEN=rotated-refresh" in saved

    @pytest.mark.real_refresh
    @patch('connectonion.useful_tools.outlook.httpx')
    def test_refresh_leaves_unrelated_project_env_untouched(self, mock_httpx, tmp_path, monkeypatch):
        """Don't scatter Microsoft keys into whatever .env the process sits next to."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("DATABASE_URL=postgres://local\n")
        config_dir = tmp_path / "co"
        config_dir.mkdir()

        refresh_response = MagicMock()
        refresh_response.status_code = 200
        refresh_response.json.return_value = {
            "access_token": "new-access",
            "expires_at": "2099-12-31T23:59:59Z",
        }
        mock_httpx.post.return_value = refresh_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "old-access",
            "MICROSOFT_REFRESH_TOKEN": "old-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2000-01-01T00:00:00Z",
            "OPENONION_API_KEY": "test-key",
            "AGENT_CONFIG_PATH": str(config_dir),
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            assert Outlook()._get_access_token() == "new-access"

        assert (tmp_path / ".env").read_text() == "DATABASE_URL=postgres://local\n"

    @pytest.mark.real_refresh
    @patch('connectonion.useful_tools.outlook.httpx')
    def test_refresh_requires_openonion_auth(self, mock_httpx):
        """A missing broker credential points to co auth, not Microsoft OAuth."""
        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "OPENONION_API_KEY": "",
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            with pytest.raises(ValueError) as exc_info:
                Outlook()._refresh_via_backend("refresh-token")

        message = str(exc_info.value)
        assert "co auth" in message
        assert "co auth microsoft" not in message
        assert "refresh-token" not in message
        mock_httpx.post.assert_not_called()

    @pytest.mark.real_refresh
    @patch('connectonion.useful_tools.outlook.httpx')
    def test_backend_rejected_openonion_key_points_to_co_auth(self, mock_httpx):
        """A broker-level 401 identifies the OpenOnion credential layer."""
        response = MagicMock(status_code=401)
        response.json.return_value = {"detail": "Invalid token"}
        mock_httpx.post.return_value = response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "OPENONION_API_KEY": "invalid-openonion-key",
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            with pytest.raises(ValueError) as exc_info:
                Outlook()._refresh_via_backend("microsoft-refresh-token")

        message = str(exc_info.value)
        assert "OpenOnion authentication failed" in message
        assert "co auth" in message
        assert "co auth microsoft" not in message
        assert "invalid-openonion-key" not in message
        assert "microsoft-refresh-token" not in message

    @pytest.mark.real_refresh
    @patch('connectonion.useful_tools.outlook.httpx')
    def test_microsoft_reauth_failure_points_to_microsoft_auth(self, mock_httpx):
        """An explicit Microsoft revocation response keeps its own remedy."""
        response = MagicMock(status_code=401)
        response.json.return_value = {
            "detail": {"error": "reauth_required"},
        }
        mock_httpx.post.return_value = response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "OPENONION_API_KEY": "valid-openonion-key",
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            with pytest.raises(ValueError) as exc_info:
                Outlook()._refresh_via_backend("revoked-refresh-token")

        message = str(exc_info.value)
        assert "Microsoft authorization expired" in message
        assert "co auth microsoft" in message
        assert "valid-openonion-key" not in message
        assert "revoked-refresh-token" not in message

    @pytest.mark.real_refresh
    @patch('connectonion.useful_tools.outlook.httpx')
    def test_other_microsoft_refresh_failure_points_to_microsoft_auth(self, mock_httpx):
        """A non-auth broker failure still identifies the Microsoft session."""
        response = MagicMock(status_code=400)
        response.json.return_value = {"detail": "invalid_grant"}
        mock_httpx.post.return_value = response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "OPENONION_API_KEY": "valid-openonion-key",
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            with pytest.raises(ValueError) as exc_info:
                Outlook()._refresh_via_backend("revoked-refresh-token")

        message = str(exc_info.value)
        assert "Microsoft session expired" in message
        assert "co auth microsoft" in message
        assert "valid-openonion-key" not in message
        assert "revoked-refresh-token" not in message

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_graph_scope_failure_points_to_microsoft_auth(self, mock_httpx):
        """Graph 403 is a Microsoft consent problem, not an OpenOnion login."""
        mock_httpx.request.return_value = MagicMock(
            status_code=403,
            text="ErrorAccessDenied",
        )

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "access-token",
            "MICROSOFT_REFRESH_TOKEN": "refresh-token",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z",
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            with pytest.raises(ValueError) as exc_info:
                Outlook()._request("GET", "/me/messages")

        message = str(exc_info.value)
        assert "Microsoft permission denied" in message
        assert "co auth microsoft" in message
        assert "access-token" not in message
        assert "refresh-token" not in message


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
            assert mock_httpx.request.call_args.args[1].endswith("/me/sendMail")

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
            outlook = Outlook(allow_external_attachments=True)
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

    def test_agent_attachment_must_stay_inside_the_project(self, tmp_path, monkeypatch):
        project = tmp_path / "project"
        project.mkdir()
        (project / ".co").mkdir()
        outside = tmp_path / "secret.txt"
        outside.write_text("secret")
        monkeypatch.chdir(project)

        with patch.dict(os.environ, {"MICROSOFT_SCOPES": "Mail.Read Mail.Send"}):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()

        with pytest.raises(PermissionError, match="outside the project"):
            outlook.send("r@example.com", "S", "B", attachments=[str(outside)])

    def test_core_rejects_oversize_before_the_graph_call(self, tmp_path):
        huge = tmp_path / "huge.bin"
        huge.write_bytes(b"")
        os.truncate(huge, 3_000_001)

        with patch.dict(os.environ, {"MICROSOFT_SCOPES": "Mail.Read Mail.Send"}):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook(allow_external_attachments=True)
        outlook._request = MagicMock()

        with pytest.raises(ValueError, match="3MB"):
            outlook.send("r@example.com", "S", "B", attachments=[str(huge)])

        outlook._request.assert_not_called()

    def test_parent_directory_replacement_cannot_change_the_opened_file(
        self, tmp_path, monkeypatch
    ):
        project = tmp_path / "project"
        project.mkdir()
        (project / ".co").mkdir()
        slot = project / "slot"
        slot.mkdir()
        local = slot / "report.txt"
        local.write_text("safe")
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "report.txt").write_text("SECRET")
        monkeypatch.chdir(project)

        with patch.dict(os.environ, {"MICROSOFT_SCOPES": "Mail.Read Mail.Send"}):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
        original_open = os.open

        def swap_parent_then_open(path, flags):
            slot.rename(project / "old-slot")
            slot.symlink_to(outside, target_is_directory=True)
            return original_open(path, flags)

        with patch.object(os, "open", side_effect=swap_parent_then_open):
            with pytest.raises(PermissionError, match="outside the project"):
                outlook.send("r@example.com", "S", "B", attachments=[str(local)])

    @pytest.mark.skipif(os.name == "nt", reason="POSIX FIFO semantics")
    def test_fifo_replacement_cannot_block_the_attachment_open(self, tmp_path):
        local = tmp_path / "report.txt"
        local.write_text("safe")
        with patch.dict(os.environ, {"MICROSOFT_SCOPES": "Mail.Read Mail.Send"}):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook(allow_external_attachments=True)
        original_open = os.open

        def swap_for_fifo_then_open(path, flags):
            local.unlink()
            os.mkfifo(local)
            assert flags & os.O_NONBLOCK
            return original_open(path, flags)

        with patch.object(os, "open", side_effect=swap_for_fifo_then_open):
            with pytest.raises(PermissionError, match="not a regular file"):
                outlook.send("r@example.com", "S", "B", attachments=[str(local)])

    def test_growth_after_fstat_is_rejected_before_graph(self, tmp_path):
        local = tmp_path / "growing.bin"
        local.write_bytes(b"x")
        with patch.dict(os.environ, {"MICROSOFT_SCOPES": "Mail.Read Mail.Send"}):
            from connectonion.useful_tools import outlook as outlook_module
            outlook = outlook_module.Outlook(allow_external_attachments=True)
        outlook._request = MagicMock()
        original_open = outlook._open_attachments

        def open_then_grow(attachments, stack):
            opened = original_open(attachments, stack)
            local.write_bytes(b"12345")
            return opened

        with patch.object(outlook_module, "OUTLOOK_ATTACHMENT_LIMIT", 4):
            with patch.object(outlook, "_open_attachments", side_effect=open_then_grow):
                with pytest.raises(ValueError, match="3MB"):
                    outlook.send("r@example.com", "S", "B", attachments=[str(local)])

        outlook._request.assert_not_called()

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_send_email_scheduled(self, mock_httpx):
        """Test scheduled send sets the deferred-send extended property."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.text = '{"id": "draft-1"}'
        mock_response.json.return_value = {"id": "draft-1"}
        send_response = MagicMock()
        send_response.status_code = 202
        send_response.text = ""
        mock_httpx.request.side_effect = [mock_response, send_response]

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.ReadWrite,Mail.Send",
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

            method, url = mock_httpx.request.call_args_list[0].args[:2]
            assert method == "POST"
            assert url.endswith("/me/messages")

            sent_message = mock_httpx.request.call_args_list[0].kwargs["json"]
            assert sent_message["singleValueExtendedProperties"] == [
                {"id": "SystemTime 0x3FEF", "value": "2026-07-06T15:30:00Z"},
                {"id": "SystemTime 0x000F", "value": "2026-07-06T15:30:00Z"},
            ]
            assert mock_httpx.request.call_count == 2
            send_method, send_url = mock_httpx.request.call_args_list[1].args[:2]
            assert send_method == "POST"
            assert send_url.endswith("/me/messages/draft-1/send")
            assert "json" not in mock_httpx.request.call_args_list[1].kwargs

    def test_send_email_scheduled_requires_readwrite_scope(self):
        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z",
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook

            with pytest.raises(ValueError, match="Mail.ReadWrite"):
                Outlook().send(
                    "recipient@example.com",
                    "Test Subject",
                    "Test Body",
                    send_at="2026-07-06T15:30:00Z",
                )

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
        """A scheduled reply is a reply draft that carries the deferred-send
        properties and is submitted as that exact draft — never the one-shot
        reply action, which delivered at once the way sendMail did (#1198)."""
        mock_httpx.request.side_effect = [
            MagicMock(status_code=201, text='{"id": "reply-draft-1"}',
                      json=MagicMock(return_value={"id": "reply-draft-1"})),
            MagicMock(status_code=200, text=""),   # PATCH
            MagicMock(status_code=202, text=""),   # send
        ]

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.ReadWrite,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            result = outlook.reply("msg-1", "See you then", send_at="2026-07-06T15:30:00Z")

            assert "scheduled" in result.lower()
            calls = mock_httpx.request.call_args_list
            assert [(c.args[0], c.args[1].split("/v1.0")[1]) for c in calls] == [
                ("POST", "/me/messages/msg-1/createReply"),
                ("PATCH", "/me/messages/reply-draft-1"),
                ("POST", "/me/messages/reply-draft-1/send"),
            ]
            assert calls[0].kwargs["json"] == {"comment": "<p>See you then</p>"}
            assert calls[1].kwargs["json"] == {"singleValueExtendedProperties": [
                {"id": "SystemTime 0x3FEF", "value": "2026-07-06T15:30:00Z"},
                {"id": "SystemTime 0x000F", "value": "2026-07-06T15:30:00Z"},
            ]}
            assert "json" not in calls[2].kwargs

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_reply_scheduled_requires_readwrite_scope(self, mock_httpx):
        """Draft creation needs Mail.ReadWrite; fail before any request, not
        with a Graph 403 after the reply action already went out."""
        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook

            with pytest.raises(ValueError, match="Mail.ReadWrite"):
                Outlook().reply("msg-1", "See you then", send_at="2026-07-06T15:30:00Z")

        mock_httpx.request.assert_not_called()

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_reply_scheduled_without_draft_id_is_not_sent(self, mock_httpx):
        """No draft id means nothing to schedule — do not fall back to sending."""
        mock_httpx.request.return_value = MagicMock(status_code=201, text="{}",
                                                    json=MagicMock(return_value={}))

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.ReadWrite,Mail.Send",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook

            with pytest.raises(ValueError, match="createReply"):
                Outlook().reply("msg-1", "See you then", send_at="2026-07-06T15:30:00Z")

        assert mock_httpx.request.call_count == 1

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


class TestOutlookReplyAttachments:
    """Replying with files attached, without giving up Graph's threading."""

    @pytest.fixture(autouse=True)
    def _connected(self, monkeypatch):
        monkeypatch.setenv("MICROSOFT_SCOPES", "Mail.Read,Mail.Send")
        monkeypatch.setenv("MICROSOFT_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("MICROSOFT_REFRESH_TOKEN", "test-refresh")

    def _outlook(self, allow_external_attachments=True):
        from connectonion.useful_tools.outlook import Outlook
        return Outlook(allow_external_attachments=allow_external_attachments)

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_reply_with_one_attachment_still_replies_to_the_thread(self, mock_httpx, tmp_path):
        """The file rides on the reply action, so the thread is kept."""
        mock_httpx.request.return_value = MagicMock(status_code=202, text="")
        signed = tmp_path / "signed.pdf"
        signed.write_bytes(b"%PDF-1.4 fake")

        result = self._outlook().reply("msg-1", "Signed copy attached",
                                      attachments=[str(signed)])

        assert "sent" in result.lower()
        assert "signed.pdf" in result

        method, url = mock_httpx.request.call_args.args[:2]
        assert method == "POST"
        # A reply must not degrade into a fresh sendMail — that loses threading.
        assert url.endswith("/me/messages/msg-1/reply")

        payload = mock_httpx.request.call_args.kwargs["json"]
        assert payload["comment"] == "<p>Signed copy attached</p>"
        attachment = payload["message"]["attachments"][0]
        assert attachment["@odata.type"] == "#microsoft.graph.fileAttachment"
        assert attachment["name"] == "signed.pdf"
        assert attachment["contentType"] == "application/pdf"
        assert base64.b64decode(attachment["contentBytes"]) == b"%PDF-1.4 fake"

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_reply_attaches_every_file_in_order(self, mock_httpx, tmp_path):
        """Several attachments all reach Graph, each with its own MIME type."""
        mock_httpx.request.return_value = MagicMock(status_code=202, text="")
        report = tmp_path / "report.pdf"
        report.write_bytes(b"%PDF report")
        chart = tmp_path / "chart.png"
        chart.write_bytes(b"\x89PNG chart")

        result = self._outlook().reply("msg-1", "Both attached",
                                      attachments=[str(report), str(chart)])

        attachments = mock_httpx.request.call_args.kwargs["json"]["message"]["attachments"]
        assert [(a["name"], a["contentType"]) for a in attachments] == [
            ("report.pdf", "application/pdf"),
            ("chart.png", "image/png"),
        ]
        assert [base64.b64decode(a["contentBytes"]) for a in attachments] == [
            b"%PDF report", b"\x89PNG chart",
        ]
        assert "report.pdf, chart.png" in result

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_scheduled_reply_keeps_both_attachments_and_deferred_send(self, mock_httpx, tmp_path, monkeypatch):
        """--attach and --at are not a choice: the reply draft carries both.

        PATCH does not take attachments, so each file is posted to the
        draft's attachments collection before the deferred-send PATCH."""
        monkeypatch.setenv("MICROSOFT_SCOPES", "Mail.ReadWrite,Mail.Send")
        mock_httpx.request.side_effect = [
            MagicMock(status_code=201, text='{"id": "reply-draft-1"}',
                      json=MagicMock(return_value={"id": "reply-draft-1"})),
            MagicMock(status_code=201, text='{"id": "att-1"}',
                      json=MagicMock(return_value={"id": "att-1"})),
            MagicMock(status_code=200, text=""),
            MagicMock(status_code=202, text=""),
        ]
        signed = tmp_path / "signed.pdf"
        signed.write_bytes(b"%PDF-1.4 fake")

        result = self._outlook().reply("msg-1", "Tomorrow", attachments=[str(signed)],
                                      send_at="2026-07-06T15:30:00Z")

        assert "scheduled" in result.lower()
        assert "signed.pdf" in result

        calls = mock_httpx.request.call_args_list
        assert [(c.args[0], c.args[1].split("/v1.0")[1]) for c in calls] == [
            ("POST", "/me/messages/msg-1/createReply"),
            ("POST", "/me/messages/reply-draft-1/attachments"),
            ("PATCH", "/me/messages/reply-draft-1"),
            ("POST", "/me/messages/reply-draft-1/send"),
        ]
        attachment = calls[1].kwargs["json"]
        assert attachment["@odata.type"] == "#microsoft.graph.fileAttachment"
        assert attachment["name"] == "signed.pdf"
        assert calls[2].kwargs["json"]["singleValueExtendedProperties"][0] == {
            "id": "SystemTime 0x3FEF", "value": "2026-07-06T15:30:00Z"
        }

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_rejected_attachment_leaves_no_reply_draft(self, mock_httpx, tmp_path, monkeypatch):
        """A missing file fails before createReply, so no stray draft is left in Drafts."""
        monkeypatch.setenv("MICROSOFT_SCOPES", "Mail.ReadWrite,Mail.Send")

        with pytest.raises(ValueError, match="Attachment not found"):
            self._outlook().reply("msg-1", "Tomorrow", attachments=[str(tmp_path / "missing.pdf")],
                                  send_at="2026-07-06T15:30:00Z")

        mock_httpx.request.assert_not_called()

    def test_missing_attachment_reports_no_reply_sent(self, tmp_path):
        """A path that isn't there must fail before anything reaches Graph."""
        outlook = self._outlook()
        outlook._request = MagicMock()

        with pytest.raises(ValueError, match="Attachment not found"):
            outlook.reply("msg-1", "Attached", attachments=[str(tmp_path / "gone.pdf")])

        outlook._request.assert_not_called()

    def test_oversize_attachment_reports_no_reply_sent(self, tmp_path):
        """The 3MB send limit applies to replies, and stops the POST."""
        huge = tmp_path / "huge.bin"
        huge.write_bytes(b"")
        os.truncate(huge, 3_000_001)
        outlook = self._outlook()
        outlook._request = MagicMock()

        with pytest.raises(ValueError, match="3MB"):
            outlook.reply("msg-1", "Attached", attachments=[str(huge)])

        outlook._request.assert_not_called()

    def test_agent_reply_attachment_must_stay_inside_the_project(self, tmp_path, monkeypatch):
        """Agent-facing instances cannot attach a file outside the project."""
        project = tmp_path / "project"
        project.mkdir()
        (project / ".co").mkdir()
        outside = tmp_path / "secret.txt"
        outside.write_text("secret")
        monkeypatch.chdir(project)

        outlook = self._outlook(allow_external_attachments=False)
        outlook._request = MagicMock()

        with pytest.raises(PermissionError, match="outside the project"):
            outlook.reply("msg-1", "Attached", attachments=[str(outside)])

        outlook._request.assert_not_called()

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_graph_rejection_is_not_reported_as_a_sent_reply(self, mock_httpx, tmp_path):
        """A Graph error on the upload must raise, not return 'Reply sent'."""
        mock_httpx.request.return_value = MagicMock(
            status_code=413, text="attachment too large"
        )
        signed = tmp_path / "signed.pdf"
        signed.write_bytes(b"%PDF-1.4 fake")

        with pytest.raises(ValueError, match="Microsoft Graph API error"):
            self._outlook().reply("msg-1", "Attached", attachments=[str(signed)])


class TestOutlookReplyPositionalCompatibility:
    """reply()'s third positional argument is send_at, as it always was."""

    @pytest.fixture(autouse=True)
    def _connected(self, monkeypatch):
        monkeypatch.setenv("MICROSOFT_SCOPES", "Mail.Read,Mail.Send")
        monkeypatch.setenv("MICROSOFT_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("MICROSOFT_REFRESH_TOKEN", "test-refresh")

    def _outlook(self):
        from connectonion.useful_tools.outlook import Outlook
        return Outlook(allow_external_attachments=True)

    @patch('connectonion.useful_tools.outlook.httpx')
    def test_legacy_third_positional_argument_still_schedules(self, mock_httpx, monkeypatch):
        """A caller written before attachments existed still schedules, not attaches."""
        monkeypatch.setenv("MICROSOFT_SCOPES", "Mail.ReadWrite,Mail.Send")
        mock_httpx.request.side_effect = [
            MagicMock(status_code=201, text='{"id": "reply-draft-1"}',
                      json=MagicMock(return_value={"id": "reply-draft-1"})),
            MagicMock(status_code=200, text=""),
            MagicMock(status_code=202, text=""),
        ]

        result = self._outlook().reply("msg-1", "See you then", "2026-07-06T15:30:00Z")

        assert "scheduled" in result.lower()
        urls = [c.args[1] for c in mock_httpx.request.call_args_list]
        assert urls[0].endswith("/me/messages/msg-1/createReply")
        # The timestamp must never be read as a file path.
        assert not any(url.endswith("/attachments") for url in urls)
        patched = mock_httpx.request.call_args_list[1].kwargs["json"]
        assert patched["singleValueExtendedProperties"][0] == {
            "id": "SystemTime 0x3FEF", "value": "2026-07-06T15:30:00Z"
        }

    def test_attachments_cannot_be_passed_positionally(self, tmp_path):
        """Keyword-only attachments freeze the positional order for good."""
        signed = tmp_path / "signed.pdf"
        signed.write_bytes(b"%PDF-1.4 fake")
        outlook = self._outlook()
        outlook._request = MagicMock()

        with pytest.raises(TypeError):
            outlook.reply("msg-1", "Attached", None, [str(signed)])

        outlook._request.assert_not_called()

    def test_reply_signature_keeps_send_at_third(self):
        """Guard the contract itself, so a future edit can't quietly reorder it."""
        import inspect

        from connectonion.useful_tools.outlook import Outlook

        params = inspect.signature(Outlook.reply).parameters
        assert list(params) == ["self", "email_id", "body", "send_at", "attachments"]
        assert params["attachments"].kind is inspect.Parameter.KEYWORD_ONLY


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


class TestOutlookContacts:
    """Test minimal Outlook contact management through Microsoft Graph."""

    ENV = {
        "MICROSOFT_SCOPES": "Mail.ReadWrite,Mail.Send,Contacts.ReadWrite",
        "MICROSOFT_ACCESS_TOKEN": "test-token",
        "MICROSOFT_REFRESH_TOKEN": "test-refresh",
    }

    @patch("connectonion.useful_tools.outlook.httpx")
    def test_add_contact_posts_name_and_email(self, mock_httpx):
        response = MagicMock(status_code=201, text="ok")
        response.json.return_value = {
            "id": "contact-1",
            "displayName": "Zhou Yifei",
            "emailAddresses": [{
                "name": "Zhou Yifei",
                "address": "zhou@example.com",
            }],
        }
        mock_httpx.request.return_value = response

        with patch.dict(os.environ, self.ENV, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            outlook._access_token = "test-token"
            contact = outlook.add_contact(
                "Zhou Yifei", "zhou@example.com"
            )

        assert contact == {
            "id": "contact-1",
            "name": "Zhou Yifei",
            "email": "zhou@example.com",
        }
        method, url = mock_httpx.request.call_args.args[:2]
        assert method == "POST"
        assert url.endswith("/me/contacts")
        assert mock_httpx.request.call_args.kwargs["json"] == {
            "displayName": "Zhou Yifei",
            "emailAddresses": [{
                "name": "Zhou Yifei",
                "address": "zhou@example.com",
            }],
        }

    @patch("connectonion.useful_tools.outlook.httpx")
    def test_list_contacts_normalizes_graph_results(self, mock_httpx):
        response = MagicMock(status_code=200, text="ok")
        response.json.return_value = {"value": [
            {
                "id": "contact-1",
                "displayName": "Zhou Yifei",
                "emailAddresses": [{
                    "name": "Zhou Yifei",
                    "address": "zhou@example.com",
                }],
            },
            {
                "id": "contact-2",
                "displayName": "No Email",
                "emailAddresses": [],
            },
        ]}
        mock_httpx.request.return_value = response

        with patch.dict(os.environ, self.ENV, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            outlook._access_token = "test-token"
            contacts = outlook.list_contacts(max_results=25)

        assert contacts == [
            {
                "id": "contact-1",
                "name": "Zhou Yifei",
                "email": "zhou@example.com",
            },
            {"id": "contact-2", "name": "No Email", "email": ""},
        ]
        _, url = mock_httpx.request.call_args.args[:2]
        assert "/me/contacts" in url
        assert "$select=id,displayName,emailAddresses" in url

    def test_search_contacts_matches_name_and_email_case_insensitively(self):
        with patch.dict(os.environ, self.ENV, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            contacts = [
                {
                    "id": "contact-1",
                    "name": "Zhou Yifei",
                    "email": "zhou@example.com",
                },
                {
                    "id": "contact-2",
                    "name": "Alice",
                    "email": "alice@example.com",
                },
            ]
            outlook._iter_contacts = MagicMock(side_effect=[
                iter(contacts),
                iter(contacts),
            ])
            assert outlook.search_contacts("YIFEI") == [{
                "id": "contact-1",
                "name": "Zhou Yifei",
                "email": "zhou@example.com",
            }]
            assert outlook.search_contacts("ou@example") == [{
                "id": "contact-1",
                "name": "Zhou Yifei",
                "email": "zhou@example.com",
            }]

    @patch("connectonion.useful_tools.outlook.httpx")
    def test_search_contacts_follows_graph_pages(self, mock_httpx):
        page1 = MagicMock(status_code=200, text="ok")
        page1.json.return_value = {
            "value": [{
                "id": "contact-1",
                "displayName": "Alice",
                "emailAddresses": [{
                    "name": "Alice",
                    "address": "alice@example.com",
                }],
            }],
            "@odata.nextLink": (
                "https://graph.microsoft.com/v1.0/me/contacts?$skip=100"
            ),
        }
        page2 = MagicMock(status_code=200, text="ok")
        page2.json.return_value = {"value": [{
            "id": "contact-2",
            "displayName": "Zhou Yifei",
            "emailAddresses": [{
                "name": "Zhou Yifei",
                "address": "zhou@example.com",
            }],
        }]}
        mock_httpx.request.side_effect = [page1, page2]

        with patch.dict(os.environ, self.ENV, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            outlook._access_token = "test-token"
            contacts = outlook.search_contacts("yifei")

        assert [contact["id"] for contact in contacts] == ["contact-2"]
        assert mock_httpx.request.call_count == 2

    def test_contact_methods_require_contacts_readwrite(self):
        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Mail.ReadWrite,Mail.Send",
        }, clear=False):
            from connectonion.useful_tools.outlook import Outlook
            outlook = Outlook()
            with pytest.raises(ValueError, match="Contacts.ReadWrite"):
                outlook.list_contacts()


class TestDownloadAttachments:
    """Saving attachments to disk, including the sender-controlled filename."""

    def _outlook(self, monkeypatch, tmp_path, attachments):
        from connectonion.useful_tools import outlook as outlook_module

        monkeypatch.setenv("MICROSOFT_SCOPES", "Mail.ReadWrite Mail.Send")
        monkeypatch.setenv("MICROSOFT_ACCESS_TOKEN", "token")
        monkeypatch.setenv("MICROSOFT_REFRESH_TOKEN", "refresh")
        monkeypatch.setattr(outlook_module, "project_root", lambda: tmp_path)

        instance = outlook_module.Outlook()
        monkeypatch.setattr(instance, "_request", lambda *a, **k: {"value": attachments})
        return instance

    def test_saves_file_attachment_bytes(self, monkeypatch, tmp_path):
        import base64

        outlook = self._outlook(monkeypatch, tmp_path, [
            {"name": "cover.jpg", "contentBytes": base64.b64encode(b"pixels").decode()},
        ])

        saved = outlook.download_attachments("msg-id", tmp_path / "out")

        assert (tmp_path / "out" / "cover.jpg").read_bytes() == b"pixels"
        assert saved == [str(tmp_path / "out" / "cover.jpg")]

    def test_preserves_duplicate_attachment_names(self, monkeypatch, tmp_path):
        import base64

        encoded = lambda value: base64.b64encode(value).decode()
        outlook = self._outlook(monkeypatch, tmp_path, [
            {"name": "cover.jpg", "contentBytes": encoded(b"first")},
            {"name": "cover.jpg", "contentBytes": encoded(b"second")},
        ])

        saved = outlook.download_attachments("msg-id", tmp_path / "out")

        assert saved == [
            str(tmp_path / "out" / "cover.jpg"),
            str(tmp_path / "out" / "cover-1.jpg"),
        ]
        assert (tmp_path / "out" / "cover.jpg").read_bytes() == b"first"
        assert (tmp_path / "out" / "cover-1.jpg").read_bytes() == b"second"

    def test_sender_cannot_escape_the_directory_with_a_relative_name(self, monkeypatch, tmp_path):
        """A sender names the attachment '../../owned.txt'; it must stay put."""
        import base64

        outlook = self._outlook(monkeypatch, tmp_path, [
            {"name": "../../owned.txt", "contentBytes": base64.b64encode(b"x").decode()},
        ])

        outlook.download_attachments("msg-id", tmp_path / "out")

        assert (tmp_path / "out" / "owned.txt").exists()
        assert not (tmp_path.parent / "owned.txt").exists()

    def test_preserves_an_existing_file(self, monkeypatch, tmp_path):
        import base64

        out_dir = tmp_path / "out"
        out_dir.mkdir()
        existing = out_dir / "pyproject.toml"
        existing.write_bytes(b"keep me")
        outlook = self._outlook(monkeypatch, tmp_path, [
            {"name": "pyproject.toml", "contentBytes": base64.b64encode(b"replace me").decode()},
        ])

        saved = outlook.download_attachments("msg-id", out_dir)

        assert existing.read_bytes() == b"keep me"
        assert saved == [str(out_dir / "pyproject-1.toml")]
        assert (out_dir / "pyproject-1.toml").read_bytes() == b"replace me"

    def test_refuses_to_follow_an_existing_symlink(self, monkeypatch, tmp_path):
        import base64

        outside = tmp_path / "outside.txt"
        outside.write_bytes(b"keep me")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (out_dir / "cover.jpg").symlink_to(outside)
        outlook = self._outlook(monkeypatch, tmp_path, [
            {"name": "cover.jpg", "contentBytes": base64.b64encode(b"replace me").decode()},
        ])

        saved = outlook.download_attachments("msg-id", out_dir)

        assert outside.read_bytes() == b"keep me"
        assert saved == [str(out_dir / "cover-1.jpg")]
        assert (out_dir / "cover-1.jpg").read_bytes() == b"replace me"

    def test_replaces_control_characters_in_sender_filename(self, monkeypatch, tmp_path):
        import base64

        outlook = self._outlook(monkeypatch, tmp_path, [
            {"name": "cover\n\x1b[31m.jpg", "contentBytes": base64.b64encode(b"pixels").decode()},
        ])

        saved = outlook.download_attachments("msg-id", tmp_path / "out")

        assert saved == [str(tmp_path / "out" / "cover__[31m.jpg")]
        assert (tmp_path / "out" / "cover__[31m.jpg").read_bytes() == b"pixels"

    def test_rejects_malformed_base64_without_creating_a_file(self, monkeypatch, tmp_path):
        outlook = self._outlook(monkeypatch, tmp_path, [
            {"name": "broken.pdf", "contentBytes": "not base64!"},
        ])

        with pytest.raises(ValueError):
            outlook.download_attachments("msg-id", tmp_path / "out")

        assert not (tmp_path / "out" / "broken.pdf").exists()

    def test_refuses_a_destination_outside_the_project(self, monkeypatch, tmp_path):
        outlook = self._outlook(monkeypatch, tmp_path, [])

        with pytest.raises(PermissionError):
            outlook.download_attachments("msg-id", tmp_path.parent / "elsewhere")

    def test_skips_attachments_without_bytes(self, monkeypatch, tmp_path):
        outlook = self._outlook(monkeypatch, tmp_path, [
            {"name": "linked.docx", "@odata.type": "#microsoft.graph.referenceAttachment"},
        ])

        assert outlook.download_attachments("msg-id", tmp_path / "out") == []

    def test_inline_signature_images_are_skipped_by_default(self, monkeypatch, tmp_path):
        """One real PDF and a corporate signature must save one file, not five (#924)."""
        import base64

        encoded = lambda value: base64.b64encode(value).decode()
        outlook = self._outlook(monkeypatch, tmp_path, [
            {"name": "invoice.pdf", "contentBytes": encoded(b"pdf")},
            {"name": "logo.png", "contentBytes": encoded(b"png"), "isInline": True},
            {"name": "banner.png", "contentBytes": encoded(b"png"), "isInline": True},
        ])

        saved = outlook.download_attachments("msg-id", tmp_path / "out")

        assert saved == [str(tmp_path / "out" / "invoice.pdf")]
        assert not (tmp_path / "out" / "logo.png").exists()

    def test_include_inline_saves_the_embedded_images_too(self, monkeypatch, tmp_path):
        import base64

        encoded = lambda value: base64.b64encode(value).decode()
        outlook = self._outlook(monkeypatch, tmp_path, [
            {"name": "invoice.pdf", "contentBytes": encoded(b"pdf")},
            {"name": "logo.png", "contentBytes": encoded(b"png"), "isInline": True},
        ])

        saved = outlook.download_attachments(
            "msg-id", tmp_path / "out", include_inline=True
        )

        assert saved == [
            str(tmp_path / "out" / "invoice.pdf"),
            str(tmp_path / "out" / "logo.png"),
        ]

    def test_an_inline_only_mail_reports_no_attachments(self, monkeypatch, tmp_path):
        """The signature-only mail is the everyday case the default protects."""
        import base64

        outlook = self._outlook(monkeypatch, tmp_path, [
            {"name": "logo.png",
             "contentBytes": base64.b64encode(b"png").decode(),
             "isInline": True},
        ])

        assert outlook.download_attachments("msg-id", tmp_path / "out") == []
