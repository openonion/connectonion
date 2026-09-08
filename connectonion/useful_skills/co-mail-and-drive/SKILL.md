---
name: co-mail-and-drive
description: Read and send mail from the user's own Gmail or Outlook account, safely stage Gmail draft attachments, send from the agent's own address, manage Outlook contacts, and work with Google Drive files — with `co gmail`, `co outlook`, `co email`, and `co gdrive`. Use when the user asks about their inbox, an email or draft they want to prepare, an attachment, a contact, or a file in Drive.
---

## Environment selection in the 1.8.4 implementation

Global `keys.env` is the default for every setting and account. To use a project
file, put `--env-file` before the command: `co --env-file /absolute/path/.env gmail
inbox`. Auth and refresh use that selected file. No project env loads implicitly;
process overrides remain explicit and provider fields are kept as whole records.
See `docs/cli/environment.md` for migration and error recovery.


# co gmail / co outlook / co email / co gdrive

The user's own mail and files, from the shell. One authorization, then plain commands.

**Read the output, not just the exit code.** All four surfaces — `co gmail`,
`co outlook`, `co email` and `co gdrive` — exit `1` when they fail (#1012 fixed
the `co email` exception). The output still carries the recovery step; read it.

## First: which mailbox does the user mean?

| Command | Whose mailbox | Ask for it when |
|---|---|---|
| `co gmail` | the user's **personal Gmail** | "my email", "my inbox", "reply to Bob" |
| `co outlook` | the user's **personal Outlook** | same, on the Microsoft account |
| `co email` | the **agent's own** address (`*@mail.openonion.ai`) | "send from the agent", "what did the agent receive" |
| `co gdrive` | the user's **Google Drive** | "my files", "that doc" |

When both mail accounts are connected and the request is ambiguous, ask which one
rather than guessing. Sending from the wrong identity is not undoable.

## Read mail

```bash
co gmail                     # bare command = inbox, 10 most recent
co gmail inbox -n 25 -u      # last 25, unread only
co gmail read 3 --listing <listing-id>              # token from the displayed listing
co gmail search "from:alice@example.com is:unread"   # -n to widen
co gmail sent -n 20
```

`co outlook` takes the same shape, and adds `download`, `scheduled`, `cancel`, `contact`:

```bash
co outlook                   # bare command = inbox
co outlook inbox -n 25 -u
co outlook read 3
co outlook search "invoice" -n 20
co outlook sent -n 20
```

Gmail search takes full Gmail query syntax (`from:`, `subject:`, `after:2026/07/01`,
`is:unread`). Outlook search is plain text over subject and body.

`co gmail read` preserves unread state by default. `co gmail read 3 --listing <listing-id> --mark-read`
requires `gmail.modify` or the full-mail grant. A known read-only grant exits
1; unknown local scope metadata lets the provider decide. Read the output and
do not describe a failed mark-read action as completed.

## Send and reply

For Gmail attachments, or whenever a person should review the final message,
use the provider-native draft workflow. Only the last command can send, and it
requires either a current review token or a real terminal's default-No confirmation:

| Intent | Command |
|---|---|
| List and number drafts | `co gmail draft list` |
| Create an unsent draft | `co gmail draft create <to> <subject> <message>` |
| Stage a local file | `co gmail draft attach <draft> <path>` |
| Stage a Drive file | `co gmail draft attach <draft> <file> --drive` |
| Append a Drive URL | `co gmail draft attach <draft> <file> --drive --link` |
| Remove a staged file | `co gmail draft remove <draft> <attachment#>` |
| Replace a staged file | `co gmail draft replace <draft> <attachment#> <source> [--drive]` |
| Inspect recipients, body, and manifest | `co gmail draft preview <draft>` |
| Review exact content and obtain a token | `co gmail draft review <draft> --json` |
| Send that approved content | `co gmail draft send <draft> --confirm <review-token> --json` |

```bash
co gmail draft list
co gmail draft create bob@example.com "Subject" "Body text"
co gmail draft list           # create prints an ID; it does not assign row 1
co gmail draft attach <draft-id> report.pdf
co gdrive list
co gmail draft attach <draft-id> 3 --drive --drive-listing <Drive-listing-id>
co gmail draft attach <draft-id> 3 --drive --drive-listing <Drive-listing-id> --link
co gmail draft remove <draft-id> 2
co gmail draft replace <draft-id> 1 corrected.pdf
co gmail draft preview <draft-id>
co gmail draft review <draft-id> --json
co gmail draft send <draft-id> --confirm <review-token> --json
```

`draft create`, `attach`, `remove`, `replace`, `preview`, and `review` never
send. Show the review to the user before sending. `--confirm` binds approval to
the account, draft, thread and current MIME content; it is not a blanket `--yes`.
Without a token, send requires a real terminal and defaults to No. Piped input
cannot approve. Declining, EOF or interruption leaves the draft intact, exits
1, and prints the review command. A stale token requires a new review.

Send submits the reviewed MIME in the same request that consumes the draft.
A concurrent Gmail edit cannot substitute different outgoing content, but may
be discarded when Gmail consumes that draft. Avoid editing it during send.
An uncertain result is recorded before submission; repeat attempts inspect a
unique Message-ID in sent mail and never blindly submit again. Keep the global
`gmail-send-attempts/` records when investigating an uncertain result.

Gmail message and draft row numbers require `--listing <listing-id>` from
the corresponding listing. Tokens bind to the provider-confirmed account and
expire after 15 minutes; only the newest 128 are retained. Full IDs work without
tokens. Other listings never retarget an older row. Bare numbers and legacy
last-listing caches are rejected. Attachment numbers come from the current
`draft preview`; Drive file numbers require `--drive-listing <Drive-listing-id>` when passed to
Gmail attach/replace, or `--listing <listing-id>` with Drive get/info/rm.
After creating a draft, prefer its printed full ID.

`--drive` attaches bytes without making a local copy. Native Docs, Sheets,
Slides, and Drawings are exported using the same formats as `co gdrive get`.
`--drive --link` appends the web URL but does not grant the recipient access or
change Drive sharing. Managed link source records live inside the Gmail draft,
survive restart, and are stripped from outgoing MIME. Ordinary body URLs are
never managed items. `co gmail draft replace <draft> <item#> <Drive-file-id>
--drive --link` can replace a file or link in one update. Preview/review numbers
cover files first, then links; use the current manifest after every edit.
Review shows source, export type, byte count, link access warnings, and duplicate
names. Unknown Drive sizes remain unknown. The limits are 25,000,000 decoded
file bytes and 35,000,000 final MIME bytes (decimal MB).

Each success and guarded failure prints a literal next command. Read it even
when output is piped; it is part of the CLI contract.

```bash
co gmail send bob@example.com "Subject" "Body text"
co gmail reply 18f2c9d0a1b2c3d4 "Sounds good, see you then."
co gmail send bob@example.com "Report" - < body.md      # '-' body reads stdin
co gmail send bob@example.com "Invoice" "Attached." --cc a@x.com --attach invoice.pdf
```

`--cc`, `--bcc` and `--attach/-a` (repeatable) work on **both** `co gmail send` and
`co outlook send`. Attachments are checked before the send: a missing file or a set
over the size limit (Gmail 25MB, Outlook 3MB) exits `1` without sending.

Outlook additionally schedules:

```bash
co outlook send bob@example.com "Nudge" "Following up" --at +2h    # +30m, +2h, or 2026-07-06T15:30:00Z
co outlook reply 3 "On it" --at +30m
co outlook scheduled          # what is queued, numbered
co outlook cancel 1           # pull one back before it goes
```

Outlook can also save an email's attachments: `co outlook download 3 --to ~/Downloads`.

## Gmail mailbox actions and incoming attachments (1.8.4 candidate)

```bash
co gmail mark <message-id> --read
co gmail mark <message-id> --unread
co gmail archive <message-id>
co gmail star <message-id>
co gmail star <message-id> --remove
co gmail label list --json
co gmail label add <message-id> <label-name-or-id>
co gmail label remove <message-id> <label-name-or-id>
co gmail attachments <message-id> --json
co gmail download <message-id> --all --to ~/Downloads --json
co gmail download <message-id> --attachment <attachment-id> --to ~/Downloads --json
co gmail unanswered --within-days 30 --last 20 --json
```

Message numbers also work with their explicit `--listing` token. Mark requires
exactly one of `--read`/`--unread`; download requires exactly one of `--all` or
`--attachment ID`. Modify operations need `gmail.modify` or the full-mail grant;
reads/downloads need Gmail read access. Missing local scopes let the API decide.
Unanswered scans one page of up to `--last` threads whose latest non-draft
message is incoming; user-started threads are included. `--exclude-automated`
opts into header-based filtering. Support/billing/invoice senders are included
by default. The result is a page, never an exact total of replies owed.

Inbox, sent, search, read, draft list/preview/review/send and every new mailbox leaf accept
`--json`. Bare `co gmail --json` is inbox JSON. Put the flag after a subcommand
when using one. Schema 1 includes `provider`, `account`, `operation`, `status`,
`complete`, `data`, `error`, and a literal `next_command`; stdout is one JSON
document. Exit 0 is success, 1 is operational/partial failure, 2 is usage error.
Normal new-command hints go to stderr. Check per-file results on partial exit.

List JSON includes `data.next_cursor`, `truncated`, and labeled estimates.
Continue with `--cursor` while repeating the same query/filter/limit. Cursors
bind account and arguments for 15 minutes; changed/expired cursors require a
fresh listing. Messages/drafts allow 1–500 items; unanswered scans 1–100 threads
and can return fewer matches. A changing live mailbox is not a frozen snapshot.

Incoming attachment IDs cover nested named files and explicit inline parts.
Use the exact ID, including a `part:` prefix when printed. Downloads require an
existing directory, preserve existing files, and suffix duplicate names. Limits
are 25 MB per file, 100 MB per invocation and 100 parts. Successful files remain
on partial failure; inspect each path/hash/error before retrying. These commands
do not send mail or change Drive sharing.

**Never send on the user's behalf without showing them the exact text and final
attachment manifest first.** Prefer `co gmail draft`; print its preview and wait
for a yes. Sending is not undoable — scheduling is, until it goes out.

## Contacts (Outlook only)

```bash
co outlook contact add "Full Name" name@example.com
co outlook contact list -n 50
co outlook contact search yifei
```

## Drive files

```bash
co gdrive                          # bare command = 20 most recently modified
co gdrive list                     # explicit form of the same listing
co gdrive search report -n 50
co gdrive info <full-file-id> --json # metadata, unknown sizes and export format; no download
co gdrive get 3 --listing <listing-id> --to ~/Downloads   # download row 3
co gdrive put report.pdf --name "Q3 report.pdf"
co gdrive rm 3 --listing <listing-id>                     # move to trash (recoverable)
```

## The two gotchas that make you report something false

**1. Gmail numbers require a frozen listing token.** Use full IDs where
possible. Inbox, search, sent, and draft lists each print a token; pass it as
`--listing <listing-id>` when using a row. Wrong accounts, expired/evicted or
corrupt listings fail with exit 1 and require relisting. Do not retry a bare
number or silently select a different row. Drive uses the same frozen-token rule; Outlook retains last-listing numbering.

**2. Piping changes the output — and you are always piping.** In a terminal these
commands print a Rich table with truncated columns and a next-step tip. Piped, they
print the untruncated form with full IDs instead:

```bash
co gmail inbox -n 50 | grep "ID:"   # full message ids, numbered 1., 2., ...
co gdrive list -n 100 | cut -f4     # name<TAB>type<TAB>size<TAB>id<TAB>row-number
co outlook contact list | cut -f2   # name<TAB>email<TAB>id
```

Never parse a truncated table column; take IDs from the piped output. The piped
form keeps the next-command tip and uses the full first Gmail ID.

Two more, for Drive specifically:

- **Drive search matches word prefixes, not substrings.** On `HelloWorld`, `Hello`
  matches and `World` does not. Empty result = say the search found nothing, not
  that the file doesn't exist.
- **Google Docs/Sheets/Slides/Drawings are exported on download** — to `.md`, `.csv`
  (first sheet only), `.pdf` and `.pdf`. Other Google-native types (folders, Forms)
  have no export format and raise "it cannot be downloaded".

## The agent's own address (`co email`)

```bash
co email                       # bare command = inbox
co email inbox -n 20 -u
co email inbox -n 1000 --offset 1000  # the next page of older mail
co email read 41               # the id in the # column, not the row position
co email send bob@example.com "Subject" "Body"
co email send bob@example.com "Subject" "Body" --from aaron@openonion.ai
co email addresses             # every address this account owns; default marked
co email sent -n 20 --to bob@example.com
co email sent read 12
```

Received inbox pages accept `-n/--last` from 1 through 1000. Use `--offset` to
skip newer rows and continue through older mail; for example, page through
offsets 0, 1000, 2000 until the command returns no rows.

It is a smaller surface than Gmail/Outlook, and the differences bite:

- **No `reply`, no `search`, no attachments, no scheduling.** To answer a message,
  send a new one with the subject you want.
- **`read` takes the id printed in the `#` column** (a server id), not "row 3", and
  currently finds it among the latest 1000 received.
- A failed send that is safe to retry prints the **full retry command**
  (`co email send ... --idempotency-key <key>`) — run it as printed so a send
  that actually went out is not duplicated.
- `co email sent` can answer "Sent mail is not available on this backend yet" —
  that is the deployment, not your command.
- `-u/--unread` is filtered locally after fetching `-n` emails, so
  `co email inbox -n 10 -u` means "unread among the last 10", not "the last 10 unread".

**Choosing the sender.** The account can own several addresses. `co email addresses`
lists them (piped: `address<TAB>default`) and marks the default; `--from` on
`co email send` picks one. Sending as an address the account does not own is a
guarded failure: the server answers 403, nothing is sent, and the message ends with
`See your addresses: co email addresses`. An account with no owned addresses gets an
empty listing (exit `0`) and the pointer `co email name <name>` to claim one.

Account admin: `co email name aaron` checks a custom address (`--buy` claims it,
from credits) and `co email upgrade plus|pro` raises the quota.

## Exit codes and what to do about them

| exit | Meaning | What to do |
|---|---|---|
| `0`, clean output | success — including legitimately empty listings | continue |
| `1` | guarded failure: account not connected, scope missing, unknown listing or attachment number, declined/rejected send, unowned `--from` address, attachment missing/too large | run the literal next command (`co auth google`, re-list/preview, correct the path) |
| `2` | usage error: unknown subcommand, missing or bad argument | fix the syntax; the error names the argument, `--help` lists the rest |

For Gmail and Drive, these are the concrete recovery routes:

| Result | Next command |
|---|---|
| Gmail listing succeeded | `co gmail read <full-message-id>` |
| Drive listing succeeded | `co gdrive get <full-file-id>` |
| Empty Gmail inbox | `co gmail search <query>` |
| Empty Gmail search | `co gmail inbox` |
| Empty Drive listing | `co gdrive search <name prefix>` |
| Empty Drive search | `co gdrive list` |
| Missing Google permission (exit 1) | `co auth google` |
| Gmail read/list failure (exit 1) | `co gmail inbox` |
| Gmail send/reply connection failure (exit 1, delivery uncertain) | `co gmail sent` |
| Drive connection or local I/O failure (exit 1) | `co gdrive list` |
| Missing upload path (exit 1) | `co gdrive put <path to an existing file>` |
| Missing Gmail read argument (exit 2) | `co gmail read --help` |
| Stale draft review (exit 1) | `co gmail draft review <draft-id> --json` |
| Uncertain draft delivery (exit 1) | `co gmail sent --json` |
| Missing Drive info argument (exit 2) | `co gdrive info --help` |
| Missing Drive get argument (exit 2) | `co gdrive get --help` |

A connection failure does not prove a write failed: inspect the provider state
before repeating a send, reply, upload, or draft creation. Provider error bodies
are omitted from CLI error messages. Outlook and agent-mail recovery behavior
is outside the Gmail/Drive audit.

The printed messages carry the current recovery step — trust them over this table.

When a command says the account is not connected:

```
❌ Google account not connected     → co auth google
❌ Gmail permission missing         → co auth google      (re-consent)
❌ Gmail draft permission missing   → co auth google      (re-consent)
❌ Google Drive permission missing  → co auth google      (re-consent)
❌ Microsoft account not connected  → co auth microsoft
❌ Microsoft <scope> permission missing → co auth microsoft
❌ No API key found (co email)      → co auth
```

"Permission missing" on a connected account means the token predates a scope added
later. A refresh **cannot widen scopes** — only re-running `co auth` fixes it.
`co auth` opens a browser and needs a human to click through: **tell the user to run
it themselves**, do not try to drive that flow.

## Done checklist

- [ ] Right mailbox chosen (asked, if both were connected)
- [ ] Exact text shown to the user before any send
- [ ] Final Gmail attachment manifest shown before any draft send
- [ ] Gmail and Drive numbers paired with their listing token; Outlook numbers from the latest listing
- [ ] IDs taken from piped output, never from a truncated table column
- [ ] `--from` address taken from `co email addresses`, never guessed
- [ ] Empty search reported as "no match", not as "does not exist"
