"""Tests for email functionality in ConnectOnion (pytest style)."""

from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import tempfile
import toml
import json
import os
import sys
import requests
import pytest

from connectonion.useful_tools.send_email import send_email, get_agent_email, is_email_active
from connectonion.useful_tools.get_emails import get_emails, mark_read, mark_unread

# Import test configuration
from tests.utils.config_helpers import (
    TEST_ACCOUNT,
    TEST_JWT_TOKEN,
    TEST_CONFIG_TOML,
    SAMPLE_EMAILS,
    TestProject,
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

    result = send_email("test@example.com", "Test Subject", "Test Message")

    assert result["success"] is True
    assert result["message_id"] == "msg_123"
    assert result["from"] == TEST_ACCOUNT["email"]

    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "Authorization" in call_args[1]["headers"]
    assert call_args[1]["headers"]["Authorization"] == f"Bearer {TEST_JWT_TOKEN}"


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


def test_get_emails_no_project():
    """Test getting emails without OPENONION_API_KEY."""
    with pytest.raises(ValueError) as exc:
        get_emails()
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

@patch('pathlib.Path.exists')
@patch('toml.load')
def test_get_agent_email(mock_toml_load, mock_exists):
    mock_exists.return_value = True
    mock_toml_load.return_value = TEST_CONFIG_TOML
    email = get_agent_email()
    assert email == TEST_ACCOUNT["email"]


@patch('pathlib.Path.exists')
@patch('toml.load')
def test_get_agent_email_generated(mock_toml_load, mock_exists):
    mock_exists.return_value = True
    mock_toml_load.return_value = {"agent": {"address": "0xabcdef1234567890"}}
    email = get_agent_email()
    assert email == "0xabcdef12@mail.openonion.ai"


@patch('pathlib.Path.exists')
@patch('toml.load')
def test_is_email_active(mock_toml_load, mock_exists):
    mock_exists.return_value = True
    mock_toml_load.return_value = {"agent": {"email_active": True}}
    active = is_email_active()
    assert active is True


@patch('pathlib.Path.exists')
def test_is_email_active_no_project(mock_exists):
    mock_exists.return_value = False
    active = is_email_active()
    assert active is False
