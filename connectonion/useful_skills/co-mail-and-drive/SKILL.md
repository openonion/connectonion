---
name: co-mail-and-drive
description: Read and send mail from the user's own Gmail or Outlook account, send from the agent's own address, manage their Outlook contacts, and list/search/download/upload their Google Drive files — with `co gmail`, `co outlook`, `co email`, and `co gdrive`. Use when the user asks about *their* inbox, an email they received or want to send, a contact, or a file in their Drive.
---

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
co gmail read 3              # open #3 from the last listing
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

`co gmail read` marks the mail read only when the token carries the `gmail.modify`
scope; with read-only + send scopes it prints the body and leaves it unread. It says
which happened — repeat what it says, don't assume.

## Send and reply

```bash
co gmail send bob@example.com "Subject" "Body text"
co gmail reply 3 "Sounds good, see you then."
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
Gmail has no download command — there is no way to save a Gmail attachment from this CLI.

**Never send on the user's behalf without showing them the exact text first.**
Draft it, print it, wait for a yes. Sending is not undoable — scheduling is, until
it goes out.

## Contacts (Outlook only)

```bash
co outlook contact add "Full Name" name@example.com
co outlook contact list -n 50
co outlook contact search yifei
```

## Drive files

```bash
co gdrive                          # bare command = 20 most recently modified
co gdrive search report -n 50
co gdrive get 3 --to ~/Downloads   # download row 3
co gdrive put report.pdf --name "Q3 report.pdf"
co gdrive rm 3                     # move to trash (recoverable)
```

## The two gotchas that make you report something false

**1. Numbers mean your last listing.** `read 3` / `get 3` resolve against the
numbering of the listing you just printed, cached in `~/.co/gmail_last_inbox.json`,
`~/.co/outlook_last_inbox.json`, `~/.co/gdrive_last_list.json`. List again and the
numbers move. Two consequences:

- Never carry a number across two listings — re-list, then act.
- Only `inbox`, `search` (and `outlook scheduled`) write the cache. `sent` does
  **not**: after `co gmail sent`, `read 1` still opens row 1 of the older inbox listing.
- A number that isn't in the cache gets `No email #N in your last listing` and exit
  `1` rather than a silently wrong email. Re-list and retry.

**2. Piping changes the output — and you are always piping.** In a terminal these
commands print a Rich table with truncated columns and a next-step tip. Piped, they
print the untruncated form with full IDs instead:

```bash
co gmail inbox -n 50 | grep "ID:"   # full message ids, numbered 1., 2., ...
co gdrive list -n 100 | cut -f4     # name<TAB>type<TAB>size<TAB>id
co outlook contact list | cut -f2   # name<TAB>email<TAB>id
```

Never parse a truncated table column; take IDs from the piped output. The piped
form keeps the "Read one with: co gmail read <#>" tip (#1011) — the row numbers
are still what `read` wants.

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
offsets 0, 1000, 2000 until the command returns no rows. A full page prints the
exact next-page command; use it as shown instead of calculating the offset.

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
| `1` | guarded failure: account not connected, scope missing, unknown listing number, rejected send, unowned `--from` address, attachment missing/too large | the message names the fix (`co auth google`, `co email addresses`, re-list, correct the path) |
| `2` | usage error: unknown subcommand, missing or bad argument | fix the syntax; the error names the argument, `--help` lists the rest |

The printed messages carry the current recovery step — trust them over this table.

When a command says the account is not connected:

```
❌ Google account not connected     → co auth google
❌ Gmail permission missing         → co auth google      (re-consent)
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
- [ ] Numbers used from the listing printed immediately before the action
- [ ] IDs taken from piped output, never from a truncated table column
- [ ] `--from` address taken from `co email addresses`, never guessed
- [ ] Empty search reported as "no match", not as "does not exist"
