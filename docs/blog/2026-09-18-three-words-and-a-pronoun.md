---
title: Three words and a pronoun
date: 2026-09-18
---

# Three words and a pronoun

Someone quoted the bot's own message in a WhatsApp group and wrote *"this one is
wrong"*. Here is everything the bot received:

```json
{"text": "this one is wrong", "sender": "126121882435737@lid",
 "mentioned": false, "at": "2026-09-18T03:56:43Z"}
```

Three words and a pronoun with nothing to point at. The consumer could not
answer the question, because it did not know what "this one" was. It could not
even tell that it had been asked — `mentioned` was false, and there was nothing
in the record to say whether that was right.

That last part is the one worth sitting with. The report that found this said it
better than I would have:

> If the reply was to another participant rather than to the bot, then
> `mentioned: false` is correct and the real bug is only that this is
> unverifiable.

A wrong answer you can check is a bug. A right answer you cannot check is also a
bug, and a more expensive one, because nobody can close it.

## It was all already there

Every reply WhatsApp sends carries a `contextInfo` with `stanzaID` — the quoted
message's id — plus `participant`, who sent it, and `quotedMessage`, the whole
thing.

We read that struct on every message. We have read it since the first version of
this provider. `_context_info` walks the message's set fields to find it,
because that is where `mentionedJID` lives and mentions are how a group bot
knows it is being spoken to.

So the quote was not missing. It was arriving, being parsed, having one field
read out of it, and being dropped on the floor.

## Why a bug like that survives

Because the parser was written to answer one question — *is this for us?* — and
it answered it correctly. `contextInfo` was, to that code, the place where
`mentionedJID` lives. It is also the place where the entire conversational
context lives, but nothing about reading one field from a struct makes you
inventory the rest of it.

The mention parser and the reply reference are the same seven lines apart, and
it took an outside report to notice, because the person who wrote those seven
lines had already decided what the struct was for.

## The field that actually changes behaviour

Not `text`, which is the obvious one. `from_me`:

```json
"quoted": {"id": "3EB0…", "sender": "132754033377342@lid",
           "text": "deploy 41 is live", "kind": "text", "from_me": true}
```

Replying to the bot and replying to someone else in the same group are different
events. The first is a question; the second is two colleagues talking, and a bot
that joins in is the bot everyone mutes. A trigger policy of *direct message,
@mention, or reply to us* is not implementable without telling them apart, and
until now the record could not.

## One value, not two copies

The obvious mistake here would have been to compute `from_me` for the record and
leave `_addressed_in_group` computing "did they reply to us" separately. Both
read the same `participant` field; both would be correct on the day they were
written; and they would drift, because two expressions of one idea always do.

When they drift, the record says one thing and the behaviour does another — and
you are back to a `mentioned` value nobody can argue with. So the gate reads the
same `from_me` the record carries.

I kept the direct participant check alongside it, for a reason worth naming: a
quoted *reference* needs a stanzaID to be worth carrying, and the *gate* does
not. If a reply ever arrives with a contextInfo shaped in some way I did not
anticipate, it should still count as a reply rather than be silently downgraded
to "not for us" because one field I chose to require was absent. Losing the
reference is a degraded record; losing the gate is an unanswered person.

## The rule underneath

When you read one field out of a structure the platform hands you, look at what
else is in it. Not as a general principle of thoroughness — as a specific
question: *what does this struct know that my caller is currently guessing at?*

The mention parser had been standing next to the answer for a month.
