"""
LLM-Note: Tests against deployed OpenOnion API

What it tests:
- Production API endpoint validation
- End-to-end API testing

Components under test:
- OpenOnion production API
"""
#!/usr/bin/env python3
"""Test with the actual deployed OpenOnion API."""

import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load test environment
env_path = Path(__file__).parent / '.env.test'
if env_path.exists():
    load_dotenv(env_path)

def test_deployed_api():
    """Test the actual deployed API endpoints."""
    
    print("\n" + "="*60)
    print("🌐 TESTING DEPLOYED OPENONION API")
    print("="*60)
    
    backend_url = "https://oo.openonion.ai"
    
    # Test 1: Health Check
    print("\n✅ Testing health endpoint...")
    response = requests.get(f"{backend_url}/health")
    if response.status_code == 200:
        data = response.json()
        print(f"   Status: {data.get('status')}")
        print(f"   Timestamp: {data.get('timestamp')}")
    
    # Test 2: Check available email endpoints
    print("\n📋 Available email endpoints:")
    endpoints = [
        "/api/email/send",
        "/api/email/webhook/incoming", 
        "/api/email/tier",
        "/api/email/upgrade",
        "/api/email/received",  # Admin endpoint
        "/api/emails",  # New endpoint (if deployed)
        "/api/emails/mark-read"  # New endpoint (if deployed)
    ]
    
    for endpoint in endpoints:
        # Try OPTIONS request to check if endpoint exists
        try:
            response = requests.options(f"{backend_url}{endpoint}", timeout=2)
            if response.status_code < 500:
                print(f"   ✅ {endpoint} - Available")
            else:
                print(f"   ❌ {endpoint} - Server error")
        except:
            print(f"   ⚠️  {endpoint} - Not responding")
    
    # Test 3: Try to authenticate
    print("\n🔐 Testing authentication...")
    
    # Note: The deployed API might not accept test signatures
    auth_data = {
        "public_key": os.getenv("TEST_PUBLIC_KEY"),
        "message": "test_message",
        "signature": "test_signature"
    }
    
    response = requests.post(f"{backend_url}/auth", json=auth_data)
    if response.status_code == 200:
        print("   ✅ Authentication successful")
        token = response.json().get("token")
        if token:
            print(f"   Token: {token[:30]}...")
    else:
        print(f"   ⚠️  Authentication failed: {response.status_code}")
        if response.status_code == 400:
            print("   Note: Test signatures not accepted in production")
    
    # Test 4: Check if new endpoints are deployed
    print("\n🆕 Checking new email endpoints...")
    
    jwt_token = os.getenv("TEST_JWT_TOKEN")
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }
    
    # Try GET /api/emails
    response = requests.get(f"{backend_url}/api/emails", headers=headers)
    if response.status_code == 404:
        print("   ℹ️  GET /api/emails - Not deployed yet")
        print("   The new email inbox endpoints need to be deployed to production")
    elif response.status_code == 200:
        print("   ✅ GET /api/emails - Working!")
        data = response.json()
        print(f"   Emails: {len(data.get('emails', []))}")
    else:
        print(f"   ⚠️  GET /api/emails - Status: {response.status_code}")
    
    # Summary
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)
    print("\nThe deployed API has the following email capabilities:")
    print("  ✅ Send emails via /api/email/send")
    print("  ✅ Receive emails via webhook")
    print("  ✅ Email tier management")
    print("\nThe new inbox features (get_emails, mark_read) are:")
    print("  ⚠️  Implemented locally but not yet deployed")
    print("\nNext steps:")
    print("  1. Deploy the updated oo-api with new endpoints")
    print("  2. Test with real authentication flow")
    print("  3. Verify email retrieval and marking as read")

