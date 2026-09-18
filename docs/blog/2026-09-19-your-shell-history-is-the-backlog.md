---
title: Your shell history is the backlog
date: 2026-09-19
---

# Your shell history is the backlog

To reply to a WhatsApp group with `co`, you need the group's chat id.
`co whatsapp reply` takes one. `co whatsapp send` takes one.

Nothing in the tool printed one.

So this is in my shell history four times from one week:

```bash
jq -r '.chat' ~/.co/inbox/whatsapp/received.jsonl | sort -u
```

Four times, in four slightly different shapes, because each time I wanted one
more field and rewrote it from the beginning rather than scrolling back.

I did not notice while doing it. I noticed while scrolling past it looking for
something else, which is a sentence I have now typed twice this month.

## The rewrites were a spec

Reading those four variants next to each other, they were all converging on the
same thing. Not "which ids exist" — I never actually wanted a list of ids, they
all look alike — but *which of these do I want right now*.

Each rewrite added one of: the last message, who sent it, when, how many there
were. So:

```
126121882435737@lid       direct  4  4  2026-09-17T04:59:17Z  Eric Fu  你好
120363410170505910@g.us   group   7  2  2026-09-17T05:00:24Z  Eric Fu  @bot 开始
#  id                     kind    n  for-us  last            who      what
```

The column I did not plan is `for-us`. It fell out of having both counts to hand
— and it is the most interesting one on the row. **The gap between `messages`
and `for-us` is the conversation happening around the bot.** Seven messages in
that group, two addressed to it. The other five are exactly what the `--context`
flag exists to pass to a model, and now you can see how much of it there is
before deciding to ask for it.

That column exists because I built the thing instead of running the query a
fifth time. You do not discover it in a `jq` pipeline, because you have to
already want it to type it.

## Rich ate the tabs, again

The rows are tab-separated so `cut -f1` gives the id — the entire point is to
pipe it into the next command.

Printed through Rich, `\t` becomes spaces. It looks correct on a terminal and
cannot be cut.

`co outlook`'s contact listing learned this months ago. It has a test whose
docstring explains it, in this repo, which I read earlier the same day. I then
reintroduced the bug in a new verb about two hours later.

The lesson that survives is not "use `print`". It is that a formatting library
is a *display* device and machine output is not display — and that knowing a
rule is not the same as it firing when you are two hours into something else.
The test is what fires.

## Three caps, one week

`-n` on `log` keeps the most recent messages. That is the third time in a week I
have had to decide which end a cap discards:

- `--since 30d` on mail returned the *oldest* ten in the window and silently
  dropped the rest — asked what arrived this month, it answered with mail from
  a month ago.
- `--context 20` keeps the last twenty turns, because a conversation is
  understood backwards.
- `log -n 50` keeps the most recent fifty, for the same reason.

Each time the answer came from asking what the *question* means rather than what
the loop reaches first. Each time the other answer was available and would have
shipped quietly. The first one did ship, for a release.

A cap is not a limit, it is a choice about what to throw away, and code that
truncates without saying which end it kept is guessing on the user's behalf.

## The rule underneath

Watch what people do *around* your tool. The commands sitting next to yours in a
shell history are a list of the things yours should have done.

Four rewrites of one pipeline is not resourcefulness. It is the same missing
feature, filed four times, by nobody.
