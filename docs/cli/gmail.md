# Gmail CLI (`co gmail`)

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

# Create, review, and then explicitly send a draft
co gmail draft create alice@example.com "Hello" "Thanks for the meeting today!"
co gmail draft list               # choose the new draft's row from this listing
co gmail draft preview 1
co gmail draft send 1
```

Use the row that matches your draft; `create` prints its full ID but does not
assign it row 1. You can use that ID directly instead of listing again.

## Setup

`co gmail` needs a connected Google account:

```bash
co auth google
```

This opens the Google OAuth flow and saves `GOOGLE_*` credentials (access
token, refresh token, scopes, email) to your project `.env` and
`~/.co/keys.env`. Tokens auto-refresh — the access token is renewed at the
start of every command, so you authorize once. Draft creation and editing need
the `gmail.modify` scope; reconnect if an older token does not have it.

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
An empty inbox or search result clears older message numbers, so a later
`read 1` cannot silently use a row from the previous listing.

A green ● marks unread.

### `co gmail read <#>` — Read one email

```bash
co gmail read 3                    # by listing number
co gmail read 18f2c9d0a1b2c3d4     # by full message id
co gmail read 3 --mark-read         # explicitly consume it
```

Prints headers in a panel and the body below it. Unread state is preserved by
default; `--mark-read` opts into changing it
(only when your token carries `gmail.modify` — a read-only token skips it).

### `co gmail reply <#> <message>` — Reply

```bash
co gmail reply 3 "Sounds good, see you then."
cat reply.txt | co gmail reply 3 -
```

Threaded — the reply goes back on the original conversation. A message of `-`
reads the body from stdin.

### `co gmail draft` — Build and review an unsent message

The draft workflow is the safe path when attachments or Drive files are
involved. Creating, attaching, removing, replacing, and previewing do not send
mail. Only `draft send` can send, and it always prints the final preview and
asks for interactive confirmation. There is no confirmation-bypass flag.

```bash
co gmail draft list
co gmail draft create alice@example.com "Report" "Please review."
co gmail draft list               # select the matching row before using a number
co gmail draft attach 1 report.pdf
co gmail draft preview 1
co gmail draft send 1
```

Drafts are numbered independently from inbox messages. A draft number means a
row from the most recent `co gmail draft list`; the mapping is cached in
`~/.co/gmail_last_drafts.json`. Attachment numbers come from `draft preview`.
A full Gmail draft ID works anywhere a draft number does.
Creating a draft does not change this numbering. An empty draft list clears it.
Answering no, ending input, or interrupting the confirmation prompt keeps the
draft, exits 1, and prints its preview command again.

Use local or Drive files without first copying Drive content to disk:

```bash
co gdrive list -n 20
co gmail draft attach 1 3 --drive          # attach Drive row 3 as bytes
co gmail draft attach 1 3 --drive --link   # append its Drive URL instead
co gmail draft remove 1 2
co gmail draft replace 1 1 corrected.pdf
co gmail draft replace 1 1 3 --drive
```

Google Docs, Sheets, Slides, and Drawings are exported with the same formats as
`co gdrive get`. A Drive link does not change the file's sharing permissions;
the recipient still needs access. The combined decoded attachment size must be
at most 25 MB.

### `co gmail send <to> <subject> <message>` — Send immediately

```bash
co gmail send alice@example.com "Report" "See notes below."
co gmail send alice@example.com "Report" - < body.txt
co gmail send a@x.com,b@y.com "Update" "Shipping today" --cc lead@x.com
co gmail send alice@example.com "Report" "Attached" -a report.pdf -a chart.csv
```

Recipients are comma-separated. `--cc` and `--bcc` take the same form. A
message of `-` reads the body from stdin. Repeat `-a`/`--attach` to attach
several files; their combined size must be at most 25 MB. Because the human
operator explicitly chooses these paths, the CLI may attach a file outside the
current project. Agent-facing `Gmail()` tools remain limited to project files.

This command sends immediately and exists for backward compatibility and
automation. Use `co gmail draft` when a human should inspect recipients, body,
and the attachment manifest before delivery.

### `co gmail sent` — Recently sent

```bash
co gmail sent
co gmail sent -n 25
```

Read-only listing; it does **not** touch the read/reply numbering.
To read a sent message, run `co gmail search in:sent`, then choose a number from
that search result.

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
co gmail draft list | cat
co gmail draft preview 1 | cat
```

The plain piped forms keep the literal next-command tip, including after
failures, so the recovery step remains visible to scripts and agents.

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

draft = gmail.create_draft("alice@example.com", "Report", "Please review.")
gmail.add_draft_attachment(draft["id"], "report.pdf")
gmail.get_draft(draft["id"])
```

## Troubleshooting

| Exit / result | Recovery command |
|---|---|
| 0, inbox or search result | `co gmail read <# from this listing>` |
| 1, missing permission | `co auth google` |
| 1, unknown message number or unreadable numbering cache | `co gmail inbox` |
| 1, send/reply connection failure | `co gmail sent` |
| 1, declined draft confirmation | `co gmail draft preview <draft ID>` |
| 2, missing read argument | `co gmail read --help` |

Read the printed cause and next command even when piping output. Provider error
bodies are omitted. A connection failure after sending can mean the response
was lost after delivery: inspect sent mail before repeating the send or reply.

- **"Google account not connected"** → run `co auth google`.
- **Missing Gmail scopes** → run `co auth google` again to re-consent.
- **`No draft #N in your last draft listing`** → run
  `co gmail draft list` and use a current number.
- **`Draft has no attachment #N`** → run `co gmail draft preview <draft>` and
  use the current manifest number.
- **A Drive link opens as access denied for the recipient** → change sharing in
  Drive yourself, or attach the file bytes with `--drive` instead of `--link`.
- **`No email #N in your last listing`** → the number is out of range or the
  listing changed; run `co gmail` to refresh the numbering.
- **Credentials found in one project but not another** → fixed in 1.3.1;
  older versions read either the project `.env` or `~/.co/keys.env`, never
  both, so a project with its own `.env` hid the Google tokens.

## See also

- [`co outlook`](outlook.md) — same surface for an Outlook mailbox
- [`co email`](email.md) — your agent's own address, no OAuth needed
- [Gmail tool](../useful_tools/gmail.md) — the full method list for agents
