# GDrive

Give your agents Google Drive access — list, search, download, and upload files.

## Usage

**Option 1: Import directly**

```python
from connectonion import GDrive

agent = Agent("assistant", tools=[GDrive()])
```

**Option 2: Copy and customize**

```bash
co copy gdrive
```

```python
from tools.gdrive import GDrive  # Your local copy
```

## Quick Start

```python
from connectonion import Agent, GDrive

drive = GDrive()
agent = Agent("assistant", tools=[drive])

agent.input("What did I change in Drive this week?")
agent.input("Download the Q3 report to my Downloads folder")
```

## Setup

```bash
co auth google
```

Drive was added to the requested scopes **after** Gmail and Calendar. If you
authorized before that, run `co auth google` once more — a token refresh cannot
widen scopes, so an older token has everything except Drive.

## Methods

| Method | Returns | What it does |
|---|---|---|
| `list_files(last=20)` | `list[dict]` | Recently modified files, newest first |
| `search_files(query, last=20)` | `list[dict]` | Files whose name matches |
| `list_recent(last=20)` | `str` | Same as `list_files`, formatted for reading |
| `search(query, last=20)` | `str` | Same as `search_files`, formatted for reading |
| `download(file_id, dest=".")` | `str` | Save a file locally |
| `upload(path, name=None)` | `dict` | Send a local file to Drive |
| `delete(file_id)` | `str` | Move to trash (recoverable) |

The `list_*` methods return data for programmatic use; `list_recent`/`search`
return the readable text an agent shows a user. Each file dict is:

```python
{
    "id": "1A2b3C4d5E6f7G8h",
    "name": "Q3 Report.pdf",
    "type": "application/pdf",
    "modified": "2026-07-26T14:30:00.000Z",
    "size": 248000,          # 0 for folders, shortcuts, and native docs
    "link": "https://drive.google.com/file/d/1A2b3C4d5E6f7G8h/view",
}
```

## Three things that will surprise you

**Search matches word prefixes, not substrings.** Drive's `name contains`
operator works on token boundaries: on a file named `HelloWorld`, searching
`Hello` matches and `World` does not. An empty result does not mean the file
is absent.

**Google Docs, Sheets, and Slides are exported, not downloaded.** They have no
file bytes of their own, so `download()` converts them and adds the matching
extension:

| In Drive | Saved as |
|---|---|
| Google Doc | Markdown `.md` |
| Google Sheet | CSV `.csv` — **first sheet only** |
| Google Slides | PDF `.pdf` |
| Google Drawing | PDF `.pdf` |

Folders and Forms have no export format at all; `download()` raises with a
clear message rather than writing something unopenable. Shortcuts resolve to
whatever they point at.

**Deleting trashes.** `delete()` moves the file to the Drive trash rather than
destroying it, so an agent calling it by mistake stays recoverable from
drive.google.com.

## Complete Example

```python
from connectonion import Agent, GDrive

drive = GDrive()

# Find and fetch, programmatically
matches = drive.search_files("invoice", last=5)
for f in matches:
    print(f["name"], f["size"], f["link"])

if matches:
    drive.download(matches[0]["id"], dest="~/Downloads")

# Or hand it to an agent and let it decide
agent = Agent("assistant", tools=[drive])
agent.input("Find my most recent invoice and download it")
```

## Scope

Uses the full `https://www.googleapis.com/auth/drive` scope. The narrower
`drive.file` scope only grants access to files the app itself created — it
cannot see anything you made in the Drive web UI, which would leave
`list_files()` essentially empty.

## From the terminal

The same tool backs [`co gdrive`](../cli/gdrive.md):

```bash
co gdrive                          # 20 most recently modified
co gdrive search report
co gdrive get 3 --to ~/Downloads
co gdrive put report.pdf
```

## See Also

- [`co gdrive`](../cli/gdrive.md) — the CLI wrapper
- [Gmail](gmail.md) — the same shape for mail
- [Google Integration](../integrations/google.md) — OAuth scopes requested
