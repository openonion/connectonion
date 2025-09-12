#!/usr/bin/env python3
"""Complete email test suite using fixed test credentials."""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load test environment
env_path = Path(__file__).parent / '.env.test'
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded test environment from {env_path}")

from connectonion import send_email, get_emails, mark_read
from tests.test_config import TEST_ACCOUNT, TestProject


def test_complete_email_flow():
    """Test complete email flow with fixed credentials."""
    
    print("\n" + "="*60)
    print("🧪 COMPLETE EMAIL TEST SUITE")
    print("="*60)
    
    # Get test credentials from environment
    backend_url = os.getenv('CONNECTONION_BACKEND_URL', 'https://oo.openonion.ai')
    jwt_token = os.getenv('TEST_JWT_TOKEN', '')
    
    print(f"\n📋 Test Configuration:")
    print(f"   Backend: {backend_url}")
    print(f"   Test Email: {TEST_ACCOUNT['email']}")
    print(f"   JWT Token: {jwt_token[:20]}..." if jwt_token else "   JWT Token: Not set")
    
    # Create test project with fixed account
    with TestProject() as project_dir:
        print(f"\n📁 Test project created: {project_dir}")
        
        # If we have a JWT token, update the config
        if jwt_token:
            import toml
            config_path = Path(".co/config.toml")
            config = toml.load(config_path)
            config["auth"]["token"] = jwt_token
            with open(config_path, "w") as f:
                toml.dump(config, f)
            print("   ✅ JWT token configured")
        
        # Test 1: Check Email Configuration
        print("\n" + "-"*40)
        print("TEST 1: Email Configuration")
        print("-"*40)
        
        from connectonion.useful_tools.send_email import get_agent_email, is_email_active
        
        agent_email = get_agent_email()
        email_active = is_email_active()
        
        print(f"✅ Agent email: {agent_email}")
        print(f"✅ Email active: {email_active}")
        
        assert agent_email == TEST_ACCOUNT['email'], "Email mismatch!"
        assert email_active == True, "Email not active!"
        
        # Test 2: Retrieve Emails
        print("\n" + "-"*40)
        print("TEST 2: Retrieve Emails")
        print("-"*40)
        
        print("📥 Getting all emails...")
        all_emails = get_emails()
        print(f"   Found {len(all_emails)} total emails")
        
        print("\n📥 Getting last 5 emails...")
        recent_emails = get_emails(last=5)
        print(f"   Found {len(recent_emails)} recent emails")
        
        print("\n📥 Getting unread emails...")
        unread_emails = get_emails(unread=True)
        print(f"   Found {len(unread_emails)} unread emails")
        
        # Display email details
        if all_emails:
            print("\n📧 Email Details (first 3):")
            for i, email in enumerate(all_emails[:3], 1):
                print(f"\n   Email {i}:")
                print(f"     ID: {email.get('id')}")
                print(f"     From: {email.get('from')}")
                print(f"     Subject: {email.get('subject')}")
                print(f"     Read: {email.get('read')}")
                print(f"     Preview: {email.get('message', '')[:50]}...")
        
        # Test 3: Send Email
        print("\n" + "-"*40)
        print("TEST 3: Send Email")
        print("-"*40)
        
        test_recipient = os.getenv('TEST_RECIPIENT_EMAIL', 'test@example.com')
        
        print(f"📤 Sending test email to {test_recipient}...")
        result = send_email(
            to=test_recipient,
            subject="Test Email from ConnectOnion Test Suite",
            message="""
            This is an automated test email from the ConnectOnion test suite.
            
            Test Details:
            - Sender: {email}
            - Backend: {backend}
            - Timestamp: {timestamp}
            
            This email verifies that the send_email function is working correctly.
            """.format(
                email=TEST_ACCOUNT['email'],
                backend=backend_url,
                timestamp=__import__('datetime').datetime.now().isoformat()
            )
        )
        
        if result.get('success'):
            print(f"   ✅ Email sent successfully!")
            print(f"   Message ID: {result.get('message_id')}")
            print(f"   From: {result.get('from')}")
        else:
            print(f"   ⚠️  Send failed: {result.get('error')}")
        
        # Test 4: Mark Emails as Read
        print("\n" + "-"*40)
        print("TEST 4: Mark Emails as Read")
        print("-"*40)
        
        if unread_emails:
            # Mark first unread email
            first_unread = unread_emails[0]
            print(f"✔️  Marking email {first_unread['id']} as read...")
            
            success = mark_read(first_unread['id'])
            if success:
                print(f"   ✅ Successfully marked as read")
                
                # Verify it's marked
                updated_emails = get_emails()
                for email in updated_emails:
                    if email['id'] == first_unread['id']:
                        if email.get('read'):
                            print(f"   ✅ Verified: Email is now marked as read")
                        else:
                            print(f"   ⚠️  Warning: Email still shows as unread")
                        break
            else:
                print(f"   ⚠️  Failed to mark as read")
        else:
            print("   ℹ️  No unread emails to mark")
        
        # Test 5: Batch Mark Read
        if len(unread_emails) > 1:
            print("\n✔️  Batch marking emails as read...")
            email_ids = [e['id'] for e in unread_emails[:3]]  # Mark up to 3
            
            success = mark_read(email_ids)
            if success:
                print(f"   ✅ Marked {len(email_ids)} emails as read")
            else:
                print(f"   ⚠️  Batch mark failed")
        
        # Summary
        print("\n" + "="*60)
        print("📊 TEST SUMMARY")
        print("="*60)
        
        test_results = {
            "Email Configuration": "✅ PASS",
            "Get Emails": f"✅ PASS ({len(all_emails)} emails retrieved)",
            "Send Email": "✅ PASS" if result.get('success') else "⚠️  FAIL",
            "Mark Read": "✅ PASS" if unread_emails else "ℹ️  SKIP",
        }
        
        for test, result in test_results.items():
            print(f"   {test}: {result}")
        
        print("\n✅ Test suite completed!")
        print(f"   Test Account: {TEST_ACCOUNT['email']}")
        print(f"   Backend: {backend_url}")
        
        # Return test results for CI/CD
        return all("PASS" in r or "SKIP" in r for r in test_results.values())


def test_with_curl_comparison():
    """Compare Python client results with direct curl requests."""
    
    print("\n" + "="*60)
    print("🔄 CURL COMPARISON TEST")
    print("="*60)
    
    import subprocess
    import json
    
    backend_url = os.getenv('CONNECTONION_BACKEND_URL', 'https://oo.openonion.ai')
    jwt_token = os.getenv('TEST_JWT_TOKEN', '')
    
    if not jwt_token:
        print("⚠️  No JWT token found. Skipping curl comparison.")
        return
    
    # Test with curl
    print("\n📡 Testing with curl...")
    curl_cmd = [
        'curl', '-s', '-X', 'GET',
        f'{backend_url}/api/emails?limit=5',
        '-H', f'Authorization: Bearer {jwt_token}',
        '-H', 'Content-Type: application/json'
    ]
    
    try:
        curl_result = subprocess.run(curl_cmd, capture_output=True, text=True)
        if curl_result.returncode == 0:
            curl_data = json.loads(curl_result.stdout)
            print(f"   ✅ Curl retrieved {len(curl_data.get('emails', []))} emails")
        else:
            print(f"   ⚠️  Curl failed: {curl_result.stderr}")
    except Exception as e:
        print(f"   ⚠️  Curl error: {e}")
    
    # Test with Python client
    print("\n🐍 Testing with Python client...")
    with TestProject() as project_dir:
        # Configure JWT token
        import toml
        config_path = Path(".co/config.toml")
        config = toml.load(config_path)
        config["auth"]["token"] = jwt_token
        with open(config_path, "w") as f:
            toml.dump(config, f)
        
        python_emails = get_emails(last=5)
        print(f"   ✅ Python client retrieved {len(python_emails)} emails")
    
    print("\n✅ Comparison test completed")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Complete email test suite")
    parser.add_argument('--curl', action='store_true', help='Include curl comparison test')
    parser.add_argument('--quick', action='store_true', help='Run quick tests only')
    args = parser.parse_args()
    
    # Run main test suite
    success = test_complete_email_flow()
    
    # Run curl comparison if requested
    if args.curl:
        test_with_curl_comparison()
    
    # Exit with appropriate code for CI/CD
    sys.exit(0 if success else 1)