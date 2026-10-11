---
description: Credentials and money, what cannot be undone, and acting as the owner now stop for anyone else when nobody is there to ask. Two reviews found the cases where "anyone else" was wrong.
tags: [Trust, Approvals]
---

# Three things wait for the owner

The rule is short. Everything an agent does for someone else is done and
recorded, except three kinds of action: credentials and money, anything that
cannot be undone, and acting as the owner in the owner's own accounts. Code
decides which kind a call is, from the tool and its arguments, so no turn can
argue a call out of its class.

The first version made the rule exact: only the owner, meaning a local caller
or an admin, could run those calls, anywhere. A review read it against every
path that starts a turn and found two ways the rule was wrong.

**It refused the owner.** You reach `co ai` in the browser through an invite,
and an invite makes you a contact, not an admin. Calls in those classes used
to ask you in the browser, and you said yes. The exact rule turned that into a
flat no, for the one person it was meant to protect.

**It let a stranger through.** `co ai listen` set the requester after the
reply came back. So the first turn of every chat ran as nobody, and nobody
counts as the owner. Every new chat thread from a stranger got one such turn.

So the line moved to where it is true today. The calls stop when someone other
than the owner asked **and nobody is connected to ask**: a chat message, an
inbox turn, a contact's unattended run. Network EXEC from anyone but an admin
stops too, because EXEC never asks anyone. That shuts the hole in the shipped
`Bash(co *)` rule, which let any contact run `co env get` or `co transfer`.
With a client connected, the approval flow asks that person as it did before.

The second review also tried the classifier on about seventy commands. These
slipped past it:

- `co gmail send --body "It's ready"` got through, because the apostrophe broke
  the word split.
- So did `sudo timeout 60 co server new`, `bash -c 'co env get …'`,
  `co server destroy` and a tool named `pay`.
- `git reset --hard` was read as a git alias, not as throwing work away.

All of these are classified now. In the other direction, an SDK tool called
`delete(id)` that deletes its own records, not files, no longer counts as
irreversible.

Next is the part that makes the remaining refusals rare. When nobody is
connected, the agent asks the owner by email from its own mailbox, and the
owner's reply decides (#2408).
