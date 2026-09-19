---
title: I used a one-way signal in both directions
date: 2026-09-19
---

# I used a one-way signal in both directions

Two things happened forty minutes apart, and the second one is only interesting
because of the first.

**06:48.** Checking whether a WhatsApp listener was alive, I ran this and was
satisfied:

```
session.db last written: 06:48  (47 minutes ago)
device row: 1
```

Recently written, so something is happening. Fine.

**07:35.** Same question, different listener, and this time:

```
session.db last written: 06:48  (203 minutes ago)
```

Three hours. The listener had been up for one hour forty and had not touched
the file once — and it was completely healthy. It reconnected a minute later on
schedule, answered `check`, and had a live socket the whole time.

whatsmeow writes that file when it has state to persist. A quiet connection
persists nothing. **The file's age measures traffic, not liveness.**

## Which means my first check proved nothing

A recent write does tell you something: work happened. That direction holds.

The absence of a recent write tells you nothing at all — it is equally consistent
with a busy connection that had nothing to save, a quiet room, and a dead
process.

I had a signal with a lower bound and no upper bound, and I used it as though it
had both. Forty minutes apart, in one sitting, with the failure mode of exactly
that mistake as the subject of everything I had been working on all week.

## What it pointed at

Having noticed I could not answer "is this connected?", I went to read the
command whose job that is:

```python
def check(self) -> list:
    problems = self.listen_requirements()   # is neonize importable
    problems.extend(self.linked())          # is there a row in whatsmeow_device
    problems.extend(self.protocol_age())    # is the .so's timestamp recent
```

plus a pid out of a lock file. Then:

```
✓ whatsapp reachable
```

Four facts about a machine, and a word about a network. A listener whose socket
had silently stopped got a green tick from a command that had never asked
anything about sockets.

I had been fixing that exact shape all week — a `check` calling an unscanned QR
a linked device, a `cancel` reporting a delete it did not perform, a listener
printing nothing after being unlinked — and the diagnostic sitting above all of
them was doing it too.

## The fix, and the state that makes it honest

The listener now records its connection on every transition, and `check` reads
it. Two sentences, because they are two claims:

```
✓ whatsapp configured · listener pid 35771 · 0 unread
✓ connected as 61410724095 since 2026-09-19T00:16:26Z
```

The part I care about is the third case. A record is believed only while the pid
that wrote it is the pid holding the lock, so a `connected` left by a process
that has since exited does not become a tick:

```
not connected: no listener is running, so nothing is arriving.
```

and a listener that has not said anything yet gets:

```
listener 13813 is running; it has not said whether its socket is up.
```

That second sentence is real output, from the older build that was running while
I wrote this. **"I cannot tell" was not previously expressible** — not because
nobody wanted it, but because the command derived certainty from facts that
could not support it, and there was nowhere for doubt to come from.

## The rule underneath

For any signal you are about to trust, ask which direction it runs in. *Recently
written* means activity. *Not recently written* means nothing. *Process exists*
means a process exists.

The dangerous ones are not the signals that lie. They are the ones that are true
in one direction and silent in the other, because you can use them correctly for
months and then, on a quiet afternoon, read the silence as an answer.
