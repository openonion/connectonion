#!/usr/bin/env python3
"""
Test the email agent with mocked responses.
Since the backend Resend API is not fully configured, 
this uses mock responses to demonstrate the agent works.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from connectonion import Agent

# Mock email functions for testing
def mock_send_email(to: str, subject: str, message: str) -> dict:
    """Mock email sending for testing."""
    print(f"\n📧 MOCK EMAIL SENT:")
    print(f"   To: {to}")
    print(f"   Subject: {subject}")
    print(f"   Message: {message[:100]}...")
    return {
        "success": True,
        "message_id": "mock_msg_123",
        "from": "0x6fdb2d9e@mail.openonion.ai"
    }

def mock_get_emails(last: int = 10, unread: bool = False) -> list:
    """Mock getting emails for testing."""
    if unread:
        return [
            {
                "id": "msg_1",
                "from": "boss@company.com",
                "subject": "Urgent: Meeting Tomorrow",
                "message": "We need to discuss the Q4 planning. Please confirm your attendance.",
                "timestamp": "2025-09-13T10:00:00Z",
                "read": False
            },
            {
                "id": "msg_2",
                "from": "support@service.com",
                "subject": "Issue with login",
                "message": "I'm having trouble accessing my account. Can you help?",
                "timestamp": "2025-09-13T09:30:00Z",
                "read": False
            }
        ]
    return [
        {
            "id": "msg_3",
            "from": "newsletter@example.com",
            "subject": "Weekly Newsletter",
            "message": "Here's what happened this week...",
            "timestamp": "2025-09-13T08:00:00Z",
            "read": True
        }
    ]

def mock_mark_read(email_id: str) -> bool:
    """Mock marking email as read."""
    print(f"   ✓ Marked {email_id} as read")
    return True

# Import the EmailManager from agent
from agent import EmailManager

# Create agent with mocked tools
def test_email_agent():
    """Test the email agent with mocked functions."""
    print("🧪 Testing Email Agent with Mocked Functions")
    print("=" * 50)
    
    # Create email manager
    manager = EmailManager()
    
    # Create agent with mock tools
    agent = Agent(
        name="test_email_agent",
        tools=[
            manager,
            mock_send_email,
            mock_get_emails,
            mock_mark_read
        ],
        system_prompt="You are an email assistant. Use the available tools to manage emails."
    )
    
    # Test tasks
    test_scenarios = [
        "Check my inbox",
        "Send an email to yingxiaohao@outlook.com saying 'The ConnectOnion email agent is working perfectly!'",
        "Reply to the urgent email from boss@company.com",
        "Show me email statistics"
    ]
    
    for scenario in test_scenarios:
        print(f"\n📝 Task: {scenario}")
        print("-" * 40)
        response = agent.input(scenario)
        print(f"Agent Response: {response}")
    
    print("\n" + "=" * 50)
    print("✅ Email agent test completed successfully!")

if __name__ == "__main__":
    test_email_agent()