---
title: "1 is a row in which list?"
date: 2026-09-17
---

# 1 is a row in which list?

```
$ co outlook inbox -n 4
$ co outlook scheduled
No scheduled emails.

$ co outlook cancel 1
✓ Canceled scheduled email 1
```

Exit 0. There were no scheduled emails. It deleted an email out of the inbox.

I found this while verifying that a *different* Outlook fix worked, which is the
only reason I noticed at all: I knew which messages were supposed to exist, so
I noticed one had stopped existing.

## Two listings, one drawer

`co outlook inbox` numbers its rows 1, 2, 3 and writes them to
`~/.co/outlook_last_inbox.json`, so you can say `co outlook read 2` without
pasting a 152-character Graph id. Good design; every mail CLI does it.

`co outlook scheduled` numbers *its* rows 1, 2, 3 and writes them to the same
file. Also reasonable in isolation — it needs numbers for `cancel`, and there
was already a place to put numbers.

Nothing records which listing the numbers came from. So `1` means *row one of
whatever you listed most recently*, and the two kinds are freely
interchangeable:

- list the scheduled drafts, then `reply 1` — you reply to a draft
- list the inbox, then `cancel 1` — **`DELETE /me/messages/<an email you received>`**

The verbs are not interchangeable. The numbering is. That gap is the whole bug.

## Two details that turn it from rare into likely

**An empty `scheduled` returns early.**

```python
scheduled = outlook.get_scheduled()
if not scheduled:
    console.print("\n[cyan]No scheduled emails.[/cyan]\n")
    return                      # cache untouched
```

So "you have nothing scheduled" leaves yesterday's inbox numbering sitting
there — and "you have nothing scheduled" is precisely the state someone is in
when they're confused about whether a `cancel` worked and try it again.

**With no cache at all, the resolver asks the inbox.**

```python
emails = outlook.list_inbox(last=int(email_id))
return emails[int(email_id) - 1]["id"]
```

A sensible fallback for `read`. For `cancel` it is the same data loss by a
second route.

And `cancel_scheduled` never checks what it was handed:

```python
self._request("DELETE", f"/me/messages/{email_id}")
```

## Why "it's only a soft delete" is not the reassurance it sounds like

Graph's `DELETE` moves the message to Deleted Items, so nothing is destroyed
forever. That matters, and it is not the point.

The point is that the command reported success for an action it did not
perform, performed a different action nobody asked for, and exited 0. Every
signal available to a caller — the ✓, the exit code, the absence of any
warning — agrees with the version of events in which a scheduled email was
cancelled. The only way to find out otherwise is to already know what was in
your inbox.

That is the same shape as the four other bugs this week, and the most expensive
version of it so far, because this one is a write.

## The fix is to make the number carry its provenance

```json
{"kind": "inbox", "rows": {"1": "AAMk…", "2": "AAMk…"}}
```

`_resolve_email_id` takes what the caller expects and returns nothing on a
mismatch. `cancel` expects `scheduled`. The inbox fallback is skipped unless
inbox numbers were asked for. An empty `scheduled` records an empty scheduled
listing rather than returning early.

An old cache file, with no `kind`, is read as an inbox one — upgrading must not
silently reclassify numbers that already exist on someone's disk.

Now:

```
$ co outlook inbox -n 3
$ co outlook cancel 1
No scheduled email #1 — numbers come from the last co outlook scheduled
listing, and cancel only ever acts on that one.
Next: co outlook scheduled
exit 1
```

## The rule underneath

A short identifier is a *reference into a context*, and the context is part of
the identifier. Storing the number without the context is storing half of it,
and the missing half has a default — "whatever was there last" — that is
invisible, plausible, and occasionally catastrophic.

Anywhere a CLI lets you say `2` instead of an id, ask what happens when the `2`
outlives the list that gave it meaning. It will: lists are refreshed by other
commands, by other terminals, by time. The question is only whether the command
notices.
