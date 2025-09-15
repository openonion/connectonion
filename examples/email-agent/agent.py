#!/usr/bin/env python3
"""
Email Manager Agent - Tools designed specifically for AI agents to handle email tasks.

This example shows how to create an AI agent that uses email tools to:
- Search for specific emails
- Send new emails
- Reply to emails
- Create drafts using AI
- Check unread emails
- Mark emails as read

The key: Users speak naturally, AI translates to tool calls.
"""

import os
import sys
from typing import Optional
import time
from pydantic import BaseModel

# Ensure the repository root is on sys.path so `import connectonion` works
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from connectonion import Agent, send_email, get_emails, mark_read, llm_do


class EmailManager:
    """Email tools designed for AI agent use.

    Each method is a tool the AI can use to complete email tasks.
    The AI receives this entire class instance and can call any method.
    """

    def search_emails(self, query: str) -> str:
        """Search emails and return formatted results for AI processing.

        The AI provides natural language queries like "from John" or "about budget".
        Returns a formatted list the AI can parse for follow-up actions.
        """
        emails = get_emails(last=100)  # Search recent emails
        matches = []

        query_lower = query.lower()
        for email in emails:
            # Simple matching - AI provides natural language
            if (query_lower in email['from'].lower() or
                query_lower in email['subject'].lower() or
                query_lower in email.get('message', '').lower()):
                matches.append(email)

        if not matches:
            return f"No emails found matching '{query}'"

        # Format for AI to parse and use
        result = f"Found {len(matches)} emails matching '{query}':\n\n"
        for i, email in enumerate(matches[:10], 1):
            # Include ID for follow-up actions
            result += f"[{email['id']}] From: {email['from']}\n"
            result += f"     Subject: {email['subject']}\n"
            # Add preview if available
            message = email.get('message', '')
            if message:
                preview = message[:60].replace('\n', ' ')
                result += f"     Preview: {preview}...\n"
            result += "\n"

        return result

    def send_email(self, to: str, subject: str, body: str) -> str:
        """Send email and return status for AI.

        The AI composes the email content based on user instructions.
        Returns confirmation with message ID or error details.
        """
        result = send_email(to, subject, body)

        if result.get('success'):
            return f"✓ Email sent successfully to {to}\n  Message ID: {result.get('message_id', 'N/A')}"
        else:
            return f"Failed to send email: {result.get('error', 'Unknown error')}"

    def reply_to_email(self, email_id: int, message: str) -> str:
        """Reply to a specific email and mark it as read.

        The AI provides the email ID (from previous searches) and composes the reply.
        Automatically marks the original email as read after replying.
        """
        # Get emails to find the original
        emails = get_emails(last=50)
        original = None

        for email in emails:
            if email.get('id') == email_id:
                original = email
                break

        if not original:
            return f"Email with ID {email_id} not found"

        # Send the reply
        result = send_email(
            original['from'],
            f"Re: {original['subject']}",
            message
        )

        if result.get('success'):
            # Mark original as read
            mark_read(str(email_id))
            return f"✓ Reply sent to {original['from']} and marked as read"
        else:
            return f"Failed to send reply: {result.get('error', 'Unknown error')}"

    def draft_email(self, to: str, subject: str, context: str) -> str:
        """Create a draft email using AI for professional composition.

        The AI uses llm_do to compose a professional email based on context.
        Returns a preview for the user to confirm before sending.
        """
        # Define structured output for the draft
        class EmailDraft(BaseModel):
            subject: str
            body: str
            tone: str  # professional, casual, formal, friendly

        # Prepare the context for the prompt template
        prompt_context = f"Context: {context}\nRecipient: {to}\nSuggested subject: {subject}"

        # Use llm_do with prompt file (following the >3 lines principle)
        draft = llm_do(
            prompt_context,
            system_prompt="prompts/email_composer.md",  # Load from file
            output=EmailDraft,
            model="gpt-4o",  # Use gpt-4o for llm_do
            temperature=0.7  # Some creativity for natural writing
        )

        # Create draft ID
        draft_id = f"draft_{int(time.time())}"

        # Format the preview
        result = f"📝 Draft created (ID: {draft_id}):\n"
        result += f"{'=' * 40}\n"
        result += f"To: {to}\n"
        result += f"Subject: {draft.subject}\n"
        result += f"Tone: {draft.tone}\n"
        result += f"{'=' * 40}\n"
        result += f"{draft.body}\n"
        result += f"{'=' * 40}\n"
        result += f"\nTo send: call send_email('{to}', '{draft.subject}', ...)"

        return result

    def get_unread_emails(self) -> str:
        """Get unread emails formatted for AI processing.

        Returns a list of unread emails with IDs for follow-up actions.
        The AI uses this to check what needs attention.
        """
        emails = get_emails(unread=True)

        if not emails:
            return "📭 No unread emails"

        result = f"📬 You have {len(emails)} unread emails:\n\n"
        for i, email in enumerate(emails[:20], 1):  # Limit to 20 for readability
            # Include email ID for follow-up actions
            result += f"[{email.get('id', i)}] From: {email['from']}\n"
            result += f"     Subject: {email['subject']}\n"

            # Add timestamp if available
            timestamp = email.get('timestamp', '')
            if timestamp:
                result += f"     Time: {timestamp}\n"

            # Add preview
            message = email.get('message', '')
            if message:
                preview = message[:60].replace('\n', ' ')
                result += f"     Preview: {preview}...\n"
            result += "\n"

        return result

    def mark_email_read(self, email_id: int) -> str:
        """Mark an email as read and confirm to AI.

        The AI uses this after processing an email to keep the inbox organized.
        Returns confirmation of the action.
        """
        success = mark_read(str(email_id))

        if success:
            return f"✓ Email {email_id} marked as read"
        else:
            return f"Could not mark email {email_id} as read"


def main():
    """Create and run the email assistant agent."""

    # Create the email manager with all tools
    email_manager = EmailManager()

    # Create AI agent with email tools
    agent = Agent(
        name="email_assistant",
        tools=[email_manager],  # Pass the entire class instance - AI gets all methods as tools
        system_prompt="prompts/email_assistant.md",  # Load prompt from file (>3 lines principle)
        model="o4-mini"  # Use o4-mini for agents
    )

    print("🤖 Email Assistant (AI-Powered)")
    print("=" * 50)
    print("\nI can help you:")
    print("  📬 Check your emails")
    print("  🔍 Search for specific emails")
    print("  ✉️ Send new emails")
    print("  💬 Reply to emails")
    print("  📝 Draft emails for review")
    print("  ✓ Mark emails as read")

    print("\n💡 Just tell me what you need:")
    print('  "Check my emails"')
    print('  "Find emails from John about the project"')
    print('  "Send an email to alice@example.com"')
    print('  "Reply to email 2 saying I agree"')
    print('  "Draft an email to the team"')
    print("\nType 'quit' to exit\n")

    # Interactive loop
    while True:
        try:
            user_input = input("\n💌 What would you like to do? ")

            if user_input.lower() in ['quit', 'exit', 'bye', 'q']:
                print("\n👋 Goodbye!")
                break

            # Let the AI agent handle the natural language request
            response = agent.input(user_input)
            print(f"\n{response}")

        except KeyboardInterrupt:
            print("\n\n👋 Email assistant stopped.")
            break
        except EOFError:
            # Handle non-interactive mode gracefully
            print("\n👋 Email assistant stopped.")
            break


if __name__ == "__main__":
    main()