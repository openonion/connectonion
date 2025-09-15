#!/usr/bin/env python3
"""
Final test to send email to yingxiaohao@outlook.com
"""

import requests

def send_test_email():
    """Send test email directly to the API."""

    # Use the test endpoint that doesn't require auth
    response = requests.get("https://oo.openonion.ai/api/test/email")

    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            print("✅ Email sent successfully to yingxiaohao@outlook.com!")
            print(f"   Email ID: {data.get('email_id')}")
            print(f"   Details: {data.get('details')}")
            return True
        else:
            print(f"❌ Failed: {data.get('error')}")
            return False
    else:
        print(f"❌ HTTP Error: {response.status_code}")
        return False

if __name__ == "__main__":
    print("🚀 Sending test email to yingxiaohao@outlook.com...")
    send_test_email()