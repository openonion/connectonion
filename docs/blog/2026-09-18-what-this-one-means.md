---
title: What "this one" means
date: 2026-09-18
---

# What "this one" means

Point at something on your screen and say "this one is wrong" to a colleague
standing next to you. They know what you mean. Do it in a WhatsApp group by
quoting the message and typing the same four words, and until this week our bot
received exactly this:

```json
{"text": "this one is wrong", "mentioned": false}
```

Four words, a pronoun, and nothing to point at.

## The two questions it could not answer

*What is wrong?* — unanswerable. The quoted line was right there in the chat for
every human in the group, and absent from the record entirely.

*Was I even asked?* — also unanswerable, and this is the worse one. `mentioned`
said no. Maybe that was correct and the person was replying to a colleague;
maybe it was wrong and the bot had just ignored a direct question. Nothing in
the record could settle it.

Whoever filed this put it better than I did:

> If the reply was to another participant rather than to the bot, then
> `mentioned: false` is correct and the real bug is only that this is
> unverifiable.

That framing is worth stealing. A wrong answer you can check is a bug — annoying,
findable, fixable. A right answer you cannot check is also a bug, and it outlives
the other kind, because nobody can prove it needs fixing.

## The data had been arriving the whole time

Every WhatsApp reply carries a `contextInfo`: `stanzaID`, the quoted message's
id; `participant`, who wrote it; and `quotedMessage`, the whole thing.

We read that struct on every single message. We have read it since the first
version of this provider, because `mentionedJID` lives in it and mentions are
how a group bot knows it is being spoken to.

So the quote was never missing. It arrived, got parsed, had one field read out
of it, and was discarded — about seven lines away from the code that needed it.

I keep coming back to why that survives, because "nobody looked" is not the
answer. Somebody looked very carefully. The parser was written to answer one
question — *is this for us?* — and it answers it correctly. To that code,
`contextInfo` **is** the place where `mentionedJID` lives. It is also the place
where the entire conversational context lives, and nothing about reading one
field from a struct prompts you to inventory the rest.

## The field that changes what the bot does

Not the quoted text, which is the obvious prize. This one:

```json
"quoted": {"id":"3EB0C796…", "sender":"132754033377342@lid",
           "text":"收到：LID @提及现在能识别了", "kind":"text", "from_me":true}
```

`from_me`. Replying to the bot and replying to someone else in the same group
are different events. The first is a question. The second is two colleagues
talking, and a bot that answers it is the bot everyone mutes on Tuesday.

You cannot implement "answer when addressed" without separating them, and until
now the record could not.

## One value, not two copies of it

The obvious shape would be: compute `from_me` for the record, and leave the
`mentioned` gate computing "did they reply to us" the way it always had. Both
read the same `participant`. Both correct on the day they are written.

And then they drift — because two expressions of one idea always do — and when
they drift the record says one thing and the behaviour does another. Which puts
you back at a `mentioned` value nobody can argue with, which was the actual bug.

So the gate reads the same `from_me` the record carries. For a reply,
`mentioned == quoted["from_me"]`, by construction rather than by agreement.

I did keep the older direct check alongside it, and the reason is worth naming:
a quoted *reference* needs a `stanzaID` to be worth carrying, and the *gate*
does not. If some reply arrives with a `contextInfo` shaped in a way I did not
anticipate, it should still count as addressed to us rather than be quietly
downgraded because one field I decided to require was absent. A degraded record
costs context. A degraded gate costs somebody an answer.

## The rule underneath

When you take one field out of a structure a platform hands you, ask what else
is in it — not as general diligence, but as a specific question: *what does this
struct already know that my callers are currently guessing at?*

Ours knew what "this one" meant. It had known for a month.
