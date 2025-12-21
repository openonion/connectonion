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

import pytest
import os
import tempfile
import csv
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path


# Future expiry time for tests (1 hour from now)
FUTURE_EXPIRY = (datetime.utcnow() + timedelta(hours=1)).isoformat() + 'Z'


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
        "GOOGLE_TOKEN_EXPIRES_AT": FUTURE_EXPIRY
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
        "GOOGLE_TOKEN_EXPIRES_AT": FUTURE_EXPIRY
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

    @patch.dict(os.environ, {"GOOGLE_SCOPES": "gmail.readonly gmail.send"}, clear=True)
    def test_get_service_missing_credentials(self):
        """Test _get_service raises error when credentials missing."""
        from connectonion.useful_tools.gmail import Gmail
        gmail = Gmail.__new__(Gmail)
        gmail._service = None

        with pytest.raises(ValueError) as exc_info:
            gmail._get_service()
        assert "Google OAuth credentials not found" in str(exc_info.value)


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
