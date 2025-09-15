#!/usr/bin/env python3
"""
Email Assistant Agent - AI-powered email management with send & receive.

This example shows how to create an AI agent that can:
- Check and read incoming emails
- Send new emails and replies
- Auto-respond to urgent messages
- Process and categorize emails
- Track email statistics

The agent uses ConnectOnion's email tools integrated into a single EmailManager class.
"""

import os
import sys
from typing import List, Dict, Optional
from datetime import datetime

# Ensure the repository root is on sys.path so `import connectonion` works
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from connectonion import Agent, send_email, get_emails, mark_read


class EmailManager:
    """Complete email management system with send and receive capabilities."""

    def __init__(self):
        self.processed_count = 0
        self.sent_count = 0
        self.received_count = 0
        self.auto_replies_sent = 0

    def check_inbox(self, show_all: bool = False, limit: int = 10) -> str:
        """Check inbox and summarize received emails.

        Args:
            show_all: If True, show all emails. If False, show only unread.
            limit: Maximum number of emails to show.
        """
        if show_all:
            emails = get_emails(last=limit)
            title = f"all emails (last {limit})"
        else:
            emails = get_emails(unread=True)
            title = "unread emails"

        if not emails:
            return f"📭 No {title}"

        self.received_count = len(emails)
        summary = f"📬 You have {len(emails)} {title}:\n\n"

        for i, email in enumerate(emails, 1):
            status = "✓" if email.get('read') else "•"
            timestamp = email.get('timestamp', 'Unknown time')
            summary += f"{status} [{i}] From: {email['from']}\n"
            summary += f"    Subject: {email['subject']}\n"
            summary += f"    Time: {timestamp}\n"

            # Show message preview
            message = email.get('message', '')
            if message:
                preview = message[:80].replace('\n', ' ')
                summary += f"    Preview: {preview}...\n"
            summary += "\n"

        return summary

    def read_email(self, email_index: int) -> str:
        """Read a specific email by index and mark it as read.

        Args:
            email_index: The index of the email to read (1-based).
        """
        emails = get_emails(last=20)

        if email_index < 1 or email_index > len(emails):
            return f"❌ Invalid email index. You have {len(emails)} emails."

        email = emails[email_index - 1]

        # Mark as read
        mark_read(str(email['id']))
        self.processed_count += 1

        # Format the full email
        result = f"📧 Email Details:\n"
        result += f"From: {email['from']}\n"
        result += f"Subject: {email['subject']}\n"
        result += f"Time: {email.get('timestamp', 'Unknown')}\n"
        result += f"{'=' * 40}\n"
        result += f"{email.get('message', 'No message content')}\n"
        result += f"{'=' * 40}\n"
        result += f"✓ Marked as read"

        return result
    
    def reply_to_email(self, email_index: int, message: str) -> str:
        """Reply to a specific email by index.

        Args:
            email_index: The index of the email to reply to (1-based).
            message: The reply message to send.
        """
        emails = get_emails(last=20)

        if email_index < 1 or email_index > len(emails):
            return f"❌ Invalid email index. You have {len(emails)} emails."

        email = emails[email_index - 1]

        # Send the reply
        result = send_email(
            email['from'],
            f"Re: {email['subject']}",
            message
        )

        if result.get('success'):
            # Mark original as read
            mark_read(str(email['id']))
            self.processed_count += 1
            self.sent_count += 1
            return f"✅ Replied to {email['from']} and marked as read"
        else:
            return f"❌ Failed to send reply: {result.get('error', 'Unknown error')}"

    def send_new_email(self, to: str, subject: str, message: str) -> str:
        """Send a new email.

        Args:
            to: Recipient email address.
            subject: Email subject.
            message: Email body content.
        """
        result = send_email(to, subject, message)
        if result.get('success'):
            self.sent_count += 1
            return f"✅ Email sent to {to}\n  Message ID: {result.get('message_id', 'N/A')}"
        return f"❌ Failed to send email: {result.get('error', 'Unknown error')}"
    
    def auto_respond(self, keywords: List[str] = None) -> str:
        """Auto-respond to emails matching keywords.

        Args:
            keywords: List of keywords to match. Defaults to ["urgent", "asap", "important"].
        """
        if keywords is None:
            keywords = ["urgent", "asap", "important"]

        emails = get_emails(unread=True)
        responded = []

        for email in emails:
            # Check if any keyword matches
            message_content = email.get('message', '')
            if any(kw.lower() in email['subject'].lower() or
                   kw.lower() in message_content.lower()
                   for kw in keywords):

                # Send auto-response
                result = send_email(
                    email['from'],
                    f"Auto-Reply: {email['subject']}",
                    f"Thank you for your message marked as important. "
                    f"I've received it and will respond within 24 hours.\n\n"
                    f"Original message received: {email.get('timestamp', 'Recently')}"
                )

                if result.get('success'):
                    mark_read(str(email['id']))
                    responded.append(email['from'])
                    self.auto_replies_sent += 1
                    self.sent_count += 1

        if responded:
            return f"🤖 Auto-responded to {len(responded)} emails from: {', '.join(responded)}"
        return "No emails matched auto-response criteria"
    
    def process_inbox(self, action: str = "categorize") -> str:
        """Process inbox emails with different actions.

        Args:
            action: What to do - "categorize", "prioritize", or "clean".
        """
        emails = get_emails(unread=True)
        if not emails:
            return "📭 No unread emails to process"

        if action == "categorize":
            categories = {
                'support': [],
                'urgent': [],
                'newsletter': [],
                'personal': [],
                'other': []
            }

            for email in emails:
                subject_lower = email['subject'].lower()
                from_lower = email['from'].lower()

                if any(word in subject_lower for word in ['support', 'help', 'issue', 'problem']):
                    categories['support'].append(email)
                elif any(word in subject_lower for word in ['urgent', 'asap', 'important']):
                    categories['urgent'].append(email)
                elif 'newsletter' in from_lower or 'noreply' in from_lower:
                    categories['newsletter'].append(email)
                elif any(domain in from_lower for domain in ['gmail.com', 'yahoo.com', 'outlook.com']):
                    categories['personal'].append(email)
                else:
                    categories['other'].append(email)

            result = "📂 Email Categories:\n"
            for cat, emails_list in categories.items():
                if emails_list:
                    result += f"  {cat.title()}: {len(emails_list)} emails\n"
            return result

        elif action == "prioritize":
            high_priority = []
            normal_priority = []

            for email in emails:
                if any(word in email['subject'].lower() or word in email.get('message', '').lower()
                       for word in ['urgent', 'asap', 'deadline', 'critical']):
                    high_priority.append(email)
                else:
                    normal_priority.append(email)

            result = "🎯 Email Priority:\n"
            result += f"  High Priority: {len(high_priority)} emails\n"
            if high_priority:
                for email in high_priority[:3]:  # Show top 3
                    result += f"    - {email['subject']} from {email['from']}\n"
            result += f"  Normal Priority: {len(normal_priority)} emails\n"
            return result

        return "Unknown action. Use: categorize, prioritize, or clean"

    def get_statistics(self) -> str:
        """Get comprehensive email statistics."""
        all_emails = get_emails(last=100)
        unread_emails = get_emails(unread=True)

        # Calculate response rate
        domains = {}
        for email in all_emails:
            domain = email['from'].split('@')[-1] if '@' in email['from'] else 'unknown'
            domains[domain] = domains.get(domain, 0) + 1

        result = f"📊 Email Statistics:\n"
        result += f"{'=' * 40}\n"
        result += f"📥 Inbox Status:\n"
        result += f"  • Total emails: {len(all_emails)}\n"
        result += f"  • Unread: {len(unread_emails)}\n"
        result += f"  • Read: {len(all_emails) - len(unread_emails)}\n\n"

        result += f"📤 Session Activity:\n"
        result += f"  • Emails sent: {self.sent_count}\n"
        result += f"  • Emails processed: {self.processed_count}\n"
        result += f"  • Auto-replies: {self.auto_replies_sent}\n\n"

        result += f"🌐 Top Domains:\n"
        for domain, count in sorted(domains.items(), key=lambda x: x[1], reverse=True)[:3]:
            result += f"  • {domain}: {count} emails\n"

        return result


def main():
    """Create and run the email assistant agent."""

    # Create stateful email manager
    email_manager = EmailManager()

    # Create AI agent with email capabilities
    agent = Agent(
        name="email_assistant",
        tools=[email_manager],  # Just pass the class instance - all methods become tools!
        system_prompt="""You are a professional email assistant that can both send and receive emails.

Your capabilities:
📥 RECEIVING & READING:
- check_inbox() - See all unread emails or show all with show_all=True
- read_email(index) - Read a specific email by number and mark it as read
- process_inbox("categorize") - Categorize emails by type
- process_inbox("prioritize") - Sort by priority

📤 SENDING & REPLYING:
- send_new_email(to, subject, message) - Send a new email
- reply_to_email(index, message) - Reply to a specific email
- auto_respond() - Auto-reply to urgent emails

📊 MANAGEMENT:
- get_statistics() - Show email statistics and activity

Guidelines:
1. Always check inbox first to see available emails
2. Use email index numbers (1, 2, 3...) to refer to specific emails
3. Confirm before sending any emails
4. Be professional and concise
5. Mark emails as read after processing

Start by checking the inbox to see what emails are available."""
    )

    print("🤖 Email Assistant Agent (Send & Receive)")
    print("=" * 50)
    print("\n📥 RECEIVING Commands:")
    print('  "Check my inbox" - See unread emails')
    print('  "Show all emails" - See all emails')
    print('  "Read email 1" - Read specific email')
    print('  "Categorize my emails" - Sort by type')

    print("\n📤 SENDING Commands:")
    print('  "Send email to alice@example.com about the meeting"')
    print('  "Reply to email 1 saying I agree"')
    print('  "Auto-respond to urgent emails"')

    print("\n📊 MANAGEMENT Commands:")
    print('  "Show statistics" - Email activity summary')
    print('  "Process my inbox" - Organize emails')

    print("\n💡 Tips:")
    print("  • Start with 'check inbox' to see available emails")
    print("  • Use email numbers (1, 2, 3) to refer to specific emails")
    print("  • Type 'quit' to exit\n")

    # Interactive loop
    while True:
        try:
            task = input("\n💌 What would you like to do? ")
            if task.lower() in ['quit', 'exit', 'bye', 'q']:
                print("\n👋 Goodbye! Your email stats:")
                print(email_manager.get_statistics())
                break

            # Let the AI agent handle the task
            response = agent.input(task)
            print(f"\n{response}")

        except KeyboardInterrupt:
            print("\n\n👋 Email assistant stopped.")
            print(email_manager.get_statistics())
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    main()


