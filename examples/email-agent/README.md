# Email Assistant Agent (Example)

A powerful email management agent example that demonstrates using ConnectOnion tools for email workflows.

## Features

- 📬 Check Inbox and summarize
- ✉️ Send Emails and replies
- 🤖 Auto-Respond based on keywords
- 🔍 Search emails by content
- 📊 Statistics summary
- ✔️ Mark emails as read

## Quick Start

```bash
cd connectonion/examples/email-agent
python agent.py
```

If running from a different CWD, ensure the repo root is on `PYTHONPATH` or use the provided `sys.path` injection in `agent.py`.

## Customize the Prompt

Edit `prompts/email_assistant.md` to change the agent's behavior and guidelines. The agent loads this markdown at startup.

## Example Commands

- "Check my emails"
- "Reply to email 1 saying I'll attend the meeting"
- "Send an email to john@example.com about the project update"
- "Search for emails about invoices"
- "Auto-respond to urgent emails"
- "Show email statistics"

## Configuration

The example uses `connectonion.send_email`, `connectonion.get_emails`, and `connectonion.mark_read` utilities.
Be sure your ConnectOnion email configuration/auth is set up (see docs below).

### Customizing Auto-Responses

Edit `auto_responses` in `EmailManager.__init__()`.

```python
self.auto_responses = {
    "meeting": "Your custom meeting response",
    "urgent": "Your custom urgent response",
}
```

### Adjusting Limits

- In `check_inbox()`, change `limit` to fetch more.
- In `search_emails()`, adjust the search window (e.g., `last=100`).

## Resources

- ConnectOnion Docs: `https://github.com/openonion/connectonion`
- Email API: `../../docs/get_emails.md`
- Send Email: `../../docs/send_email.md`

## Notes

- This example mirrors the CLI template, adapted for `examples/` usage.
- It injects the repository path for clean `import connectonion` without install.

