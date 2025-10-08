"""Tests for email functionality in ConnectOnion."""

import unittest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import tempfile
import toml
import json
import os
import sys

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
    
    @patch('pathlib.Path.exists')
    @patch('toml.load')
    @patch('requests.post')
    def test_send_email_success(self, mock_post, mock_toml_load, mock_exists):
        """Test successful email sending."""
        # Setup mocks
        mock_exists.return_value = True
        mock_toml_load.return_value = self.test_config
        
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
    
    @patch('pathlib.Path.exists')
    @patch('toml.load')
    def test_send_email_not_activated(self, mock_toml_load, mock_exists):
        """Test email sending when not activated."""
        # Setup mocks
        mock_exists.return_value = True
        config = self.test_config.copy()
        config["agent"]["email_active"] = False
        mock_toml_load.return_value = config
        
        # Test
        result = send_email("test@example.com", "Test", "Message")
        
        # Assertions
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Email not activated. Run 'co auth' to activate.")
    
    @patch('pathlib.Path.exists')
    def test_send_email_no_project(self, mock_exists):
        """Test email sending outside ConnectOnion project."""
        mock_exists.return_value = False
        
        result = send_email("test@example.com", "Test", "Message")
        
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Not in a ConnectOnion project. Run 'co init' first.")
    
    @patch('pathlib.Path.exists')
    @patch('toml.load')
    def test_invalid_email_address(self, mock_toml_load, mock_exists):
        """Test with invalid email address."""
        mock_exists.return_value = True
        mock_toml_load.return_value = self.test_config
        
        # Test invalid email
        result = send_email("not-an-email", "Test", "Message")
        
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Invalid email address: not-an-email")
    
    @patch('pathlib.Path.exists')
    @patch('toml.load')
    @patch('requests.post')
    def test_send_email_rate_limit(self, mock_post, mock_toml_load, mock_exists):
        """Test rate limit handling."""
        mock_exists.return_value = True
        mock_toml_load.return_value = self.test_config
        
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
    
    @patch('pathlib.Path.exists')
    @patch('toml.load')
    @patch('requests.get')
    def test_get_emails_success(self, mock_get, mock_toml_load, mock_exists):
        """Test successful email retrieval."""
        # Setup mocks
        mock_exists.return_value = True
        mock_toml_load.return_value = self.test_config
        
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
    
    @patch('pathlib.Path.exists')
    @patch('toml.load')
    @patch('requests.get')
    def test_get_emails_unread_only(self, mock_get, mock_toml_load, mock_exists):
        """Test getting only unread emails."""
        mock_exists.return_value = True
        mock_toml_load.return_value = self.test_config
        
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
    
    @patch('pathlib.Path.exists')
    def test_get_emails_no_project(self, mock_exists):
        """Test getting emails outside project."""
        mock_exists.return_value = False
        
        emails = get_emails()
        
        self.assertEqual(emails, [])
    
    @patch('pathlib.Path.exists')
    @patch('toml.load')
    def test_get_emails_not_activated(self, mock_toml_load, mock_exists):
        """Test when email not activated."""
        mock_exists.return_value = True
        config = self.test_config.copy()
        config["agent"]["email_active"] = False
        mock_toml_load.return_value = config
        
        emails = get_emails()
        
        self.assertEqual(emails, [])
    
    @patch('pathlib.Path.exists')
    @patch('toml.load')
    @patch('requests.get')
    def test_get_emails_api_error(self, mock_get, mock_toml_load, mock_exists):
        """Test handling API errors."""
        mock_exists.return_value = True
        mock_toml_load.return_value = self.test_config
        
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response
        
        emails = get_emails()
        
        self.assertEqual(emails, [])


class TestMarkRead(unittest.TestCase):
    """Test the mark_read function."""
    
    def setUp(self):
        """Set up test configuration."""
        # Use fixed test account from test_config
        self.test_config = TEST_CONFIG_TOML
    
    @patch('pathlib.Path.exists')
    @patch('toml.load')
    @patch('requests.post')
    def test_mark_read_single(self, mock_post, mock_toml_load, mock_exists):
        """Test marking single email as read."""
        mock_exists.return_value = True
        mock_toml_load.return_value = self.test_config
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        result = mark_read("msg_123")
        
        self.assertTrue(result)
        
        # Verify API call
        call_args = mock_post.call_args
        self.assertEqual(call_args[1]["json"]["email_ids"], ["msg_123"])
    
    @patch('pathlib.Path.exists')
    @patch('toml.load')
    @patch('requests.post')
    def test_mark_read_multiple(self, mock_post, mock_toml_load, mock_exists):
        """Test marking multiple emails as read."""
        mock_exists.return_value = True
        mock_toml_load.return_value = self.test_config
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        result = mark_read(["msg_1", "msg_2", "msg_3"])
        
        self.assertTrue(result)
        
        # Verify API call
        call_args = mock_post.call_args
        self.assertEqual(call_args[1]["json"]["email_ids"], ["msg_1", "msg_2", "msg_3"])
    
    @patch('pathlib.Path.exists')
    def test_mark_read_no_project(self, mock_exists):
        """Test marking as read outside project."""
        mock_exists.return_value = False
        
        result = mark_read("msg_123")
        
        self.assertFalse(result)
    
    def test_mark_read_empty_list(self):
        """Test with empty email list."""
        result = mark_read([])
        
        self.assertFalse(result)
    
    @patch('pathlib.Path.exists')
    @patch('toml.load')
    @patch('requests.post')
    def test_mark_read_api_error(self, mock_post, mock_toml_load, mock_exists):
        """Test handling API errors."""
        mock_exists.return_value = True
        mock_toml_load.return_value = self.test_config
        
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_post.return_value = mock_response
        
        result = mark_read("msg_123")
        
        self.assertFalse(result)


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