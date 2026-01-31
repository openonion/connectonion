# Microsoft Integration (co auth microsoft)

> Send emails via Outlook and read calendar events from your AI agents. 30-second setup.

---

## Quick Start

```bash
co auth microsoft
```

What happens:
1. Clears any existing Microsoft connection (allows switching accounts)
2. Opens browser to Microsoft OAuth consent screen
3. You authorize Mail + Calendar permissions
4. Credentials saved to `.env` (both local and global `~/.co/keys.env`)
5. Ready to use Outlook and Microsoft Calendar tools immediately

**That's it.** Your agents can now send emails via Outlook and read your Microsoft calendar.

**Switching accounts?** Just run `co auth microsoft` again - it will clear the old connection and let you pick a new Microsoft account.

---

## Prerequisites

Before running `co auth microsoft`, you must authenticate with OpenOnion:

```bash
co auth
```

This creates your `OPENONION_API_KEY` which is required for Microsoft OAuth to work.

---

## What Gets Saved

After successful authentication, your `.env` file contains:

```bash
# Microsoft OAuth Credentials
MICROSOFT_ACCESS_TOKEN=eyJ0eXAi...
MICROSOFT_REFRESH_TOKEN=0.ATcA...
MICROSOFT_TOKEN_EXPIRES_AT=2025-12-31T23:59:59
MICROSOFT_SCOPES=Mail.Read,Mail.Send,Calendars.Read,Calendars.ReadWrite
MICROSOFT_EMAIL=your.email@outlook.com
```

**Security notes:**
- Credentials are saved to both local `.env` and `~/.co/keys.env`
- File permissions set to `0600` (read/write for owner only) on Unix systems
- Access tokens expire, but refresh tokens allow automatic renewal
- You can revoke access anytime via Microsoft Account settings

---

## Permissions Requested

When you run `co auth microsoft`, we request these Microsoft Graph API scopes:

| Scope | Purpose | What agents can do |
|-------|---------|-------------------|
| `Mail.Read` | Read user emails | Read inbox, search emails |
| `Mail.Send` | Send emails on your behalf | Send emails via Outlook |
| `Calendars.Read` | Read calendar events | Read your calendar to check availability |
| `Calendars.ReadWrite` | Create/modify calendar events | Create and update events |
| `User.Read` | Get your profile | Identify which Microsoft account is connected |
| `offline_access` | Refresh tokens | Keep credentials working without re-auth |

**Privacy**: We only request the permissions needed. We cannot:
- Delete your emails
- Access your OneDrive or other services
- Access your contacts beyond basic profile

---

## Using Microsoft OAuth in Agents

Once authenticated, your agents can use Microsoft-powered tools:

### Send Email via Outlook

```python
from connectonion import Agent, Outlook

outlook = Outlook()

agent = Agent(
    "Outlook Assistant",
    tools=[outlook]
)

agent.input("Send an email to alice@example.com saying hello")
```

### Read Calendar Events

```python
from connectonion import Agent, MicrosoftCalendar

calendar = MicrosoftCalendar()

agent = Agent(
    "Calendar Assistant",
    tools=[calendar]
)

agent.input("What's on my calendar this week?")
```

---

## Outlook Tool Methods

The `Outlook` tool provides these capabilities:

```python
from connectonion import Outlook

outlook = Outlook()

# Reading emails
outlook.read_inbox(last=10, unread=False)  # Get recent inbox emails
outlook.get_sent_emails(max_results=10)    # Get sent emails
outlook.search_emails("quarterly report")   # Search all emails
outlook.get_email_body(email_id)           # Get full email content

# Sending emails
outlook.send(to="alice@example.com", subject="Hello", body="Hi there!")
outlook.send(to="alice@example.com", subject="Hello", body="Hi!", cc="bob@example.com")
outlook.reply(email_id, body="Thanks for your message")

# Actions
outlook.mark_read(email_id)     # Mark email as read
outlook.mark_unread(email_id)   # Mark email as unread
outlook.archive_email(email_id) # Move to archive folder

# Stats
outlook.count_unread()          # Count unread emails in inbox
outlook.get_my_email()          # Get connected Microsoft email address
```

---

## Microsoft Calendar Tool Methods

The `MicrosoftCalendar` tool provides:

```python
from connectonion import MicrosoftCalendar

calendar = MicrosoftCalendar()

# Reading events
calendar.list_events(days_ahead=7, max_results=20)  # Get upcoming events
calendar.get_today_events()                          # Get today's events
calendar.get_event(event_id)                         # Get event details

# Creating events
calendar.create_event(
    title="Team Meeting",
    start_time="2025-01-15 14:00",
    end_time="2025-01-15 15:00",
    description="Weekly sync",
    attendees="alice@example.com,bob@example.com",
    location="Conference Room A"
)

# Create Teams meeting (with auto-generated meeting link)
calendar.create_teams_meeting(
    title="Project Sync",
    start_time="2025-01-15 14:00",
    end_time="2025-01-15 15:00",
    attendees="alice@example.com,bob@example.com"
)

# Updating & deleting
calendar.update_event(event_id, title="Updated Title")
calendar.delete_event(event_id)

# Meetings & availability
calendar.get_upcoming_meetings(days_ahead=7)   # Get events with attendees
calendar.find_free_slots("2025-01-15", duration_minutes=60)  # Find free time
calendar.check_availability("2025-01-15 14:00")  # Check if specific time is free
```

---

## Troubleshooting

### "Not authenticated with OpenOnion"

You need to run `co auth` first to get your `OPENONION_API_KEY`:

```bash
co auth
co auth microsoft
```

### Authorization Timeout

If the browser window doesn't complete authorization within 5 minutes:

```bash
# Try again
co auth microsoft
```

### Access Denied / User Cancelled

If you click "Cancel" on the Microsoft consent screen:

```bash
# Just run it again when ready
co auth microsoft
```

### Credentials Not Working

Check if credentials are properly saved:

```bash
# Check local .env
cat .env | grep MICROSOFT_

# Check global keys
cat ~/.co/keys.env | grep MICROSOFT_
```

If credentials exist but don't work, re-authenticate:

```bash
co auth microsoft
```

### Switch Microsoft Account

To use a different Microsoft account:

```bash
co auth microsoft
```

This automatically clears the old connection before starting a new OAuth flow.

### Revoke Access

To disconnect your Microsoft account:

1. Via Microsoft Account Settings:
   - Go to https://account.live.com/consent/Manage
   - Find "OpenOnion" and click "Remove"

2. Manually remove credentials:
   ```bash
   # Remove from local .env
   sed -i '' '/^MICROSOFT_/d' .env

   # Remove from global keys
   sed -i '' '/^MICROSOFT_/d' ~/.co/keys.env
   ```

---

## Environment Variables Reference

After running `co auth microsoft`, these variables are available:

```bash
MICROSOFT_ACCESS_TOKEN      # Short-lived token for API calls (expires in 1 hour)
MICROSOFT_REFRESH_TOKEN     # Long-lived token for getting new access tokens
MICROSOFT_TOKEN_EXPIRES_AT  # ISO timestamp when access token expires
MICROSOFT_SCOPES            # Comma-separated list of granted scopes
MICROSOFT_EMAIL             # Your Microsoft account email address
```

**Usage in code:**

```python
import os

# Check if Microsoft OAuth is configured
if os.getenv("MICROSOFT_ACCESS_TOKEN"):
    print(f"Connected as: {os.getenv('MICROSOFT_EMAIL')}")
else:
    print("Not connected. Run: co auth microsoft")
```

---

## How It Works

Behind the scenes, `co auth microsoft`:

1. **Clears existing connection**: Calls `/api/v1/oauth/microsoft/revoke` to remove old credentials
2. **Initiates OAuth flow**: Calls `/api/v1/oauth/microsoft/init` with your `OPENONION_API_KEY`
3. **Opens browser**: Launches Microsoft's OAuth consent screen with required scopes
4. **Polls for completion**: Checks `/api/v1/oauth/microsoft/status` every 5 seconds
5. **Retrieves credentials**: Gets tokens from `/api/v1/oauth/microsoft/credentials`
6. **Saves locally**: Writes credentials to `.env` files with secure permissions

The backend handles:
- OAuth 2.0 authorization code flow
- Token refresh logic via Microsoft Graph API
- Secure storage of credentials
- Association with your OpenOnion account

---

## Comparison: Google vs Microsoft

| Feature | Google (`co auth google`) | Microsoft (`co auth microsoft`) |
|---------|--------------------------|--------------------------------|
| Email | Gmail | Outlook |
| Calendar | Google Calendar | Microsoft Calendar |
| API | Google APIs | Microsoft Graph API |
| Scopes | gmail.send, calendar | Mail.Read, Mail.Send, Calendars.* |
| Token endpoint | oauth2.googleapis.com | login.microsoftonline.com |

Both follow the same CLI pattern and save credentials in the same format.

---

## Security Best Practices

1. **Never commit `.env` files**: Add to `.gitignore`
   ```bash
   echo ".env" >> .gitignore
   ```

2. **Use environment-specific credentials**:
   - Development: Use test Microsoft account
   - Production: Use production account

3. **Regularly rotate credentials**:
   ```bash
   # Re-authenticate every few months
   co auth microsoft
   ```

4. **Monitor usage**: Check your Microsoft Account activity regularly

5. **Revoke when done**: If you stop using a project, revoke access

---

## Related

- [Google Integration](google.md) - Gmail and Google Calendar integration
- [CLI Auth](../cli/auth.md) - Authenticate with OpenOnion first
- [Global .co Directory](../co-directory-structure.md) - Where credentials are stored

---

## Privacy Policy & Terms

By using `co auth microsoft`, you agree to:
- [OpenOnion Privacy Policy](https://o.openonion.ai/privacy)
- [OpenOnion Terms of Service](https://o.openonion.ai/terms)
- [Microsoft APIs Terms of Use](https://docs.microsoft.com/en-us/legal/microsoft-apis/terms-of-use)

We only use your Microsoft data for the purposes you authorize. We never:
- Sell your data
- Share with third parties (except Microsoft)
- Store more than necessary
- Access data beyond requested scopes

You can revoke access at any time.
