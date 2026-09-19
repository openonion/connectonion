---
title: A bot that lives in the group
date: 2026-09-17
---

# A bot that lives in the group

1.8.6a1 shipped WhatsApp as an inbox provider with a sentence in its own release
notes admitting the thing had never been run against a real account. Today we
ran it. Someone typed `@` in a real group, picked the bot, and sent `测试`.

Nothing happened.

It kept not happening, five times, for five unrelated reasons, and every one of
them looked exactly the same from where the person was standing.

## Five different bugs, one symptom

The first time, the message never reached the inbox at all: protobuf 7 had
removed a field our mention-parser read on every message, so every message was
logged as "event not understood" and dropped. The second time it arrived and was
recorded `mentioned: false`, because WhatsApp had migrated the account to LID
addressing six hours earlier and the mention carried an id that shares no digits
with the phone number we were matching. Another time the pairing had quietly
never completed, and `check` said `✓ whatsapp reachable` anyway because it was
looking at a file that exists before the QR is even drawn.

Each of those took a session to diagnose. Not because any of them was subtle —
they are all two-line fixes — but because from inside the group they produce
identical evidence: *I asked the bot something and nothing happened.*

And every automated signal we had agreed nothing was wrong. The listener was
up. The socket was connected. The test suite was green. `check` was green. The
process exit codes were zero.

## The thing that was actually missing

At some point, halfway through the third of these, the owner said what turned
out to be the fix — not for any one bug, but for the shape of all of them:

> 每次你读到或者看到消息 可以先给个 reaction

React when you see it, so the sender knows it landed. Then, before you answer,
change the reaction to a different one.

I built it as a courtesy. It isn't one.

The interval between "asked" and "answered" is where a bot in a group spends
most of its life — a model thinking, a script running, someone being asked a
question. That interval had no representation at all. It rendered as nothing,
and *nothing* is also what a crashed listener renders as. There was no observable
difference between working and dead, which is why five different failures were
indistinguishable from each other and from success.

Two emoji fix that, and they fix it for everyone in the room rather than for
whoever has ssh:

- **no mark** — it never arrived, or was never recognised as addressed to us
- **👀 only** — it's queued, and nothing has picked it up
- **✍️ with no answer** — the reply path failed

That is the entire triage tree of this week's bugs, made legible from inside the
conversation, using two characters.

Here is the run that closed it out:

```
05:00:24Z  received  "@132754033377342 开始"
05:00:25Z  👀 sent as 3EB0770C79D2FE830B6672
05:06:07Z  ✍️ sent as 3EB0FBB30DD75EB564468F
           reply 3EB0C796D27ADACFDFE66A
```

## Two details that the courtesy framing would have got wrong

**Where the second mark goes.** The obvious place is right before the reply is
sent. In `co whatsapp consume` that would be wrong: there, the *command* is the
answering and can take minutes, while the send after it takes milliseconds. A
mark placed there would light up for an instant before the answer landed —
covering precisely none of the interval it exists for. It goes before the
command instead.

**What it must never cost.** The first mark runs inside the SDK's message
handler, where an exception is a Go-side panic that ends the listener. A receipt
is worth less than the process; both marks are caught and become a log line.

And the log line is not optional either. My first version logged only failures,
which meant "sent" and "never attempted" were identically silent — the exact
failure mode the feature exists to eliminate, reintroduced inside the feature.
It now logs both, with the id the platform hands back, because an id we could
not have invented is the difference between a claim and a receipt.

## What I'd take from it

When you put software in a room with people, the hard problem is not doing the
work. It is being legible while you do it. A status that lives only in a log
file is a status nobody has, and every one of this week's bugs was expensive
specifically because the system had no way to say which of several very different
things was going on.

The bot is in the group now, and when you ask it something, you can see it
thinking. The install is three commands and a QR code you scan once:

```bash
pip install --pre 'connectonion[whatsapp]'
brew install libmagic
co whatsapp listen                  # scan from the phone, once, ever
co whatsapp consume -- claude -p
```

Release notes: `docs/releases/1.8.6a2.md`. The acceptance run that found all of
this, with every timestamp and every gate: `docs/acceptance/1.8.6/whatsapp-live-2026-09-17.md`.
