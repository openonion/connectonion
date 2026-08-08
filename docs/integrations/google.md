# Google Integration (co auth google)

> Send emails via Gmail and read calendar events from your AI agents. 30-second setup.

---

## Quick Start

```bash
co auth google
```

What happens:
1. Clears any existing Google connection (allows switching accounts)
2. Opens browser to Google OAuth consent screen
3. You authorize Gmail Send + Calendar Read permissions
4. Credentials saved to `.env` (both local and global `~/.co/keys.env`)
5. Ready to use Gmail and Calendar tools immediately

**That's it.** Your agents can now send emails and read your calendar.

**Switching accounts?** Just run `co auth google` again - it will clear the old connection and let you pick a new Google account.

---

## Prerequisites

Before running `co auth google`, you must authenticate with OpenOnion:

```bash
co auth
```

This creates your `OPENONION_API_KEY` which is required for Google OAuth to work.

---

## What Gets Saved

After successful authentication, your `.env` file contains:

```bash
# Google OAuth Credentials
GOOGLE_ACCESS_TOKEN=ya29.a0A...
GOOGLE_REFRESH_TOKEN=1//0g...
GOOGLE_TOKEN_EXPIRES_AT=2025-12-31T23:59:59
GOOGLE_SCOPES=gmail.send,calendar.readonly
GOOGLE_EMAIL=your.email@gmail.com
```

**Security notes:**
- Credentials are saved to both local `.env` and `~/.co/keys.env`
- File permissions set to `0600` (read/write for owner only) on Unix systems
- Access tokens expire, but refresh tokens allow automatic renewal
- You can revoke access anytime via Google Account settings or the dashboard

---

## Permissions Requested

When you run `co auth google`, we request these Google scopes:

| Scope | Purpose | What agents can do |
|-------|---------|-------------------|
| `gmail.send` | Send emails on your behalf | Use `send_email()` tool to send emails |
| `calendar.readonly` | Read calendar events | Read your calendar to check availability |
| `userinfo.email` | Get your email address | Identify which Google account is connected |

**Privacy**: We only request the minimum permissions needed. We cannot:
- Read your inbox (use built-in `get_emails()` for that)
- Delete or modify calendar events
- Access your Google Drive or other services

---

## Using Google OAuth in Agents

Once authenticated, your agents can use Google-powered tools:

### Send Email via Gmail

```python
from connectonion import Agent, send_email

def send_gmail(to: str, subject: str, body: str) -> str:
    """Send email via your Gmail account."""
    result = send_email(to, subject, body)
    return f"Email sent to {to}: {result}"

agent = Agent(
    "Gmail Assistant",
    tools=[send_gmail]
)

agent.input("Send an email to alice@example.com saying hello")
```

### Read Calendar Events

```python
from connectonion import Agent, GoogleCalendar

calendar = GoogleCalendar()

agent = Agent(
    "Calendar Assistant",
    tools=[calendar]
)

agent.input("What's on my calendar this week?")
```

Use the built-in tool instead of constructing `Credentials` with a Google
client ID or secret. Those secrets stay on the OpenOnion backend, which also
refreshes short-lived access tokens.

---

## Complete Example: Scheduling Agent

Here's a full agent that can check your calendar and send meeting invites:

```python
from connectonion import Agent, Gmail, GoogleCalendar

gmail = Gmail()
calendar = GoogleCalendar()

agent = Agent(
    "Scheduling Agent",
    tools=[calendar, gmail],
    system_prompt="""You are a scheduling assistant.

You can:
1. Check calendar availability
2. Send meeting invitations via Gmail

When asked to schedule a meeting:
1. First check if the proposed time is available
2. If available, send the meeting invite
3. Report back to the user
"""
)

agent.input("""
Schedule a 1-hour meeting with bob@example.com
for tomorrow at 2pm. Subject: Q4 Planning Discussion
""")
```

---

## Troubleshooting

### "Not authenticated with OpenOnion"

You need to run `co auth` first to get your `OPENONION_API_KEY`:

```bash
co auth
co auth google
```

### Authorization Timeout

If the browser window doesn't complete authorization within 5 minutes:

```bash
# Try again
co auth google
```

The command polls the backend every 5 seconds waiting for your authorization.

### Access Denied / User Cancelled

If you click "Cancel" on the Google consent screen:

```bash
# Just run it again when ready
co auth google
```

### Credentials Not Working

Check if credentials are properly saved:

```bash
# Check local .env
cat .env | grep GOOGLE_

# Check global keys
cat ~/.co/keys.env | grep GOOGLE_
```

If credentials exist but don't work, re-authenticate:

```bash
co auth google
```

This replaces the credentials only after the new authorization succeeds, so
running deployments keep working while the browser flow is in progress.

### Switch Google Account

To use a different Google account:

```bash
co auth google
```

Pick your desired account in the browser. The old connection remains usable
until the new OAuth callback completes.

### Revoke Access

To disconnect your Google account:

1. Via Google Account Settings:
   - Go to https://myaccount.google.com/permissions
   - Find "OpenOnion" and click "Remove access"

2. Via OpenOnion Dashboard:
   - Visit https://o.openonion.ai
   - Click "Disconnect Google Account"

3. Manually remove credentials:
   ```bash
   # Remove from local .env
   sed -i '' '/^GOOGLE_/d' .env

   # Remove from global keys
   sed -i '' '/^GOOGLE_/d' ~/.co/keys.env
   ```

---

## Security Best Practices

1. **Never commit `.env` files**: Add to `.gitignore`
   ```bash
   echo ".env" >> .gitignore
   ```

2. **Use environment-specific credentials**:
   - Development: Use test Google account
   - Production: Use production account

3. **Regularly rotate credentials**:
   ```bash
   # Re-authenticate every few months
   co auth google
   ```

4. **Monitor usage**: Check your Google Account activity regularly

5. **Revoke when done**: If you stop using a project, revoke access

---

## How It Works

Behind the scenes, `co auth google`:

1. **Keeps the current connection alive** while re-authorization is in progress
2. **Initiates OAuth flow**: Calls `/api/v1/oauth/google/init` with your `OPENONION_API_KEY`
3. **Opens browser**: Launches Google's OAuth consent screen with required scopes
4. **Polls for completion**: Checks `/api/v1/oauth/google/status` for a newly written credential
5. **Retrieves credentials**: Gets tokens from `/api/v1/oauth/google/credentials`
6. **Saves locally**: Writes credentials to `.env` files with secure permissions

The backend handles:
- OAuth 2.0 authorization code flow
- Token refresh logic
- Secure storage of credentials
- Association with your OpenOnion account

---

## Environment Variables Reference

After running `co auth google`, these variables are available:

```bash
GOOGLE_ACCESS_TOKEN      # Short-lived token for API calls (expires in 1 hour)
GOOGLE_REFRESH_TOKEN     # Long-lived token for getting new access tokens
GOOGLE_TOKEN_EXPIRES_AT  # ISO timestamp when access token expires
GOOGLE_SCOPES            # Comma-separated list of granted scopes
GOOGLE_EMAIL             # Your Google account email address
```

**Usage in code:**

```python
import os

# Check if Google OAuth is configured
if os.getenv("GOOGLE_ACCESS_TOKEN"):
    print(f"Connected as: {os.getenv('GOOGLE_EMAIL')}")
else:
    print("Not connected. Run: co auth google")
```

---

## Related

- [CLI Auth](../cli/auth.md) - Authenticate with OpenOnion first
- [Send Email](../useful_tools/send_email.md) - Send emails via OpenOnion's email service
- [Get Emails](../useful_tools/get_emails.md) - Read emails from your OpenOnion inbox
- [Global .co Directory](../co-directory-structure.md) - Where credentials are stored

---

## Privacy Policy & Terms

By using `co auth google`, you agree to:
- [OpenOnion Privacy Policy](https://o.openonion.ai/privacy)
- [OpenOnion Terms of Service](https://o.openonion.ai/terms)
- [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy)

We only use your Google data for the purposes you authorize. We never:
- Sell your data
- Share with third parties (except Google)
- Store more than necessary
- Access data beyond requested scopes

You can revoke access at any time.
