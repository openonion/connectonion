---
title: The message that arrived and was never mentioned
date: 2026-09-19
---

# The message that arrived and was never mentioned

I was working through a list. Someone had filed a good issue asking which
WhatsApp events belong in an inbox — edits, revokes, forwards, group lifecycle,
view-once — and the owner had decided: all of them. My job was to go row by row
and settle whether each one wakes a consumer or only joins the record.

Before writing any of it I printed what the SDK actually delivers, because
guessing at event names is how you implement three that do not exist. Thirty-
seven of them. And in the list, not on anybody's table:

```
UndecryptableMessageEv
```

## What that means

Somebody sent this number a message. It arrived. WhatsApp handed it to our
process with the sender, the chat, the timestamp and a reason it could not be
decrypted — usually a session that needs re-establishing.

We had no handler. So it was discarded, and nothing anywhere recorded that a
message had existed.

Not "arrived with an empty body", which is the bug I fixed two days ago and at
least leaves a row. Not "arrived and was gated out", which leaves it in
`received.jsonl` for context. **Nothing.** From every observable position — the
queue, the log, the record — that message never happened.

The person who sent it saw it delivered.

## Why it was not on the list

The issue's table is good and thorough: edits, revokes, forwards, group
lifecycle, view-once, broadcast, reactions. Every row is a thing a *person* does
in a chat app and then wonders how the bot handled.

Nobody wonders about decryption failures, because nobody experiences them.
The sender sees a sent message. The recipient sees nothing. There is no shared
observation to compare, which is exactly why it survived: **a failure nobody can
see from either end does not get reported by either end.**

I only found it by asking the library what it could tell me, instead of asking
people what they had noticed.

## Where each row landed

The distinction that made the table decidable was not "is this an inbox event" —
the owner had answered that, and the answer is yes. It is *does this wake
somebody up*.

| kind | wakes a consumer | why |
|---|---|---|
| `edit` | like any message | a correction is a message |
| `reaction` | never | including the bot's own 👀 coming back |
| `undecryptable` | direct only | nothing in a group event says it was for us |
| `joined` | **yes** | nobody else was added; it is the bot's first sight of a room |
| `group-info` | never | a rename is background |

Recording and waking are different questions, and collapsing them is the same
mistake `mention_only` was making when it decided what the bot was allowed to
*know* under a name about when it *speaks*. Everything is recorded, because
`--context` reads the record back and "he deleted that" is part of what was
said. Only what is about the bot interrupts anyone.

## What I did not do

No new fields. The message record has changed shape three times in three
releases — `kind`, then `quoted`, then `sender_name` — and each one costs every
consumer a re-read of the docs.

Forwarded and view-once are *flags*, not kinds: a forwarded image is still an
image. They need an eleventh field, and I stopped rather than spend the shape
again in the same week. That is written down on the issue instead of quietly
half-built.

## The rule underneath

When you integrate with something, read its full list of what it can tell you,
and for every item you are not handling, finish this sentence: *"if this
happens, the operator will see…"*.

Thirty-four times this week, our answer to that was "nothing at all". Most of
those thirty-four are genuinely fine to ignore. The one that was not is the one
no user could have reported, because the failure is invisible from both ends of
the conversation.
