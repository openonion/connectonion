# Outlook

Give your agents Outlook access via Microsoft Graph API.

## Quick Start

```python
from connectonion import Agent, Outlook

outlook = Outlook()
agent = Agent("assistant", tools=[outlook])

agent.input("Show me my recent emails")
agent.input("Send an email to alice@example.com saying hello")
```

## Setup

```bash
co auth microsoft
```

Your agent can now read and manage Outlook emails.

**Switch accounts?** Run `co auth microsoft` again to connect a different Microsoft account.

## Agent Methods

### Reading

**`read_inbox(last=10, unread=False)`**
- Read emails from inbox
- `last`: Number of emails (default: 10)
- `unread`: Only unread emails (default: False)

**`get_sent_emails(max_results=10)`**
- Get emails you sent

**`get_email_body(email_id)`**
- Get full email content with headers

### Search

**`search_emails(query, max_results=10)`**
- Search using Microsoft Graph search
- Examples: `"quarterly report"`, `"meeting notes"`, `"invoice"`

### Sending

**`send(to, subject, body, cc=None, bcc=None)`**
- Send email via Microsoft Graph API
- `to`: Recipient email (comma-separated for multiple)
- `subject`: Email subject
- `body`: Email body (plain text)
- `cc`: Optional CC recipients
- `bcc`: Optional BCC recipients

**`reply(email_id, body)`**
- Reply to an existing email

### Actions

**`mark_read(email_id)`**
- Mark email as read

**`mark_unread(email_id)`**
- Mark email as unread

**`archive_email(email_id)`**
- Move email to archive folder

### Stats

**`count_unread()`**
- Count unread emails in inbox

**`get_my_email()`**
- Get connected Microsoft email address

## Example

```python
from connectonion import Agent, Outlook, Memory

outlook = Outlook()
memory = Memory()

agent = Agent(
    name="email-assistant",
    tools=[outlook, memory],
    system_prompt="You help manage Outlook emails and remember important info."
)

agent.input("Check unread emails and save important deadlines to memory")
agent.input("Send an email to alice@example.com about the project update")
agent.input("Find all emails about the quarterly report")
```

## Customizing

Need to modify Outlook's behavior? Copy the source to your project:

```bash
co copy outlook
```

Then import from your local copy:

```python
# from connectonion import Outlook  # Before
from tools.outlook import Outlook    # After - customize freely!
```

## Troubleshooting

**Missing Microsoft Mail scopes**: Run `co auth microsoft`

**Credentials not found**: Run `co auth microsoft`

**Token expired**: Tokens auto-refresh. If issues persist, run `co auth microsoft` again.
