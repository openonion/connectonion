---
title: The window that would have been dropped
date: 2026-09-16
---

# The window that would have been dropped

`co gmail inbox --since 30d --json` does not work. It stops and says so:

```
--since/--until do not work with --json yet; run without --json,
or see issue #1521
```

Shipping that refusal was the hard call in an otherwise small change, and the
case for *not* shipping it was strong enough that I nearly didn't.

## The shape of the problem

Gmail's `--json` already exists and answers with a versioned envelope —
`schema_version`, `provider`, `account`, `status`, `data`, `error`, plus
`--cursor` paging. That contract has callers.

The new date window arrived separately. Composing the two properly means
deciding how a window interacts with cursor paging: does the cursor stay valid
if the window moves, does `status` report that the window truncated the result,
what does `completeness` mean when both a cap and a window are in play. Real
work, none of it done.

So for one release, the two features exist and cannot be combined.

## The argument for letting it through

Accept both flags, ignore the window, return the last ten messages.

It sounds indefensible written down. It is not, in the moment. The command
succeeds. The envelope is well-formed. The caller gets messages — real ones,
from their real mailbox, the most recent ones, which is what they'd have got
before the flag existed. Nobody is worse off than last week. The flag arrives
"partially supported", the docs note it, and the composition lands next release.

That reasoning is how the calendar bug in 1.8.5 happened. `co gcalendar` created
events with attendees, invited nobody, and printed `Event created`. Every signal
said success. It survived until a client's guest mentioned they'd received
nothing.

## What decided it

The two failures are not equally visible, and the difference is not about
severity.

An error is a thing the caller can see. A dropped window is not — not from the
output, not from the exit code, not from the JSON, not ever. The envelope that
comes back from `--since 30d --json` is byte-identical to the one from a plain
`--json`. There is no field that says "your filter was ignored". An agent
building a monthly report on those ten messages has no way to learn the window
never applied. It finds out weeks later, from a number that is wrong and has
always looked right.

That asymmetry is the whole decision. Both options fail; only one of them is
detectable.

## The cost of saying no

It is not free, and pretending otherwise would be its own kind of dishonesty.

Someone with a script doing `--since 7d --json` has to change it — either drop
`--json` and parse text, or wait. The command surface is now slightly ragged:
two flags that each work alone and not together, which is a thing you have to
remember. Documentation has to carry the exception.

I think that is the right trade, but it is a trade, and the receipt is the issue
number in the error message. `see issue #1521` is not decoration — it is where
the caller goes to find out whether this is still true.

## The rule underneath

When two features cannot yet be combined honestly, refuse at the boundary
instead of producing an answer that is confidently incomplete.

The releases this week keep circling the same failure: a calendar invitation
that reached nobody while printing success, a recovery pass that failed every
sixty seconds to an empty room, a scope link that said "App updated" and granted
nothing. None of those were crashes. All of them were confident output
describing something that had not happened.

An error costs someone an afternoon. Silent success costs them the thing they
were relying on, and they find out from somebody else.
