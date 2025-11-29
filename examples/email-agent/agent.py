#!/usr/bin/env python3
"""
Email Manager Agent - AI-powered email assistant with Gmail integration.

Features:
- ReAct pattern: Plan before acting, reflect after each action, evaluate on complete
- Gmail approval: User confirms before sending emails
- CRM sync: Automatically update contact records after sending

Usage:
    python examples/email-agent/agent.py
"""

import os
import sys
from pathlib import Path

# Ensure the repository root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from connectonion import Agent, Gmail
from connectonion.useful_plugins import re_act, gmail_plugin


def main():
    """Create and run the email assistant agent."""

    # Create Gmail instance with all email capabilities
    gmail = Gmail()

    # Create AI agent with:
    # - Gmail tools (send, reply, get_emails, search, etc.)
    # - re_act plugin (plan → reflect → evaluate)
    # - gmail_plugin (approval before send, CRM sync after send)
    agent = Agent(
        name="email_assistant",
        tools=[gmail],
        system_prompt="prompts/email_assistant.md",
        model="co/o4-mini",
        plugins=[re_act, gmail_plugin]
    )

    print("🤖 Email Assistant (AI-Powered)")
    print("=" * 50)
    print("\nPowered by:")
    print("  💭 ReAct - Plans before acting, reflects after")
    print("  ✅ Gmail Approval - Confirms before sending")
    print("  📊 CRM Sync - Updates contacts automatically")

    print("\nI can help you:")
    print("  📧 Check your emails")
    print("  🔍 Search for specific emails")
    print("  ✉️ Send new emails")
    print("  💬 Reply to emails")
    print("  ✓ Mark emails as read")
    print("  📋 Manage contacts")

    print("\n💡 Just tell me what you need:")
    print('  "Check my unread emails"')
    print('  "Find emails from John about the project"')
    print('  "Send an email to alice@example.com saying thanks"')
    print('  "Reply to the last email"')
    print("\nType 'quit' to exit\n")

    # Interactive loop
    while True:
        try:
            user_input = input("\n💌 What would you like to do? ")

            if user_input.lower() in ['quit', 'exit', 'bye', 'q']:
                print("\n👋 Goodbye!")
                break

            if not user_input.strip():
                continue

            # Let the AI agent handle the request
            response = agent.input(user_input)
            print(f"\n{response}")

        except KeyboardInterrupt:
            print("\n\n👋 Email assistant stopped.")
            break
        except EOFError:
            print("\n👋 Email assistant stopped.")
            break


if __name__ == "__main__":
    main()
