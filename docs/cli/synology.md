# Synology CLI (co syno)

Verify, browse, search, download, upload, and audit sharing links for Synology NAS files from the
terminal — the same File Station access your agents get from the
[Synology tool](../useful_tools/synology.md), as a command.

## Quick Start

```bash
# Connect your NAS (one-time)
co syno login

# Verify read-only access and surface the TLS posture
co syno status

# See your shared folders
co syno ls

# Look inside one
co syno ls /home/photos

# Download file #3 from the listing
co syno get 3
```

Use `--json` on read-only commands when another program or agent consumes the
result. Everything below is detail.

## Setup

```bash
co syno login
```

You'll be asked for your **QuickConnect ID** — the name in
`quickconnect.to/<ID>`, found in DSM under *Control Panel → External Access →
QuickConnect* — then your DSM username and password.

If you'd rather skip QuickConnect, or it stops working, connect directly:

```bash
co syno login --url https://nas.local:5001
co syno login --url https://mynas.synology.me:5001
```

Credentials are saved to `~/.co/keys.env` and never leave your machine — a NAS
has no OAuth to broker, so there is no `co auth synology`.

DSM accounts that require a one-time 2FA code are not supported yet. Use a
suitable least-privilege account or stop rather than bypassing the account's
policy.

### How the connection is chosen

QuickConnect isn't one address, it's several, and they are not equally fast:

| Route | Speed | Works |
|---|---|---|
| LAN (`192.168.x.x`) | full gigabit | at home only |
| DDNS / forwarded port | full WAN speed | if you've forwarded ports |
| Synology relay | **throttled** | anywhere |

`co syno login` probes them in that order and remembers which one answered, so
you get the fast path at home without giving up access from a café. If the
saved address stops responding — you moved networks — run `co syno login`
again.

## Commands

### `co syno status` — Read-only connection check

```bash
co syno status
co syno status --json
```

This makes a read-only File Station request to prove the saved session or
credentials work. It also reports whether TLS certificate verification is
enabled; in 1.8.5 it is not.

### `co syno` — Shared folders

```bash
co syno                  # your shared folders
co syno ls /home         # inside one
co syno ls /home -n 50
co syno ls /home --json  # stable machine-readable envelope
```

Entries are numbered. **Numbers mean your last listing** — `co syno get 3`
downloads the third row of the table you just saw. Running `co syno` again
renumbers.

Paths always start with a shared folder, e.g. `/home/photos`, not
`/volume1/home/photos`.

### `co syno search` — Find by name

```bash
co syno search invoice
co syno search '*.raw' --in /home/photos
co syno search invoice --json
```

Matching is case-insensitive. Without glob characters (`*`, `?`) the pattern is
treated as a substring. Search walks subfolders, so scoping it with `--in` is
much faster than searching everything.

### `co syno get` — Download

```bash
co syno get 3
co syno get 3 --to ~/Downloads
co syno get /home/photos/cat.jpg
```

Takes a listing number or a full NAS path.

### `co syno put` — Upload

```bash
co syno put report.pdf /home/docs
co syno put report.pdf /home/docs --overwrite
```

Without `--overwrite`, an existing file of the same name is left alone.

### `co syno share` — Sharing link

```bash
co syno share 3
```

Creates a public File Station sharing link with no password or expiry and prints
the URL. This changes NAS state.

### `co syno shares` — Audit existing links

```bash
co syno shares
co syno shares -n 100 --json
```

Lists existing public sharing links without creating or changing them. The JSON
form preserves each link's id, path, URL, expiry, and status in a stable envelope.

### JSON contract

`status`, `ls`, `search`, and `shares` accept `--json`. Success and guarded
failure both produce exactly one JSON document with schema version `1`:

```json
{"schema_version":1,"ok":true,"command":"co syno status","data":{},"next_command":"co syno ls --json"}
```

Guarded failures exit `1` and replace `data` with an `error` object containing a
stable `code` and human-readable `message`. Syntax errors exit `2`.

## Piping

In a terminal you get a numbered table. Piped, you get tab-separated rows with
full paths, followed by one literal next-command tip. Filter data rows before
using tools such as `cut`:

```bash
co syno ls /home/photos | grep $'\t' | cut -f4
```

## There is no `co syno rm`

Deliberate. `SYNO.FileStation.Delete` deletes **permanently** — DSM's recycle
bin is a share-level filesystem convention the web UI implements, not something
the API exposes. Unlike `co gdrive rm`, a `co syno rm` could not be made
recoverable, so it isn't offered. Delete from DSM, where the recycle bin
applies.

## Use it from an agent

```python
from connectonion import Agent, Synology

agent = Agent("nas-assistant", tools=[Synology()])
agent.input("Find the invoices from last month and download them")
```

## Troubleshooting

**"Synology NAS not connected"** — run `co syno login`.

**"Could not reach your NAS on any known address"** — the saved address is
stale (you changed networks) or the NAS is off. Re-run `co syno login`, or use
`--url` with a reachable address.

**"2-step verification code required"** — this CLI does not implement the DSM
OTP exchange yet. Use a suitable least-privilege account or manage the files in
DSM; do not disable an account policy just to make the command pass.

**Certificate warnings** — DSM often ships with a self-signed certificate, and
1.8.5 does not verify the NAS certificate. Traffic is encrypted, but the CLI
does not cryptographically verify the server identity. Prefer a trusted direct
URL and treat certificate verification as an open hardening item.
