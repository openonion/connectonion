---
title: The query everybody wrote first
date: 2026-09-18
---

# The query everybody wrote first

To reply to a group, you need its chat id. `co whatsapp reply` takes one.
`co whatsapp send` takes one. Nothing in the CLI printed one.

So the first thing anyone did with a fresh inbox was this:

```bash
jq -r '.chat' ~/.co/inbox/whatsapp/received.jsonl | sort -u
```

I wrote it. The person filing the production reports wrote it. It is in my shell
history four times from this week alone, in four slightly different shapes,
because each time I wanted one more field and rewrote it from scratch.

That is the tell. A query you keep rewriting is a command you have not added
yet.

## What the rewriting was for

Looking at those four variants, they were all converging on the same thing —
not just "which ids exist" but *which of these do I want*:

```
126121882435737@lid       direct  4  4  2026-09-17T04:59:17Z  Eric Fu  你好
120363410170505910@g.us   group   7  2  2026-09-17T05:00:24Z  Eric Fu  @bot 开始
#  id                     kind    n  for-us  last            who      what
```

A list of ids is useless; they all look alike. What lets you pick is the last
thing said, who said it, and when. So `chats` prints those.

The column I did not plan is `for-us`. It fell out of having both numbers to
hand, and it turns out to be the most interesting one: **the gap between
`messages` and `for-us` is the conversation happening around the bot.** Seven
messages in that group, two of them addressed to it. The other five are exactly
the context that `--context` exists to pass along, and now you can see how much
of it there is before you ask for it.

## Rich ate the tabs, again

The rows are tab-separated so `cut -f1` gives the id — the whole point is to
pipe it into the next command.

Printed through Rich, `\t` becomes spaces. It looks right on a terminal and
cannot be cut. The contact listing in `co outlook` learned this months ago and
has a test whose docstring says so; I reintroduced it in a new verb about two
hours after reading that test.

Plain `print()` now, with a test that pins the row at a fixed console width and
asserts `split("\t")` gives seven fields. The lesson that survives is not "use
print" — it is that a formatting library is a *display* device, and machine
output is not display.

## Where the filters came from

`log` had no arguments. It printed everything, forever, which is fine for
`-f` and useless for "what did they say in that group last week".

```bash
co whatsapp log --chat 120363410170505910@g.us -n 50
co whatsapp log --sender "Eric Fu" --since 7d
```

Three small decisions in there, each of which had a wrong answer available:

**`--sender` matches an id or a name.** The id is unreadable and the name is
what a person actually knows. Accepting only the id would have been more
"correct" and useless at a prompt.

**A filtered log does not follow.** `-f` tails the inbox; a filter answers from
the record and stops. Combining them would mean two different things at once —
"replay what matched, then watch for more that matches" is a third feature, and
nobody has asked for it.

**`--since` reuses the mail CLI's parser.** `30d`, `2w`, a date. Writing a
second grammar for the same idea is how `7d` comes to mean two different things
in one tool, and there is no version of that which gets noticed early.

**`-n` keeps the most recent.** Third time this week a cap has had to pick an
end — the mail window, `--context`, now this. Every time the answer comes from
what the question means rather than what the loop reaches first, and every time
it would have been easy to ship the other one.

## The rule underneath

Watch what people do *around* your tool. The shell history next to a command is
a list of the things the command should have done.

Four rewrites of one `jq` pipeline is not four people being resourceful. It is
the same missing feature, reported four times, by nobody.
