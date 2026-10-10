---
description: Two lines in the co handoff brief read wrong to the person receiving it. "1 turns" is now "1 turn", and what the recipient may do sits under the header, or is left out.
tags: [Handoff]
---

# "1 turns", and a line that read like the task

We sent a real handoff from a Mac to Parrot on 1.9.2b5 (`ho-a055c28c`) and
then read it the way the recipient would. Two lines were wrong.

The first was small. Under *Code and references* the brief said:

> Transcript excerpt: 1 turns of the sender's notes file session

A handoff drafted with `--from-file` always has exactly one turn, the notes
file. So every notes-file handoff ever sent contained that grammar mistake.
The brief already had a `_count` helper that gets "1 decision, 2 rejected
options" right. The excerpt line was written by hand and didn't use it. Now it
does.

The second was the one that mattered. The *Task* section ended with:

> You may: not stated by the sender

It was printed as a paragraph inside `## Task`, right under the task itself.
A coding agent reading the brief takes everything in that section as part of
what it has to do. "You may: not stated" reads like an unfinished instruction,
and the agent has to decide what to do with it. That line was never part of
the task. It is the sender's grant: what the recipient's agent is allowed to
do.

## Where it goes now

When the sender stated permissions, they appear right under the header, next
to From and To, labelled with who they apply to:

```
# Handoff: Store the login token

From: me@… · To: ody@… · 2026-10-10 · ho-1a2b3c4d

Recipient may: edit auth/; open a PR

## Task
Store the login session token; done when the cookie is set on login.
```

When the sender stated none, the line is left out. "Not stated by the sender"
gave the reader nothing to use. It only took up space in the section the
reader trusts most. The rule for drafting doesn't change: `may_do` lists only
what the sender actually said.

Both changes appear in all three places the brief is shown: the sender's
preview, the mail and `HANDOFF.md`. All three come from the same function.
