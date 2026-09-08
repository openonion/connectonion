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
co gmail read 3 --listing <listing-id>

# Create, review, and then explicitly send a draft
co gmail draft create alice@example.com "Hello" "Thanks for the meeting today!"
co gmail draft list               # choose the new draft's row from this listing
co gmail draft preview <draft-id>
co gmail draft send <draft-id>
```

Use the row that matches your draft; `create` prints its full ID but does not
assign it row 1. You can use that ID directly instead of listing again.

## Setup

`co gmail` needs a connected Google account:

```bash
co auth google
```

This opens the Google OAuth flow and saves `GOOGLE_*` credentials (access
token, refresh token, scopes, email) to the selected env file: global
`~/.co/keys.env` by default. Use `co --env-file /absolute/project/.env auth google`
to select another file explicitly. Tokens auto-refresh — the access token is renewed at the
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

Every listing prints a `Listing:` token. A number requires that token, for
example `co gmail read 3 --listing <listing-id>`. Full IDs need no token.
Listings are frozen for 15 minutes and bound to the provider-confirmed account.
Opening another inbox, search, sent, or empty listing cannot change an earlier
row. Up to 128 listings are retained; expired, evicted, corrupt, or mismatched
listings fail with exit 1. Relist or use a full ID. Legacy last-listing caches
are ignored; bare numbers now fail instead of choosing an ambiguous message.

A green ● marks unread.

### `co gmail read <#>` — Read one email

```bash
co gmail read 3 --listing <listing-id>                    # by listing number
co gmail read 18f2c9d0a1b2c3d4     # by full message id
co gmail read 3 --listing <listing-id> --mark-read         # explicitly consume it
```

Prints headers in a panel and the body below it. Unread state is preserved by
default; `--mark-read` opts into changing it
with `gmail.modify` or the full-mail grant. A known read-only grant exits 1;
missing local scope metadata lets the provider decide. The command never
reports success when the requested mark-read action failed.

### `co gmail reply <#> <message>` — Reply

```bash
co gmail reply 18f2c9d0a1b2c3d4 "Sounds good, see you then."
cat reply.txt | co gmail reply 18f2c9d0a1b2c3d4 -
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
co gmail draft attach <draft-id> report.pdf
co gmail draft preview <draft-id>
co gmail draft send <draft-id>
```

Draft numbers use `--listing <listing-id>` from `co gmail draft list` and
the same account/expiry rules as messages. Message tokens cannot resolve drafts.
A full Gmail draft ID works without a listing. Attachment numbers come from
`draft preview` and still refer to that draft's current attachment manifest.
Creating a draft prints its ID and does not change any frozen listing.
The ID-only cache lives in the global config directory's `gmail-listings/`;
it stores an account digest, not the account address or message contents.
Answering no, ending input, or interrupting the confirmation prompt keeps the
draft, exits 1, and prints its preview command again.

Use local or Drive files without first copying Drive content to disk:

```bash
co gdrive list -n 20
co gmail draft attach <draft-id> 3 --drive          # attach Drive row 3 as bytes
co gmail draft attach <draft-id> 3 --drive --link   # append its Drive URL instead
co gmail draft remove <draft-id> 2
co gmail draft replace <draft-id> 1 corrected.pdf
co gmail draft replace <draft-id> 1 3 --drive
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

Read-only listing with full message IDs and its own frozen listing token.
Read a sent message directly by ID, or use its row with that token. Older inbox
and search listings retain their original rows.

### `co gmail search <query>` — Search

Takes full Gmail query syntax, not just plain words:

```bash
co gmail search "invoice"
co gmail search "from:alice@example.com is:unread"
co gmail search "subject:meeting after:2026/07/01" -n 25
```

Search results use the same full-ID and `--listing` rules as the inbox.

## Piping

### Structured pages and mailbox actions (1.8.4 candidate)

```bash
co gmail inbox --json
co gmail search "in:sent" -n 25 --json
co gmail search "in:sent" -n 25 --cursor <next-cursor> --json
co gmail read <message-id> --json
co gmail draft list --json
co gmail draft preview <draft-id> --json
co gmail mark <message-id> --read
co gmail mark <message-id> --unread
co gmail archive <message-id>
co gmail star <message-id> --remove
co gmail label list --json
co gmail label add <message-id> <label-name-or-id>
co gmail label remove <message-id> <label-name-or-id>
co gmail attachments <message-id> --json
co gmail download <message-id> --all --to ~/Downloads --json
co gmail download <message-id> --attachment <attachment-id> --to ~/Downloads --json
co gmail unanswered --within-days 30 --last 20 --json
```

Every new mailbox command supports `--json`, as do inbox, sent, search, read,
draft list and draft preview. `co gmail --json` is the default inbox. JSON uses
one schema-1 envelope: `provider`, `account`, `operation`, `status`, `complete`,
`data`, `error`, `next_command`. It prints no prompts or extra stdout text.
New commands put human hints on stderr. Operational/partial failures exit 1;
invalid flags and missing arguments exit 2. A read with `--mark-read` fails when
that mutation fails. Unknown scope metadata lets the provider decide.

`data.next_cursor` continues the same account/query/filter/limit for 15 minutes.
`data.truncated` reports more candidate pages; `complete` means this requested
page or operation completed, not that the entire mailbox was fetched. Messages
and drafts allow 1–500 items; unanswered scans 1–100 threads per page and can
return fewer matches. Provider counts are estimates. Unanswered's estimate is
explicitly for candidate threads. Live pages may repeat/omit rows if mail changes.
Human listings also report whether more provider results exist.

Unanswered selects the latest non-draft message by provider timestamp, checks
that it is incoming and within the selected window, and includes conversations
you started. Exact normalized mailbox identity and provider SENT evidence avoid
substring matches and guessed aliases. `--exclude-automated` is optional and
filters Auto-Submitted and bulk/list/junk headers. Sender names such as support,
billing and invoice are not automatically filtered.

Incoming attachments include nested named files and explicitly inline parts.
Provider attachment IDs and `part:<partId>` inline identifiers are stable within
the message. Attached-message bytes are downloaded as one file; nested children
are also listed when the provider supplies them as MIME parts. Downloads require
an existing destination directory and exactly one selector: `--all` or
`--attachment ID`. Names are sanitized; collisions gain suffixes. Existing files
and symlinks are never overwritten. Private temporary files become visible only
after base64 and size checks pass. Limits: 25 MB/file, 100 MB/invocation,
100 attachments, MIME depth 30/1,000 nodes, and 40 MB per streamed API response.
Filesystems without atomic hard-link placement report a failure. Partial results
retain completed files and include each path, hash or error; inspect before retry.

Actions need `gmail.modify` or the full-mail grant. Read/list/download operations
need Gmail read access. No label creation, automatic reply, Drive sharing or
scheduled sending is added. [DD-068](../design-decisions/068-gmail-mailbox-pages-and-downloads.md)
records the transport and pagination decisions.

### Human output

In a terminal you get a Rich table with truncated columns. When output is
piped, you get the plain listing with **full message ids** instead, so scripts
and agents never receive a truncated value:

```bash
co gmail inbox -n 50 | grep "ID:"
co gmail draft list | cat
co gmail draft preview <draft-id> | cat
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
| 0, inbox or search result | `co gmail read <full-message-id>` |
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
- **Unavailable draft listing** → run
  `co gmail draft list` and use its full ID or its number with `--listing`.
- **`Draft has no attachment #N`** → run `co gmail draft preview <draft>` and
  use the current manifest number.
- **A Drive link opens as access denied for the recipient** → change sharing in
  Drive yourself, or attach the file bytes with `--drive` instead of `--link`.
- **Unavailable message listing** → relist with `co gmail inbox`, then use a
  full ID or the new token. An account mismatch cannot fall back to another list.
- **An intentional project account is no longer selected** → use
  `co --env-file /absolute/project/.env gmail inbox`. The 1.8.4 implementation
  defaults to global settings; see [environment migration](environment.md).

## See also

- [`co outlook`](outlook.md) — same surface for an Outlook mailbox
- [`co email`](email.md) — your agent's own address, no OAuth needed
- [Gmail tool](../useful_tools/gmail.md) — the full method list for agents
