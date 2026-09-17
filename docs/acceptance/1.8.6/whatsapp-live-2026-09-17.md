# WhatsApp live acceptance — 17 September 2026

Candidate: `main` at `8cd13f2e` plus the two fixes this run produced
(`#1559`, `#1562`), against the owner's own linked number `61410724095` in a
real group. The inbox was isolated with `CO_INBOX_HOME`, so the real
`~/.co/inbox/whatsapp` was untouched. Times are UTC.

> **This run found two defects that every automated signal had agreed was
> fine**, and both are the same shape: the listener was up, connected,
> authenticated, `check` was green and the offline suite passed, while the bot
> could not read a single message. They are recorded below in the order they
> were hit, because the order is the finding.

## Setup

- Linked companion device, paired 2026-09-17 `03:51:42`, one row in
  `whatsmeow_device`.
- Listener: `co whatsapp listen`, reconnecting from the stored session with no
  QR on every restart (verified four times across the run).
- `neonize 0.4.3.post0`, `protobuf 7.36.0`, Python 3.14, macOS.

## Defect 1 — every message dropped on protobuf 7

At `03:57:24` the owner sent two messages. Both reached WhatsApp. Neither
reached the inbox:

```
03:57:24Z event not understood (AttributeError: 'google._upb._message.FieldDescriptor' object has no attribute 'label'); skipped
03:57:24Z event not understood (AttributeError: 'google._upb._message.FieldDescriptor' object has no attribute 'label'); skipped
```

protobuf 7 removed `FieldDescriptor.label`. `_context_info` read it on the first
field of **every** message, so the per-message `except` — which exists because a
raising callback panics across neonize's Go boundary and ends the process —
turned a total incompatibility into a per-message shrug. `new/` stayed empty and
nothing else in the system disagreed.

Fixed in #1559 (prefer `is_repeated`, fall back to the old comparison, since
both protobuf generations are in the wild).

## Defect 2 — `check` called an unscanned QR a linked device

`linked()` asked whether `session.db` existed. neonize creates that file when
the client starts, before the QR is drawn and whether or not anyone scans it. A
pairing that timed out left a 160 KB database and `co whatsapp check` answered
`✓ whatsapp reachable` with `whatsmeow_device` holding **0 rows**.

Two of its own unit tests had written `session.db` as `b"linked"` — seven bytes
standing in for a paired device — so the suite agreed with the bug.

Fixed in #1559: `linked()` counts rows in `whatsmeow_device`, the table
whatsmeow writes when the phone confirms and reads to reconnect without a QR.

## Defect 3 — an @mention did not register

With both fixes running, a real @mention from the WhatsApp app arrived as:

```json
{"chat": "120363410170505910@g.us", "sender": "126121882435737@lid",
 "text": "@132754033377342 测试", "mentioned": false}
```

`132754033377342` is the account's **LID**, not a phone number. The device holds
both ids:

```
jid              = 61410724095:2@s.whatsapp.net
lid              = 132754033377342:2@lid
lid_migration_ts = 1789610758      → 2026-09-17 01:25 UTC
```

WhatsApp migrated this account six hours before the run. We matched against
`Device.JID` alone; `Device` has carried `LID` all along. A `mention_only`
channel would have stayed silent while being addressed — no error, no log line.

The live e2e suite did **not** catch this: its group test sends the *text*
`@<number>`, which lands on the "our id appears in the text" path and never on
`mentionedJID`. That gap is now written into the test's own docstring.

Fixed in #1562: identity is the set of ids the account answers to, and all three
matching paths test membership in it.

## Gates

**Gate 1 — inbound, both directions.** Same group, same sender, same text,
before and after #1562:

| time | message | `mentioned` |
|---|---|---|
| `04:21:37` | group, `@132754033377342 测试` | **false** — before the fix |
| `04:27:25` | direct, `你好` | **true** |
| `04:27:57` | group, `@132754033377342 测试` | **true** — after the fix |
| `04:33:47` | direct, `好的` | **true** |
| `04:34:13` | group, not addressed to the bot | **false** |

The last row is the one that matters as much as the mention: a group message
that does not name the bot is recorded in full and gated correctly, so
`mention_only` stays quiet without losing the message.

**Gate 2 — reconnect without a QR.** The listener was restarted four times
across the run. Every restart authenticated from the stored session; no QR was
drawn on any of them. `04:26:17Z connected as 61410724095 (also
132754033377342)` — the connect line now names both ids, which is what would
have made Defect 3 one glance instead of an investigation.

**Gate 3 — reply.** `co whatsapp reply AC8191B5B6FBC9B74C91D050653D1B3B`
returned `3EB0F30CD86CC259178E17`, recorded in `sent.jsonl` with `ok: true`, and
the message appeared in the group.

**Gate 4 — deduplication.** `3AFF29907422123D2A81` arrived twice from
WhatsApp's own retry and the second copy was dropped: `04:28:22Z duplicate
3AFF29907422123D2A81 dropped`. One file in `new/`.

**Gate 5 — `check` on a real session.** Exit 0, `✓ whatsapp reachable · listener
pid … · 0 unread`, and exit 3 naming the missing link on a session whose QR was
never scanned.

## Not exercised

- **A disconnect longer than the heartbeat.** Every restart in this run was a
  clean process restart, which exercises startup recovery, not a socket the
  server dropped. Recorded as unreached rather than worked around.
- **Non-text messages.** Two group messages arrived with `text: ""`
  (`3AFF29907422123D2A81`, `3A224C26D97D0FCC456D`). What they actually were —
  an image, a sticker, a reaction, a system event — is not recorded anywhere,
  which is the gap: `Message` has no field for kind, so a consumer receives an
  empty message and cannot tell an unsupported type from someone sending
  nothing. Not diagnosed further here; filed rather than guessed at.
- **A second number as an automated driver.** `tests/e2e/real_api/test_real_whatsapp.py`
  is built for exactly this and needs one more number linked once; until then
  the live gates above are run by a person.

## Findings filed

- #1563 — `reply` records `reply_to` and the message it sends does not quote the
  original; the ledger and the wire disagree.
- #1564 — an inbox has no way to say "seen"; a reaction verb.
- #1565 — a consumer is handed one message and no conversation.
