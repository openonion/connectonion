---
title: The word "reachable" was doing no work
date: 2026-09-19
---

# The word "reachable" was doing no work

I had the listener running on a real WhatsApp number and wanted to confirm it
was healthy. An hour and forty minutes, no new log lines. Quiet — but quiet is
the thing this whole release has been about being unable to distinguish from
dead.

So I reached for a second signal:

```
session.db last written: 06:48  (203 minutes ago)
```

Three hours. The listener had been up for one hour forty and had not touched the
file once.

Which taught me something about my own reasoning rather than about the bug: I
had used "session.db was written recently" as proof of life forty minutes
earlier in the same session. It is not. whatsmeow writes when it has state to
persist, so a quiet connection writes nothing, and the file's age measures
*traffic*, not *liveness*. I had been holding a signal with only one direction
and reading it in both.

## Then I read what `check` actually checks

```
$ co whatsapp check
✓ whatsapp reachable · listener pid 13813 · 0 unread
```

```python
def check(self) -> list:
    problems = self.listen_requirements()   # is neonize importable
    problems.extend(self.linked())          # is there a row in whatsmeow_device
    problems.extend(self.protocol_age())    # is the .so's timestamp recent
    return problems
```

Plus a pid read out of a lock file.

**Nothing in there touches the network.** A package being importable, a row in
SQLite, a timestamp inside a shared library, and a process holding a lock. From
those four facts the command was printing the word *reachable* — a claim about a
socket, made without consulting a socket.

So a listener whose connection had quietly stopped, in any way that does not
raise `LoggedOutEv`, still got a green tick. The command people run to find
exactly that failure was an instance of it.

This week I have fixed: a `check` that called an unscanned QR a linked device; a
`cancel` that reported success for a delete it did not perform; a listener that
printed nothing after being unlinked. And all three sat underneath a diagnostic
doing the same thing at a higher level.

## The fix is that the listener says so

`check` runs in a different process from the listener, so it cannot ask the
client object anything. The listener now writes what it knows:

```json
{"state":"connected","at":"2026-09-19T00:16:26Z","pid":35771,
 "account":"61410724095","ids":["132754033377342","61410724095"]}
```

written on every transition — connected, disconnected, stopped — rather than on
a timer. A heartbeat would say "something ran recently"; what is wanted is "the
socket is up, and this is when that last changed".

And the output splits into two sentences that mean different things:

```
✓ whatsapp configured · listener pid 35771 · 0 unread
✓ connected as 61410724095 since 2026-09-19T00:16:26Z
```

## The part I am most pleased with is the third case

There are not two states here, there are three, and the third is the one that
makes this honest:

```
✓ whatsapp configured · listener pid 13813 · 0 unread
listener 13813 is running; it has not said whether its socket is up.
Next: co whatsapp log
```

That is the real output from the listener that was already running when I built
this — an older build, with no idea it was supposed to leave a record.

A `connected` file from a process that has since exited says what was true once.
Reading it as current is how a stale file becomes a confident wrong answer, so
the record is only believed while the pid that wrote it is the pid holding the
lock. Otherwise the command says it does not know.

Saying "I cannot tell" is a real answer. It was not available before, because
the command had no way to be uncertain — it was deriving certainty from facts
that could not support it.

## The rule underneath

Read the words your tool prints as if you had to defend them. *Reachable* is a
claim about a network. *Configured* is a claim about a machine. They had the
same implementation.

Every diagnostic is a sentence someone will believe. The question worth asking
of each one is not "does this pass" but **"what would have to be true for this
to be false, and does the check look at any of it?"**
