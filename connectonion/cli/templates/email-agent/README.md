# Email Assistant Agent

A powerful email management agent that can handle your inbox like a professional assistant.

## Features

- 📬 **Check Inbox** - View and summarize emails
- ✉️ **Send Emails** - Compose and send new emails
- 💬 **Smart Replies** - Reply to specific emails
- 🤖 **Auto-Respond** - Automatic responses based on keywords
- 🔍 **Search** - Find emails by content
- 📊 **Statistics** - Email usage analytics
- ✔️ **Mark Read** - Organize your inbox

## Quick Start

```bash
# Run the agent
python agent.py
```

## Example Commands

### Check Your Inbox
```
You: Check my emails
Assistant: You have 5 unread emails...
```

### Send an Email
```
You: Send an email to alice@example.com about the meeting tomorrow
Assistant: I'll compose an email about the meeting tomorrow...
```

### Reply to an Email
```
You: Reply to email 1 saying I'll attend
Assistant: Sending reply to john@example.com...
```

### Auto-Respond
```
You: Auto-respond to urgent emails
Assistant: Sent 3 auto-responses...
```

### Search Emails
```
You: Search for emails about invoices
Assistant: Found 4 emails containing 'invoices'...
```

## Configuration

The agent automatically uses your ConnectOnion email configuration from `.co/config.toml`.

### Customizing Auto-Responses

Edit the `auto_responses` dictionary in `EmailManager.__init__()`:

```python
self.auto_responses = {
    "meeting": "Your custom meeting response",
    "urgent": "Your custom urgent response",
    # Add more keywords and responses
}
```

### Adjusting Email Limits

Change the default limits in the functions:

```python
# In check_inbox()
emails = get_emails(last=20)  # Get more emails

# In search_emails()
emails = get_emails(last=100)  # Search more emails
```

## Email Categories

The agent automatically categorizes emails:

- 📅 **Meetings** - Calendar invites, appointments
- 🚨 **Urgent** - ASAP, critical messages
- 💼 **Work** - Projects, tasks, deadlines
- 📢 **Newsletters** - Subscriptions, updates
- 🛒 **Shopping** - Orders, deliveries
- 📧 **Other** - Everything else

## Advanced Usage

### Using the EmailManager Directly

```python
from agent import EmailManager

manager = EmailManager()

# Check inbox
summary = manager.check_inbox()
print(summary)

# Send email
result = manager.compose_and_send(
    "bob@example.com",
    "Project Update",
    "Here's the latest status..."
)

# Get statistics
stats = manager.get_statistics()
print(stats)
```

### Integrating with Other Agents

```python
from connectonion import Agent
from agent import EmailManager

# Combine with other tools
agent = Agent(
    "assistant",
    tools=[
        EmailManager(),
        your_other_tools
    ]
)
```

## Email Filtering

The agent can filter emails by:

- **Read/Unread status**
- **Sender email address**
- **Keywords in subject or body**
- **Date range** (with modifications)

## Security Notes

- Never share your API keys
- The agent respects email privacy
- All emails are processed locally
- Authentication via ConnectOnion's secure system

## Customization Ideas

1. **Add scheduling** - Send emails at specific times
2. **Create templates** - Pre-written responses
3. **Add attachments** - Support file attachments
4. **Email rules** - Automatic actions based on criteria
5. **Integrate calendar** - Schedule meetings from emails

## Troubleshooting

### "Email not activated"
Run `co auth` to activate your email address.

### "No emails found"
- Check if emails exist in your inbox
- Verify authentication is working
- Try with `show_all=True` to see all emails

### "Failed to send"
- Check recipient email format
- Verify your email is activated
- Check for rate limits

## Example Session

```
🤖 Email Assistant Agent Started

Checking your inbox...

📬 You have 3 unread emails:

• [1] alice@example.com
    Subject: Project Meeting Tomorrow
    Date: 2024-01-15
    Preview: Hi, can we meet tomorrow at 2pm to discuss...

• [2] support@service.com
    Subject: Your ticket #1234 has been updated
    Date: 2024-01-15
    Preview: We've resolved your issue...

• [3] newsletter@company.com
    Subject: Weekly Newsletter
    Date: 2024-01-14
    Preview: This week's highlights...

📊 Categories:
   📅 Meetings: 1 emails
   💼 Work: 1 emails
   📢 Newsletters: 1 emails

💬 How can I help you with your emails today?

You: Reply to Alice saying I'll be there at 2pm

🤖 Assistant: I'll send a reply to Alice confirming your attendance at 2pm.

✅ Reply sent to alice@example.com (Message ID: msg_12345)
The email has been marked as read.

You: Mark all newsletters as read

🤖 Assistant: I'll mark all newsletter emails as read for you.

✅ Marked 1 emails from newsletter@company.com as read

You: Show statistics

🤖 Assistant: Here are your email statistics:

📊 Email Statistics:
        
Total Emails: 25
Unread: 1
Processed this session: 2
Sent this session: 1

Top Senders:
   • alice@example.com: 5 emails
   • support@service.com: 3 emails
   • newsletter@company.com: 3 emails
   • bob@example.com: 2 emails
   • john@example.com: 2 emails
```

## Resources

- [ConnectOnion Documentation](https://github.com/openonion/connectonion)
- [Email API Guide](../../docs/get_emails.md)
- [Send Email Guide](../../docs/send_email.md)