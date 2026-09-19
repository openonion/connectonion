---
title: The log showed a message nobody had seen
date: 2026-09-19
---

# The log showed a message nobody had seen

The feature was small and the test was green. An agent writes Markdown, WhatsApp
does not read Markdown, so translate it on the way out: `**ready**` becomes
`*ready*`, a link becomes a label and a URL somebody can tap.

I put the translation inside `send()`, which is the obvious place. Every caller
goes through `send`, including `consume`, which replies without passing through
any CLI handler. One conversion, one place, nothing to remember.

Then I sent one on the real account and read it back.

```
$ co whatsapp send … 'Formatting check: **bold**, *italic*, [the run](https://…)'
3EB030E4E27A670781BB9A

$ # what sent.jsonl says about it
Formatting check: **bold**, *italic*, [the run](https://…)
```

The record held what I typed. The group received something else.

## Two strings, one of them fiction

`handle_send` does this:

```python
sent = p.send(chat, body, reply_to=reply_to)
inbox.record_sent(chat=chat, text=body, provider_id=sent)
```

`body` is what the caller typed. `p.send` translated it on the way past. So the
log is a faithful record of the input to a function, and the chat contains the
output, and nothing anywhere holds both.

Nobody would notice for a while. `log` is what you read *later* — when a client
asks what the bot told them, or when you are working out why an answer landed
badly. It is consulted precisely when the thing it describes is no longer on
screen, which is exactly when an inaccuracy cannot be caught.

## It is the same bug I had just shipped a release about

The release immediately before this one existed because `co whatsapp check`
printed `✓ whatsapp reachable` from four facts, none of which was the network.
A statement about one thing, derived from something adjacent, presented with
confidence.

This is that, in the file that is supposed to be evidence. *This is what was
sent* — derived from what was passed in, which is adjacent to what was sent and
is not the same string.

I wrote a release note about the first one and introduced the second inside the
same week, in code I was writing *while* thinking about it.

## The fix is about who holds the string

Rendering moved out of `send` and into the caller, one helper at each of the
five places that send:

```python
body = _wire(p, _text_from(text), plain)     # the exact characters going out
sent = p.send(chat, body, reply_to=reply_to, plain=True)
inbox.record_sent(chat=chat, text=body, provider_id=sent)
```

Now there is one string. It goes to the platform and it goes to the log,
because they are the same variable.

`plain=True` on the send is load-bearing: the translation is not idempotent.
`*bold*` is italic in Markdown and bold on WhatsApp, so a second pass moves it
to `_bold_` — a function that quietly corrupts its own output when applied
twice, which is a good reason never to leave "did this already run?" implicit.

## What I would look for next time

The shape is a transformation that happens on one branch of a fork. The value
goes two places — the wire and the record, the API and the cache, the email and
the audit row — and only one branch gets the transform.

It looks right at the call site, because the call site handles one of the two.

The question that finds it: **when this value goes to more than one place, is it
the same variable?** Not "is it the same content", which is an assumption. The
same variable, so the language makes it true instead of me.
