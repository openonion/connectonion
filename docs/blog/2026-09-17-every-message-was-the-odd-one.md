---
title: Every message was the odd one
date: 2026-09-17
---

# Every message was the odd one

This is the whole log of a WhatsApp listener that worked perfectly and
delivered nothing:

```
2026-09-17T03:51:42Z  paired
2026-09-17T03:51:46Z  connected
2026-09-17T03:54:49Z  connected as 61410724095
2026-09-17T03:57:24Z  event not understood (AttributeError: 'google._upb._message.FieldDescriptor' object has no attribute 'label'); skipped
2026-09-17T03:57:24Z  event not understood (AttributeError: 'google._upb._message.FieldDescriptor' object has no attribute 'label'); skipped
```

The phone was linked. The socket was up. Two messages were sent, and both of
them are in that log. Neither reached the inbox, and `co whatsapp ls` was
empty.

## The line that did it

`_context_info` walks a message's set fields looking for the one carrying
`contextInfo` — where mentions and quoted messages live. Every message variant
has its own copy of it, so rather than naming each type, it asks the descriptor:

```python
if descriptor.label == descriptor.LABEL_REPEATED:
    continue
```

protobuf 7 removed `FieldDescriptor.label`. It is not deprecated, not renamed
in place — gone, with `is_repeated` added back in 6.x as the replacement. The
constant survives, so `descriptor.LABEL_REPEATED` still evaluates to `3`; only
the attribute being compared to it disappeared.

That line runs on the first field of every message. Not the unusual ones. All
of them.

## Why it produced a log line instead of a crash

Around the handler sits this, and the comment on it is not wrong:

```python
# A raising handler would surface as a Go-side panic and take the
# whole process down, listener and all. A payload we cannot read is
# one log line.
try:
    message = self.to_message(event)
except Exception as exc:
    inbox.log(f"event not understood ({type(exc).__name__}: {exc}); skipped")
    return
```

neonize is compiled Go. An exception escaping a callback does not raise in
Python where someone can see it; it panics across the boundary and takes down a
listener meant to run for weeks. WhatsApp sends event types nobody documented.
One unreadable payload genuinely should not end the process.

So the dilemma is real, and it is not "should this `except` exist". It should.
The dilemma is that this handler cannot tell the difference between the two
things it might be catching, and those two things could not be further apart:

- *This message is odd.* Skip it, keep the other 999 flowing. Correct.
- *This build cannot read any message.* Skip it, 999 more times, and report
  nothing but skips. Catastrophic.

Both are one message that failed to parse. The code sees one message that
failed to parse. The tolerance that is right per-message is exactly wrong in
aggregate, and nothing in the handler knows which regime it is in.

## The instrument agreed with it

The obvious answer is "then check the tool's health", and I did. `co whatsapp
check` said:

```
✓ whatsapp reachable
```

It had asked whether `session.db` existed. neonize creates that file when the
client starts — before the QR is drawn, whether or not any phone scans it. So
the file's presence proved the process had started, and was being read as proof
a device had linked.

That is its own bug, and it is fixed in the same change: `linked()` now counts
rows in `whatsmeow_device`, the table whatsmeow writes when the phone confirms
the pairing and reads to reconnect without a new QR. "Is there a row" and "can
this reconnect" are the same question, which is what makes it the right thing to
measure.

Two of its existing tests had to change, and why is the part worth keeping.
Both did:

```python
(tmp_path / "session.db").write_bytes(b"linked")
```

Seven bytes standing in for a paired device. The stand-in agreed with the bug,
so the suite stayed green the entire time the behaviour was wrong. They build a
real session database with a real device row now.

## What I changed, and what I didn't

The parse is a two-line fix — prefer `is_repeated`, fall back to the old
comparison — because both protobuf generations are in the wild.

I did not narrow the `except`. Catching `AttributeError` specifically would have
turned today's bug into a crash and left tomorrow's identical bug swallowed
just the same. The class of error was never the signal.

What was missing is that nobody was counting. A listener that skips one message
in a thousand is healthy. A listener that has skipped every message since it
started is broken, and those are distinguishable with a ratio — which is the
thing I could not read off a per-event log line, and the thing I'm carrying into
the next change rather than pretending two lines fixed it.

## The rule underneath

A tolerance is a statement about *rate*, not about *kind*. "Skip what you cannot
read" is only safe while most things are readable, and the code that acts on it
has no idea whether that is still true.

The acceptance run is what caught this, and it is worth being precise about how:
not by reading the log, but by the owner sending two messages and asking where
they went. Every automated signal we had — process up, socket connected, `check`
green, test suite passing — was consistent with a system that could not read a
single message.
