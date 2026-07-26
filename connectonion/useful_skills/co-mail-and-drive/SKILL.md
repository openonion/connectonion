---
name: co-mail-and-drive
description: Read and send mail from the user's own Gmail or Outlook account, manage their Outlook contacts, and list/search/download/upload their Google Drive files — with `co gmail`, `co outlook`, and `co gdrive`. Use when the user asks about *their* inbox, an email they received or want to send, a contact, or a file in their Drive.
tools:
  - Bash(co gmail *)
  - Bash(co outlook *)
  - Bash(co gdrive *)
  - Bash(co auth *)
  - read_file
---

# co gmail / co outlook / co gdrive

The user's **own** mail and files, from the shell. One authorization, then plain commands.

## First: which mailbox does the user mean?

| Command | Whose mailbox |
|---|---|
| `co gmail` | the user's **personal Gmail** |
| `co outlook` | the user's **personal Outlook** |
| `co email` | the **agent's own** address (`*@mail.openonion.ai`) — a different thing |

If the user says "my email", "check my inbox", "reply to Bob" → `co gmail` or `co outlook`.
If they say "send from the agent" or mention their agent's address → `co email`.
When both accounts are connected and it's ambiguous, ask which one rather than guessing.

## Read mail

```bash
co gmail                     # 10 most recent
co gmail inbox -n 25 -u      # last 25, unread only
co gmail read 3              # open #3, marks it read
co gmail search "from:alice@example.com is:unread"
```

`co outlook` takes exactly the same shape (`inbox`, `read`, `reply`, `send`, `sent`, `search`).

**Numbers mean the last listing you printed.** `read 3` opens row 3 of the table
you just showed. If you list again, the numbering changes. Never carry a number
across two listings — re-list, then read.

Gmail search takes full Gmail query syntax (`from:`, `subject:`, `after:2026/07/01`,
`is:unread`). Outlook search is plain text over subject and body.

## Send and reply

```bash
co gmail send bob@example.com "Subject" "Body text"
co gmail reply 3 "Sounds good, see you then."
```

A body of `-` reads stdin — use it for anything long or multi-line:

```bash
co gmail send bob@example.com "Report" - < body.md
```

Outlook additionally supports attachments and scheduling:

```bash
co outlook send bob@example.com "Invoice" "Attached." --attach invoice.pdf
co outlook send bob@example.com "Nudge" "Following up" --at +2h
```

**Never send on the user's behalf without showing them the exact text first.**
Draft it, print it, wait for a yes. Sending is not undoable.

## Contacts (Outlook)

```bash
co outlook contact add "Full Name" name@example.com
co outlook contact list
co outlook contact search yifei
```

## Drive files

```bash
co gdrive                          # 20 most recently modified
co gdrive search report
co gdrive get 3 --to ~/Downloads   # download row 3
co gdrive put report.pdf           # upload
co gdrive rm 3                     # move to trash (recoverable)
```

Same numbering rule as mail: numbers mean the last listing.

Two things worth knowing before you report a result:

- **Drive search matches word prefixes, not substrings.** On `HelloWorld`,
  searching `Hello` matches and `World` does not. If a search comes back empty,
  say that rather than concluding the file doesn't exist.
- **Google Docs/Sheets/Slides get exported on download** — to `.md`, `.csv`
  (first sheet only), and `.pdf` respectively. Folders and Forms cannot be
  downloaded at all.

## Piping — always do this when you need the data

In a terminal these commands print a table with truncated columns. When output is
piped they print full IDs instead. **You are always piping**, so you get the
untruncated form for free:

```bash
co gdrive list -n 100 | cut -f4     # just the file ids
co gmail inbox -n 50 | grep "ID:"   # full message ids
```

Never parse a truncated table column. If you need an ID, take it from the piped
output.

## When a command says it's not connected

```
❌ Google account not connected     → co auth google
❌ Gmail permission missing         → co auth google   (re-consent)
❌ Google Drive permission missing  → co auth google   (re-consent)
❌ Microsoft ... permission missing → co auth microsoft
```

"Permission missing" on a connected account means the token predates a scope
that was added later. A token refresh **cannot widen scopes** — only re-running
`co auth` fixes it.

`co auth` opens a browser and needs the user to click through. **Tell the user to
run it themselves**; do not try to drive that flow.
