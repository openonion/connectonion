"""Tests for email functionality in ConnectOnion (pytest style)."""
"""
LLM-Note: Tests for email functions

What it tests:
- Email Functions functionality

Components under test:
- Module: email_functions
"""


from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import tempfile
import yaml
import json
import os
import sys
import requests
import pytest

import importlib
# The `send_email` function is re-exported in the connectonion.useful_tools package
# namespace, which shadows the submodule for attribute-based lookups. Resolve the
# actual module object via importlib so patch.object targets the module, not the fn.
send_email_module = importlib.import_module("connectonion.useful_tools.send_email")
from connectonion.useful_tools.send_email import send_email, get_agent_email, is_email_active
from connectonion.useful_tools.get_emails import get_emails, get_sent, mark_read, mark_unread

# Import test configuration
from tests.utils.config_helpers import (
    TEST_ACCOUNT,
    TEST_JWT_TOKEN,
    TEST_CONFIG_TOML,
    SAMPLE_EMAILS,
    ProjectHelper,
)


# -------- send_email tests -------- #

@patch.dict('os.environ', {'OPENONION_API_KEY': TEST_JWT_TOKEN, 'AGENT_EMAIL': TEST_ACCOUNT["email"]})
@patch('requests.post')
def test_send_email_success(mock_post):
    """Test successful email sending."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"message_id": "msg_123"}
    mock_post.return_value = mock_response

    result = send_email(
        "test@example.com", "Test Subject", "Test Message",
        idempotency_key="send-test-123",
    )

    assert result["success"] is True
    assert result["message_id"] == "msg_123"
    assert result["from"] == TEST_ACCOUNT["email"]
    assert result["request_id"] == "send-test-123"
    assert result["idempotency_key"] == "send-test-123"

    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "Authorization" in call_args[1]["headers"]
    assert call_args[1]["headers"]["Authorization"] == f"Bearer {TEST_JWT_TOKEN}"
    assert call_args[1]["headers"]["X-Request-ID"] == "send-test-123"
    assert call_args[1]["headers"]["Idempotency-Key"] == "send-test-123"


@patch.dict('os.environ', {'OPENONION_API_KEY': 'test-token-123', 'AGENT_EMAIL': 'test@openonion.ai'})
@patch('requests.post')
def test_send_email_not_activated(mock_post):
    """Test email sending when backend returns not activated error."""
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.json.return_value = {"detail": "Email not activated. Run 'co auth' to activate."}
    mock_post.return_value = mock_response

    result = send_email("test@example.com", "Test", "Message")

    assert result["success"] is False
    assert "Email not activated" in result["error"]


# Neutralize .env discovery so a stray ~/.co/keys.env on the dev machine can't
# re-inject real credentials into the cleared environment (keeps this hermetic).
# patch.object on the module object avoids the send_email module-vs-function name
# collision that string-target patching resolves inconsistently across Python versions.
@patch.object(send_email_module, 'load_dotenv', lambda *a, **k: None)
@patch.dict('os.environ', {}, clear=True)
def test_send_email_no_project():
    """Test email sending when missing OPENONION_API_KEY."""
    result = send_email("test@example.com", "Test", "Message")
    assert result["success"] is False
    assert ("OPENONION_API_KEY" in result["error"]) or ("No .env file" in result["error"])


@patch.dict('os.environ', {'OPENONION_API_KEY': 'test-token-123', 'AGENT_EMAIL': 'test@openonion.ai'})
def test_invalid_email_address():
    """Test with invalid email address."""
    result = send_email("not-an-email", "Test", "Message")
    assert result["success"] is False
    assert result["error"] == "Invalid email address: not-an-email"


@patch.dict('os.environ', {'OPENONION_API_KEY': 'test-token-123', 'AGENT_EMAIL': 'test@openonion.ai'})
@patch('requests.post')
def test_send_email_rate_limit(mock_post):
    """Test rate limit handling."""
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_post.return_value = mock_response

    result = send_email("test@example.com", "Test", "Message")

    assert result["success"] is False
    assert result["error"] == "Rate limit exceeded"


@patch.dict('os.environ', {'OPENONION_API_KEY': 'test-token-123', 'AGENT_EMAIL': 'test@openonion.ai'})
@patch('requests.post')
def test_send_email_keeps_server_ids_on_a_stable_json_error(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 502
    mock_response.headers = {"X-Request-ID": "header-id"}
    mock_response.json.return_value = {
        "detail": "Retry with the same idempotency key.",
        "request_id": "server-request",
        "idempotency_key": "send-original",
    }
    mock_post.return_value = mock_response

    result = send_email(
        "test@example.com", "Test", "Message",
        idempotency_key="send-original",
    )

    assert result == {
        "success": False,
        "error": "Retry with the same idempotency key.",
        "request_id": "server-request",
        "idempotency_key": "send-original",
        "retryable": True,
    }


@patch.dict('os.environ', {'OPENONION_API_KEY': 'test-token-123', 'AGENT_EMAIL': 'test@openonion.ai'})
@patch('requests.post')
def test_send_email_preserves_a_non_retryable_backend_verdict(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 409
    mock_response.headers = {"X-Request-ID": "req-old"}
    mock_response.json.return_value = {
        "detail": "The safe-retry window expired; the email was not resent.",
        "error": {
            "code": "idempotency_window_expired",
            "message": "The safe-retry window expired; the email was not resent.",
            "retryable": False,
        },
        "request_id": "req-old",
        "idempotency_key": "send-old",
    }
    mock_post.return_value = mock_response

    result = send_email(
        "test@example.com", "Test", "Message", idempotency_key="send-old"
    )

    assert result["success"] is False
    assert result["retryable"] is False
    assert result["idempotency_key"] == "send-old"


@patch.dict('os.environ', {'OPENONION_API_KEY': 'test-token-123', 'AGENT_EMAIL': 'test@openonion.ai'})
@patch('requests.post', side_effect=requests.exceptions.Timeout)
def test_send_email_timeout_returns_the_key_for_a_safe_retry(mock_post):
    result = send_email(
        "test@example.com", "Test", "Message",
        idempotency_key="send-timeout",
    )

    assert result["success"] is False
    assert result["request_id"] == "send-timeout"
    assert result["idempotency_key"] == "send-timeout"
    assert result["retryable"] is True
    assert "same idempotency key" in result["error"]


# -------- get_emails tests -------- #

@pytest.fixture
def sample_emails_backend_format():
    return [
        {
            "id": email["id"],
            "from_email": email["from"],
            "subject": email["subject"],
            "text_body": email["message"],
            "received_at": email["timestamp"],
            "is_read": email["read"],
        }
        for email in SAMPLE_EMAILS[:2]
    ]


@patch.dict('os.environ', {'OPENONION_API_KEY': TEST_JWT_TOKEN})
@patch('requests.get')
def test_get_emails_success(mock_get, sample_emails_backend_format):
    """Test successful email retrieval."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"emails": sample_emails_backend_format}
    mock_get.return_value = mock_response

    emails = get_emails(last=5)

    assert len(emails) == 2
    assert emails[0]["id"] == "msg_test_001"
    assert emails[0]["from"] == "alice@example.com"
    assert emails[0]["subject"] == "Test Email 1"
    assert emails[0]["message"] == "This is test email number 1"
    assert emails[0]["read"] is False

    mock_get.assert_called_once()
    call_args = mock_get.call_args
    assert call_args[1]["params"]["limit"] == 5
    assert call_args[1]["params"]["unread_only"] is False


@pytest.mark.parametrize("last", [0, 101, 1000, -1, True, 1.5, "10"])
@patch.dict('os.environ', {}, clear=True)
@patch('requests.get')
def test_get_emails_rejects_an_unsupported_received_mail_limit(mock_get, last):
    with pytest.raises(ValueError, match="last must be between 1 and 100"):
        get_emails(last=last)
    mock_get.assert_not_called()


@patch.dict('os.environ', {'OPENONION_API_KEY': TEST_JWT_TOKEN})
@patch('requests.get')
def test_get_emails_accepts_the_received_mail_maximum(mock_get):
    response = MagicMock()
    response.json.return_value = {"emails": []}
    mock_get.return_value = response

    assert get_emails(last=100) == []
    assert mock_get.call_args.kwargs["params"]["limit"] == 100


@patch.dict('os.environ', {'OPENONION_API_KEY': TEST_JWT_TOKEN})
@patch('requests.get')
def test_get_emails_unread_only(mock_get):
    """Test getting only unread emails."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"emails": [{
        "id": SAMPLE_EMAILS[0]["id"],
        "from_email": SAMPLE_EMAILS[0]["from"],
        "subject": SAMPLE_EMAILS[0]["subject"],
        "text_body": SAMPLE_EMAILS[0]["message"],
        "received_at": SAMPLE_EMAILS[0]["timestamp"],
        "is_read": SAMPLE_EMAILS[0]["read"],
    }]}
    mock_get.return_value = mock_response

    emails = get_emails(unread=True)

    assert len(emails) == 1
    assert emails[0]["read"] is False
    call_args = mock_get.call_args
    assert call_args[1]["params"]["unread_only"] is True


@patch.dict('os.environ', {}, clear=True)
def test_get_emails_no_project():
    """Test getting emails without OPENONION_API_KEY."""
    with pytest.raises(ValueError) as exc:
        get_emails()
    assert "OPENONION_API_KEY not found" in str(exc.value)


# === The Sent mailbox (issue #662) ===

A_SENT_ROW = {
    "id": 7,
    "to": "alice@example.com",
    "from": "0xtest@mail.openonion.ai",
    "subject": "hello",
    "body": "<p>hi</p>",
    "status": "sent",
    "message_id": "re_123",
    "sent_at": "2026-08-07T03:00:00",
}


@patch.dict('os.environ', {'OPENONION_API_KEY': TEST_JWT_TOKEN})
@patch('requests.get')
def test_get_sent_returns_what_was_sent(mock_get):
    """A sent email can be read back: recipient, body, status, message id."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"emails": [A_SENT_ROW], "count": 1}
    mock_get.return_value = mock_response

    emails = get_sent(last=5)

    assert len(emails) == 1
    assert emails[0]["to"] == "alice@example.com"
    assert emails[0]["body"] == "<p>hi</p>"
    assert emails[0]["status"] == "sent"
    assert emails[0]["message_id"] == "re_123"
    assert emails[0]["timestamp"] == "2026-08-07T03:00:00"

    call_args = mock_get.call_args
    assert call_args[0][0].endswith("/api/v1/email/sent")
    assert call_args[1]["params"] == {"limit": 5}


@patch.dict('os.environ', {'OPENONION_API_KEY': TEST_JWT_TOKEN})
@patch('requests.get')
def test_get_sent_still_accepts_one_thousand(mock_get):
    response = MagicMock()
    response.json.return_value = {"emails": []}
    mock_get.return_value = response

    assert get_sent(last=1000) == []
    assert mock_get.call_args.kwargs["params"]["limit"] == 1000


@patch.dict('os.environ', {'OPENONION_API_KEY': TEST_JWT_TOKEN})
@patch('requests.get')
def test_get_sent_filters_by_recipient(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"emails": [], "count": 0}
    mock_get.return_value = mock_response

    get_sent(to="alice@example.com")

    assert mock_get.call_args[1]["params"] == {"limit": 10, "to": "alice@example.com"}


@patch.dict('os.environ', {}, clear=True)
def test_get_sent_without_auth_says_so():
    with pytest.raises(ValueError) as exc:
        get_sent()
    assert "OPENONION_API_KEY not found" in str(exc.value)


@patch.dict('os.environ', {'OPENONION_API_KEY': TEST_JWT_TOKEN})
@patch('requests.get')
def test_get_emails_api_error(mock_get):
    """Test handling API errors."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
    mock_get.return_value = mock_response

    with pytest.raises(requests.HTTPError):
        get_emails()


# -------- mark_read tests -------- #

@patch.dict('os.environ', {'OPENONION_API_KEY': TEST_JWT_TOKEN})
@patch('requests.post')
def test_mark_read_single(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    result = mark_read("msg_123")
    assert result is True


@patch.dict('os.environ', {'OPENONION_API_KEY': TEST_JWT_TOKEN})
@patch('requests.post')
def test_mark_read_multiple(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    result = mark_read(["msg_1", "msg_2", "msg_3"])
    assert result is True


@patch.dict('os.environ', {}, clear=True)
def test_mark_read_no_project():
    with pytest.raises(ValueError) as exc:
        mark_read("msg_123")
    assert "OPENONION_API_KEY not found" in str(exc.value)


def test_mark_read_empty_list():
    with pytest.raises(ValueError) as exc:
        mark_read([])
    assert "No email IDs provided" in str(exc.value)


@patch.dict('os.environ', {'OPENONION_API_KEY': TEST_JWT_TOKEN})
@patch('requests.post')
def test_mark_read_api_error(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
    mock_post.return_value = mock_response

    with pytest.raises(requests.HTTPError):
        mark_read("msg_123")


# -------- helper function tests -------- #
# Note: We patch 'yaml.safe_load' globally instead of
# 'connectonion.useful_tools.send_email.yaml.safe_load' because
# __init__.py re-exports the send_email function, shadowing the module name.

@patch('pathlib.Path.exists')
@patch('yaml.safe_load')
@patch('builtins.open', new_callable=mock_open)
def test_get_agent_email(mock_file, mock_yaml_load, mock_exists):
    mock_exists.return_value = True
    mock_yaml_load.return_value = TEST_CONFIG_TOML
    email = get_agent_email()
    assert email == TEST_ACCOUNT["email"]


@patch('pathlib.Path.exists')
@patch('yaml.safe_load')
@patch('builtins.open', new_callable=mock_open)
def test_get_agent_email_generated(mock_file, mock_yaml_load, mock_exists):
    mock_exists.return_value = True
    mock_yaml_load.return_value = {"agent": {"address": "0xabcdef1234567890"}}
    email = get_agent_email()
    assert email == "0xabcdef12@mail.openonion.ai"


def test_is_email_active(monkeypatch):
    monkeypatch.setenv("IS_EMAIL_ACTIVE", "true")
    active = is_email_active()
    assert active is True


def test_is_email_active_not_set(monkeypatch):
    monkeypatch.delenv("IS_EMAIL_ACTIVE", raising=False)
    active = is_email_active()
    assert active is False
