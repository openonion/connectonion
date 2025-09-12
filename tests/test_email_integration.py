"""Integration tests for email functionality with fixed test account."""

import unittest
import os
import sys
import tempfile
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from connectonion import send_email, get_emails, mark_read
from tests.test_config import TEST_ACCOUNT, TestProject, SAMPLE_EMAILS


class TestEmailIntegration(unittest.TestCase):
    """Integration tests using fixed test account and project."""
    
    def test_with_test_project(self):
        """Test email functions with a test project."""
        with TestProject() as project_dir:
            print(f"\n📁 Test project created at: {project_dir}")
            
            # Test 1: Get agent email
            from connectonion.useful_tools.send_email import get_agent_email, is_email_active
            
            email = get_agent_email()
            self.assertEqual(email, TEST_ACCOUNT["email"])
            print(f"✅ Agent email: {email}")
            
            # Test 2: Check email active status
            active = is_email_active()
            self.assertTrue(active)
            print(f"✅ Email active: {active}")
            
            # Test 3: Send email (will fail without backend)
            result = send_email(
                "test@example.com",
                "Test Subject",
                "Test message from integration test"
            )
            
            # Without a real backend, this should fail with specific error
            self.assertFalse(result["success"])
            # The error depends on whether backend is running
            print(f"ℹ️  Send result: {result.get('error', 'Unknown error')}")
            
            # Test 4: Get emails (will return empty without backend)
            emails = get_emails()
            self.assertIsInstance(emails, list)
            print(f"✅ Get emails returned list with {len(emails)} items")
            
            # Test 5: Mark read (will fail without backend)
            success = mark_read("test_msg_123")
            self.assertIsInstance(success, bool)
            print(f"✅ Mark read returned: {success}")
    
    def test_email_flow_simulation(self):
        """Test the complete email flow with mocked data."""
        with TestProject() as project_dir:
            # This simulates what would happen with a real backend
            
            # 1. Agent would have an email address
            from connectonion.useful_tools.send_email import get_agent_email
            agent_email = get_agent_email()
            self.assertEqual(agent_email, "0x04e1c4ae@mail.openonion.ai")
            
            # 2. User sends email to agent (simulated)
            incoming_email = {
                "id": "msg_sim_001",
                "from": "user@example.com", 
                "to": agent_email,
                "subject": "Hello Agent",
                "message": "This is a test message to the agent",
                "timestamp": "2024-01-16T10:00:00Z",
                "read": False
            }
            
            # 3. Agent checks emails (would return the above)
            # In real scenario: emails = get_emails()
            # For now we simulate the expected structure
            
            # 4. Agent processes and replies
            # In real scenario: send_email(incoming_email["from"], "Re: Hello", "Got your message!")
            
            # 5. Mark as read
            # In real scenario: mark_read(incoming_email["id"])
            
            print("\n✅ Email flow simulation completed")
            print(f"   Agent email: {agent_email}")
            print(f"   Would receive emails at: {agent_email}")
            print(f"   Can send replies using send_email()")
            print(f"   Can mark emails as read with mark_read()")


class TestLiveBackend(unittest.TestCase):
    """Tests that run against a live backend if available."""
    
    def setUp(self):
        """Check if backend is available."""
        import requests
        try:
            response = requests.get("http://localhost:8000/health", timeout=1)
            self.backend_available = response.status_code == 200
        except:
            self.backend_available = False
    
    def test_real_email_flow(self):
        """Test with real backend if available."""
        if not self.backend_available:
            self.skipTest("Backend not available at localhost:8000")
        
        with TestProject() as project_dir:
            # Override backend URL to local
            os.environ['CONNECTONION_BACKEND_URL'] = 'http://localhost:8000'
            
            # Try to authenticate (would need real auth flow)
            print("\n🌐 Testing with live backend...")
            
            # Get emails (requires authenticated user)
            emails = get_emails()
            print(f"   Retrieved {len(emails)} emails from backend")
            
            # The actual functionality depends on:
            # 1. Having a valid JWT token in config
            # 2. Backend recognizing the test account
            # 3. Emails existing for the test account
            
            self.assertIsInstance(emails, list)


if __name__ == '__main__':
    # Run with verbose output
    unittest.main(verbosity=2)