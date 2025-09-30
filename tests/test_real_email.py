#!/usr/bin/env python3
"""Test email functionality with live backend - uses environment variables safely."""

import os
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from connectonion import send_email, get_emails, mark_read
from tests.test_config import TestProject


def test_live_email():
    """Test with deployed backend using environment variables."""
    
    print("\n🧪 Live Email Test")
    print("=" * 50)
    
    # Use environment variables - NEVER hardcode credentials!
    backend_url = os.getenv("CONNECTONION_BACKEND_URL", "https://oo.openonion.ai")
    
    # Check if we have required environment variables
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Please set OPENAI_API_KEY environment variable")
        print("   export OPENAI_API_KEY=your-key-here")
        return
    
    print(f"🌐 Using backend: {backend_url}")
    
    with TestProject() as project_dir:
        print(f"📁 Test project: {project_dir}")
        
        # The test project already has the test account configured
        # Now test the functionality
        
        # Test 1: Check current inbox
        print("\n📥 Checking inbox...")
        emails = get_emails()
        
        if emails:
            print(f"✅ Found {len(emails)} emails")
            for i, email in enumerate(emails[:3], 1):
                print(f"\n   Email {i}:")
                print(f"     From: {email.get('from')}")
                print(f"     Subject: {email.get('subject')}")
                print(f"     Read: {email.get('read')}")
        else:
            print("📭 No emails in inbox")
        
        # Test 2: Send a test email
        print("\n📤 Sending test email...")
        result = send_email(
            to="test@example.com",
            subject="Test from ConnectOnion",
            message="This is a test email sent via the ConnectOnion API"
        )
        
        if result.get("success"):
            print(f"✅ Email sent successfully!")
            print(f"   Message ID: {result.get('message_id')}")
            print(f"   From: {result.get('from')}")
        else:
            print(f"⚠️  Send failed: {result.get('error')}")
        
        # Test 3: Mark emails as read
        if emails and len(emails) > 0:
            unread = [e for e in emails if not e.get('read')]
            if unread:
                print(f"\n✔️  Marking {len(unread)} emails as read...")
                for email in unread[:3]:  # Mark up to 3
                    success = mark_read(email['id'])
                    if success:
                        print(f"   ✅ Marked {email['id']} as read")
                    else:
                        print(f"   ⚠️  Failed to mark {email['id']}")
        
        print("\n" + "=" * 50)
        print("✅ Test completed")
        print("\n⚠️  Remember: NEVER commit API keys to version control!")


if __name__ == "__main__":
    # Safety check
    if len(sys.argv) > 1 and sys.argv[1] == "--confirm":
        test_live_email()
    else:
        print("⚠️  This test connects to the live backend.")
        print("   Run with --confirm flag to proceed:")
        print("   python test_email_live.py --confirm")
        print("\n📝 Required environment variables:")
        print("   - OPENAI_API_KEY")
        print("   - CONNECTONION_BACKEND_URL (optional)")
        print("\n🔒 Security: Use environment variables, never hardcode keys!")