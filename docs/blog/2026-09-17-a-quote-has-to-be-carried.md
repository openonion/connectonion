---
title: A quote has to be carried, not referenced
date: 2026-09-17
---

# A quote has to be carried, not referenced

`co whatsapp reply` wrote this into its ledger:

```json
{"chat":"120363410170505910@g.us","reply_to":"AC8191B5B6FBC9B74C91D050653D1B3B",
 "id":"3EB0F30CD86CC259178E17","ok":true,"by":"reply"}
```

and sent a message that quoted nothing. The answer landed in the right group —
that part was never broken — but as a loose line with no visible connection to
the question. In a group where four conversations are interleaved, that is most
of what a reply is for.

`reply_to` was written into the outbox request by `send`, carried across the
spool, and read by nobody:

```python
_publish(answer, {"id": self._send_now(payload["chat"], payload["text"])})
```

Two of the three fields.

## Why Feishu does not have this bug

Because on Feishu a reply is a *reference*:

```python
result = self._post(f"/open-apis/im/v1/messages/{reply_to}/reply", body)
```

You name the message. The platform knows what it said, who sent it, and which
chat it was in, so the chat is not a parameter and the quoted content is not
something you have to hold on to.

WhatsApp has no such endpoint, because there is no server to ask. A companion
device is a peer: the quote travels *inside* the outgoing message, as a
`ContextInfo` carrying the original's id, its sender, and **the original
message itself**. Which means, to reply to something, you have to still have it.

## The choice that made

Three options, and the one we were on by accident was the third.

**Keep the raw events.** neonize hands over the full protobuf; we could store it
and quote with perfect fidelity, media and all. It also means writing every
message anyone sends in every group the number is in to disk in full, forever —
other people's content, retained because we might one day reply to it. For a
feature this size that is the wrong trade, and it is the sort of default nobody
revisits.

**Rebuild the quote from what we already keep.** A quote is three things: the
original's id, who sent it, and its text. All three are in `received.jsonl`,
because the inbox is a log and always was. So:

```python
return events.Message(
    Info=events.MessageInfo(ID=original.id, MessageSource=events.MessageSource(
        Chat=_build_jid(original.chat), Sender=_build_jid(original.sender),
        IsGroup=original.chat.endswith(f"@{GROUP_SERVER}"))),
    Message=e2e.Message(conversation=original.text or ""),
)
```

No new storage, and it survives a listener restart, which the "hold recent
events in memory" version would not.

**Say nothing and send a loose message.** What it was doing.

The cost of the middle option is honest and worth naming: quoting an image
quotes its text, which for an image is empty. A quoted photo will render as a
quoted blank. That is a real limitation, it is written in the code, and it is
better than either retaining everyone's media or silently dropping the thread.

## The part I want to keep

`_quoted` returns `None` when the original has aged out of the log, and the
reply goes out unquoted rather than failing:

```
None when the original is not in the record any more. An answer that reaches
the right chat unquoted is worth more to the person waiting than an exception.
```

It is tempting to raise — the caller asked for a reply to a specific message and
cannot have one. But the person on the other end is waiting for an answer, not
for a thread. Degrading costs them a visual link; failing costs them the reply.

## Proving it, given a stand-in

The unit tests hand `_quoted` a fake protobuf. A fake I wrote will agree with
me about the fields I chose to set, which proves we call `build_reply_message`
and says nothing about whether WhatsApp would understand the result — the same
trap as the seven-byte `session.db` that stood in for a paired device earlier
this week.

So there is a second test, in the live suite, that builds the quote with the
real protobuf types and runs neonize's own `_make_quoted_message` over it:

```
stanzaID      = AC8191
participant   = 447700900123@s.whatsapp.net
quotedMessage = 那个价格表还是不对
```

That one needs a subprocess, because importing neonize starts a worker thread
and the suite refuses to let a test leave one behind. Which is the right rule:
the workaround took four lines, and the rule has already caught a real starvation
bug.

## The rule underneath

When two platforms give you the same verb, check whether it means the same
thing. `reply` on Feishu is a pointer; `reply` on WhatsApp is a copy. Writing
one interface over both is correct — the caller should not care — but the
interface hides exactly the difference that decides what you have to store,
and a field quietly dropped at the far end of a spool looks like success from
every side that can see it.
