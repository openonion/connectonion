"""Unit tests for connectonion/useful_tools/gmail.py

Tests cover:
- Gmail initialization with scope validation
- read_inbox, get_sent_emails, get_all_emails, search_emails
- get_email_body, get_email_attachments
- send, reply
- mark_read, mark_unread, archive_email, star_email
- get_labels, add_label, get_emails_with_label
- count_unread, get_my_identity, detect_all_my_emails
- CRM: get_all_contacts, analyze_contact, get_unanswered_emails
- CSV caching: sync_emails, sync_contacts, get_cached_contacts
- update_contact, bulk_update_contacts
"""
"""
LLM-Note: Tests for gmail

What it tests:
- Gmail functionality

Components under test:
- Module: gmail
"""


import pytest
import os
import tempfile
import csv
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path


# Future expiry time for tests (1 hour from now)
FUTURE_EXPIRY = (datetime.utcnow() + timedelta(hours=1)).isoformat() + 'Z'


@pytest.fixture(autouse=True)
def _stub_token_refresh(request, monkeypatch):
    """Gmail refreshes its access token once per instance; stub that network
    call so API-operation tests stay isolated. Tests of the refresh flow
    itself opt out with @pytest.mark.real_refresh."""
    if "real_refresh" in request.keywords:
        return
    from connectonion.useful_tools.gmail import Gmail
    monkeypatch.setattr(Gmail, "_refresh_via_backend", lambda self, rt: "test_token")


class TestGmailInit:
    """Tests for Gmail initialization and scope validation."""

    @patch.dict(os.environ, {
        "GOOGLE_SCOPES": "gmail.readonly gmail.send",
        "GOOGLE_ACCESS_TOKEN": "test_token",
        "GOOGLE_REFRESH_TOKEN": "test_refresh"
    })
    def test_init_with_valid_scopes(self):
        """Test Gmail initializes successfully with required scopes."""
        from connectonion.useful_tools.gmail import Gmail
        gmail = Gmail()
        assert gmail._service is None  # Lazy loaded
        assert gmail.emails_csv == "data/emails.csv"
        assert gmail.contacts_csv == "data/contacts.csv"

    @patch.dict(os.environ, {
        "GOOGLE_SCOPES": "gmail.readonly gmail.send",
        "GOOGLE_ACCESS_TOKEN": "test_token",
        "GOOGLE_REFRESH_TOKEN": "test_refresh"
    })
    def test_init_with_custom_paths(self):
        """Test Gmail initializes with custom CSV paths."""
        from connectonion.useful_tools.gmail import Gmail
        gmail = Gmail(emails_csv="custom/emails.csv", contacts_csv="custom/contacts.csv")
        assert gmail.emails_csv == "custom/emails.csv"
        assert gmail.contacts_csv == "custom/contacts.csv"

    @patch.dict(os.environ, {"GOOGLE_SCOPES": "gmail.send"}, clear=True)
    def test_init_missing_readonly_scope(self):
        """Test Gmail raises error when gmail.readonly scope is missing."""
        from connectonion.useful_tools.gmail import Gmail
        with pytest.raises(ValueError) as exc_info:
            Gmail()
        assert "gmail.readonly" in str(exc_info.value)

    @patch.dict(os.environ, {"GOOGLE_SCOPES": "gmail.readonly"}, clear=True)
    def test_init_missing_send_scope(self):
        """Test Gmail raises error when gmail.send scope is missing."""
        from connectonion.useful_tools.gmail import Gmail
        with pytest.raises(ValueError) as exc_info:
            Gmail()
        assert "gmail.send" in str(exc_info.value)


class TestGmailGetService:
    """Tests for _get_service method and token handling."""

    @patch.dict(os.environ, {
        "GOOGLE_SCOPES": "gmail.readonly gmail.send",
        "GOOGLE_ACCESS_TOKEN": "test_token",
        "GOOGLE_REFRESH_TOKEN": "test_refresh",
        "GOOGLE_TOKEN_EXPIRES_AT": FUTURE_EXPIRY,
        "OPENONION_API_KEY": "api-key",
    })
    @patch('connectonion.useful_tools.gmail.build')
    def test_get_service_creates_service(self, mock_build):
        """Test _get_service creates Gmail API service."""
        from connectonion.useful_tools.gmail import Gmail
        mock_service = Mock()
        mock_build.return_value = mock_service

        gmail = Gmail()
        service = gmail._get_service()

        assert service == mock_service
        mock_build.assert_called_once()

    @patch.dict(os.environ, {
        "GOOGLE_SCOPES": "gmail.readonly gmail.send",
        "GOOGLE_ACCESS_TOKEN": "test_token",
        "GOOGLE_REFRESH_TOKEN": "test_refresh",
        "GOOGLE_TOKEN_EXPIRES_AT": FUTURE_EXPIRY,
        "OPENONION_API_KEY": "api-key",
    })
    @patch('connectonion.useful_tools.gmail.build')
    def test_get_service_caches_service(self, mock_build):
        """Test _get_service returns cached service on second call."""
        from connectonion.useful_tools.gmail import Gmail
        mock_service = Mock()
        mock_build.return_value = mock_service

        gmail = Gmail()
        service1 = gmail._get_service()
        service2 = gmail._get_service()

        assert service1 == service2
        assert mock_build.call_count == 1  # Only built once

    @pytest.mark.real_refresh
    @patch.dict(os.environ, {
        "GOOGLE_SCOPES": "gmail.readonly gmail.send",
        "GOOGLE_ACCESS_TOKEN": "stale_token",
        "GOOGLE_REFRESH_TOKEN": "test_refresh",
        "GOOGLE_TOKEN_EXPIRES_AT": FUTURE_EXPIRY,
        "OPENONION_API_KEY": "api-key",
    })
    @patch('connectonion.useful_tools.gmail.build')
    def test_get_service_refreshes_even_when_expiry_looks_fresh(self, mock_build, monkeypatch):
        """Refresh is unconditional — an hour-old token is stale by the next run."""
        from connectonion.useful_tools.gmail import Gmail
        calls = []
        monkeypatch.setattr(
            Gmail, "_refresh_via_backend",
            lambda self, rt: calls.append(rt) or "fresh_token",
        )

        Gmail()._get_service()

        assert calls == [None]
        assert mock_build.call_args.kwargs["credentials"].token == "fresh_token"

    @pytest.mark.real_refresh
    @patch.dict(os.environ, {
        "GOOGLE_SCOPES": "gmail.readonly gmail.send",
        "GOOGLE_ACCESS_TOKEN": "stale_token",
        "GOOGLE_REFRESH_TOKEN": "test_refresh",
        "OPENONION_API_KEY": "api-key",
    }, clear=True)
    @patch('connectonion.useful_tools.gmail.build')
    def test_get_service_refreshes_without_expiry_variable(self, mock_build, monkeypatch):
        """GOOGLE_TOKEN_EXPIRES_AT can be absent — that must not skip the refresh."""
        from connectonion.useful_tools.gmail import Gmail
        monkeypatch.setattr(Gmail, "_refresh_via_backend", lambda self, rt: "fresh_token")

        Gmail()._get_service()

        assert mock_build.call_args.kwargs["credentials"].token == "fresh_token"

    @patch.dict(os.environ, {"GOOGLE_SCOPES": "gmail.readonly gmail.send"}, clear=True)
    def test_get_service_missing_credentials(self):
        """Test _get_service raises error when credentials missing."""
        from connectonion.useful_tools.gmail import Gmail
        gmail = Gmail.__new__(Gmail)
        gmail._service = None

        with pytest.raises(ValueError) as exc_info:
            gmail._get_service()
        assert "OPENONION_API_KEY not found" in str(exc_info.value)

    @pytest.mark.real_refresh
    @patch.dict(os.environ, {
        "GOOGLE_SCOPES": "gmail.readonly gmail.send",
        "OPENONION_API_KEY": "api-key",
        "GOOGLE_TOKEN_EXPIRES_AT": FUTURE_EXPIRY,
    }, clear=True)
    @patch('connectonion.useful_tools.gmail.build')
    def test_google_auth_can_refresh_a_cached_service_after_401(
        self, mock_build, monkeypatch
    ):
        from connectonion.useful_tools.gmail import Gmail

        tokens = iter(["initial", "after-401"])
        monkeypatch.setattr(
            Gmail, "_refresh_via_backend", lambda self, _rt: next(tokens)
        )
        gmail = Gmail()
        gmail._get_service()
        credentials = mock_build.call_args.kwargs["credentials"]

        credentials.refresh(None)

        assert credentials.token == "after-401"
        assert credentials.expiry.tzinfo is None

    @pytest.mark.real_refresh
    def test_backend_refresh_uses_server_token_and_persists_rotation(
        self, monkeypatch, tmp_path
    ):
        from connectonion.useful_tools.gmail import Gmail

        monkeypatch.setenv("OPENONION_API_KEY", "api-key")
        monkeypatch.setenv("AGENT_CONFIG_PATH", str(tmp_path))
        response = Mock(status_code=200)
        response.json.return_value = {
            "access_token": "fresh-access",
            "refresh_token": "rotated-refresh",
            "expires_at": "2026-08-08T12:00:00+00:00",
        }

        with patch("httpx.post", return_value=response) as post:
            token = Gmail.__new__(Gmail)._refresh_via_backend("stale-local-token")

        assert token == "fresh-access"
        assert "json" not in post.call_args.kwargs
        assert post.call_args.kwargs["timeout"] == 15.0
        assert os.environ["GOOGLE_REFRESH_TOKEN"] == "rotated-refresh"
        saved = (tmp_path / "keys.env").read_text()
        assert "GOOGLE_REFRESH_TOKEN=rotated-refresh" in saved

    @pytest.mark.real_refresh
    def test_backend_reauth_error_is_actionable_without_leaking_provider_body(
        self, monkeypatch
    ):
        from connectonion.useful_tools.gmail import Gmail

        monkeypatch.setenv("OPENONION_API_KEY", "api-key")
        response = Mock(status_code=401)
        response.json.return_value = {
            "detail": {"error": "reauth_required"},
            "provider_secret": "must-not-appear",
        }
        with patch("httpx.post", return_value=response):
            with pytest.raises(ValueError) as error:
                Gmail.__new__(Gmail)._refresh_via_backend(None)

        assert "co auth google" in str(error.value)
        assert "must-not-appear" not in str(error.value)


class TestReadEmails:
    """Tests for email reading methods."""

    @pytest.fixture
    def gmail_with_mock(self):
        """Create Gmail instance with mocked _get_service."""
        with patch.dict(os.environ, {
            "GOOGLE_SCOPES": "gmail.readonly gmail.send",
            "GOOGLE_ACCESS_TOKEN": "test_token",
            "GOOGLE_REFRESH_TOKEN": "test_refresh"
        }):
            from connectonion.useful_tools.gmail import Gmail
            gmail = Gmail()
            mock_service = Mock()
            gmail._get_service = Mock(return_value=mock_service)
            return gmail, mock_service

    def test_read_inbox_basic(self, gmail_with_mock):
        """Test read_inbox returns formatted email list."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().list().execute.return_value = {
            'messages': [{'id': 'msg1'}]
        }
        mock_service.users().messages().get().execute.return_value = {
            'id': 'msg1',
            'payload': {
                'headers': [
                    {'name': 'From', 'value': 'sender@example.com'},
                    {'name': 'Subject', 'value': 'Test Subject'},
                    {'name': 'Date', 'value': '2024-01-15'}
                ]
            },
            'snippet': 'Email preview text...',
            'labelIds': ['UNREAD']
        }

        result = gmail.read_inbox(last=5)

        assert "sender@example.com" in result
        assert "Test Subject" in result
        assert "[UNREAD]" in result

    def test_read_inbox_unread_only(self, gmail_with_mock):
        """Test read_inbox with unread=True filter."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().list().execute.return_value = {'messages': []}

        gmail.read_inbox(last=10, unread=True)

        # Verify query includes unread filter
        mock_service.users().messages().list.assert_called()
        call_kwargs = mock_service.users().messages().list.call_args[1]
        assert "is:unread" in call_kwargs['q']

    def test_read_inbox_empty(self, gmail_with_mock):
        """Test read_inbox with no messages."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().list().execute.return_value = {'messages': []}

        result = gmail.read_inbox()

        assert "No emails found" in result

    def test_get_sent_emails(self, gmail_with_mock):
        """Test get_sent_emails returns sent emails."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().list().execute.return_value = {
            'messages': [{'id': 'sent1'}]
        }
        mock_service.users().messages().get().execute.return_value = {
            'id': 'sent1',
            'payload': {
                'headers': [
                    {'name': 'From', 'value': 'me@example.com'},
                    {'name': 'Subject', 'value': 'Sent Email'},
                    {'name': 'Date', 'value': '2024-01-15'}
                ]
            },
            'snippet': 'Sent content...',
            'labelIds': []
        }

        result = gmail.get_sent_emails(max_results=5)

        assert "Sent Email" in result
        mock_service.users().messages().list.assert_called()
        call_kwargs = mock_service.users().messages().list.call_args[1]
        assert "in:sent" in call_kwargs['q']

    def test_get_all_emails(self, gmail_with_mock):
        """Test get_all_emails returns all emails."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().list().execute.return_value = {
            'messages': [{'id': 'msg1'}]
        }
        mock_service.users().messages().get().execute.return_value = {
            'id': 'msg1',
            'payload': {
                'headers': [
                    {'name': 'From', 'value': 'anyone@example.com'},
                    {'name': 'Subject', 'value': 'Any Email'},
                    {'name': 'Date', 'value': '2024-01-15'}
                ]
            },
            'snippet': 'Content...',
            'labelIds': []
        }

        result = gmail.get_all_emails(max_results=50)

        assert "Any Email" in result

    def test_search_emails(self, gmail_with_mock):
        """Test search_emails with query."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().list().execute.return_value = {
            'messages': [{'id': 'found1'}]
        }
        mock_service.users().messages().get().execute.return_value = {
            'id': 'found1',
            'payload': {
                'headers': [
                    {'name': 'From', 'value': 'alice@example.com'},
                    {'name': 'Subject', 'value': 'Meeting Notes'},
                    {'name': 'Date', 'value': '2024-01-15'}
                ]
            },
            'snippet': 'Meeting details...',
            'labelIds': []
        }

        result = gmail.search_emails(query="from:alice@example.com", max_results=10)

        assert "alice@example.com" in result
        assert "Meeting Notes" in result

    def test_search_emails_no_results(self, gmail_with_mock):
        """Test search_emails with no matches."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().list().execute.return_value = {'messages': []}

        result = gmail.search_emails(query="nonexistent")

        assert "No emails found matching query" in result


class TestListingFormat:
    """Pins the exact text of every listing method.

    read_inbox/search_emails/get_sent_emails/get_all_emails are agent-facing
    tool output, so their wording and layout are the contract. These goldens
    were captured from the pre-refactor implementation.
    """

    @pytest.fixture
    def gmail_with_mock(self):
        with patch.dict(os.environ, {
            "GOOGLE_SCOPES": "gmail.readonly gmail.send",
            "GOOGLE_ACCESS_TOKEN": "test_token",
            "GOOGLE_REFRESH_TOKEN": "test_refresh"
        }):
            from connectonion.useful_tools.gmail import Gmail
            gmail = Gmail()
            mock_service = Mock()
            gmail._get_service = Mock(return_value=mock_service)
            return gmail, mock_service

    def load(self, mock_service, messages):
        """Serve `messages` (keyed by id) from the mocked Gmail API."""
        mock_service.users().messages().list().execute.return_value = {
            'messages': [{'id': mid} for mid in messages]
        }
        mock_service.users().messages().get.side_effect = lambda **kw: Mock(
            execute=Mock(return_value=messages[kw['id']])
        )

    def two_emails(self):
        return {
            'msg1': {
                'payload': {'headers': [
                    {'name': 'From', 'value': 'alice@example.com'},
                    {'name': 'Subject', 'value': 'Meeting Notes'},
                    {'name': 'Date', 'value': 'Sun, 26 Jul 2026 14:30:00 +0000'},
                ]},
                'snippet': 'Hello there',
                'labelIds': ['UNREAD', 'INBOX'],
            },
            # No headers at all, and a snippet past the 80-char preview cut.
            'msg2': {'payload': {'headers': []}, 'snippet': 'b' * 100, 'labelIds': []},
        }

    GOLDEN = (
        "Found 2 email(s):\n"
        "\n"
        "1. [UNREAD] From: alice@example.com\n"
        "   Subject: Meeting Notes\n"
        "   Date: Sun, 26 Jul 2026 14:30:00 +0000\n"
        "   Preview: Hello there...\n"
        "   ID: msg1\n"
        "\n"
        "2.  From: Unknown\n"
        "   Subject: No Subject\n"
        "   Date: Unknown\n"
        "   Preview: " + "b" * 80 + "...\n"
        "   ID: msg2\n"
    )

    def test_read_inbox_exact_output(self, gmail_with_mock):
        gmail, mock_service = gmail_with_mock
        self.load(mock_service, self.two_emails())

        assert gmail.read_inbox(last=10) == self.GOLDEN

    def test_search_emails_exact_output(self, gmail_with_mock):
        gmail, mock_service = gmail_with_mock
        self.load(mock_service, self.two_emails())

        assert gmail.search_emails("from:alice@example.com") == self.GOLDEN

    def test_get_sent_emails_exact_output(self, gmail_with_mock):
        gmail, mock_service = gmail_with_mock
        self.load(mock_service, self.two_emails())

        assert gmail.get_sent_emails() == self.GOLDEN

    def test_get_all_emails_exact_output(self, gmail_with_mock):
        gmail, mock_service = gmail_with_mock
        self.load(mock_service, self.two_emails())

        assert gmail.get_all_emails() == self.GOLDEN

    def test_message_without_snippet_key(self, gmail_with_mock):
        gmail, mock_service = gmail_with_mock
        self.load(mock_service, {'msg1': {'payload': {'headers': []}, 'labelIds': []}})

        assert gmail.read_inbox() == (
            "Found 1 email(s):\n"
            "\n"
            "1.  From: Unknown\n"
            "   Subject: No Subject\n"
            "   Date: Unknown\n"
            "   Preview: ...\n"
            "   ID: msg1\n"
        )

    def test_limit_truncates_to_requested_count(self, gmail_with_mock):
        gmail, mock_service = gmail_with_mock
        self.load(mock_service, self.two_emails())

        result = gmail.read_inbox(last=1)

        assert result.startswith("Found 1 email(s):")
        assert "msg2" not in result

    def test_list_inbox_returns_the_same_emails_it_formats(self, gmail_with_mock):
        """The CLI reads dicts, the agent reads text — they must agree."""
        gmail, mock_service = gmail_with_mock
        self.load(mock_service, self.two_emails())

        assert gmail.list_inbox(last=10) == [
            {'id': 'msg1', 'from': 'alice@example.com', 'subject': 'Meeting Notes',
             'date': 'Sun, 26 Jul 2026 14:30:00 +0000', 'snippet': 'Hello there', 'unread': True},
            {'id': 'msg2', 'from': 'Unknown', 'subject': 'No Subject',
             'date': 'Unknown', 'snippet': 'b' * 100, 'unread': False},
        ]

    def test_list_search_returns_dicts_for_the_query(self, gmail_with_mock):
        gmail, mock_service = gmail_with_mock
        self.load(mock_service, self.two_emails())

        emails = gmail.list_search("from:alice@example.com", max_results=5)

        assert [e['id'] for e in emails] == ['msg1', 'msg2']
        call_kwargs = mock_service.users().messages().list.call_args[1]
        assert call_kwargs['q'] == "from:alice@example.com"
        assert call_kwargs['maxResults'] == 5

    def test_list_inbox_unread_filter(self, gmail_with_mock):
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().list().execute.return_value = {'messages': []}

        assert gmail.list_inbox(last=10, unread=True) == []
        assert mock_service.users().messages().list.call_args[1]['q'] == "is:unread in:inbox"

    def test_list_inbox_default_scopes_to_inbox(self, gmail_with_mock):
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().list().execute.return_value = {'messages': []}

        gmail.list_inbox(last=10)

        assert mock_service.users().messages().list.call_args[1]['q'] == "in:inbox"

    def test_empty_listings_say_no_emails_found(self, gmail_with_mock):
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().list().execute.return_value = {'messages': []}

        assert gmail.read_inbox() == "No emails found."
        assert gmail.get_sent_emails() == "No emails found."
        assert gmail.get_all_emails() == "No emails found."
        assert gmail.search_emails("nope") == "No emails found matching query: nope"


class TestEmailContent:
    """Tests for email body and attachment methods."""

    @pytest.fixture
    def gmail_with_mock(self):
        """Create Gmail instance with mocked _get_service."""
        with patch.dict(os.environ, {
            "GOOGLE_SCOPES": "gmail.readonly gmail.send",
            "GOOGLE_ACCESS_TOKEN": "test_token",
            "GOOGLE_REFRESH_TOKEN": "test_refresh"
        }):
            from connectonion.useful_tools.gmail import Gmail
            gmail = Gmail()
            mock_service = Mock()
            gmail._get_service = Mock(return_value=mock_service)
            return gmail, mock_service

    def test_get_email_body_plain_text(self, gmail_with_mock):
        """Test get_email_body extracts plain text body."""
        import base64
        gmail, mock_service = gmail_with_mock
        body_content = "Hello, this is the email body."
        encoded_body = base64.urlsafe_b64encode(body_content.encode()).decode()

        mock_service.users().messages().get().execute.return_value = {
            'id': 'msg1',
            'payload': {
                'headers': [
                    {'name': 'From', 'value': 'sender@example.com'},
                    {'name': 'To', 'value': 'me@example.com'},
                    {'name': 'Subject', 'value': 'Test Email'},
                    {'name': 'Date', 'value': '2024-01-15'}
                ],
                'mimeType': 'text/plain',
                'body': {'data': encoded_body}
            }
        }

        result = gmail.get_email_body('msg1')

        assert "Hello, this is the email body" in result
        assert "sender@example.com" in result
        assert "Test Email" in result

    def test_get_email_body_multipart(self, gmail_with_mock):
        """Test get_email_body handles multipart emails."""
        import base64
        gmail, mock_service = gmail_with_mock
        plain_content = "Plain text version"
        encoded_plain = base64.urlsafe_b64encode(plain_content.encode()).decode()

        mock_service.users().messages().get().execute.return_value = {
            'id': 'msg1',
            'payload': {
                'headers': [
                    {'name': 'From', 'value': 'sender@example.com'},
                    {'name': 'To', 'value': 'me@example.com'},
                    {'name': 'Subject', 'value': 'Multipart Email'},
                    {'name': 'Date', 'value': '2024-01-15'}
                ],
                'mimeType': 'multipart/alternative',
                'parts': [
                    {
                        'mimeType': 'text/plain',
                        'body': {'data': encoded_plain}
                    },
                    {
                        'mimeType': 'text/html',
                        'body': {'data': base64.urlsafe_b64encode(b'<p>HTML version</p>').decode()}
                    }
                ]
            }
        }

        result = gmail.get_email_body('msg1')

        assert "Plain text version" in result

    def test_extract_html_body_uses_parser_and_omits_non_text_content(self, gmail_with_mock):
        """HTML variants cannot bypass the plain-text conversion boundary."""
        import base64
        gmail, _ = gmail_with_mock
        html = (
            '<p>Hello&nbsp;<strong>world</strong></p>'
            '<p>co<strong>de</strong>!</p>'
            '<ScRiPt data-example="true" >steal()</ScRiPt>'
            '<style >p { display: none }</style>'
            '<p>Next line</p>'
        )
        encoded_html = base64.urlsafe_b64encode(html.encode()).decode()

        result = gmail._extract_body({
            'mimeType': 'text/html',
            'body': {'data': encoded_html},
        })

        assert result == "Hello world code! Next line"

    def test_get_email_attachments(self, gmail_with_mock):
        """Test get_email_attachments lists attachments."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().get().execute.return_value = {
            'id': 'msg1',
            'payload': {
                'headers': [],
                'parts': [
                    {
                        'filename': 'document.pdf',
                        'body': {'size': 102400, 'attachmentId': 'att123'}
                    },
                    {
                        'filename': 'image.png',
                        'body': {'size': 51200, 'attachmentId': 'att456'}
                    }
                ]
            }
        }

        result = gmail.get_email_attachments('msg1')

        assert "document.pdf" in result
        assert "image.png" in result
        assert "2 attachment(s)" in result

    def test_get_email_attachments_none(self, gmail_with_mock):
        """Test get_email_attachments with no attachments."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().get().execute.return_value = {
            'id': 'msg1',
            'payload': {
                'headers': [],
                'parts': [{'mimeType': 'text/plain', 'body': {'data': 'test'}}]
            }
        }

        result = gmail.get_email_attachments('msg1')

        assert "No attachments" in result


class TestSendReply:
    """Tests for send and reply methods."""

    @pytest.fixture
    def gmail_with_mock(self):
        """Create Gmail instance with mocked _get_service."""
        with patch.dict(os.environ, {
            "GOOGLE_SCOPES": "gmail.readonly gmail.send",
            "GOOGLE_ACCESS_TOKEN": "test_token",
            "GOOGLE_REFRESH_TOKEN": "test_refresh"
        }):
            from connectonion.useful_tools.gmail import Gmail
            gmail = Gmail()
            mock_service = Mock()
            gmail._get_service = Mock(return_value=mock_service)
            return gmail, mock_service

    def test_send_basic(self, gmail_with_mock):
        """Test basic email send."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().send().execute.return_value = {'id': 'sent123'}

        result = gmail.send(
            to="recipient@example.com",
            subject="Test Subject",
            body="Hello, this is a test."
        )

        assert "Email sent successfully" in result
        assert "recipient@example.com" in result
        assert "sent123" in result

    def test_send_with_cc_bcc(self, gmail_with_mock):
        """Test send email with CC and BCC."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().send().execute.return_value = {'id': 'sent456'}

        result = gmail.send(
            to="recipient@example.com",
            subject="Test with CC",
            body="Body content",
            cc="cc@example.com",
            bcc="bcc@example.com"
        )

        assert "Email sent successfully" in result

    def test_reply_to_email(self, gmail_with_mock):
        """Test reply to an email."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().get().execute.return_value = {
            'threadId': 'thread123',
            'payload': {
                'headers': [
                    {'name': 'From', 'value': 'sender@example.com'},
                    {'name': 'To', 'value': 'me@example.com'},
                    {'name': 'Subject', 'value': 'Original Subject'},
                    {'name': 'Message-ID', 'value': '<msgid123@example.com>'}
                ]
            }
        }
        mock_service.users().messages().send().execute.return_value = {'id': 'reply123'}

        result = gmail.reply(email_id='original123', body='Thanks for your email!')

        assert "Reply sent successfully" in result
        assert "reply123" in result


class TestEmailActions:
    """Tests for email action methods (mark read, archive, star, etc.)."""

    @pytest.fixture
    def gmail_with_mock(self):
        """Create Gmail instance with mocked _get_service."""
        with patch.dict(os.environ, {
            "GOOGLE_SCOPES": "gmail.readonly gmail.send",
            "GOOGLE_ACCESS_TOKEN": "test_token",
            "GOOGLE_REFRESH_TOKEN": "test_refresh"
        }):
            from connectonion.useful_tools.gmail import Gmail
            gmail = Gmail()
            mock_service = Mock()
            gmail._get_service = Mock(return_value=mock_service)
            return gmail, mock_service

    def test_mark_read(self, gmail_with_mock):
        """Test marking email as read."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().modify().execute.return_value = {}

        result = gmail.mark_read('msg123')

        assert "Marked email as read" in result
        mock_service.users().messages().modify.assert_called()
        call_kwargs = mock_service.users().messages().modify.call_args[1]
        assert call_kwargs['body'] == {'removeLabelIds': ['UNREAD']}

    def test_mark_unread(self, gmail_with_mock):
        """Test marking email as unread."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().modify().execute.return_value = {}

        result = gmail.mark_unread('msg123')

        assert "Marked email as unread" in result
        call_kwargs = mock_service.users().messages().modify.call_args[1]
        assert call_kwargs['body'] == {'addLabelIds': ['UNREAD']}

    def test_archive_email(self, gmail_with_mock):
        """Test archiving email."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().modify().execute.return_value = {}

        result = gmail.archive_email('msg123')

        assert "Archived email" in result
        call_kwargs = mock_service.users().messages().modify.call_args[1]
        assert call_kwargs['body'] == {'removeLabelIds': ['INBOX']}

    def test_star_email(self, gmail_with_mock):
        """Test starring email."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().modify().execute.return_value = {}

        result = gmail.star_email('msg123')

        assert "Starred email" in result
        call_kwargs = mock_service.users().messages().modify.call_args[1]
        assert call_kwargs['body'] == {'addLabelIds': ['STARRED']}


class TestLabels:
    """Tests for label management methods."""

    @pytest.fixture
    def gmail_with_mock(self):
        """Create Gmail instance with mocked _get_service."""
        with patch.dict(os.environ, {
            "GOOGLE_SCOPES": "gmail.readonly gmail.send",
            "GOOGLE_ACCESS_TOKEN": "test_token",
            "GOOGLE_REFRESH_TOKEN": "test_refresh"
        }):
            from connectonion.useful_tools.gmail import Gmail
            gmail = Gmail()
            mock_service = Mock()
            gmail._get_service = Mock(return_value=mock_service)
            return gmail, mock_service

    def test_get_labels(self, gmail_with_mock):
        """Test getting all labels."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().labels().list().execute.return_value = {
            'labels': [
                {'id': 'INBOX', 'name': 'INBOX', 'type': 'system'},
                {'id': 'Label_1', 'name': 'Work', 'type': 'user'},
                {'id': 'Label_2', 'name': 'Personal', 'type': 'user'}
            ]
        }

        result = gmail.get_labels()

        assert "INBOX" in result
        assert "Work" in result
        assert "Personal" in result
        assert "3 label(s)" in result

    def test_get_labels_empty(self, gmail_with_mock):
        """Test get_labels with no labels."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().labels().list().execute.return_value = {'labels': []}

        result = gmail.get_labels()

        assert "No labels found" in result

    def test_add_label_by_name(self, gmail_with_mock):
        """Test adding label to email by label name."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().labels().list().execute.return_value = {
            'labels': [
                {'id': 'Label_1', 'name': 'Important'}
            ]
        }
        mock_service.users().messages().modify().execute.return_value = {}

        result = gmail.add_label('msg123', 'Important')

        assert "Added label 'Important'" in result

    def test_get_emails_with_label(self, gmail_with_mock):
        """Test getting emails with specific label."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().labels().list().execute.return_value = {
            'labels': [{'id': 'Label_1', 'name': 'Work'}]
        }
        mock_service.users().messages().list().execute.return_value = {
            'messages': [{'id': 'msg1'}]
        }
        mock_service.users().messages().get().execute.return_value = {
            'id': 'msg1',
            'payload': {
                'headers': [
                    {'name': 'From', 'value': 'work@example.com'},
                    {'name': 'Subject', 'value': 'Work Email'},
                    {'name': 'Date', 'value': '2024-01-15'}
                ]
            },
            'snippet': 'Work content...',
            'labelIds': ['Label_1']
        }

        result = gmail.get_emails_with_label('Work')

        assert "Work Email" in result

    def test_get_emails_with_label_not_found(self, gmail_with_mock):
        """Test getting emails with nonexistent label."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().labels().list().execute.return_value = {
            'labels': [{'id': 'Label_1', 'name': 'Work'}]
        }

        result = gmail.get_emails_with_label('Nonexistent')

        assert "Label not found" in result


class TestStats:
    """Tests for email statistics methods."""

    @pytest.fixture
    def gmail_with_mock(self):
        """Create Gmail instance with mocked _get_service."""
        with patch.dict(os.environ, {
            "GOOGLE_SCOPES": "gmail.readonly gmail.send",
            "GOOGLE_ACCESS_TOKEN": "test_token",
            "GOOGLE_REFRESH_TOKEN": "test_refresh"
        }):
            from connectonion.useful_tools.gmail import Gmail
            gmail = Gmail()
            mock_service = Mock()
            gmail._get_service = Mock(return_value=mock_service)
            return gmail, mock_service

    def test_count_unread(self, gmail_with_mock):
        """Test counting unread emails."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().list().execute.return_value = {
            'resultSizeEstimate': 42
        }

        result = gmail.count_unread()

        assert "42 unread email(s)" in result

    def test_get_my_identity(self, gmail_with_mock):
        """Test getting user's email identity."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().getProfile().execute.return_value = {
            'emailAddress': 'user@example.com'
        }
        mock_service.users().settings().sendAs().list().execute.return_value = {
            'sendAs': [
                {'sendAsEmail': 'user@example.com'},
                {'sendAsEmail': 'alias@company.com'}
            ]
        }

        result = gmail.get_my_identity()

        assert "user@example.com" in result
        assert "alias@company.com" in result


class TestCRM:
    """Tests for CRM-related methods."""

    def _create_gmail(self, tmppath):
        """Create Gmail instance with custom paths."""
        with patch.dict(os.environ, {
            "GOOGLE_SCOPES": "gmail.readonly gmail.send",
            "GOOGLE_ACCESS_TOKEN": "test_token",
            "GOOGLE_REFRESH_TOKEN": "test_refresh"
        }):
            from connectonion.useful_tools.gmail import Gmail
            gmail = Gmail(
                emails_csv=str(tmppath / "emails.csv"),
                contacts_csv=str(tmppath / "contacts.csv")
            )
            mock_service = Mock()
            gmail._get_service = Mock(return_value=mock_service)
            return gmail, mock_service

    def test_update_contact(self):
        """Test updating a contact's CRM fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create initial contacts.csv
            contacts_file = tmppath / "contacts.csv"
            with open(contacts_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'email', 'name', 'frequency', 'last_contact', 'type', 'company',
                    'relationship', 'priority', 'deal', 'next_contact_date', 'tags', 'notes'
                ])
                writer.writeheader()
                writer.writerow({
                    'email': 'contact@example.com',
                    'name': 'John Doe',
                    'frequency': '5',
                    'last_contact': '2024-01-15',
                    'type': '',
                    'company': '',
                    'relationship': '',
                    'priority': '',
                    'deal': '',
                    'next_contact_date': '',
                    'tags': '',
                    'notes': ''
                })

            gmail, mock_service = self._create_gmail(tmppath)
            result = gmail.update_contact(
                email='contact@example.com',
                type='PERSON',
                priority='high',
                company='Acme Corp'
            )

            assert "Updated contact@example.com" in result
            assert "type=PERSON" in result
            assert "priority=high" in result

            # Verify file was updated
            with open(contacts_file, 'r') as f:
                reader = csv.DictReader(f)
                row = next(reader)
                assert row['type'] == 'PERSON'
                assert row['priority'] == 'high'
                assert row['company'] == 'Acme Corp'

    def test_update_contact_not_found(self):
        """Test updating a nonexistent contact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            contacts_file = tmppath / "contacts.csv"
            with open(contacts_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'email', 'name', 'frequency', 'last_contact', 'type', 'company',
                    'relationship', 'priority', 'deal', 'next_contact_date', 'tags', 'notes'
                ])
                writer.writeheader()

            gmail, mock_service = self._create_gmail(tmppath)
            result = gmail.update_contact(email='nonexistent@example.com', type='PERSON')

            assert "not found" in result

    def test_get_cached_contacts(self):
        """Test getting contacts from CSV cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            contacts_file = tmppath / "contacts.csv"
            with open(contacts_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'email', 'name', 'frequency', 'last_contact', 'type', 'company',
                    'relationship', 'priority', 'deal', 'next_contact_date', 'tags', 'notes'
                ])
                writer.writeheader()
                writer.writerow({
                    'email': 'cached@example.com',
                    'name': 'Cached Contact',
                    'frequency': '10',
                    'last_contact': '2024-01-15',
                    'type': 'PERSON',
                    'company': '',
                    'relationship': '',
                    'priority': 'high',
                    'deal': '',
                    'next_contact_date': '',
                    'tags': '',
                    'notes': ''
                })

            gmail, mock_service = self._create_gmail(tmppath)
            result = gmail.get_cached_contacts()

            assert "cached@example.com" in result
            assert "Cached Contact" in result

    def test_get_cached_contacts_no_file(self):
        """Test get_cached_contacts when no cache exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            gmail, mock_service = self._create_gmail(tmppath)
            result = gmail.get_cached_contacts()

            assert "No cached contacts" in result

    def test_bulk_update_contacts(self):
        """Test bulk updating multiple contacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            contacts_file = tmppath / "contacts.csv"
            with open(contacts_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'email', 'name', 'frequency', 'last_contact', 'type', 'company',
                    'relationship', 'priority', 'deal', 'next_contact_date', 'tags', 'notes'
                ])
                writer.writeheader()
                writer.writerow({
                    'email': 'person1@example.com',
                    'name': 'Person 1',
                    'frequency': '5',
                    'last_contact': '',
                    'type': '',
                    'company': '',
                    'relationship': '',
                    'priority': '',
                    'deal': '',
                    'next_contact_date': '',
                    'tags': '',
                    'notes': ''
                })
                writer.writerow({
                    'email': 'person2@example.com',
                    'name': 'Person 2',
                    'frequency': '3',
                    'last_contact': '',
                    'type': '',
                    'company': '',
                    'relationship': '',
                    'priority': '',
                    'deal': '',
                    'next_contact_date': '',
                    'tags': '',
                    'notes': ''
                })

            gmail, mock_service = self._create_gmail(tmppath)
            result = gmail.bulk_update_contacts([
                {'email': 'person1@example.com', 'type': 'PERSON', 'priority': 'high'},
                {'email': 'person2@example.com', 'type': 'SERVICE', 'priority': 'low'}
            ])

            assert "Bulk updated 2 contacts" in result

            # Verify updates
            with open(contacts_file, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                assert rows[0]['type'] == 'PERSON'
                assert rows[0]['priority'] == 'high'
                assert rows[1]['type'] == 'SERVICE'
                assert rows[1]['priority'] == 'low'


class TestAnalyzeContact:
    """Tests for analyze_contact method with mocked LLM."""

    @pytest.fixture
    def gmail_with_mock(self):
        """Create Gmail instance with mocked _get_service."""
        with patch.dict(os.environ, {
            "GOOGLE_SCOPES": "gmail.readonly gmail.send",
            "GOOGLE_ACCESS_TOKEN": "test_token",
            "GOOGLE_REFRESH_TOKEN": "test_refresh"
        }):
            from connectonion.useful_tools.gmail import Gmail
            gmail = Gmail()
            mock_service = Mock()
            gmail._get_service = Mock(return_value=mock_service)
            return gmail, mock_service

    def test_analyze_contact_calls_llm(self, gmail_with_mock):
        """Test that analyze_contact calls llm_do with email content."""
        import importlib
        llm_do_module = importlib.import_module('connectonion.llm_do')

        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().list().execute.return_value = {
            'messages': [{'id': 'msg1'}]
        }
        mock_service.users().messages().get().execute.return_value = {
            'id': 'msg1',
            'payload': {
                'headers': [
                    {'name': 'From', 'value': 'contact@example.com'},
                    {'name': 'Subject', 'value': 'Hello'},
                    {'name': 'Date', 'value': '2024-01-15'}
                ]
            },
            'snippet': 'Hi there...',
            'labelIds': []
        }

        with patch.object(llm_do_module, 'llm_do') as mock_llm_do:
            mock_llm_do.return_value = "This is a business contact. Tags: partner, vendor."

            result = gmail.analyze_contact('contact@example.com', max_emails=10)

            assert "Analysis for contact@example.com" in result
            assert "business contact" in result
            mock_llm_do.assert_called_once()


class TestGmailIntegration:
    """Integration tests for Gmail as agent tool."""

    @patch.dict(os.environ, {
        "GOOGLE_SCOPES": "gmail.readonly gmail.send",
        "GOOGLE_ACCESS_TOKEN": "test_token",
        "GOOGLE_REFRESH_TOKEN": "test_refresh"
    })
    def test_gmail_integrates_with_agent(self):
        """Test that Gmail can be used as an agent tool."""
        from connectonion import Agent
        from connectonion.core.llm import LLMResponse
        from connectonion.core.usage import TokenUsage
        from connectonion.useful_tools.gmail import Gmail

        # Create mock LLM
        mock_llm = Mock()
        mock_llm.model = "test-model"
        mock_llm.complete.return_value = LLMResponse(
            content="Test response",
            tool_calls=[],
            raw_response=None,
            usage=TokenUsage(),
        )

        gmail = Gmail()

        # Should not raise
        agent = Agent(
            "test",
            llm=mock_llm,
            tools=[gmail],
            log=False,
        )

        # Verify Gmail methods are registered as tools
        assert 'read_inbox' in agent.tools
        assert 'search_emails' in agent.tools
        assert 'send' in agent.tools
        assert 'reply' in agent.tools
        assert 'get_labels' in agent.tools
        assert 'get_all_contacts' in agent.tools
        assert 'update_contact' in agent.tools


class TestGmailSendAttachments:
    """Sending a file, which `co outlook` could do and `co gmail` could not (#800).

    Every assertion here reads the raw MIME that would go to the API rather
    than trusting the call happened. The Gmail API takes one opaque base64
    blob, so "we called send" proves nothing about whether the file is in it.
    """


    @pytest.fixture
    def gmail_with_mock(self):
        """Same shape as the one in TestEmailContent -- fixtures there are
        class-scoped, so this class needs its own."""
        with patch.dict(os.environ, {
            "GOOGLE_SCOPES": "gmail.readonly gmail.send",
            "GOOGLE_ACCESS_TOKEN": "test_token",
            "GOOGLE_REFRESH_TOKEN": "test_refresh"
        }):
            from connectonion.useful_tools.gmail import Gmail
            gmail = Gmail(allow_external_attachments=True)
            mock_service = Mock()
            gmail._get_service = Mock(return_value=mock_service)
            return gmail, mock_service

    @staticmethod
    def _sent_mime(mock_service):
        """The message the API was actually handed, decoded back to MIME."""
        import base64
        body = mock_service.users().messages().send.call_args.kwargs["body"]
        return base64.urlsafe_b64decode(body["raw"]).decode("utf-8", "replace")

    def test_a_file_is_attached_with_its_name(self, gmail_with_mock, tmp_path):
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().send().execute.return_value = {'id': 'a1'}
        doc = tmp_path / "invoice.pdf"
        doc.write_bytes(b"%PDF-1.4 pretend")

        gmail.send(to="r@example.com", subject="S", body="B",
                   attachments=[str(doc)])

        mime = self._sent_mime(mock_service)
        assert "invoice.pdf" in mime, "the filename has to survive to the recipient"
        assert "multipart" in mime.lower()

    def test_the_body_survives_alongside_the_attachment(self, gmail_with_mock, tmp_path):
        """A multipart rewrite is exactly where a body goes missing."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().send().execute.return_value = {'id': 'a2'}
        doc = tmp_path / "note.txt"
        doc.write_text("data")

        gmail.send(to="r@example.com", subject="S", body="the body text",
                   attachments=[str(doc)])

        assert "the body text" in self._sent_mime(mock_service)

    def test_several_files_all_arrive(self, gmail_with_mock, tmp_path):
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().send().execute.return_value = {'id': 'a3'}
        one, two = tmp_path / "one.txt", tmp_path / "two.csv"
        one.write_text("1")
        two.write_text("2")

        gmail.send(to="r@example.com", subject="S", body="B",
                   attachments=[str(one), str(two)])

        mime = self._sent_mime(mock_service)
        assert "one.txt" in mime and "two.csv" in mime

    def test_no_attachments_is_unchanged(self, gmail_with_mock):
        """The path every existing caller takes. Adding attachments must not
        turn an ordinary mail into a multipart one."""
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().send().execute.return_value = {'id': 'a4'}

        gmail.send(to="r@example.com", subject="S", body="plain body")

        mime = self._sent_mime(mock_service)
        assert "plain body" in mime
        assert "multipart" not in mime.lower()

    def test_a_missing_file_says_which_one(self, gmail_with_mock):
        """Named, because the caller passed a list and needs to know which
        entry was wrong."""
        gmail, _ = gmail_with_mock

        with pytest.raises(Exception) as raised:
            gmail.send(to="r@example.com", subject="S", body="B",
                       attachments=["/nonexistent/quarterly.xlsx"])

        assert "quarterly.xlsx" in str(raised.value)

    def test_cc_and_bcc_still_work_with_an_attachment(self, gmail_with_mock, tmp_path):
        gmail, mock_service = gmail_with_mock
        mock_service.users().messages().send().execute.return_value = {'id': 'a5'}
        doc = tmp_path / "f.txt"
        doc.write_text("x")

        gmail.send(to="r@example.com", subject="S", body="B",
                   cc="c@example.com", bcc="b@example.com",
                   attachments=[str(doc)])

        mime = self._sent_mime(mock_service)
        assert "c@example.com" in mime and "b@example.com" in mime

    def test_an_agent_can_attach_a_file_inside_its_project(self, tmp_path, monkeypatch):
        from contextlib import ExitStack

        project = tmp_path / "project"
        project.mkdir()
        (project / ".co").mkdir()
        attachment = project / "report.txt"
        attachment.write_text("safe")
        monkeypatch.chdir(project)

        with patch.dict(os.environ, {"GOOGLE_SCOPES": "gmail.readonly gmail.send"}):
            from connectonion.useful_tools.gmail import Gmail
            gmail = Gmail()

        with ExitStack() as stack:
            opened = gmail._open_attachments([str(attachment)], stack)
            assert [name for name, _ in opened] == ["report.txt"]

    def test_an_agent_cannot_attach_a_file_outside_its_project(self, tmp_path, monkeypatch):
        from contextlib import ExitStack

        project = tmp_path / "project"
        project.mkdir()
        (project / ".co").mkdir()
        outside = tmp_path / "secret.txt"
        outside.write_text("secret")
        monkeypatch.chdir(project)

        with patch.dict(os.environ, {"GOOGLE_SCOPES": "gmail.readonly gmail.send"}):
            from connectonion.useful_tools.gmail import Gmail
            gmail = Gmail()

        with ExitStack() as stack:
            with pytest.raises(PermissionError, match="outside the project"):
                gmail._open_attachments([str(outside)], stack)

    def test_a_symlink_cannot_escape_the_project(self, tmp_path, monkeypatch):
        from contextlib import ExitStack

        project = tmp_path / "project"
        project.mkdir()
        (project / ".co").mkdir()
        outside = tmp_path / "secret.txt"
        outside.write_text("secret")
        link = project / "looks-local.txt"
        link.symlink_to(outside)
        monkeypatch.chdir(project)

        with patch.dict(os.environ, {"GOOGLE_SCOPES": "gmail.readonly gmail.send"}):
            from connectonion.useful_tools.gmail import Gmail
            gmail = Gmail()

        with ExitStack() as stack:
            with pytest.raises(PermissionError, match="outside the project"):
                gmail._open_attachments([str(link)], stack)

    def test_a_checked_file_is_not_reopened_after_a_symlink_swap(self, tmp_path, monkeypatch):
        from contextlib import ExitStack

        project = tmp_path / "project"
        project.mkdir()
        (project / ".co").mkdir()
        local = project / "report.txt"
        local.write_bytes(b"safe report")
        outside = tmp_path / "secret.txt"
        outside.write_bytes(b"secret")
        monkeypatch.chdir(project)

        with patch.dict(os.environ, {"GOOGLE_SCOPES": "gmail.readonly gmail.send"}):
            from connectonion.useful_tools.gmail import Gmail
            gmail = Gmail()

        with ExitStack() as stack:
            opened = gmail._open_attachments([str(local)], stack)
            local.unlink()
            local.symlink_to(outside)
            message = gmail._multipart_with("body", opened)

        assert message.get_payload()[1].get_payload(decode=True) == b"safe report"

    def test_a_parent_directory_swap_cannot_escape_the_project(self, tmp_path, monkeypatch):
        from contextlib import ExitStack

        project = tmp_path / "project"
        project.mkdir()
        (project / ".co").mkdir()
        slot = project / "slot"
        slot.mkdir()
        local = slot / "report.txt"
        local.write_bytes(b"safe")
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "report.txt").write_bytes(b"SECRET")
        monkeypatch.chdir(project)

        with patch.dict(os.environ, {"GOOGLE_SCOPES": "gmail.readonly gmail.send"}):
            from connectonion.useful_tools.gmail import Gmail
            gmail = Gmail()

        original_open = os.open

        def swap_parent_then_open(path, flags):
            slot.rename(project / "old-slot")
            slot.symlink_to(outside, target_is_directory=True)
            return original_open(path, flags)

        with patch.object(os, "open", side_effect=swap_parent_then_open):
            with ExitStack() as stack:
                with pytest.raises(PermissionError, match="outside the project"):
                    gmail._open_attachments([str(local)], stack)

    def test_a_safe_symlink_keeps_the_sender_selected_filename(self, tmp_path, monkeypatch):
        from contextlib import ExitStack

        project = tmp_path / "project"
        project.mkdir()
        (project / ".co").mkdir()
        target = project / "artifact-123"
        target.write_bytes(b"pdf")
        link = project / "invoice.pdf"
        link.symlink_to(target)
        monkeypatch.chdir(project)

        with patch.dict(os.environ, {"GOOGLE_SCOPES": "gmail.readonly gmail.send"}):
            from connectonion.useful_tools.gmail import Gmail
            gmail = Gmail()

        with ExitStack() as stack:
            opened = gmail._open_attachments([str(link)], stack)
            message = gmail._multipart_with("body", opened)

        part = message.get_payload()[1]
        assert part.get_filename() == "invoice.pdf"
        assert part.get_content_type() == "application/pdf"

    def test_growth_after_fstat_is_caught_during_the_read(self, tmp_path):
        from contextlib import ExitStack

        local = tmp_path / "growing.bin"
        local.write_bytes(b"x")
        with patch.dict(os.environ, {"GOOGLE_SCOPES": "gmail.readonly gmail.send"}):
            from connectonion.useful_tools import gmail as gmail_module
            gmail = gmail_module.Gmail(allow_external_attachments=True)

        with patch.object(gmail_module, "GMAIL_ATTACHMENT_LIMIT", 4):
            with ExitStack() as stack:
                opened = gmail._open_attachments([str(local)], stack)
                local.write_bytes(b"12345")
                with pytest.raises(ValueError, match="25MB"):
                    gmail._multipart_with("body", opened)

    def test_the_core_rejects_oversize_before_touching_the_api(self, tmp_path):
        huge = tmp_path / "huge.bin"
        huge.write_bytes(b"")
        os.truncate(huge, 25_000_001)

        with patch.dict(os.environ, {"GOOGLE_SCOPES": "gmail.readonly gmail.send"}):
            from connectonion.useful_tools.gmail import Gmail
            gmail = Gmail(allow_external_attachments=True)
        gmail._get_service = Mock()

        with pytest.raises(ValueError, match="25MB"):
            gmail.send("r@example.com", "S", "B", attachments=[str(huge)])

        gmail._get_service.assert_not_called()
