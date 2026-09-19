---
title: The read-back habit cannot catch this one
date: 2026-09-19
---

# The read-back habit cannot catch this one

I have a rule I trust more than most: after sending something, read it back
from wherever it was recorded. It has caught a wrong recipient, a truncated
attachment, a number eaten by shell quoting. It is cheap and it almost always
works.

On Friday it certified a mistake.

```
$ co whatsapp send 120363411567190840@g.us
3EB051DF0FC1EF995EF15B
$ echo $?
0
```

A fragment had been left in the shell line, so the text argument was gone. The
command did what it was told: no argument means read stdin, stdin was at EOF,
so the message was the empty string. WhatsApp accepted it. A blank bubble
appeared in a customer's group.

Then I read it back, as I always do:

```json
{"at":"2026-09-19T01:09:23Z","chat":"120363411567190840@g.us","text":"","id":"3EB051DF0FC1EF995EF15B","ok":true}
```

`"ok": true`. And it was. The record is completely accurate.

## What the habit actually checks

Reading back compares *what was recorded* against *what I meant*. It works
because the recording is usually made from the thing that was sent, so an
error between my intention and the wire shows up as a difference.

But the comparison is only as good as the second half — and the second half was
never written down anywhere. "What I meant" lives in my head at the moment of
typing. When the mistake is that I meant something and typed nothing, there is
no artifact to compare against. The log says `""` and I look at `""` and there
is no disagreement to notice.

Every signal on that command agreed: an id, exit 0, a row with `ok: true`, a
`Next:` hint. A blank message is not an error condition anywhere in the stack.
It is the successful transmission of zero bytes of text.

## Reversibility is a property of the tool, not the mistake

The same slip in an editor costs a keystroke. Here it cost a message in front
of a client, permanently — because `co whatsapp` had no `delete`.

That is the part worth generalising. The cost of an error is not set by how bad
the error is; it is set by what the tool lets you do afterwards. The same empty
string is a shrug in one place and an apology in another, and the difference is
entirely in the tooling around it.

We shipped `edit` and `delete` an hour before I found this, for unrelated
reasons. The first real use of `delete` was removing these blanks from that
group.

## The fix, and the thing it does not do

Empty and whitespace-only text is now a usage error on `send`, `reply` and
`edit`: nothing is sent, and **nothing is written to the log**. A refusal is not
an attempt, and a row saying otherwise would be the same class of lie one layer
down.

The `reply` case took a second look. `reply` marks a message answered, and if
the refusal had landed after that, a typo would have cost the *question* as well
as the answer — a blank you can delete, a lost question nobody knows about.

What the fix does not do is make the read-back habit work here. It can't. The
habit compares a record against a memory, and no amount of recording fixes an
empty memory.

What works instead is upstream: make the impossible state unrepresentable, so
there is no successful path to certify. A required argument costs a caller one
retry and removes the class — which is a much better deal than any amount of
checking afterwards.
