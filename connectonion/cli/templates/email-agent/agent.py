"""
Email Assistant Agent - A comprehensive email management agent.

This agent can:
- Check and summarize your inbox
- Send emails on your behalf
- Auto-respond to specific types of emails
- Mark emails as read/unread
- Filter and organize emails
"""

import os
import re
from datetime import datetime
from typing import List, Dict, Optional
from connectonion import Agent, send_email, get_emails, mark_read


class EmailManager:
    """Manages email operations with smart filtering and responses."""
    
    def __init__(self):
        self.processed_count = 0
        self.sent_count = 0
        self.auto_responses = {
            "meeting": "Thank you for the meeting request. I'll review my calendar and get back to you shortly.",
            "urgent": "I've received your urgent message and will prioritize it immediately.",
            "support": "Thank you for contacting support. We'll address your issue within 24 hours.",
            "invoice": "Invoice received. Our accounting team will process it within 3-5 business days."
        }
    
    def check_inbox(self, show_all: bool = False, limit: int = 10) -> str:
        """Check inbox and provide a summary of emails.
        
        Args:
            show_all: Show all emails or just unread
            limit: Maximum number of emails to retrieve
            
        Returns:
            Summary of emails in the inbox
        """
        emails = get_emails(last=limit) if show_all else get_emails(unread=True)
        
        if not emails:
            return "📭 No emails to show"
        
        summary = f"📬 You have {len(emails)} {'emails' if show_all else 'unread emails'}:\n\n"
        
        for i, email in enumerate(emails, 1):
            status = "✓" if email.get('read') else "•"
            timestamp = email.get('timestamp', '')[:10]  # Just date
            
            summary += f"{status} [{i}] {email.get('from')}\n"
            summary += f"    Subject: {email.get('subject')}\n"
            summary += f"    Date: {timestamp}\n"
            summary += f"    Preview: {email.get('message', '')[:100]}...\n\n"
        
        # Add categories summary
        categories = self._categorize_emails(emails)
        if categories:
            summary += "\n📊 Categories:\n"
            for category, count in categories.items():
                summary += f"   {category}: {count} emails\n"
        
        return summary
    
    def send_reply(self, email_index: int, message: str) -> str:
        """Reply to a specific email by index.
        
        Args:
            email_index: Index of the email to reply to (1-based)
            message: Reply message content
            
        Returns:
            Status of the send operation
        """
        emails = get_emails()
        
        if email_index < 1 or email_index > len(emails):
            return f"❌ Invalid email index. You have {len(emails)} emails."
        
        email = emails[email_index - 1]
        
        # Send the reply
        result = send_email(
            to=email['from'],
            subject=f"Re: {email['subject']}",
            message=message
        )
        
        if result.get('success'):
            # Mark original as read
            mark_read(email['id'])
            self.sent_count += 1
            self.processed_count += 1
            return f"✅ Reply sent to {email['from']} (Message ID: {result.get('message_id')})"
        else:
            return f"❌ Failed to send reply: {result.get('error')}"
    
    def auto_respond(self, keywords: Optional[List[str]] = None) -> str:
        """Auto-respond to emails based on keywords.
        
        Args:
            keywords: List of keywords to trigger auto-response
            
        Returns:
            Summary of auto-responses sent
        """
        if keywords is None:
            keywords = list(self.auto_responses.keys())
        
        emails = get_emails(unread=True)
        responded = []
        
        for email in emails:
            content = f"{email.get('subject', '')} {email.get('message', '')}".lower()
            
            for keyword in keywords:
                if keyword.lower() in content:
                    # Get appropriate response
                    response_text = self.auto_responses.get(
                        keyword.lower(), 
                        "Thank you for your email. I'll respond as soon as possible."
                    )
                    
                    # Send auto-response
                    result = send_email(
                        to=email['from'],
                        subject=f"Auto-Reply: {email['subject']}",
                        message=f"{response_text}\n\n---\nOriginal message received: {email.get('timestamp', '')}"
                    )
                    
                    if result.get('success'):
                        mark_read(email['id'])
                        responded.append({
                            'to': email['from'],
                            'keyword': keyword,
                            'subject': email['subject']
                        })
                        self.sent_count += 1
                        self.processed_count += 1
                    break  # Only one response per email
        
        if responded:
            summary = f"🤖 Sent {len(responded)} auto-responses:\n"
            for resp in responded:
                summary += f"   • {resp['to']} (triggered by '{resp['keyword']}')\n"
            return summary
        else:
            return "No emails matched auto-response criteria"
    
    def mark_as_read_by_sender(self, sender_email: str) -> str:
        """Mark all emails from a specific sender as read.
        
        Args:
            sender_email: Email address of the sender
            
        Returns:
            Status message
        """
        emails = get_emails()
        to_mark = [e['id'] for e in emails if e.get('from') == sender_email and not e.get('read')]
        
        if not to_mark:
            return f"No unread emails from {sender_email}"
        
        success = mark_read(to_mark)
        if success:
            self.processed_count += len(to_mark)
            return f"✅ Marked {len(to_mark)} emails from {sender_email} as read"
        else:
            return f"❌ Failed to mark emails as read"
    
    def search_emails(self, search_term: str) -> str:
        """Search for emails containing specific terms.
        
        Args:
            search_term: Term to search for in subjects and messages
            
        Returns:
            List of matching emails
        """
        emails = get_emails(last=50)  # Search last 50 emails
        matches = []
        
        search_lower = search_term.lower()
        for email in emails:
            if (search_lower in email.get('subject', '').lower() or 
                search_lower in email.get('message', '').lower() or
                search_lower in email.get('from', '').lower()):
                matches.append(email)
        
        if not matches:
            return f"No emails found containing '{search_term}'"
        
        result = f"🔍 Found {len(matches)} emails containing '{search_term}':\n\n"
        for i, email in enumerate(matches[:10], 1):  # Show max 10
            result += f"[{i}] From: {email['from']}\n"
            result += f"    Subject: {email['subject']}\n"
            result += f"    Date: {email.get('timestamp', '')[:10]}\n\n"
        
        if len(matches) > 10:
            result += f"... and {len(matches) - 10} more"
        
        return result
    
    def compose_and_send(self, to: str, subject: str, message: str) -> str:
        """Compose and send a new email.
        
        Args:
            to: Recipient email address
            subject: Email subject
            message: Email body
            
        Returns:
            Status of the send operation
        """
        # Validate email
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', to):
            return f"❌ Invalid email address: {to}"
        
        result = send_email(to, subject, message)
        
        if result.get('success'):
            self.sent_count += 1
            return f"✅ Email sent to {to}\n   Subject: {subject}\n   Message ID: {result.get('message_id')}"
        else:
            return f"❌ Failed to send: {result.get('error')}"
    
    def get_statistics(self) -> str:
        """Get email processing statistics.
        
        Returns:
            Statistics summary
        """
        all_emails = get_emails(last=50)
        unread = get_emails(unread=True)
        
        stats = f"""📊 Email Statistics:
        
Total Emails: {len(all_emails)}
Unread: {len(unread)}
Processed this session: {self.processed_count}
Sent this session: {self.sent_count}

Top Senders:"""
        
        # Count emails by sender
        sender_counts = {}
        for email in all_emails:
            sender = email.get('from', 'Unknown')
            sender_counts[sender] = sender_counts.get(sender, 0) + 1
        
        # Show top 5 senders
        for sender, count in sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            stats += f"\n   • {sender}: {count} emails"
        
        return stats
    
    def _categorize_emails(self, emails: List[Dict]) -> Dict[str, int]:
        """Categorize emails by content type."""
        categories = {
            "📅 Meetings": 0,
            "🚨 Urgent": 0,
            "💼 Work": 0,
            "📢 Newsletters": 0,
            "🛒 Shopping": 0,
            "📧 Other": 0
        }
        
        for email in emails:
            content = f"{email.get('subject', '')} {email.get('message', '')}".lower()
            
            if any(word in content for word in ['meeting', 'calendar', 'schedule', 'appointment']):
                categories["📅 Meetings"] += 1
            elif any(word in content for word in ['urgent', 'asap', 'immediately', 'critical']):
                categories["🚨 Urgent"] += 1
            elif any(word in content for word in ['project', 'task', 'deadline', 'report']):
                categories["💼 Work"] += 1
            elif any(word in content for word in ['newsletter', 'subscribe', 'unsubscribe']):
                categories["📢 Newsletters"] += 1
            elif any(word in content for word in ['order', 'shipping', 'delivery', 'invoice']):
                categories["🛒 Shopping"] += 1
            else:
                categories["📧 Other"] += 1
        
        # Return only non-zero categories
        return {k: v for k, v in categories.items() if v > 0}


def main():
    """Run the email assistant agent."""
    
    # Create email manager instance
    email_manager = EmailManager()
    
    # Create agent with email tools
    agent = Agent(
        name="email-assistant",
        tools=[
            email_manager,  # Pass the entire class as a tool!
            send_email,     # Also include standalone functions
            get_emails,
            mark_read
        ],
        system_prompt="""You are a professional email assistant that helps manage emails efficiently.

Your capabilities include:
- Checking and summarizing the inbox
- Sending emails and replies
- Auto-responding to specific types of emails
- Marking emails as read
- Searching for specific emails
- Providing email statistics

Guidelines:
1. Be professional and courteous in all communications
2. Prioritize urgent and important emails
3. Keep responses concise and clear
4. Always confirm before sending emails
5. Protect user privacy - never share email contents unnecessarily

When asked about emails, start by checking the inbox to see what's available.
When composing emails, ensure proper formatting and professional tone.
"""
    )
    
    # Example: Check inbox on startup
    print("🤖 Email Assistant Agent Started\n")
    print("Checking your inbox...\n")
    
    # Get initial inbox status
    inbox_summary = email_manager.check_inbox(limit=5)
    print(inbox_summary)
    
    # Interactive mode
    print("\n💬 How can I help you with your emails today?")
    print("   Examples:")
    print("   - 'Check my emails'")
    print("   - 'Reply to email 1 saying I'll attend the meeting'")
    print("   - 'Send an email to john@example.com about the project update'")
    print("   - 'Search for emails about invoices'")
    print("   - 'Auto-respond to urgent emails'")
    print("   - 'Show email statistics'\n")
    
    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() in ['exit', 'quit', 'bye']:
                print("\n👋 Goodbye! Your email assistant is signing off.")
                break
            
            # Process with agent
            response = agent.input(user_input)
            print(f"\n🤖 Assistant: {response}\n")
            
        except KeyboardInterrupt:
            print("\n\n👋 Email assistant stopped.")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")


if __name__ == "__main__":
    main()