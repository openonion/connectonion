# CLI Send

Send files to another agent. They arrive byte for byte, are checked against
their sha256, and an interrupted send carries on from where it stopped.

## Quick Start

```bash
co send 0x1e85... ./C2350.MP4          # one file
co send 0x1e85... ./footage/           # a folder: the files inside it, under footage/
co receive                             # on the other machine: what arrived
```

```text
$ co send 0x1e85... ./C2350.MP4
C2350.MP4: sending 5.0 GB / 5.0 GB (100%)
C2350.MP4  5.0 GB  sha256 0e23935aa64d…  stored as 2026-11-16/C2350.MP4

$ co receive
2026-11-16/C2350.MP4  5.0 GB  from 0x29d79879…  sha256 0e23935aa64d… verified

in /home/kim/editing-agent/.co/inbox/files/
```

## What the receiver needs

- **A running Host, for a direct send.** `co ai`, `co host` or the background
  service. When there is none, small files wait on the server instead (below).
- **The sender as a contact.** A contact, a whitelisted address or an admin
  may send; anyone else is refused, even on a `trust: open` agent. Add one
  with `co trust add 0x29d7...`.
- **Reachable directly, for large files.** On the same network, or at a
  public address (`AGENT_PUBLIC_DOMAIN`, as `co deploy --to` sets up).
- **Room on its disk.** An offer that would leave less than 1 GB free is
  refused before anything is sent.

## Where files land

```
.co/inbox/files/
  2026-11-16/C2350.MP4         verified, listed by co receive
  2026-11-16/C2350-1.MP4       a second file with the same name: never overwritten
  received.jsonl               one line per file: from, name, size, sha256, path
  .partial/<sender>/           what has arrived so far of unfinished sends
```

A file appears under its date only after its size and sha256 match what the
sender offered. Bytes that do not match are deleted, not kept.

## When the receiver cannot be reached

Behind a home or office router, or with its Host stopped, the receiver cannot
take a direct send. A file of up to 10 MB then waits on the server for 7 days,
encrypted so that only the receiver can open it:

```text
$ co send 0x1e85... ./cut-notes.pdf
co send: 0x1e85d1… is not reachable directly from here: its Host is behind a router or not running.
cut-notes.pdf  2.4 MB  sha256 9c1f0e7a2b44…  waiting for the receiver, encrypted to it, for 7 days; `co receive` there takes it, and it is deleted once taken or when the days are up

$ co receive                           # on the receiving machine, any time in the next 7 days
took 2026-11-17/cut-notes.pdf from 0x29d79879…, which was waiting on the server
2026-11-17/cut-notes.pdf  2.4 MB  from 0x29d79879…  sha256 9c1f0e7a2b44… verified
```

- The server holds a box sealed to the receiver's key, and the name and sha256
  sealed the same way. It sees addresses and sizes, never a name or the
  contents.
- `co receive` takes files only from a contact, a whitelisted address or an
  admin, the same rule as a direct send. A file from anyone else stays where
  it is, and `co receive` names the sender and the day it will be deleted.
- The box proves who made it. A file the sender's key did not seal, or whose
  sha256 does not match, is deleted, not kept.
- Larger files need the receiver to be reachable directly.

## When the connection drops

The receiver keeps every byte that arrived, filed under the file's sha256.
`co send` retries by itself for a while; if it gives up, or you stop it, run
the same command again. The receiver answers with how much it already has and
the send continues from there:

```text
$ co send 0x1e85... ./C2350.MP4        # stopped at 1.2 GB
$ co send 0x1e85... ./C2350.MP4        # carries on from 1.2 GB
```

The sender hashes the file first, so a 5 GB file takes some seconds before the
first byte goes out. Change the file in between and it is a different file:
the send starts from zero.

## How it works

`co send` looks the receiver up the way `co call` does (the relay lists its
addresses, `/info` confirms one), opens the same end-to-end sealed WebSocket,
and sends a `FILE_OFFER` followed by 1 MB `FILE_CHUNK` frames. Each chunk's
signature covers its sha256, and the receiver checks the bytes against it
before writing them.

| Frame | Direction | Carries |
|---|---|---|
| `FILE_OFFER` | sender → receiver | `sha256`, `size`, `name` |
| `FILE_ACCEPTED` | receiver → sender | `received`: where to continue from |
| `FILE_CHUNK` | sender → receiver | `offset`, `chunk_sha256` (signed), `data` |
| `FILE_PROGRESS` | receiver → sender | `received` |
| `FILE_STORED` | receiver → sender | `path`, `size`, `sha256` |

## Options

```
co send <address> <path>... [--relay URL]
co receive [--json]
```
