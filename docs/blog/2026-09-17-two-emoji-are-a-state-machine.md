---
title: Two emoji are a state machine
date: 2026-09-17
---

# Two emoji are a state machine

A bot in a group chat has one honest problem: between being asked and
answering, it looks exactly like a bot that has crashed. Minutes pass. A model
is thinking, a consumer is running, a person is being asked something. From the
group's side, all of that renders as nothing.

The fix is two reactions:

```
05:00:24Z  received  "@132754033377342 开始"
05:00:25Z  👀 on AC4F3BE8… sent as 3EB0770C79D2FE830B6672
05:06:07Z  ✍️ on AC4F3BE8… sent as 3EB0FBB30DD75EB564468F
           reply 3EB0C796D27ADACFDFE66A
```

👀 when the message enters the queue. ✍️ when an answer is actually on its way.
WhatsApp replaces a sender's previous reaction rather than stacking them, so
the pair reads as one status changing rather than two marks accumulating.

## Why two and not one

The obvious version is one "seen" marker. It does not work, and the reason is
worth stating: a marker that never changes carries no information about
whether anything is happening. Five minutes after 👀 appears, the group knows
the message arrived and knows nothing else — which is the same position they
were in before, just with a decoration.

The interval between the two marks *is* the thing being communicated. That is
the whole design.

## The part I did not expect to matter most

It is a debugger, and a better one than the log.

Three separate bugs this week were the same shape: nothing visible happened,
and every automated signal agreed everything was fine. Messages silently
dropped on protobuf 7. `check` calling an unscanned QR a linked device. An
@mention recorded as `mentioned: false` because the account had migrated to LID
addressing. Each one took a session of digging to distinguish from the others,
because the symptom — *I asked the bot and nothing happened* — was identical.

With the marks, the symptom is different in each case, from inside the chat,
with no log access:

- **no emoji** → the message never arrived, or was never recognised as
  addressed to us
- **👀 only** → it is in the queue and nothing picked it up
- **✍️ with no answer** → the reply path failed

That is the whole triage tree, visible to whoever is standing in the group
wondering why the bot is quiet.

## Where each mark goes, and why they are not symmetrical

The first is set by the listener, directly, because the listener already holds
the socket — WhatsApp allows one connection per linked device and the listener
owns it.

The second cannot be, because `co whatsapp reply` is a different process. It
goes through the same outbox spool every other outbound uses, which is what
forced the spool to start carrying a *kind*: until now a queued request was
assumed to be text.

In `consume` the second mark goes **before the command runs**, not before the
send. In a reply-by-hand there is nothing between the two, so it does not
matter; in `consume` the command *is* the answering and can take minutes, while
the send afterwards takes milliseconds. Marking after the command would light
up for the instant before the answer lands — which is the same as not marking,
and specifically fails to cover the one interval this exists for.

## Two rules it has to obey

**It never marks a message nobody addressed to us.** The bot is a participant in
other people's conversation; putting our emoji on messages that were not for us
is noise at best.

**It never costs the message or the answer.** The first mark runs inside
neonize's `MessageEv` handler, where an exception is a Go-side panic that ends
the listener — a receipt is not worth the process. The second sits in front of
the reply; a receipt that failed must not take the answer with it. Both are
caught and become a log line.

## The log line is not optional

The first version logged only failures. Which meant a reaction that was never
attempted and one that went out successfully produced identical silence — the
exact failure mode of the three bugs above, reintroduced by the feature built
to make them visible. It caught my eye because I went looking for the evidence
that it had worked and there wasn't any.

It now logs both, with the id the platform handed back:

```
👀 on AC4F3BE8… sent as 3EB0770C79D2FE830B6672
```

`sent as <id>` is the difference between a claim and a receipt. The id came
from WhatsApp; it is not something we could have written down on our own.

## The rule underneath

When the honest answer is "I am working on it", say so in the medium the person
is already looking at. A status that only exists in a log file is a status
nobody has.
