# gmail_plugin

Email approval and CRM sync for Gmail operations.

## Quick Start

```python
from connectonion import Agent, Gmail
from connectonion.useful_plugins import gmail_plugin

gmail = Gmail()
agent = Agent("assistant", tools=[gmail], plugins=[gmail_plugin])

agent.input("Send email to alice@example.com")
# ┌─ Email to Send ─────────────────┐
# │ To: alice@example.com           │
# │ Subject: Hello                  │
# │                                 │
# │ Message body...                 │
# └─────────────────────────────────┘
# Send this email?
```

## Features

1. **Email Approval** - Preview and approve before sending
2. **CRM Sync** - Auto-update contact's last_contact date

## Approval Options

- **Yes, send it** - Send once
- **Auto approve emails to '{recipient}'** - Auto-approve this recipient
- **Auto approve all replies this session** - Auto-approve replies
- **Auto approve all emails this session** - Auto-approve everything

## Events

| Handler | Event | Purpose |
|---------|-------|---------|
| `check_email_approval` | `before_each_tool` | Prompt approval before send |
| `sync_crm_after_send` | `after_each_tool` | Update CRM after send |

## Session Data

- `agent.current_session['gmail_approved_recipients']` - Set of approved recipients
- `agent.current_session['gmail_approve_replies']` - Auto-approve replies flag
- `agent.current_session['gmail_approve_all']` - Auto-approve all flag

## CRM Integration

After sending, the plugin auto-updates:
- `last_contact` → Today's date
- `next_contact_date` → Cleared
