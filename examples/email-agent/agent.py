#!/usr/bin/env python3
"""
Email Assistant Agent - AI-powered email management.

This example shows how to create an AI agent that can:
- Check and summarize your inbox
- Send emails on your behalf
- Auto-respond to urgent messages
- Process support tickets
- Track email statistics

The agent uses the ConnectOnion email tools (send_email, get_emails, mark_read)
along with a custom EmailManager class for stateful operations.
"""

import os
import sys
from typing import List

# Ensure the repository root is on sys.path so `import connectonion` works
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from connectonion import Agent, send_email, get_emails, mark_read


class EmailManager:
    """Stateful email management with tracking."""
    
    def __init__(self):
        self.processed_count = 0
        self.auto_replies_sent = 0
    
    def check_inbox(self, show_all: bool = False) -> str:
        """Check inbox and summarize emails."""
        emails = get_emails(unread=not show_all)
        
        if not emails:
            return "📭 No new emails"
        
        summary = f"📬 You have {len(emails)} {'emails' if show_all else 'unread emails'}:\n\n"
        
        for i, email in enumerate(emails, 1):
            status = "✓" if email['read'] else "•"
            summary += f"{status} [{i}] From: {email['from']}\n"
            summary += f"    Subject: {email['subject']}\n"
            summary += f"    Preview: {email['message'][:50]}...\n\n"
        
        return summary
    
    def reply_to_email(self, email_index: int, message: str) -> str:
        """Reply to a specific email by index."""
        emails = get_emails()
        
        if email_index < 1 or email_index > len(emails):
            return f"❌ Invalid email index. You have {len(emails)} emails."
        
        email = emails[email_index - 1]
        
        # Send the reply
        send_email(
            email['from'],
            f"Re: {email['subject']}",
            message
        )
        
        # Mark original as read
        mark_read(email['id'])
        self.processed_count += 1
        
        return f"✅ Replied to {email['from']} and marked as read"
    
    def auto_respond(self, keywords: List[str] = None) -> str:
        """Auto-respond to emails matching keywords."""
        if keywords is None:
            keywords = ["urgent", "asap", "important"]
        
        emails = get_emails(unread=True)
        responded = []
        
        for email in emails:
            # Check if any keyword matches
            if any(kw.lower() in email['subject'].lower() or 
                   kw.lower() in email['message'].lower() 
                   for kw in keywords):
                
                # Send auto-response
                send_email(
                    email['from'],
                    f"Auto-Reply: {email['subject']}",
                    f"Thank you for your message marked as important. "
                    f"I've received it and will respond within 24 hours.\n\n"
                    f"Original message received: {email['timestamp']}"
                )
                
                mark_read(email['id'])
                responded.append(email['from'])
                self.auto_replies_sent += 1
        
        if responded:
            return f"🤖 Auto-responded to {len(responded)} emails from: {', '.join(responded)}"
        return "No emails matched auto-response criteria"
    
    def process_support_tickets(self) -> str:
        """Process support emails and create tickets."""
        support_emails = []
        
        for email in get_emails(unread=True):
            if any(word in email['subject'].lower() 
                   for word in ['support', 'help', 'issue', 'problem', 'bug']):
                
                support_emails.append(email)
                
                # Acknowledge receipt
                ticket_id = f"TICKET-{len(support_emails):04d}"
                
                send_email(
                    email['from'],
                    f"Support Ticket Created: {ticket_id}",
                    f"Thank you for contacting support.\n\n"
                    f"Your ticket {ticket_id} has been created.\n"
                    f"Subject: {email['subject']}\n\n"
                    f"We'll respond within 24 hours."
                )
                
                mark_read(email['id'])
                self.processed_count += 1
        
        if support_emails:
            return f"🎫 Created {len(support_emails)} support tickets"
        return "No support emails found"
    
    def send_new_email(self, to: str, subject: str, message: str) -> str:
        """Send a new email."""
        result = send_email(to, subject, message)
        if result['success']:
            return f"✅ Email sent to {to}"
        return f"❌ Failed to send email: {result.get('error', 'Unknown error')}"
    
    def get_latest_emails(self, count: int = 10) -> str:
        """Get the latest emails."""
        emails = get_emails(last=count)
        if not emails:
            return "No emails found"
        
        result = f"Latest {len(emails)} emails:\n\n"
        for i, email in enumerate(emails, 1):
            result += f"[{i}] From: {email['from']}\n"
            result += f"    Subject: {email['subject']}\n"
            result += f"    Preview: {email['message'][:50]}...\n\n"
        return result
    
    def get_statistics(self) -> str:
        """Get email processing statistics."""
        total = len(get_emails())
        unread = len(get_emails(unread=True))
        
        return (
            f"📊 Email Statistics:\n"
            f"• Total emails: {total}\n"
            f"• Unread: {unread}\n"
            f"• Processed this session: {self.processed_count}\n"
            f"• Auto-replies sent: {self.auto_replies_sent}"
        )


def main():
    """Create and run the email assistant agent."""
    
    # Create stateful email manager
    email_manager = EmailManager()
    
    # Create AI agent with email capabilities
    agent = Agent(
        name="email_assistant",
        tools=[email_manager],  # Just pass the class - it has all the methods!
        system_prompt="""You are a professional email assistant.
        
Your capabilities:
- Check and summarize inbox
- Reply to emails 
- Auto-respond to urgent messages
- Process support tickets
- Provide email statistics

Guidelines:
1. Always confirm before sending emails
2. Be professional and courteous
3. Prioritize urgent/important emails
4. Keep responses concise
5. Track what you've processed

When checking emails, start with check_inbox() to see what's available.
"""
    )
    
    print("🤖 Email Assistant Agent")
    print("========================\n")
    print("I can help you:")
    print("• Check your inbox")
    print("• Send and reply to emails")
    print("• Auto-respond to urgent messages")
    print("• Process support tickets")
    print("• Show email statistics\n")
    print("Examples:")
    print('  "Check my emails"')
    print('  "Reply to email 1 saying I\'ll be there"')
    print('  "Send an email to alice@example.com about the meeting"')
    print('  "Auto-respond to urgent emails"')
    print('  "Show me email statistics"\n')
    
    # Interactive loop
    while True:
        try:
            task = input("\n💌 What would you like to do? ")
            if task.lower() in ['quit', 'exit', 'bye']:
                print("\n👋 Goodbye!")
                break
            
            # Let the AI agent handle the task
            response = agent.input(task)
            print(f"\nAssistant: {response}")
            
        except KeyboardInterrupt:
            print("\n\n👋 Email assistant stopped.")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    main()


