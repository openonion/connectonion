"""Tests for email functionality in ConnectOnion."""

import unittest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import tempfile
import toml
import json
import os
import sys
import requests

from connectonion.useful_tools.send_email import send_email, get_agent_email, is_email_active
from connectonion.useful_tools.get_emails import get_emails, mark_read, mark_unread

# Import test configuration
from tests.test_config import TEST_ACCOUNT, TEST_JWT_TOKEN, TEST_CONFIG_TOML, SAMPLE_EMAILS, TestProject


class TestSendEmail(unittest.TestCase):
    """Test the send_email function."""
    
    def setUp(self):
        """Set up test configuration."""
        # Use fixed test account from test_config
        self.test_config = TEST_CONFIG_TOML
    
    @patch.dict('os.environ', {'OPENONION_API_KEY': TEST_JWT_TOKEN, 'AGENT_EMAIL': TEST_ACCOUNT["email"]})
    @patch('requests.post')
    def test_send_email_success(self, mock_post):
        """Test successful email sending."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message_id": "msg_123"}
        mock_post.return_value = mock_response

        # Test
        result = send_email("test@example.com", "Test Subject", "Test Message")

        # Assertions
        self.assertTrue(result["success"])
        self.assertEqual(result["message_id"], "msg_123")
        self.assertEqual(result["from"], TEST_ACCOUNT["email"])

        # Verify API call
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertIn("Authorization", call_args[1]["headers"])
        self.assertEqual(call_args[1]["headers"]["Authorization"], f"Bearer {TEST_JWT_TOKEN}")
    
    @patch.dict('os.environ', {'OPENONION_API_KEY': 'test-token-123', 'AGENT_EMAIL': 'test@openonion.ai'})
    @patch('requests.post')
    def test_send_email_not_activated(self, mock_post):
        """Test email sending when backend returns not activated error."""
        # Mock API response for not activated
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"detail": "Email not activated. Run 'co auth' to activate."}
        mock_post.return_value = mock_response

        # Test
        result = send_email("test@example.com", "Test", "Message")

        # Assertions
        self.assertFalse(result["success"])
        self.assertIn("Email not activated", result["error"])
    
    def test_send_email_no_project(self):
        """Test email sending when missing OPENONION_API_KEY."""
        # Without API key in env, should return error
        result = send_email("test@example.com", "Test", "Message")

        self.assertFalse(result["success"])
        # Either no .env file or OPENONION_API_KEY not in it
        self.assertTrue("OPENONION_API_KEY" in result["error"] or "No .env file" in result["error"])
    
    @patch.dict('os.environ', {'OPENONION_API_KEY': 'test-token-123', 'AGENT_EMAIL': 'test@openonion.ai'})
    def test_invalid_email_address(self):
        """Test with invalid email address."""
        # Test invalid email
        result = send_email("not-an-email", "Test", "Message")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Invalid email address: not-an-email")
    
    @patch.dict('os.environ', {'OPENONION_API_KEY': 'test-token-123', 'AGENT_EMAIL': 'test@openonion.ai'})
    @patch('requests.post')
    def test_send_email_rate_limit(self, mock_post):
        """Test rate limit handling."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_post.return_value = mock_response

        result = send_email("test@example.com", "Test", "Message")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Rate limit exceeded")


class TestGetEmails(unittest.TestCase):
    """Test the get_emails function."""
    
    def setUp(self):
        """Set up test configuration."""
        # Use fixed test account from test_config
        self.test_config = TEST_CONFIG_TOML
        
        # Convert SAMPLE_EMAILS to backend format
        self.sample_emails = [
            {
                "id": email["id"],
                "from_email": email["from"],
                "subject": email["subject"],
                "text_body": email["message"],
                "received_at": email["timestamp"],
                "is_read": email["read"]
            }
            for email in SAMPLE_EMAILS[:2]
        ]
    
    @patch.dict('os.environ', {'OPENONION_API_KEY': TEST_JWT_TOKEN})
    @patch('requests.get')
    def test_get_emails_success(self, mock_get):
        """Test successful email retrieval."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"emails": self.sample_emails}
        mock_get.return_value = mock_response

        # Test
        emails = get_emails(last=5)

        # Assertions
        self.assertEqual(len(emails), 2)
        self.assertEqual(emails[0]["id"], "msg_test_001")
        self.assertEqual(emails[0]["from"], "alice@example.com")
        self.assertEqual(emails[0]["subject"], "Test Email 1")
        self.assertEqual(emails[0]["message"], "This is test email number 1")
        self.assertEqual(emails[0]["read"], False)

        # Verify API call
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        self.assertEqual(call_args[1]["params"]["limit"], 5)
        self.assertFalse(call_args[1]["params"]["unread_only"])
    
    @patch.dict('os.environ', {'OPENONION_API_KEY': TEST_JWT_TOKEN})
    @patch('requests.get')
    def test_get_emails_unread_only(self, mock_get):
        """Test getting only unread emails."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"emails": [self.sample_emails[0]]}
        mock_get.return_value = mock_response

        emails = get_emails(unread=True)

        self.assertEqual(len(emails), 1)
        self.assertFalse(emails[0]["read"])

        # Verify unread_only parameter
        call_args = mock_get.call_args
        self.assertTrue(call_args[1]["params"]["unread_only"])
    
    def test_get_emails_no_project(self):
        """Test getting emails without OPENONION_API_KEY."""
        # Without environment variables, should raise ValueError
        with self.assertRaises(ValueError) as context:
            get_emails()

        self.assertIn("OPENONION_API_KEY not found", str(context.exception))

    @patch.dict('os.environ', {'OPENONION_API_KEY': TEST_JWT_TOKEN})
    @patch('requests.get')
    def test_get_emails_api_error(self, mock_get):
        """Test handling API errors."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        mock_get.return_value = mock_response

        # Should raise HTTPError when API fails
        with self.assertRaises(requests.HTTPError):
            get_emails()


class TestMarkRead(unittest.TestCase):
    """Test the mark_read function."""
    
    def setUp(self):
        """Set up test configuration."""
        # Use fixed test account from test_config
        self.test_config = TEST_CONFIG_TOML
    
    @patch.dict('os.environ', {'OPENONION_API_KEY': TEST_JWT_TOKEN})
    @patch('requests.post')
    def test_mark_read_single(self, mock_post):
        """Test marking single email as read."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = mark_read("msg_123")

        self.assertTrue(result)
    
    @patch.dict('os.environ', {'OPENONION_API_KEY': TEST_JWT_TOKEN})
    @patch('requests.post')
    def test_mark_read_multiple(self, mock_post):
        """Test marking multiple emails as read."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = mark_read(["msg_1", "msg_2", "msg_3"])

        self.assertTrue(result)
    
    def test_mark_read_no_project(self):
        """Test marking as read without OPENONION_API_KEY."""
        # Without environment variables, should raise ValueError
        with self.assertRaises(ValueError) as context:
            mark_read("msg_123")

        self.assertIn("OPENONION_API_KEY not found", str(context.exception))
    
    def test_mark_read_empty_list(self):
        """Test with empty email list."""
        # Empty list should raise ValueError
        with self.assertRaises(ValueError) as context:
            mark_read([])

        self.assertIn("No email IDs provided", str(context.exception))
    
    @patch.dict('os.environ', {'OPENONION_API_KEY': TEST_JWT_TOKEN})
    @patch('requests.post')
    def test_mark_read_api_error(self, mock_post):
        """Test handling API errors."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_post.return_value = mock_response

        # Should raise HTTPError when API fails
        with self.assertRaises(requests.HTTPError):
            mark_read("msg_123")


class TestHelperFunctions(unittest.TestCase):
    """Test helper functions."""
    
    @patch('pathlib.Path.exists')
    @patch('toml.load')
    def test_get_agent_email(self, mock_toml_load, mock_exists):
        """Test getting agent email."""
        mock_exists.return_value = True
        mock_toml_load.return_value = TEST_CONFIG_TOML
        
        email = get_agent_email()
        
        self.assertEqual(email, TEST_ACCOUNT["email"])
    
    @patch('pathlib.Path.exists')
    @patch('toml.load')
    def test_get_agent_email_generated(self, mock_toml_load, mock_exists):
        """Test generating email from address."""
        mock_exists.return_value = True
        mock_toml_load.return_value = {
            "agent": {
                "address": "0xabcdef1234567890"
            }
        }
        
        email = get_agent_email()
        
        self.assertEqual(email, "0xabcdef12@mail.openonion.ai")
    
    @patch('pathlib.Path.exists')
    @patch('toml.load')
    def test_is_email_active(self, mock_toml_load, mock_exists):
        """Test checking email activation."""
        mock_exists.return_value = True
        mock_toml_load.return_value = {
            "agent": {
                "email_active": True
            }
        }
        
        active = is_email_active()
        
        self.assertTrue(active)
    
    @patch('pathlib.Path.exists')
    def test_is_email_active_no_project(self, mock_exists):
        """Test email active check outside project."""
        mock_exists.return_value = False
        
        active = is_email_active()
        
        self.assertFalse(active)


if __name__ == '__main__':
    unittest.main()