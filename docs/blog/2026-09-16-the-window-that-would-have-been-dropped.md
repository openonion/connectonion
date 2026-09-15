---
title: The window that would have been dropped
date: 2026-09-16
---

# The window that would have been dropped

`co outlook inbox --since 30d` and `co gmail inbox --since 2w` work now. So does
`--until`, and `co outlook inbox --json`. Small, useful, and the interesting part
is the one combination that refuses.

## The refusal

```
$ co gmail inbox --since 30d --json
--since/--until do not work with --json yet; run without --json,
or see issue #1521
```

Gmail's `--json` already exists and answers with a versioned envelope —
`schema_version`, `provider`, `account`, `status`, `data`, `error`, plus
`--cursor` paging. The date window has not been composed with that contract yet.

The easy thing would have been to accept both flags and quietly ignore the
window. The command would have returned the last ten messages, printed a clean
JSON envelope, and exited 0. Every visible signal says success. The caller reads
"messages from the last 30 days" and gets "the most recent ten, from whenever".

That is a worse outcome than the error, and it is worse in a specific way: it is
undetectable from the output. An agent building a report on those ten messages
has no way to know the window was dropped. It would find out weeks later, from a
number that was wrong and had always looked right.

## What the issue said, and what was there

The issue described this as a wiring job — the library already had `list_between`,
so the CLI just had to expose it.

It did not. That description was read off an unmerged Wiki branch, where the
method existed; on `main` neither provider had it. Believing the issue would have
meant an afternoon looking for a function that was not there.

So `list_between` and `my_addresses` come over for both providers, **ported
verbatim** from the Wiki branch, so that when that branch lands the two copies
are identical text and there is nothing to reconcile. They were never Wiki-specific
anyway — anything that reads mail by time window needs them, and leaving them
inside a 6,785-line feature branch was the wrong address.

## Outlook gets `--json`, Gmail keeps the one it has

Outlook had no `--json` at all. It gets a plain array of the provider's own
fields. Gmail's envelope is untouched.

Two differently-shaped `--json` outputs in the same CLI is worse than one command
lacking the flag: the reader cannot tell which shape they are about to get
without remembering which provider they typed. One gap is a thing you can look
up. Two contradictory answers is a thing you get wrong silently.

## A date it cannot read

```
$ co outlook inbox --since 上周
Cannot read '上周' as a date. Use 30d, 2w, 6m, 1y, or 2026-06-01.      (exit 2)
```

It names the formats rather than saying the input was invalid. Someone who typed
a date in a form the parser does not take needs the list, not a verdict.

## The pattern

Three decisions in one small PR, all the same shape: when two features cannot yet
be combined honestly, say so at the boundary instead of producing an answer that
is confidently incomplete.

The releases this week have been full of the other version of that — a calendar
invitation that reached nobody while printing "Event created", a recovery pass
that failed every sixty seconds to an empty room. Silence and false success cost
more than an error, because an error is the only one of the three that sends
somebody to look.
