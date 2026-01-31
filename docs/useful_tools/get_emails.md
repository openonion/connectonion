# Get Emails

> Check your inbox with one line. Process emails safely. Keep it simple.

## Usage

**Option 1: Import directly**

```python
from connectonion import get_emails, mark_read

agent = Agent("assistant", tools=[get_emails, mark_read])
```

**Option 2: Copy and customize**

```bash
co copy get_emails
```

```python
from tools.get_emails import get_emails, mark_read  # Your local copy
```

---

## Quick Start (10 seconds)

```python
from connectonion import get_emails, send_email, mark_read

# Get your emails
emails = get_emails()
```

**That's it.** You have your emails.

---

## Core Concept

Three functions. That's all:

```python
get_emails(last=10, unread=False)  # Get emails
send_email(to, subject, message)   # Send email (already done)
mark_read(email_id)                # Mark as read after processing
```

**Important**: Emails are NOT auto-marked as read. You control when to mark them.

---

## Common Patterns

### Check for new emails

```python
from connectonion import get_emails, mark_read

# Get unread emails
new_emails = get_emails(unread=True)

for email in new_emails:
    print(f"New from {email['from']}: {email['subject']}")
    
    # Process the email
    if process_email(email):
        mark_read(email['id'])  # Only mark if processed successfully
```

### Get latest email

```python
# Get just the most recent email
emails = get_emails(last=1)
if emails:
    latest = emails[0]
    print(f"Latest: {latest['subject']}")
```

### Reply to emails

```python
# Check and reply pattern
for email in get_emails(unread=True):
    if "urgent" in email["subject"].lower():
        # Send reply
        send_email(
            email["from"], 
            f"Re: {email['subject']}", 
            "I'm on it!"
        )
        # Mark as handled
        mark_read(email['id'])
```

---

## Complete Email Agent Example

Here's a full-featured email assistant agent that can manage your inbox:

```python
from connectonion import Agent, get_emails, send_email, mark_read
from typing import List, Dict
import json

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
    
    def archive_old_emails(self, days: int = 30) -> str:
        """Mark old emails as read to clean up inbox."""
        # For demo, we'll just mark all read emails
        emails = get_emails(last=50)
        old_count = 0
        
        for email in emails:
            if email['read']:
                continue
            # In real implementation, check timestamp
            # For now, just demonstrate the pattern
            mark_read(email['id'])
            old_count += 1
        
        return f"📦 Archived {old_count} old emails"
    
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


# Create the email agent
email_manager = EmailManager()

email_agent = Agent(
    name="email_assistant",
    tools=[
        email_manager,  # Pass the whole class instance!
        get_emails,     # Also available as standalone
        send_email,     # For custom operations
        mark_read       # For manual marking
    ],
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

# Example usage
if __name__ == "__main__":
    # Interactive email management
    while True:
        task = input("\n💌 What would you like to do with your emails? ")
        if task.lower() in ['quit', 'exit']:
            break
        
        result = email_agent.input(task)
        print(result)
```

---

## Using the Email Agent

### Example Conversations

```python
# Check inbox
>>> email_agent.input("Check my inbox")
"""
I'll check your inbox for you.

📬 You have 3 unread emails:

• [1] From: alice@example.com
    Subject: Project Update
    Preview: The new features are ready for review. Can we...

• [2] From: support@service.com
    Subject: Issue with login
    Preview: I'm having trouble accessing my account...

• [3] From: boss@company.com
    Subject: Urgent: Meeting Tomorrow
    Preview: We need to discuss the Q4 planning...

You have 2 urgent/important emails that may need immediate attention.
"""

# Reply to specific email
>>> email_agent.input("Reply to email 3 saying I'll be there")
"""
I'll reply to email #3 from boss@company.com about the urgent meeting.

✅ Replied to boss@company.com and marked as read
The reply "I'll be there" has been sent with subject "Re: Urgent: Meeting Tomorrow"
"""

# Auto-respond to urgent emails
>>> email_agent.input("Auto-respond to all urgent emails")
"""
I'll set up auto-responses for urgent emails.

🤖 Auto-responded to 2 emails from: alice@example.com, boss@company.com

Auto-responses have been sent to emails marked as urgent or important, 
letting senders know you've received their message and will respond within 24 hours.
"""

# Process support requests
>>> email_agent.input("Handle any support tickets")
"""
I'll process support emails and create tickets.

🎫 Created 1 support ticket

Support ticket TICKET-0001 has been created for the email from support@service.com
about "Issue with login". An acknowledgment has been sent to the customer.
"""

# Get statistics
>>> email_agent.input("Show me email statistics")
"""
Here are your email statistics:

📊 Email Statistics:
• Total emails: 25
• Unread: 12
• Processed this session: 4
• Auto-replies sent: 2

You've handled 4 emails so far, with 12 still unread in your inbox.
"""
```

---

## API Reference

### get_emails()

```python
get_emails(last=10, unread=False) -> list
```

**Parameters:**
- `last` (int): Number of emails to retrieve. Default: 10
- `unread` (bool): Only get unread emails. Default: False

**Returns:**
List of email dictionaries:
```python
[
    {
        'id': 'msg_123',
        'from': 'alice@example.com',
        'subject': 'Project Update',
        'message': 'The new feature is ready...',
        'timestamp': '2024-01-15T10:30:00Z',
        'read': False
    }
]
```

### mark_read()

```python
mark_read(email_id) -> bool
```

**Parameters:**
- `email_id` (str or list): Single ID or list of IDs to mark as read

**Returns:**
- `True` if successful
- `False` if failed

---

## Simple Standalone Examples

### Out-of-Office Responder

```python
from connectonion import get_emails, send_email, mark_read
import time

def out_of_office():
    """Simple out-of-office responder."""
    message = """
    Thank you for your email.
    
    I am currently out of office and will return on Monday.
    For urgent matters, please contact support@company.com.
    
    Best regards
    """
    
    while True:
        for email in get_emails(unread=True):
            # Skip if already replied (has Re: in subject)
            if not email['subject'].startswith('Re:'):
                send_email(
                    email['from'],
                    f"Out of Office: Re: {email['subject']}",
                    message
                )
                mark_read(email['id'])
                print(f"Auto-replied to {email['from']}")
        
        time.sleep(300)  # Check every 5 minutes

# Run the responder
out_of_office()
```

### Daily Digest

```python
from connectonion import get_emails, send_email
from datetime import datetime

def create_daily_digest():
    """Create a daily email digest."""
    emails = get_emails(last=50)
    
    # Group by sender
    by_sender = {}
    for email in emails:
        sender = email['from']
        if sender not in by_sender:
            by_sender[sender] = []
        by_sender[sender].append(email['subject'])
    
    # Create digest
    digest = f"📧 Daily Email Digest - {datetime.now().strftime('%Y-%m-%d')}\n\n"
    digest += f"Total emails: {len(emails)}\n"
    digest += f"Unique senders: {len(by_sender)}\n\n"
    
    for sender, subjects in by_sender.items():
        digest += f"From {sender} ({len(subjects)} emails):\n"
        for subject in subjects[:3]:  # Show first 3
            digest += f"  • {subject}\n"
        if len(subjects) > 3:
            digest += f"  ... and {len(subjects)-3} more\n"
        digest += "\n"
    
    # Send digest to yourself
    send_email(
        "me@example.com",
        "Daily Email Digest",
        digest
    )
    
    return "Digest sent!"

# Create and send digest
create_daily_digest()
```

---

## Why No Auto-Mark?

**The Problem with auto-marking:**
```python
# BAD: Auto-mark on fetch
emails = get_emails(unread=True)  # Server marks as read 😱
process_emails(emails)  # Crashes! 💥
# Emails lost forever - marked read but not processed!
```

**Our Safe Approach:**
```python
# GOOD: Explicit marking
emails = get_emails(unread=True)  # Stays unread
process_emails(emails)  # Process them
mark_read([e['id'] for e in emails])  # Mark only after success ✅
```

---

## Philosophy

**Three functions for everything email:**
- `get_emails()` - Read emails
- `send_email()` - Send emails  
- `mark_read()` - Mark as processed

No complexity. No confusion. Just email.

Keep simple things simple.