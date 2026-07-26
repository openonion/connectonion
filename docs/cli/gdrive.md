# Google Drive CLI (co gdrive)

List, search, download, and upload Drive files from the terminal — the same
Drive access your agents get from the [GDrive tool](../useful_tools/gdrive.md),
as a command.

## Quick Start

```bash
# Connect your Google account (one-time)
co auth google

# See what changed recently (the zero-arg default)
co gdrive

# Download file #3 from the listing
co gdrive get 3

# Upload something
co gdrive put report.pdf
```

That's the whole surface. Everything below is detail.

## Setup

`co gdrive` needs a connected Google account with the Drive scope:

```bash
co auth google
```

Drive was added to the requested scopes **after** Gmail and Calendar. If you
authorized before that, run `co auth google` once more — a token refresh
cannot widen scopes, so an older token has everything except Drive. The
command tells you exactly that if it happens.

## Commands

### `co gdrive` — Recent files

```bash
co gdrive                # 20 most recently modified
co gdrive list -n 50
```

Files are numbered. **Numbers mean your last listing** — `co gdrive get 3`
downloads the third row of the table you just saw. Running `co gdrive` again
renumbers.

Trashed files are excluded.

### `co gdrive search <query>` — Find by name

```bash
co gdrive search report
co gdrive search "Q3 budget" -n 5
```

One caveat worth knowing: Drive matches **word prefixes, not any substring**.
On a file named `HelloWorld`, searching `Hello` matches and `World` does not.
That is the API's behavior, not ours.

### `co gdrive get <#>` — Download

```bash
co gdrive get 3                       # into the current directory
co gdrive get 3 --to ~/Downloads      # into a directory
co gdrive get 3 --to notes.md         # to an exact path
co gdrive get 1A2b3C4d5E6f7G8h        # by full file id
```

Google Docs, Sheets, and Slides have no file bytes of their own, so they are
**exported** on the way down and get the matching extension:

| In Drive | Downloads as |
|---|---|
| Google Doc | Markdown (`.md`) |
| Google Sheet | CSV (`.csv`, first sheet) |
| Google Slides | PDF (`.pdf`) |
| Google Drawing | PDF (`.pdf`) |

Everything else downloads byte-for-byte. Folders and Forms have no export
format at all — the command says so rather than writing a broken file.
Shortcuts resolve to whatever they point at.

### `co gdrive put <path>` — Upload

```bash
co gdrive put report.pdf
co gdrive put ./out/report.pdf --name "Q3 Report.pdf"
```

Uploads to the root of your Drive and prints the link.

### `co gdrive rm <#>` — Trash

```bash
co gdrive rm 3
```

Moves the file to the Drive trash. It is **not** permanently deleted — restore
it from drive.google.com if that was a mistake.

## Piping

In a terminal you get a Rich table with truncated columns. When output is
piped, each file is one tab-separated row of `name`, `type`, `size`, and the
**full file id**, so scripts never receive a truncated value:

```bash
co gdrive list -n 100 | cut -f4      # just the ids
co gdrive search report | cut -f1    # just the names
```

## Using it from an agent

```python
from connectonion import Agent, GDrive

agent = Agent("assistant", tools=[GDrive()])
agent.input("What did I change in Drive this week?")
```

Or call it directly:

```python
drive = GDrive()
drive.list_files(last=20)
drive.search_files("report")
drive.download("1A2b3C4d5E6f7G8h", dest="~/Downloads")
drive.upload("report.pdf")
```

## Troubleshooting

- **"Google account not connected"** → run `co auth google`.
- **"Google Drive permission missing"** → your token predates Drive support;
  run `co auth google` again to re-consent.
- **`No file #N in your last listing`** → the number is out of range or the
  listing changed; run `co gdrive` to refresh the numbering.
- **A search finds nothing you can see in Drive** → Drive matches word
  prefixes, not substrings. Try the beginning of a word in the name.

## See also

- [`co gmail`](gmail.md) — the same shape for your Gmail mailbox
- [Google Integration](../integrations/google.md) — the OAuth scopes requested
