# Synology Tool

Give an agent File Station access to a Synology NAS — list, search, download,
upload, and share files.

```python
from connectonion import Agent, Synology

agent = Agent("nas-assistant", tools=[Synology()])
agent.input("Find last month's invoices and download them to ~/Downloads")
```

## Setup

```bash
co syno login
```

Saves `SYNOLOGY_URL`, `SYNOLOGY_ACCOUNT`, `SYNOLOGY_PASSWORD` and
`SYNOLOGY_SID` to `~/.co/keys.env`. `Synology()` reads them from the
environment; you can also pass them directly:

```python
Synology(url="https://nas.local:5001", account="aaron", password="…")
```

## Methods

| Method | Does |
|---|---|
| `list_files(path=None, last=20)` | Shared folders, or one folder's contents |
| `search_files(query, path="/", last=20)` | Find files by name |
| `download(path, dest=".")` | Fetch a file to disk |
| `upload(local_path, path, overwrite=False)` | Send a file to a NAS folder |
| `share(path)` | Create a public sharing link, returns the URL |

`list_files()` and `search_files()` return dicts:

```python
{"path": "/home/a.txt", "name": "a.txt", "type": "file", "size": 1024, "modified": 1700000000}
```

Paths start with a shared folder (`/home/photos`), not a volume
(`/volume1/home/photos`).

## Sessions

DSM session ids expire after 7 days, and a duplicate login elsewhere ends them
sooner. The tool detects both and re-authenticates transparently, so an agent
never sees a session error.

## Connecting

`resolve_quickconnect(server_id)` turns a QuickConnect ID into base-URL
candidates ordered LAN → DDNS → relay, and `pick_reachable(candidates)` returns
the first that answers. The relay always works but is throttled by Synology, so
it is the last resort rather than the default.

Both are module-level functions, usable independently:

```python
from connectonion.useful_tools.synology import resolve_quickconnect, pick_reachable

url = pick_reachable(resolve_quickconnect("mynas"))
```

## No delete

`SYNO.FileStation.Delete` is permanent — DSM's recycle bin is a share-level
filesystem convention, not an API feature. The tool does not expose delete, so
an agent cannot irreversibly destroy NAS files.

## TLS

DSM ships a self-signed certificate by default, so certificate verification is
off for NAS connections. Traffic is still HTTPS.

See the [CLI docs](../cli/synology.md) for the `co syno` commands.
