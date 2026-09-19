---
title: The cap fell on the wrong end
date: 2026-09-17
---

# The cap fell on the wrong end

Yesterday's post argued that `co gmail inbox --since 30d --json` should refuse
rather than quietly ignore the window, because a dropped window is invisible
and an error is not. Today, checking the other provider against a real mailbox:

```
--last 5      (no window)   newest is 2026-09-17T05:00:28Z
--since 1d    10 messages   all from 2026-09-16, nothing from the 17th
--since 30d   10 messages   2026-08-18 .. 2026-08-19
```

`--since 30d` answers with ten messages from a month ago. Not truncated at the
end you would expect — truncated at the *start*, so the newest thing it returns
is three weeks stale, and nothing says the other four weeks exist.

The refusal I defended in Gmail was defending against precisely this. Outlook
shipped it.

## Both layers picked the same wrong end

`Outlook.list_between` asks Graph for `receivedDateTime asc` with `$top`. Graph
applies `$top` after `$orderby`, so a capped ascending query means *the oldest N
in this range*.

That is not a bug where it was written. Its caller is the wiki importer, which
walks a mailbox forward from a cursor and wants exactly that. The method is
doing its job.

Then `window_listing` walks the window forwards from `since` and stops when it
has enough:

```python
cursor = start
while (end - cursor).total_seconds() >= 1 and len(rows) < last:
    stop = min(cursor + timedelta(days=7), end)
    rows += client.list_between(cursor.isoformat(), stop.isoformat(), ...)
    cursor = stop
```

It fills up inside the first week-chunk — a month ago — and returns. The rest of
the window is never requested.

Neither layer is wrong on its own terms. The cap has to fall somewhere, and each
of them independently made the reasonable local choice. It is the composition
that produces an answer nobody would accept if they could see it.

## The two sentences that disagreed

The CLI help:

> `--since`  Everything in a window **instead of** the last -n

The function's own docstring, one file away:

> Every message in the window, oldest first, **capped at `last`**.

Both were written by someone who knew what they meant. Only one of them is what
a user reads, and it is the one that is false. The docstring was not hiding
anything — it says "capped" right there — it just was not where the promise was
being made.

## The test that held the bug in place

```python
starts = [call[0][:10] for call in box.calls]
assert starts == sorted(starts)                      # forward, oldest first
```

That assertion is the bug, written down and guarded. It passed for the whole
life of the defect, and changing the walk direction turned it red — which is
how it should feel, and also why nobody had changed it.

The fake could not have caught it either:

```python
def list_between(self, start, end, max_results):
    return [... for i in range(min(self.per_call, max_results))]
```

Two rows per call, regardless of what is in the range. Ask it for the oldest
two or the newest two and it answers identically. The wrong half and the right
half are the same object to it — which is the third time this week a stand-in
has agreed with a bug, after the seven-byte `session.db` and the hand-typed
`@mention`.

The regression test uses a mailbox with one message an hour and more mail in the
window than the cap, because that is the only shape where the question "which
half did you keep" has an answer.

## What changed

`list_between` takes `newest_first`, defaulting to `False` so the importer is
untouched, and sorts ascending either way — the flag chooses *which* messages,
not their order. `window_listing` walks backwards from the recent edge.

And when the cap bites before reaching the far edge, it now says so:

```
Showing the 10 most recent in this window; there are more. Next: raise -n
```

On stderr, so `--json` remains exactly one array on stdout and nothing parsing
it has to change. A person finds out; a pipeline does not break.

## The rule underneath

A cap is a decision about what to discard, and discarding is never neutral.
Every layer here defaulted to "keep what I reach first", which is the ordering
the code happened to have rather than the ordering the question implied.

When you truncate, say which end you kept, and say that you truncated. The
second half is the part we skipped, and it is the half that turns a wrong answer
into a partial one.
