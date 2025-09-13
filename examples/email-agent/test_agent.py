#!/usr/bin/env python3
"""
Test the Email Agent functionality.

This test file will:
1. Test sending emails to a configured address
2. Test checking inbox
3. Test the AI agent's ability to handle email tasks
"""

import os
import sys
from dotenv import load_dotenv

# Ensure the repository root is on sys.path so `import connectonion` works
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from connectonion import Agent, send_email, get_emails, mark_read

# Load environment variables
load_dotenv()

# Get test email address from environment
TEST_EMAIL = os.getenv('TEST_TO_EMAIL_ADDR', 'yingxiaohao@outlook.com')


def test_direct_email_functions():
    """Test the direct email functions."""
    print("=" * 50)
    print("Testing Direct Email Functions")
    print("=" * 50)
    
    # Test 1: Send a simple email
    print(f"\n1. Sending test email to {TEST_EMAIL}...")
    result = send_email(
        TEST_EMAIL,
        "Test Email from ConnectOnion",
        "This is a test email sent from the ConnectOnion email agent example."
    )
    print(f"   Result: {result}")
    
    # Test 2: Check inbox
    print("\n2. Checking inbox (last 5 emails)...")
    emails = get_emails(last=5)
    print(f"   Found {len(emails)} emails")
    for i, email in enumerate(emails, 1):
        print(f"   [{i}] From: {email['from']}")
        print(f"       Subject: {email['subject']}")
    
    # Test 3: Check unread emails
    print("\n3. Checking unread emails...")
    unread = get_emails(unread=True)
    print(f"   Found {len(unread)} unread emails")
    
    return True


def test_email_manager_class():
    """Test the EmailManager class methods."""
    print("\n" + "=" * 50)
    print("Testing EmailManager Class")
    print("=" * 50)
    
    from agent import EmailManager
    
    manager = EmailManager()
    
    # Test 1: Check inbox
    print("\n1. Testing check_inbox()...")
    result = manager.check_inbox()
    print(result[:200] + "..." if len(result) > 200 else result)
    
    # Test 2: Send new email
    print(f"\n2. Testing send_new_email() to {TEST_EMAIL}...")
    result = manager.send_new_email(
        TEST_EMAIL,
        "Test from EmailManager",
        "This email was sent using the EmailManager class."
    )
    print(f"   {result}")
    
    # Test 3: Get statistics
    print("\n3. Testing get_statistics()...")
    stats = manager.get_statistics()
    print(stats)
    
    return True


def test_ai_agent():
    """Test the AI agent with email capabilities."""
    print("\n" + "=" * 50)
    print("Testing AI Agent with Email Tools")
    print("=" * 50)
    
    from agent import EmailManager
    
    # Create email manager
    email_manager = EmailManager()
    
    # Create agent
    agent = Agent(
        name="email_test_agent",
        tools=[email_manager],
        system_prompt="You are a helpful email assistant for testing."
    )
    
    # Test tasks
    test_tasks = [
        f"Send a test email to {TEST_EMAIL} saying 'Hello from the ConnectOnion AI agent test!'",
        "Check my inbox and tell me how many emails I have",
        "Show me email statistics"
    ]
    
    for i, task in enumerate(test_tasks, 1):
        print(f"\n{i}. Task: {task}")
        response = agent.input(task)
        print(f"   Response: {response[:200]}..." if len(response) > 200 else f"   Response: {response}")
    
    return True


def main():
    """Run all tests."""
    print("🧪 Email Agent Test Suite")
    print(f"📧 Test email address: {TEST_EMAIL}")
    print("=" * 50)
    
    # Create .env file if it doesn't exist
    if not os.path.exists('.env'):
        print("\n📝 Creating .env file with default test email...")
        with open('.env', 'w') as f:
            f.write(f"TEST_TO_EMAIL_ADDR={TEST_EMAIL}\n")
        print(f"   Created .env with TEST_TO_EMAIL_ADDR={TEST_EMAIL}")
    
    try:
        # Run tests
        print("\n🚀 Starting tests...\n")
        
        # Test 1: Direct functions
        if test_direct_email_functions():
            print("\n✅ Direct email functions test passed")
        
        # Test 2: EmailManager class
        if test_email_manager_class():
            print("\n✅ EmailManager class test passed")
        
        # Test 3: AI Agent
        if test_ai_agent():
            print("\n✅ AI Agent test passed")
        
        print("\n" + "=" * 50)
        print("🎉 All tests completed successfully!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())