---
title: Three reports from people using it
date: 2026-09-18
---

# Three reports from people using it

Everything in 1.8.6a4 came from someone running the bot in a real group and
noticing something wrong. Not from a roadmap, not from a test, and — this is the
part I keep having to relearn — not from any signal the software produced about
itself.

Three reports. All three were invisible to CI.

## "Who said this?"

Messages were arriving like this:

```json
{"sender": "126121882435737@lid", "text": "the price sheet is wrong"}
```

That `@lid` is WhatsApp's internal identifier. It is stable, it is correct, and
it tells a human absolutely nothing. Every consumer reading these was going to
end up building the same lookup table — we already maintain one for Lark, for
exactly this reason, and it comes up every time somebody asks "who said this?".

The thing that made this satisfying to fix: the answer was already on the disk.
`whatsmeow_contacts` had 2020 rows sitting in the session file, 857 of them
keyed by `@lid`, put there by the history sync that happens when you link a
device. We had been carrying the phone book around and printing the phone number.

So `sender_name` is a SQLite point lookup on a file we already have open. No API
call, nothing new to configure, nothing to keep in sync.

I read it fresh on every message rather than caching it, and the reasoning is
worth stating: people rename themselves. A cached name goes stale, and a stale
name in a record is *worse* than an opaque id, because it reads as
authoritative. Nobody is misled by `126121882435737@lid`.

## "It only got the last message"

```
14:31  the price sheet is still wrong
14:32  it's missing the cleaning column
14:34  @bot recompute it
```

The consumer got the third line on its own. Recompute what, with which
correction?

The bot was in the room for all three. It wrote all three to `received.jsonl`.
And then handed over one.

What I found underneath is the kind of thing I now look for specifically:
`mention_only` was doing **two jobs under one name**. Deciding *when the bot
speaks* is a politeness rule and it is correct — without it a bot answers
everything and gets muted by Tuesday. But it had also, silently, been deciding
*what the bot is allowed to know*.

Those are not the same question, and one flag was answering both. `--context 20`
separates them.

One detail that only showed up when I looked at real output: my first version
read `received.jsonl` alone, so the transcript contained what people said to the
bot and nothing the bot said back. Hand that to a model and it apologises for
not having responded, or re-answers something it answered twenty minutes ago.
A record that omits one participant isn't shorter — it's a different
conversation. `sent.jsonl` is merged in now.

## "It says it's listening and nothing arrives"

A session stopped working in production. `send` failed. `check` was green.
`listen` printed `listening` and received nothing, indefinitely.

We were subscribed to **three of neonize's thirty-seven events**.

Among the thirty-four we were not: `LoggedOutEv` — the phone unlinked this
device. `StreamReplacedEv` — another client took the session. `TemporaryBanEv`.
All arriving. All discarded.

So when the phone unlinked it, the process kept its socket, kept printing
nothing, and kept receiving nothing — because from the inside, a connection that
will never deliver again looks exactly like a quiet afternoon.

I nearly built the wrong fix here. My instinct was that `listen` should refuse
to start on a logged-out session, and I ran it first only out of habit:

```
$ co whatsapp listen
listening · …
████ ▄▄▄▄▄ █▀▀█▀█ ▀▄██  █▄█▄█ ▄▄█▀ ▀█ ▀▀ ▄▀▀▄  █▄▀▀▀█ █  █ ▄▄▄▄▄ ████
```

It shows a QR. Starting on a logged-out session already works correctly — it is
the route back. The refusal I was about to add would have broken recovery and
fixed nothing, and the only reason I know that is that I ran the command instead
of reasoning about it.

The real failure is narrower: the listener was **already running** when the
unlink happened. One that starts can offer a QR; one already connected cannot go
back and offer one.

Three events now stop it with a reason and exit 3 — the same code as a missing
credential, because it is the same category: a person must act, and no restart
helps. The rest became log lines, because a disconnection is not a failure but
it is exactly what you need to see later when someone asks whether a message
could have been missed.

## What the three have in common

None of them produced a signal. Tests green, process up, exit code 0, `check`
reporting healthy.

What found them was somebody using the software and being surprised. Which
means the bar for "is this ready" cannot be the test suite passing — it has to
include somebody actually using it, in the real place, with real messages, and
saying what they saw.

That is not a new lesson. It is just one that keeps costing us a day at a time
until it's built into how a release gets called done.
