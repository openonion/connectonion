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

Each result prints a next command, including when output is piped.

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
List and search share their numbering cache. An empty result clears the old
numbers; it does not leave an earlier row available for `get` or `rm`.

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
format at all — the command fails rather than writing a broken file.
Shortcuts resolve to whatever they point at.

To stage a Drive file directly into an unsent Gmail draft, keep the current
Drive listing and use its row number:

```bash
co gmail draft list               # select an existing draft independently
co gdrive list -n 20
co gmail draft attach 1 3 --drive
co gmail draft attach 1 3 --drive --link
```

The first form reads the file into the Gmail draft without writing a local
copy. The link form changes neither Drive content nor sharing permissions.

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
piped, each file is one tab-separated row of `name`, `type`, `size`, the
**full file id**, and the **row number** used by `get`. The original four
columns keep their positions; the row number is column five:

```bash
co gdrive list -n 100 | cut -f4      # just the ids
co gdrive search report | cut -f1    # just the names
```

These commands also print a final tip line, which is not a file row. If parsing
rows, filter for five tab-separated fields first:

```bash
co gdrive list | awk -F '\t' 'NF == 5 { print $4 }'
```

The tip names the fifth column as the source of the number for `co gdrive get`.

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

| Exit / result | Recovery command |
|---|---|
| 0, listing or search results | `co gdrive get <# from this listing>` |
| 0, empty search | `co gdrive list` |
| 1, missing permission | `co auth google` |
| 1, unknown row or unreadable cache | `co gdrive list` |
| 1, missing upload file | `co gdrive put <path to an existing file>` |
| 1, provider, connection, or local I/O failure | `co gdrive list` |
| 2, missing download argument | `co gdrive get --help` |

Provider error bodies are omitted. A lost upload response does not establish
that the upload failed. Inspect the latest listing before uploading again to
avoid duplicates. The printed recovery command remains visible through pipes.

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
