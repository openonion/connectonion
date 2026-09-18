---
title: When you speak is not what you know
date: 2026-09-18
---

# When you speak is not what you know

Here is a real exchange in a group, as the people in it saw it:

```
14:31  Aaron:  the price sheet is still wrong
14:32  Aaron:  it's missing the cleaning column
14:34  Aaron:  @bot recompute it
```

And here is everything the bot was handed:

```json
{"text": "@bot recompute it", "mentioned": true}
```

Recompute *what*, with *which* correction? The bot was in the room for all three
messages. It wrote all three to its log. And the consumer that had to answer got
the last one on its own.

## One switch doing two jobs

Every group channel has `mention_only`, and it does something sensible: stay
quiet unless addressed. Without it a bot answers every message in the group and
gets muted by Tuesday.

But `mention_only` was also, quietly, deciding **what the bot is allowed to
know**. A message that did not name the bot was not passed to the consumer at
all — not as an answer to give, and not as background either.

Those are two different decisions wearing one flag. *When do you speak* is a
politeness rule. *What do you know* is a capability. Collapsing them gives you a
bot that is well-mannered and useless: present for the whole conversation,
briefed on one line of it.

## It was all already on disk

`received.jsonl` holds every message the listener ever saw — including the ones
that named nobody. It has since the first version, because the log is the log.
Non-mentioned group messages are in there in full; I checked during an
acceptance run and they were all present.

So this was never a capture problem. The transcript existed; nothing offered it
to the process that needed it.

`co whatsapp receive --context 20` now does:

```json
"context": [
  {"from":"them","text":"the price sheet is still wrong"},
  {"from":"them","text":"it's missing the cleaning column"},
  {"from":"us","text":"looking now"}
]
```

## The `from: "us"` rows are not a nicety

My first version read `received.jsonl` only, and the transcript it produced was
subtly wrong in a way that matters: it showed what people said to the bot and
nothing the bot said back.

Hand that to a model and it does exactly what you would do reading a
conversation where one participant is silent — it apologises for not having
responded, or it answers a question it already answered twenty minutes ago.

So `sent.jsonl` is merged in by time. The bot's own turns are part of the
conversation, and a record that omits them is not a shorter transcript, it is a
different one.

## Why it is off by default

Context is not free, in two ways that pull in different directions.

The obvious one is tokens: twenty turns in front of every message is twenty
turns you pay for on every message.

The one I care about more: those turns are **other people's messages**. A group
has people in it who never addressed the bot and may not have thought about it
being there. Passing their words to a consumer — which might be a model, a
subprocess, a remote API — is a real thing to do, and the right shape for a real
thing is a flag someone typed rather than a default they inherited.

`--context 0` is the default and the output is byte-identical to before.

## The cap falls on the older end

`context 20` keeps the *last* twenty turns, not the first twenty. This is the
second time this week I have had to choose which end a cap discards — the mail
window was the other — and both times the answer came from asking what the
question meant rather than what the loop happened to do first.

A conversation is understood backwards from its most recent turn. The first
twenty messages of a long thread are the least useful twenty you could pick.

## The rule underneath

When one flag controls two behaviours, it is controlling the one you thought
about and silently deciding the other.

`mention_only` had been shipping a policy about knowledge under a name about
speech since the feature existed, and it never looked wrong, because the name
described exactly half of what it did.
