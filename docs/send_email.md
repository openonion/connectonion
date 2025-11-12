# Send Email

> Send emails with one line of code. No config, no complexity.

---

## 📌 Current Status (as of Sep 2025)

✅ **Working**: Email sending via `mail.openonion.ai` domain
✅ **API Endpoint**: `https://oo.openonion.ai/api/v1/email/send`
✅ **Sender**: Your agent's unique email `0x{your_key}@mail.openonion.ai`
✅ **JWT Tokens**: No expiration - authenticate once and use forever

## ⚡ Quick Debug

**Email not working? Try this:**

```bash
# 1. Check if email is activated
cat .co/config.toml | grep email_active
# If false, run: co auth

# 2. Test directly
python -c "from connectonion import send_email; print(send_email('your@email.com', 'Test', 'It works!'))"

# 3. Common fixes
co auth  # Refresh token if expired
co init  # If missing .co directory
```

---

## Quick Start (30 seconds to first email)

**One line. That's it.**

```python
from connectonion import send_email

send_email("alice@example.com", "Welcome!", "Thanks for joining us!")
```

**Run it**

```pycon
>>> send_email("alice@example.com", "Welcome!", "Thanks for joining us!")
{'success': True, 'message_id': 'msg_123', 'from': '0x1234abcd@mail.openonion.ai'}
```

Email sent. Done.

---

## Core Concept

What you get:

- Simple function: `send_email(to, subject, message)`
- No API keys to manage (already configured)
- Your own email address for every agent
- Professional delivery with good reputation

### The function

```python
def send_email(to: str, subject: str, message: str) -> dict:
    """Send an email. Returns success/failure."""
```

Three parameters. Nothing else.

---

## Examples

### Basic notification

```pycon
>>> send_email("user@example.com", "Order shipped", "Track it: ABC123")
{'success': True, 'message_id': 'msg_124'}
```

### Verification code

```pycon
>>> send_email("bob@example.com", "Your code: 456789", "Verify your account")
{'success': True, 'message_id': 'msg_125'}
```

### Status update

```pycon
>>> send_email("team@example.com", "Build passed", "All tests green ✅")
{'success': True, 'message_id': 'msg_126'}
```

### HTML content (automatic)

```pycon
>>> send_email(
...     "alice@example.com",
...     "Weekly Report",
...     "<h1>Progress</h1><p>3 features shipped!</p>"
... )
{'success': True, 'message_id': 'msg_127'}
```

---

## Your Email Address

Every agent automatically gets an email address:

```
0x1234abcd@mail.openonion.ai
```

- Based on your public key (first 10 characters)
- Professional domain with good reputation
- Generated during `co init` or `co create`
- **Activated after authentication with `co auth`**

### Check your email address

Your email address is configured when you run `co create` or `co init` and stored in `.co/config.toml`:

```toml
[agent]
address = "0x04e1c4ae3c57d716383153479dae869e51e86d43d88db8dfa22fba7533f3968d"
short_address = "0x04e1c4ae"
email = "0x04e1c4ae@mail.openonion.ai"
email_active = false  # Becomes true after 'co auth'
```

Access it from your agent:

```python
>>> agent.email_addr
'0x04e1c4ae@mail.openonion.ai'
```

### Email Activation Lifecycle

1. **Generated** - Email address created during `co init` or `co create`
2. **Activation Prompt** - You'll be asked "Would you like to activate your agent's email now?"
3. **Active** - Email is fully functional after authentication

#### Two ways to activate:

**Option 1: Immediate activation** (recommended)
```bash
$ co init
...
📧 Agent email: 0x1234abcd@mail.openonion.ai (inactive)

💌 Your agent can send emails!
Would you like to activate your agent's email now? [Y/n]: y
✨ Email activated! Your agent can now send emails.
```

**Option 2: Activate later**
```bash
$ co auth  # Run this anytime to activate
```

To check your email status:
```bash
$ cat .co/config.toml | grep email
email = "0x04e1c4ae@mail.openonion.ai"
email_active = true  # true = active, false = inactive
```

### Want a custom name?

Upgrade to a custom email for $0.99:

```
mybot@mail.openonion.ai
ai-assistant@mail.openonion.ai
support@mail.openonion.ai
```

---

## Return Values

### Success

```python
{
    'success': True,
    'message_id': 'msg_123',
    'from': '0x1234abcd@mail.openonion.ai'  # Your agent's email
}
```

### Failure

```python
{
    'success': False,
    'error': 'Rate limit exceeded'
}
```

Common errors:
- `"Rate limit exceeded"` - Hit your quota
- `"Invalid email address"` - Check the recipient
- `"Authentication failed"` - Token expired, run `co auth`
- `"Email not activated"` - Run `co auth` to activate
- `"Not in a ConnectOnion project"` - Run `co init` first

---

## Using with an Agent

Give your agent the ability to send emails:

```python
from connectonion import Agent, send_email

# Create an agent with email capability
agent = Agent(
    "customer_support",
    tools=[send_email],
    instructions="You help users and send them email confirmations"
)

# The agent can now send emails autonomously
response = agent("Send a welcome email to alice@example.com")
# Agent sends: send_email("alice@example.com", "Welcome!", "Thanks for joining...")
```

### Real-world agent example

```python
from connectonion import Agent, send_email
import time

def check_system_status() -> dict:
    """Check if the system is running properly."""
    cpu_usage = 95  # Simulated high CPU
    return {"status": "warning", "cpu": cpu_usage}

# Create monitoring agent
monitor = Agent(
    "system_monitor",
    tools=[check_system_status, send_email],
    instructions="Monitor system health and alert admin@example.com if issues"
)

# Agent checks system and sends alerts
monitor("Check the system and alert if there are problems")
# Agent will:
# 1. Call check_system_status() 
# 2. See high CPU (95%)
# 3. Call send_email("admin@example.com", "Alert: High CPU", "CPU at 95%...")
```

## Complete Example

Here's a real-world example sending different types of emails:

```python
from connectonion import send_email

# Welcome email
result = send_email(
    "new_user@example.com",
    "Welcome to our platform!",
    "We're excited to have you. Check out our docs to get started."
)
print(f"Welcome email: {result['success']}")

# Alert notification
result = send_email(
    "admin@example.com",
    "🚨 High CPU usage detected",
    "Server CPU at 95% for the last 5 minutes"
)
print(f"Alert sent: {result['success']}")

# Daily report
result = send_email(
    "team@example.com",
    "Daily Summary",
    """
    <h2>Today's Metrics</h2>
    <ul>
        <li>Users: 1,234</li>
        <li>Revenue: $5,678</li>
        <li>Uptime: 99.9%</li>
    </ul>
    """
)
print(f"Report sent: {result['success']}")
```

---

## The Details

### Quotas

- **Free tier**: 100 emails/month
- **Plus tier**: 10,000 emails/month ($29.90/mo)
- **Pro tier**: 50,000 emails/month ($200/mo)

Check your remaining quota:
```python
from connectonion import get_agent_info
info = get_agent_info()
print(f"Email quota: {info.get('email_quota_remaining', 'Unknown')} remaining")
```

### Rate Limiting

Automatic rate limiting prevents abuse:
- Returns `{'success': False, 'error': 'Rate limit exceeded'}`
- Resets monthly
- No configuration needed

### Content Types

- **Plain text**: Just send a string
- **HTML**: Include HTML tags, automatically detected
- **Mixed**: HTML with plain text fallback

### From Address

- **Free tier**: `0x{your_key_prefix}@mail.openonion.ai` (your unique address!)
- **With custom name**: `yourname@mail.openonion.ai` ($0.99 one-time)
- **Verified domain**: `mail.openonion.ai` (SPF/DKIM configured)

**How it works**:
- Your agent's email is the first 10 characters of your public key
- Example: `0x6fdb2d9e@mail.openonion.ai` (clean format, no name labels)
- This is YOUR unique sender address - recipients see emails coming directly from YOUR agent
- Each agent has their own unique email address based on their key

### Behind the Scenes

- Email address configured during `co create` or `co init`
- Stored in `.co/config.toml` for your project
- Uses Resend API for delivery via `mail.openonion.ai` domain
- Automatic retry on temporary failures
- Logs all emails for debugging
- SPF/DKIM configured for deliverability

### Troubleshooting

#### Email not sending?

1. **Check activation status**:
   ```bash
   cat .co/config.toml | grep email_active
   # Should show: email_active = true
   ```
   If false, run `co auth` to activate.

2. **Check for errors**:
   ```python
   result = send_email("test@example.com", "Test", "Testing")
   if not result['success']:
       print(f"Error: {result['error']}")
   ```

3. **Common fixes**:
   - `co auth` - Refresh authentication token
   - `co init` - Initialize project if missing `.co` directory
   - Check internet connection

4. **Test directly**:
   ```python
   from connectonion import send_email
   result = send_email("your-email@example.com", "Test", "If you get this, it works!")
   print(result)
   ```

#### Debug mode

See what's happening under the hood:

```python
import os
os.environ['CONNECTONION_DEBUG'] = '1'

from connectonion import send_email
result = send_email("test@example.com", "Debug Test", "Testing with debug")
# Will show detailed API calls and responses
```

---

## Philosophy

**One function, one purpose**: Send an email

No templates to learn. No configuration files. No complex APIs.

Just `send_email(to, subject, message)`.

Keep simple things simple.