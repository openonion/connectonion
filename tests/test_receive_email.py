#!/usr/bin/env python
"""Test email receiving functionality"""

import os
import sys
import json
from pathlib import Path

# Add connectonion to path
sys.path.insert(0, str(Path(__file__).parent / "connectonion"))

from connectonion.useful_tools.get_emails import get_emails, mark_read

def test_receive_emails():
    """Test receiving emails"""
    print("Testing email receiving functionality...")
    print("-" * 50)

    # First, check if we're in a ConnectOnion project
    co_dir = Path(".co")
    if not co_dir.exists():
        print("❌ Not in a ConnectOnion project. Run 'co init' first.")
        return False

    # Check config
    config_path = co_dir / "config.toml"
    if config_path.exists():
        with open(config_path) as f:
            config_content = f.read()
            print("📧 Agent configuration:")
            for line in config_content.split('\n'):
                if 'email' in line.lower():
                    print(f"  {line.strip()}")
    print("-" * 50)

    # Try to get emails
    try:
        print("\n📥 Fetching last 5 emails...")
        emails = get_emails(last=5, unread=False)

        if not emails:
            print("📭 No emails received yet.")
            print("\nTo test receiving:")
            print("1. Send an email to your agent's address (shown above)")
            print("2. Wait a few seconds")
            print("3. Run this test again")
            return True

        print(f"✅ Found {len(emails)} email(s)!")
        print("-" * 50)

        # Display emails
        for i, email in enumerate(emails, 1):
            print(f"\n📧 Email {i}:")
            print(f"  From: {email.get('from', 'Unknown')}")
            print(f"  Subject: {email.get('subject', 'No subject')}")
            print(f"  Message: {email.get('message', 'No message')[:100]}...")
            print(f"  Timestamp: {email.get('timestamp', 'Unknown')}")
            print(f"  Read: {'✓' if email.get('read') else '✗'}")
            print(f"  ID: {email.get('id', 'Unknown')}")

        # Test marking as read
        if emails and not emails[0].get('read'):
            email_id = emails[0].get('id')
            if email_id:
                print(f"\n📝 Testing mark as read for email ID: {email_id}")
                success = mark_read(email_id)
                if success:
                    print("✅ Successfully marked as read!")
                else:
                    print("⚠️ Failed to mark as read")

        return True

    except Exception as e:
        print(f"❌ Error fetching emails: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_unread_only():
    """Test fetching only unread emails"""
    print("\n" + "=" * 50)
    print("Testing unread emails only...")
    print("-" * 50)

    try:
        unread_emails = get_emails(last=10, unread=True)
        if unread_emails:
            print(f"📬 Found {len(unread_emails)} unread email(s)")
            for email in unread_emails:
                print(f"  - {email.get('subject', 'No subject')} from {email.get('from', 'Unknown')}")
        else:
            print("✅ No unread emails")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("🔧 ConnectOnion Email Receiving Test")
    print("=" * 50)

    # Test basic receiving
    success1 = test_receive_emails()

    # Test unread filter
    success2 = test_unread_only()

    print("\n" + "=" * 50)
    if success1 and success2:
        print("✅ All email receiving tests passed!")
    else:
        print("⚠️ Some tests failed. Check the output above.")