# Outlook

Give your agents Outlook access via Microsoft Graph API.

## Usage

**Option 1: Import directly**

```python
from connectonion import Outlook

agent = Agent("assistant", tools=[Outlook()])
```

**Option 2: Copy and customize**

```bash
co copy outlook
```

```python
from tools.outlook import Outlook  # Your local copy
```

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

Microsoft refresh tokens stay encrypted in oo-api; the local client keeps only
connection metadata and obtains short-lived access tokens on demand.

Your agent can now read and manage Outlook emails.

**Switch accounts?** Run `co auth microsoft` again to connect a different Microsoft account.

**Prefer the terminal?** The same functions are available as
[`co outlook`](../cli/outlook.md) commands (`inbox`, `read`, `send`, `reply`,
`sent`, `search`, `scheduled`).

## Agent Methods

### Reading

**`read_inbox(last=10, unread=False)`**
- Read emails from inbox
- `last`: Number of emails (default: 10)
- `unread`: Only unread emails (default: False)

**`list_inbox(last=10, unread=False)`**
- Programmatic counterpart of `read_inbox()` — returns a list of dicts
  (`id`, `from`, `from_name`, `subject`, `date`, `snippet`, `unread`)
  instead of a formatted string. Used by the `co outlook` CLI.

**`get_sent_emails(max_results=10)`**
- Get emails you sent

**`get_email_body(email_id)`**
- Get full email content with headers

### Search

**`search_emails(query, max_results=10)`**
- Search using Microsoft Graph search
- Examples: `"quarterly report"`, `"meeting notes"`, `"invoice"`

### Sending

**`send(to, subject, body, cc=None, bcc=None, attachments=None, send_at=None)`**
- Send email via Microsoft Graph API, now or scheduled
- `to`: Recipient email (comma-separated for multiple)
- `subject`: Email subject
- `body`: Email body (plain text)
- `cc`: Optional CC recipients
- `bcc`: Optional BCC recipients
- `attachments`: Optional list of local file paths (images, screenshots,
  PDFs, etc. — Graph sendMail limit is ~3MB total)
- `send_at`: Optional UTC ISO time (e.g. `"2026-07-06T15:30:00Z"`) —
  Exchange holds delivery until then (deferred send, works with just the
  `Mail.Send` scope)

```python
outlook.send(
    "alice@example.com", "Report", "See attached.",
    attachments=["report.pdf", "screenshot.png"],
    send_at="2026-07-06T15:30:00Z",
)
```

**`reply(email_id, body, send_at=None)`**
- Reply to an existing email (threaded), now or scheduled
- `body` is plain text — paragraphs (blank-line separated) convert to HTML
  `<p>` blocks and single newlines to `<br>`, with HTML characters escaped,
  so replies keep their formatting in Outlook
- `send_at`: Optional UTC ISO time — Exchange holds delivery until then

### Scheduled sends

**`get_scheduled(max_results=25)`**
- List emails waiting for scheduled delivery (deferred-send drafts)
- Returns dicts with `id`, `subject`, `to`, `send_at` (UTC ISO)

**`cancel_scheduled(email_id)`**
- Cancel a scheduled email by deleting its deferred draft before delivery
- Works on personal outlook.com accounts; some Exchange work/school
  tenants reject the delete with 403 — there, use Outlook's "Cancel Send"

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

**Connection not found**: Run `co auth microsoft`

**Authorization expired**: oo-api refreshes access tokens automatically. If it
asks for interaction, run `co auth microsoft` again.
