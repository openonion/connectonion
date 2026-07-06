# Outlook CLI (co outlook)

Send and read email from your Outlook account right in the terminal — the same
Microsoft Graph access your agents get from the [Outlook tool](../useful_tools/outlook.md),
as a command.

## Quick Start

```bash
# Connect your Microsoft account (one-time)
co auth microsoft

# Check your inbox (the zero-arg default)
co outlook

# Read message #3 from the inbox list
co outlook read 3

# Send a message
co outlook send alice@example.com "Hello" "Thanks for the meeting today!"
```

That's the whole surface. Everything below is detail.

## Setup

`co outlook` needs a connected Microsoft account with Mail scopes:

```bash
co auth microsoft
```

This opens the Microsoft OAuth flow and saves `MICROSOFT_*` credentials
(access token, refresh token, scopes, email) to your project `.env` and
`~/.co/keys.env`. Tokens auto-refresh. If credentials or Mail scopes are
missing, any `co outlook` command tells you to run `co auth microsoft` first.
See [Microsoft Integration](../integrations/microsoft.md) for scope details.

## Commands

### `co outlook` — Show the inbox

With no subcommand, prints your most recent emails. Same as `co outlook inbox`.

```bash
co outlook
```

### `co outlook inbox` — List received email

```bash
co outlook inbox                 # last 10
co outlook inbox -n 25           # last 25  (alias: --last)
co outlook inbox -u              # only unread  (alias: --unread)
```

Unread messages are marked with a green `●`. The leftmost `#` is the email's
number — pass it to `co outlook read`. The numbering is cached (in
`~/.co/outlook_last_inbox.json`), so `read 3` still finds the right message
in a later shell session.

**Options**
- `--last, -n` — how many to show (default: 10)
- `--unread, -u` — only unread messages

### `co outlook read <#>` — Read one message

```bash
co outlook read 3
```

Prints the full body (sender, subject, date, content). Accepts the `#` from
your last listing (inbox or search) or a full Graph message ID. If your
Microsoft auth includes the `Mail.ReadWrite` scope, the message is also
marked read.

### `co outlook reply <#> <message>` — Reply

```bash
co outlook reply 3 "Sounds good, see you then."
```

Sends a threaded reply to an email from your last listing. Use `-` as the
message to read the reply body from stdin, and `--at +2h` (or a UTC ISO
time) to schedule the reply like a scheduled send.

### `co outlook send <to> <subject> <message>` — Send

```bash
co outlook send bob@example.com "Subject line" "Body text"
```

All three arguments are positional and required. `to`, `--cc`, and `--bcc`
take comma-separated addresses for multiple recipients.

**Options**
- `--cc` — CC recipients (comma-separated)
- `--bcc` — BCC recipients (comma-separated)
- `--attach, -a FILE` — attach a local file; repeat for multiple
- `--at` — schedule delivery: `+30m`, `+2h`, or a UTC ISO time

**Attachments** — screenshots, PDFs, images, anything:

```bash
co outlook send bob@example.com "Report" "See attached." \
    --attach report.pdf --attach screenshot.png
```

> Graph's `sendMail` limit is ~3MB total across attachments.

**Scheduling** — Exchange holds delivery until the time you give (deferred
send), so it works with just the `Mail.Send` scope and no extra setup:

```bash
co outlook send bob@example.com "Reminder" "Standup in 30." --at +30m
co outlook send bob@example.com "Launch" "We're live!" --at 2026-07-06T15:30:00Z
```

`+30m` / `+2h` are relative to now; anything else is taken as a UTC ISO time.
See what's queued with `co outlook scheduled`.

**Long bodies** — pass `-` as the message to read the body from stdin:

```bash
co outlook send alice@example.com "Weekly update" - < body.txt
```

### `co outlook sent` — List sent email

```bash
co outlook sent            # last 10
co outlook sent -n 25      # last 25
```

### `co outlook search <query>` — Search

```bash
co outlook search "quarterly report"
co outlook search invoice -n 25
```

Matches subject and body via Microsoft Graph search.

### `co outlook scheduled` — List scheduled sends

```bash
co outlook scheduled
```

Shows every email waiting for scheduled delivery (deferred-send drafts),
with recipient, subject, and local send time:

```
                     ⏰ Outlook — scheduled sends
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ To                          ┃ Subject                ┃ Sends at     ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ tamara.berryman@unsw.edu.au │ RE: Access to the MCIC │ Jul 07 08:00 │
└─────────────────────────────┴────────────────────────┴──────────────┘
```

The listing is read-only: Exchange locks deferred messages against API
deletion (403), so **to cancel a scheduled send, open the message in
Outlook and use its own "Cancel Send"** — it sits in Drafts until
delivery time.

## Same functions, in your agent

The CLI is a thin wrapper over the [Outlook tool](../useful_tools/outlook.md),
so anything `co outlook` does, your agent can do too:

```python
from connectonion import Agent, Outlook

outlook = Outlook()
agent = Agent("assistant", tools=[outlook])

agent.input("Check my inbox and send the report to alice@example.com")
```

Or call it directly:

```python
outlook = Outlook()
outlook.list_inbox(last=10, unread=True)
outlook.send(
    "alice@example.com", "Report", "See attached.",
    attachments=["report.pdf"],
    send_at="2026-07-06T15:30:00Z",
)
```

## Troubleshooting

- **"Microsoft account not connected"** → run `co auth microsoft`.
- **Missing Mail scopes** → run `co auth microsoft` again to re-consent.
- **Token expired** → tokens auto-refresh; if issues persist, re-run
  `co auth microsoft`.
- **`No email #N in your inbox`** → the number is out of range; run
  `co outlook inbox` to refresh the listing.
- **Cancelling a scheduled send** → not possible via API (Exchange returns
  403 once the message is locked for delivery); use Cancel Send in Outlook.
