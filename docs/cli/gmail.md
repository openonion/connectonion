# Gmail CLI (co gmail)

Send and read email from your Gmail account right in the terminal — the same
Gmail API access your agents get from the [Gmail tool](../useful_tools/gmail.md),
as a command.

## Quick Start

```bash
# Connect your Google account (one-time)
co auth google

# Check your inbox (the zero-arg default)
co gmail

# Read message #3 from the inbox list
co gmail read 3

# Send a message
co gmail send alice@example.com "Hello" "Thanks for the meeting today!"
```

That's the whole surface. Everything below is detail.

## Setup

`co gmail` needs a connected Google account:

```bash
co auth google
```

This opens the Google OAuth flow and saves `GOOGLE_*` credentials (access
token, refresh token, scopes, email) to your project `.env` and
`~/.co/keys.env`. Tokens auto-refresh — the access token is renewed at the
start of every command, so you authorize once.

See [Google Integration](../integrations/google.md) for the requested scopes.

## Commands

### `co gmail` — Show the inbox

With no subcommand, prints your most recent emails. Same as `co gmail inbox`.

```bash
co gmail                 # 10 most recent
co gmail inbox -n 25     # last 25
co gmail inbox -u        # unread only
```

Emails are numbered. **Numbers mean your last listing** — `co gmail read 3`
opens the third row of the table you just saw. Running `co gmail` again
renumbers.

A green ● marks unread.

### `co gmail read <#>` — Read one email

```bash
co gmail read 3                    # by listing number
co gmail read 18f2c9d0a1b2c3d4     # by full message id
```

Prints headers in a panel and the body below it, then marks the email read
(only when your token carries `gmail.modify` — a read-only token skips it).

### `co gmail reply <#> <message>` — Reply

```bash
co gmail reply 3 "Sounds good, see you then."
cat reply.txt | co gmail reply 3 -
```

Threaded — the reply goes back on the original conversation. A message of `-`
reads the body from stdin.

### `co gmail send <to> <subject> <message>` — Send

```bash
co gmail send alice@example.com "Report" "See notes below."
co gmail send alice@example.com "Report" - < body.txt
co gmail send a@x.com,b@y.com "Update" "Shipping today" --cc lead@x.com
```

Recipients are comma-separated. `--cc` and `--bcc` take the same form. A
message of `-` reads the body from stdin.

### `co gmail sent` — Recently sent

```bash
co gmail sent
co gmail sent -n 25
```

Read-only listing; it does **not** touch the read/reply numbering.

### `co gmail search <query>` — Search

Takes full Gmail query syntax, not just plain words:

```bash
co gmail search "invoice"
co gmail search "from:alice@example.com is:unread"
co gmail search "subject:meeting after:2026/07/01" -n 25
```

Matches are numbered exactly like the inbox, so `co gmail read <#>` works on
search results too.

## Piping

In a terminal you get a Rich table with truncated columns. When output is
piped, you get the plain listing with **full message ids** instead, so scripts
and agents never receive a truncated value:

```bash
co gmail inbox -n 50 | grep "ID:"
```

## Using it from an agent

The CLI wraps the same `Gmail` tool your agents use:

```python
from connectonion import Agent, Gmail

agent = Agent("assistant", tools=[Gmail()])
agent.input("Any unread mail from Alice?")
```

Or call it directly:

```python
gmail = Gmail()
gmail.list_inbox(last=10, unread=True)
gmail.list_search("from:alice@example.com")
gmail.send("alice@example.com", "Report", "See attached.")
```

## Troubleshooting

- **"Google account not connected"** → run `co auth google`.
- **Missing Gmail scopes** → run `co auth google` again to re-consent.
- **`No email #N in your last listing`** → the number is out of range or the
  listing changed; run `co gmail` to refresh the numbering.
- **Credentials found in one project but not another** → fixed in 1.3.1;
  older versions read either the project `.env` or `~/.co/keys.env`, never
  both, so a project with its own `.env` hid the Google tokens.

## See also

- [`co outlook`](outlook.md) — same surface for an Outlook mailbox
- [`co email`](email.md) — your agent's own address, no OAuth needed
- [Gmail tool](../useful_tools/gmail.md) — the full method list for agents
