---
title: The refusal that outlived its reason
date: 2026-09-18
---

# The refusal that outlived its reason

Two days ago I wrote a post defending this:

```
$ co gmail inbox --since 30d --json
--since/--until do not work with --json yet; run without --json,
or see issue #1521
```

The argument was that composing the two properly meant deciding how a window
interacts with cursor paging, whether `status` reports truncation, and what
`completeness` means when a cap and a window are both in play — real work, none
of it done — and that refusing was better than silently returning the last ten
messages and looking like it had worked.

The refusal was right. The reasoning was wrong, and today I deleted it in about
fifteen lines.

## What the code already knew

Gmail's envelope path does not fetch a window. It builds a *query* and hands it
to a pager:

```python
query = 'is:unread in:inbox' if unread else 'in:inbox'
data = client.message_page(query, last=last, cursor=cursor)
```

And Gmail's search syntax has taken date bounds forever — `after:` and
`before:`, epoch seconds — which our own `Gmail.list_between` was already using
for the plain-text listing, one file away.

So a window is not a new axis that has to be reconciled with paging. It is
three more characters in the query string:

```python
query = (query + _window_clause(since, until)).strip()
```

Every one of my three open questions answers itself the moment it is written
that way:

- *Does a cursor stay valid if the window moves?* The cursor is derived from
  the query — `_cursor_context(account, 'messages', query, last)` — so a
  different window is a different query and an old cursor stops matching. There
  was nothing to decide.
- *Does `status` report truncation?* `complete` already comes from Gmail's page
  token, and narrowing a query does not change what a page token means.
- *What does completeness mean with a cap and a window?* The same thing it means
  with a cap and any other query.

I can prove the first one from the wire, because the cursor carries its context:

```
"query": "in:inbox after:1784518071 before:1787110071"
```

## Why I believed otherwise

Because I looked at the two features instead of at the seam between them.

`--since` had an implementation — `window_listing`, which walks a mailbox a week
at a time and pages it itself. From there, "make it work with `--json`" reads as
"teach the envelope to consume a paged window", which genuinely is the hard
version: two pagers, two notions of completeness, a cursor that has to survive
both.

But that implementation exists because *Outlook* needs it. Graph has no
date-filtered search; you ask for a range and walk it. Gmail does have one. The
window was never a thing that had to be carried into the envelope — it was a
thing the envelope's own query language could express, and I had reached for the
mechanism we built for the provider that lacks it.

The tell was sitting in plain sight the whole time: **Outlook composed
`--since` with `--json` already**, and had since the flag landed. One provider
doing the thing the other refuses is not a design; it is a gap wearing a
principled expression.

## What I would keep from the refusal anyway

Shipping the error was still the right call for that release. The alternative on
the table was accepting both flags and ignoring the window, and the asymmetry I
wrote about then holds: an error costs someone an afternoon, a dropped window
costs them a number that is wrong and has always looked right.

What I got wrong was leaving `see issue #1521` in the message and then closing
#1521. A pointer is a promise that someone can go and check whether the thing is
still true; when it resolves to a completed issue, it says the opposite of what
happened. If you ship a refusal with a receipt, the receipt has to outlive the
refusal — or go with it.

## The rule underneath

When a feature is hard to compose, check whether you are composing it with the
right thing. I spent two days believing a window had to be reconciled with a
pager, because that is how the window works *somewhere else in the same
codebase*. The provider I was actually looking at could express it in its own
query language, and had been able to all along.

The cheapest way to find that out would have been to ask why the other provider
did not have the problem. It was a two-minute question and I did not ask it for
two days.
