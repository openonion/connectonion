# Gmail

Give your agents Gmail access.

## Usage

**Option 1: Import directly**

```python
from connectonion import Gmail

agent = Agent("assistant", tools=[Gmail()])
```

**Option 2: Copy and customize**

```bash
co copy gmail
```

```python
from tools.gmail import Gmail  # Your local copy
```

## Quick Start

```python
from connectonion import Agent, Gmail

gmail = Gmail()
agent = Agent("assistant", tools=[gmail])

agent.input("Show me my recent emails")
agent.input("Find emails from alice@example.com")
```

## Setup

```bash
co auth google
```

Your agent can now read and manage Gmail.

**Switch accounts?** Run `co auth google` again to connect a different Google account.

## Agent Methods

### Reading

**`read_inbox(last=10, unread=False)`**
- Read emails from inbox
- `last`: Number of emails (default: 10)
- `unread`: Only unread emails (default: False)

**`get_sent_emails(max_results=10)`**
- Get emails you sent

**`get_all_emails(max_results=50)`**
- Get emails from all folders (inbox, sent, archive)

**`list_inbox(last=10, unread=False)`**
- Same fetch as `read_inbox()` but returns a list of dicts instead of text
- Each dict: `{id, from, subject, date, snippet, unread}`
- Use this when your code needs the data; use `read_inbox()` when an agent needs something readable

### Search

**`search_emails(query, max_results=10)`**
- Search using Gmail query syntax
- Examples: `"from:alice@example.com"`, `"subject:meeting"`, `"is:unread has:attachment"`

**`list_search(query, max_results=10)`**
- Same search, returned as dicts in the same shape as `list_inbox()`

### Content

**`get_email_body(email_id)`**
- Get full email content

**`get_email_attachments(email_id)`**
- List attachments (filename, size)

### Actions

**`send(to, subject, body, cc=None, bcc=None, attachments=None)`**
- Send plain-text mail, optionally attaching a list of files
- Agent-facing `Gmail()` instances can attach only files inside the current project; resolved symlinks cannot escape it
- Attachments have a 25 MB combined limit, enforced before file contents are read

### Drafts

Draft methods edit provider-native Gmail drafts and never send them. The
terminal's separate `co gmail draft send` command performs the final preview
and confirmation; draft sending is intentionally not exposed as a public agent
method.

**`list_drafts(last=20)`**
- List draft IDs, recipients, subjects, and attachment counts

**`create_draft(to, subject, body, cc=None, bcc=None)`**
- Create and return an unsent draft

**`get_draft(draft_id)`**
- Return recipients, body, and the exact attachment manifest

**`add_draft_attachment(draft_id, path)`**
- Stage a local project file; the draft remains unsent
- Uses the same path and 25 MB protections as `send()`

**`add_draft_link(draft_id, name, url)`**
- Append a link to a plain-text body; this does not change sharing permissions

**`remove_draft_attachment(draft_id, attachment)`**
- Remove the one-based attachment number from `get_draft()`

**`replace_draft_attachment(draft_id, attachment, path)`**
- Replace one attachment with a local project file in one draft update

**`mark_read(email_id)`**
- Mark email as read

**`mark_unread(email_id)`**
- Mark email as unread

**`archive_email(email_id)`**
- Archive email (remove from inbox)

**`star_email(email_id)`**
- Add star to email

### Labels

**`get_labels()`**
- List all Gmail labels

**`add_label(email_id, label)`**
- Add label to email

**`get_emails_with_label(label, max_results=10)`**
- Get emails with specific label

### Stats

**`count_unread()`**
- Count unread emails

### CRM

**`get_all_contacts(max_emails=500)`**
- Extract all unique contacts from emails
- Fast regex-based extraction
- Returns list of contacts with email and name

**`analyze_contact(email, max_emails=50)`**
- Analyze specific contact using LLM
- Provides relationship context, topics, patterns, tags
- Example: `gmail.analyze_contact("alice@example.com")`

## Example

```python
from connectonion import Agent, Gmail, Memory

gmail = Gmail()
memory = Memory()

agent = Agent(
    name="email-assistant",
    tools=[gmail, memory],
    system_prompt="You help manage emails and remember important info."
)

agent.input("Check unread emails and save important deadlines to memory")
agent.input("Archive all newsletter emails from this week")
```

## Customizing

Need to modify Gmail's behavior? Copy the source to your project:

```bash
co copy gmail
```

Then import from your local copy:

```python
# from connectonion import Gmail  # Before
from tools.gmail import Gmail      # After - customize freely!
```

## From the terminal

The same tool backs [`co gmail`](../cli/gmail.md), so anything your agent can do
you can do by hand:

```bash
co gmail                                            # inbox
co gmail read 3                                     # open #3, preserve unread state
co gmail read 3 --mark-read                         # explicitly mark read
co gmail send bob@example.com "Hi" "Body text"
co gmail search "from:alice@example.com is:unread"
co gmail draft create bob@example.com "Report" "Please review."
co gmail draft attach 1 report.pdf
co gmail draft preview 1
co gmail draft send 1          # previews and asks; there is no --yes
```

## See Also

- [`co gmail`](../cli/gmail.md) — the CLI wrapper
- [GDrive](gdrive.md) — the same shape for Drive files
- [Outlook](outlook.md) — the equivalent for a Microsoft account

## Troubleshooting

**Missing gmail.readonly scope**: Run `co auth google`

**Credentials not found**: Run `co auth google`
