# Gmail

Give your agents Gmail access.

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

### Search

**`search_emails(query, max_results=10)`**
- Search using Gmail query syntax
- Examples: `"from:alice@example.com"`, `"subject:meeting"`, `"is:unread has:attachment"`

### Content

**`get_email_body(email_id)`**
- Get full email content

**`get_email_attachments(email_id)`**
- List attachments (filename, size)

### Actions

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

## Troubleshooting

**Missing gmail.readonly scope**: Run `co auth google`

**Credentials not found**: Run `co auth google`
