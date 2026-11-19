# `co wechat` — read your own WeChat history, locally (design)

Status: **design + skeleton only.** The command surface, prerequisite checks and
key storage land in this change. Decryption and key acquisition are deferred to a
consented spike on a real machine (see "Why not more in this PR"). Tracks #3146;
live reading/sending is #1215.

## Goal

`co wechat` lets the owner read **their own** WeChat for Mac history on their own
machine. It is read-only and local: it never writes to WeChat's files, never
touches WeChat's network protocol, and nothing leaves the machine. The export is
written as Markdown/JSON under the REM notebook's sources, so REM can admit it the
same way it admits mail — after the owner's consent.

```
co wechat doctor              # are the prerequisites in place? (read-only)
co wechat key --help          # how to obtain the DB key, as a consented local step
co wechat key set x'<hex>'    # save a key you obtained, into ~/.co/keys.env
co wechat chats               # list chats from the decrypted DB        [deferred]
co wechat export <chat> [--since ...] [--all]   # export to the notebook [deferred]
```

## Where the data lives

WeChat 4.x for Mac keeps SQLite databases under:

```
~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/<account>/db_storage/
```

Reading that container triggers a macOS privacy (TCC) prompt. An unattended `find`
or `ls` there blocks on the prompt — observed twice while researching this. So the
command asks for access up front (`co wechat doctor` names the folder and tells the
owner to grant the terminal Full Disk Access) and never traverses the container in
a way that can hang a non-interactive run.

## Encryption, and why no new dependency is needed

The databases are encrypted with WCDB, which is SQLCipher 4. Decryption needs only
AES-256-CBC + HMAC-SHA512 + PBKDF2 — all provided by `cryptography`, already present
in our environment as a transitive dependency. The SQLCipher-4 page format
(16-byte salt header, per-page IV, per-page HMAC) is short enough to decrypt
page-by-page ourselves, so **`co wechat` adds no new dependency package.** This
matches the owner's explicit constraint: learn the method, don't pull in a bundle.

The decryptor is ~40 lines. It is **not** in this change, because it cannot be
tested honestly yet: there is no trusted SQLCipher implementation on hand to
validate a test fixture against, so a fixture we both encrypt and decrypt with our
own understanding would prove nothing. It lands once the spike below yields a real
encrypted DB to verify against.

## The key, as a consented manual step

The SQLCipher key is not on disk. It exists only in the running WeChat process.
On this machine WeChat is 4.1.15, with hardened runtime and SIP enabled.

- **Memory scanning no longer works** from WeChat 4.1.10 on: the raw key no longer
  sits in process memory and SQLCipher symbols are stripped. The older scan-memory
  exporters fail on 4.1.15.
- **The current method does not require disabling SIP.** Make an ad-hoc re-signed
  *copy* of WeChat, launch the copy, and capture the key with Apple's own debugger
  (`lldb`, from the Xcode Command Line Tools) at the moment it opens a database.

`co wechat` does **not** ship a turnkey key extractor. Obtaining the key:

- is driven by the owner, on their own account, with explicit consent each time;
- uses only OS tools (`codesign`, `lldb`, `python3`) — no pip package, no bundled
  binary; `co wechat key --help` prints the procedure and links the open-source
  references below;
- never re-signs or modifies the real `/Applications/WeChat.app`, only a copy;
- never happens automatically, and never because WeChat updated.

Once obtained, `co wechat key set x'<hex>'` stores it (owner-only `0600`) in
`~/.co/keys.env` as `WECHAT_DB_KEY`, and the read commands use it from there.

### Open-source references (read, not yet run or vendored)

- https://github.com/huahan111/wechat-mac-reader — re-sign a copy + `lldb`; author reports 4.1.x on macOS 26, no sudo
- https://github.com/DaneelOlivaw1/macos-wechat-export — re-signed copy + SQLCipher read, Apple Silicon
- https://github.com/robbin/wechat-exporter — a written decryption spec (page format, HMAC, WAL, acceptance)
- https://github.com/huohuoer/wechat-cli — macOS arm64 CLI, closest in shape to `co`
- https://github.com/ppwwyyxx/wechat-dump — long-standing reference implementation

## Message types to cover (export)

Text; quotes and replies; links; files; images (path or thumbnail); voice
(metadata, or ASR via `co asr`); group sender names; timestamps in the owner's
timezone.

## Privacy and account risk

- Local only. Nothing leaves the machine. Never written outside the notebook.
- `[personal]` / `[sensitive]` rules apply before anything reaches a model.
- Third-party access to WeChat data may conflict with WeChat's terms. The command
  must never write to WeChat's files and never touch its network protocol. One
  Windows backup exporter was taken down by a Tencent DMCA complaint — a reason to
  keep this strictly a local read of the owner's own data.
- Re-signing is a reverse-engineering step. It stays an explicit, consented,
  local-only action and never a default `co` behaviour.

## Acceptance (for the follow-up that adds decryption)

- On the owner's Mac, export one named chat for the last 30 days; message count and
  last message match what WeChat shows.
- A second run exports only new messages.
- `co audit "co wechat"` passes.

## Staged plan

1. **This change:** surface + `doctor` + `key set`/`key --help` + wiring + tests.
   No decryption, no extractor. Reviewable without a live WeChat.
2. **Consented spike (owner present):** obtain the key via the re-signed copy,
   decrypt one DB, check the last 10 messages of one chat against WeChat.
3. **Decryption:** land the ~40-line page decryptor with a round-trip test
   validated against the real DB from step 2; implement `chats` and `export`.
4. **Incremental + REM:** re-read on a schedule, append new messages only, admit
   into REM with consent. Determine whether the key survives a WeChat restart,
   re-login or update, and if not, say so plainly instead of exporting nothing.

## Why not more in this PR

The valuable core is small, but the two hard pieces — key acquisition and
decryption — both need a real machine, the owner's consent, and a real encrypted
DB to verify against. Writing them now would mean shipping untested security code.
This change lands everything that is honestly testable offline and documents the
rest, so the size of the remaining work is clear: roughly 40 lines of decryptor
and a documented manual key step, both landing with tests after the spike.
