# `co wechat` — read your own WeChat history, locally (design)

Status: **working, pending verification against a real WeChat database.** The
command surface, prerequisite checks, key storage, the SQLCipher-4 decryption
engine, and `chats`/`decrypt`/`export` all land here. The decryption engine is
tested against an independent `sqlcipher`-CLI oracle (`tests/fixtures/wechat/`);
what remains unverified until the owner runs it on their own Mac is (a) obtaining
the key, which is a consented manual step, and (b) WeChat 4.1.15's exact table
schema, which `co wechat chats` is built to reveal. Tracks #3146; live
reading/sending is #1215.

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
co wechat chats               # decrypt each DB in memory; show its tables + row counts
co wechat decrypt --out DIR   # write plaintext SQLite copies you can open with any tool
co wechat export --db D --table T [--format json|md] [--out F]   # one table → JSON/Markdown
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

The decryptor is ~60 lines, in `useful_tools/wechat.py`. It is tested **against an
independent oracle, not circularly**: `tests/fixtures/wechat/encrypted.db` was
produced by the `sqlcipher` CLI (a different implementation) with a throwaway key;
our code decrypts it and plain `sqlite3` reads it back, `integrity_check=ok`. The
SQLCipher-4-default profile it uses (page 4096, kdf_iter 256000, HMAC-SHA512,
PBKDF2-HMAC-SHA512) is what WeChat 4.x uses. What the oracle cannot confirm is
WeChat 4.1.15's own table schema — so `co wechat chats` reveals the schema rather
than assuming it, and `co wechat export` is schema-agnostic (any table → JSON/MD).

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

1. **This change:** surface + `doctor` + `key set`/`key --help` + the decryption
   engine + `chats`/`decrypt`/`export`, tested against an independent oracle.
   Ships to a preview so the owner can run it on their own Mac.
2. **Consented spike (owner present):** obtain the key via the re-signed copy,
   `co wechat key set` it, `co wechat chats` to see the real schema, and check the
   last messages of one chat against WeChat.
3. **Chat-aware export:** with the real schema known, map tables to chats and
   render quotes, replies, media, voice (via `co asr`), sender names and local
   timestamps — on top of the generic `export` that already works.
4. **Incremental + REM:** re-read on a schedule, append new messages only, admit
   into REM with consent. Determine whether the key survives a WeChat restart,
   re-login or update, and if not, say so plainly instead of exporting nothing.

## What is still unverified

Two things cannot be confirmed until the owner runs it on their own Mac, and both
are surfaced by the tool rather than hidden:

- **Key acquisition** is a consented manual step (`co wechat key --help`); the tool
  stores a key you obtained but does not extract one for you.
- **WeChat 4.1.15's table schema** is unknown to us; `co wechat chats` reveals it,
  and `export` is schema-agnostic, so neither depends on a guess.

## WeChat in co rem (people from your chats)

`co wechat sync` writes your WeChat messages as inbox files under `~/.co/inbox/wechat/` (`received.jsonl`,
`own.jsonl`, `chats.json`, all 0600), in the same shape as `co whatsapp`. co rem reads them like WhatsApp and runs
`co wechat sync` itself before each read, so it always sees what WeChat for Mac has now.

```bash
co rem sources add wechat                 # every one-to-one chat: the people you talk to
co rem sources add wechat --chat <id>@chatroom   # a group too, by its id (ids in ~/.co/inbox/wechat/chats.json)
co rem start                              # shows what will be read and asks before anything is
```

`*` (the default) means every chat with one person; groups and official accounts are read only when named, so
one community's group never feeds another person's page. Only what WeChat for Mac stores locally is there:
messages since this Mac logged in, plus any history migrated from the phone.
