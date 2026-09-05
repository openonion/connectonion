# DD-063: An inbound channel is one directory and three verbs

**Status:** Proposed

**Date:** 2026-09-02

**Related:** [Issue #1389](https://github.com/openonion/connectonion/issues/1389),
[Issue #1310](https://github.com/openonion/connectonion/issues/1310),
[Issue #349](https://github.com/openonion/connectonion/issues/349),
[Issue #352](https://github.com/openonion/connectonion/issues/352),
[053 One browser protocol, native coding adapters](053-oip-only-browser-and-native-coding-adapters.md)

## Context

A deployed Agent can be woken by an OIP peer holding an Ed25519 key, or by a
clock entry in `.co/schedule.yaml`. Nobody in Feishu, Telegram, WhatsApp or
Slack can reach it. Seven inbound-channel issues exist and none has code.

This decision went through three shapes in one day, and the first two are
recorded because their failure is the argument for the third.

**Shape one: a listener inside the Host.** A lifespan beside the relay and
the schedule, authorizing a `provider:tenant:sender` principal through the
trust system, staging into `.co/inbox.sqlite3`, calling `input_handler`.
Correct, and heavy: it changes the session record, the trust system, the
dashboard, and reserves an approval-ownership change in OIP. It also decides
things a channel should not decide, such as which human may command the
Agent, when the product assumption is that an Agent has a handful of users
and the channel's owner is the Agent's owner.

**Shape two: a listener that is an OIP client.** A separate process holding
a small allowlist and calling `connect(address).input()`. Nothing in the Host
changes. But it still binds the channel to one consumer, ConnectOnion's own
Agent, and every other consumer (Claude Code, Codex, a shell script) needs a
mode of its own.

**Shape three** is below. It stops designing consumers.

The field evidence that shaped it, all from 2026: OpenClaw dedupes inbound
messages in a 20-minute in-process cache and replayed one Telegram message
about fifty times after an LLM outage (openclaw#58611); it flattened contact
names and group titles into the prompt until Imperva showed they carried
injected instructions (fixed in 2026.4.23); its default let every DM share
one session, which its docs now warn against. Claude Code's channels went the
other way: an MCP server, one notification, one tag, gating at the edge, no
daemon, so messages sent while the session is down are lost. Every platform
surveyed delivers at least once, wants an acknowledgement within about three
seconds, retries, and documents a message id to dedupe on. Maildir solved
"many writers, many readers, no locks, crash-safe" for mail in 1995 with a
directory and `rename(2)`.

## Decision

### The tool turns messages into files. Consumers come by themselves.

```text
~/.co/feishu/
├── inbox.jsonl      every message received, one JSON line, appended, never deleted
├── outbox.jsonl     every message sent, and every send that failed
├── new/             messages nobody has taken yet, one file each
│   └── 1756808267-om_9f8e
├── cur/             taken but not yet replied
├── log              the tool's own log: connected, reconnecting, send failed
└── listen.lock      pid of the running listener
```

The file in `new/` and the line in `inbox.jsonl` are the same bytes. The
file name is arrival time then message id, so `ls` is arrival order and a
human can match it to the platform.

Anything that can read a file is a consumer. `ls new/` is the unread count.
`tail -f inbox.jsonl` is a live view. `grep on_7c6d inbox.jsonl | jq .text`
is a history. Taking a message is `mv new/X cur/X`, which is atomic, so two
consumers never take the same one. The queue gives each message to exactly
one responder. The log lets any number of observers watch. Same data, one
consuming view and one not.

The directory is global, under `~/.co/<provider>/`, because a Feishu
application belongs to a person, not a project. A second application points
`CO_FEISHU_HOME` elsewhere, the way `GNUPGHOME` does. Two projects listening
to the same bot compete for its messages, which is right: one bot answers
once.

### Three verbs, and `reply`

```text
co feishu listen              keep the connection open; each message → inbox.jsonl + new/
co feishu receive [--timeout N]   block until new/ has one; mv to cur/; print it
co feishu send CHAT           stdin → one message
co feishu reply ID            stdin → the chat and thread that message came from
```

`listen` is the only long-running process and the only writer. `receive` and
`send` touch files and the platform API. `receive` pairs with `send` the way
`recv(2)` pairs with `send(2)`: block until one arrives, take it, return it.
`--timeout 0` does not block; a timeout exits 124, like `timeout(1)`.

`reply ID` exists so an agent carries one string. Chat and thread are read
back from `inbox.jsonl`. It refuses a second reply to the same id unless
`--again`, so a re-run loop cannot answer twice.

If `receive` finds no listener running, it starts one in the background and
records the pid in `listen.lock`. This is the `gpg-agent` convention: "you
forgot to start the daemon" is not an error a person should meet. `listen`
in the foreground is for watching, for `co deploy`, and for systemd.

Sugar, each expressible with the four verbs: `serve -- CMD` (loop `receive`,
pipe to `CMD`, `reply` with its stdout), `mcp` (a stdio MCP server exposing
`receive`, `send`, `reply` as tools and pushing Claude Code channel
notifications), `ls`, `log -f`, `check`.

### The message

```json
{"id":"om_9f8e","chat":"oc_a1b2","thread":null,"sender":"on_7c6d",
 "text":"看一下今天失败的部署","mentioned":true,"at":"2026-09-02T10:31:07Z"}
```

Identical fields on every provider. `chat` is the conversation key. The
provider payload stays out unless `listen --raw`, so contact names, group
titles and link previews never reach a prompt by accident.

### What `listen` does that no consumer sees

- Acknowledges the platform within three seconds by doing nothing but writing
  files; the agent turn is somebody else's process.
- Writes `inbox.jsonl` and `new/` before acknowledging, so a crash after the
  acknowledgement loses nothing.
- Deduplicates by message id against `inbox.jsonl`. Feishu and Meta both
  document redelivery; the dedup window is therefore the log, not a cache.
- Moves `cur/` entries older than one hour back to `new/`. A consumer that
  took a message and died does not make it vanish. This is SQS's visibility
  timeout with a directory.
- Reconnects with backoff and writes each attempt to `log`.
- Rate-limits sends per platform (Feishu: five per second per group, shared
  with every bot in it; Telegram: twenty per minute per group).
- Prints nothing on success. Fails with the missing item and the next action.

### Consumers, none of which the tool knows about

```text
co ai --listen feishu,telegram     the project's agent; co ai decides where its input comes from
claude  ←mcp←  co feishu mcp       Claude Code channel push; Codex polls receive
co feishu serve -- claude -p       one claude per message
while m=$(co feishu receive); …    any shell
tail -f ~/.co/feishu/inbox.jsonl   any observer
```

`--listen` is a `co ai` flag, not a Feishu flag, because `co ai` owns the
decision of where its input comes from. Permissions, allowlists beyond the
platform's own scope, session policy and approvals live in the consumer.

### Providers

| | receive via | direction | laptop | backend |
|---|---|---|---|---|
| feishu / lark | SDK long connection | dials out | yes | none |
| telegram | getUpdates long poll | dials out | yes | none |
| discord | Gateway WebSocket | dials out | yes | none |
| slack | Socket Mode | dials out | yes | none |
| whatsapp | Meta webhook | dials in | no | oo-api stores, CLI pulls |

Four of five need no backend, on purpose: the tool works without OpenOnion
being reachable. WhatsApp is the exception because Meta only pushes to a
public HTTPS address; oo-api receives the webhook and the CLI pulls, the
same shape `co sms` has today. Users bring their own WhatsApp Business
Account and number; OpenOnion provisioning numbers is a later product
decision. `reply` outside Meta's 24-hour window exits 3 with the reason.

Verbs are identical everywhere. Differences hide inside opaque ids and in
`check`, which validates each provider's own credentials.

## Consequences

- No Host, OIP, core or trust change. `connectonion/listen/` imports nothing
  from `core/` or `network/host/`. If the tool proves useful to people who do
  not run ConnectOnion, the directory moves to its own package unchanged.
- `co telegram send` already ships and is this contract's `send`.
- Messages are plain text on disk under a 0700 directory. Whoever can read
  the home directory can read them. `inbox.jsonl` grows; rotating it is
  `logrotate`'s job.
- Text only in the first slices. An `attachments` field is the forward path.
- `docs/PRODUCT.md` §11 "Written but not wired" carries the tool until the
  live acceptance in #1310 passes.

## Evidence required for acceptance

- **Duplicate storm.** The same message id delivered fifty times while no
  consumer runs produces one line in `inbox.jsonl`, one file in `new/`, and
  after one `receive` and one `reply`, one line in `outbox.jsonl`.
- **Crash between write and acknowledgement.** Kill `listen` after the file
  exists and before the acknowledgement; the platform redelivers; the second
  copy is dropped.
- **Consumer death.** `receive` takes a message; the consumer is killed; after
  one hour `listen` returns it to `new/`; the next `receive` gets it.
- **Two consumers.** Two `receive` loops against one directory never print
  the same id.
- **Three seconds.** The Feishu handler returns within the deadline while
  `new/` holds a thousand files.
- **Silence.** `listen` writes nothing to stdout on a clean hour of traffic.

## Rejected alternatives

- **A listener inside the Host with trust integration** (shape one): correct
  and heavy, and it decides who may command the Agent, which is not the
  channel's decision.
- **A listener that is an OIP client** (shape two): binds the channel to one
  consumer; every other consumer needs a mode.
- **A log with a cursor instead of `new/`**: fewer files, more concepts;
  needs a lock and an offset, and two consumers race.
- **`receive` deletes instead of moving to `cur/`**: one directory fewer, and
  a consumer crash makes a message vanish silently, which is exactly the
  case the log exists to explain.
- **`wait` as the verb**: ambiguous about whether it consumes. `receive`
  pairs with `send` and everyone knows it blocks.
- **A per-project directory**: a Feishu application is a person's, not a
  project's.
- **In-memory dedup**: openclaw#58611.
- **Baileys or any WhatsApp Web bridge**: bans on reconnect loops; official
  API only.
- **A generic listener framework**: seven providers, zero implementations.
  Same verbs, same directory layout, five small modules.
