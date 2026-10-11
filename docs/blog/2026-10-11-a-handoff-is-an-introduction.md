---
description: After a handoff was accepted, neither side could reach the other by name. Now each side makes the other its agent's contact, and the next step is a policy per contact.
tags: [Handoff]
---

# A handoff is an introduction

This morning a handoff went from this Mac to a Gmail inbox. From there it was
pasted into a fresh Codex on another machine, and it was accepted in 36
seconds. The sender's `co handoff status` showed who accepted, down to the
agent's full `0x` address. It looked done.

Then we asked a simple follow-up question. Could the recipient hand the work
back, and could the sender send the next task to the same person, by name?

Neither could. The recipient had kept the sender only inside the record for
that one handoff. The sender's address book still said `parrot-test` was a
Gmail address and knew nothing about the agent that had just accepted. That
agent had been written to `peers.json`, which records who accepted which
handoff and nothing else. Two people had just started working together, and
neither side knew who the other was.

## Why it was like that

It was on purpose. In co, an agent's contact may run the tools its Host
pre-authorises and drive its logged-in browser. A handoff code arrives in an
email, and an email can be forwarded. So the acceptor was kept out of the
trust lists, and the address book was left out along with them.

## What changed

We asked Aaron, and his answer was that someone you just handed work to is
obviously a contact, and that the real gap is the policy. Now:

- `co handoff accept` makes the sender the recipient's agent contact, the
  same list `co trust list` shows, and gives them a name, so
  `co handoff send <name>` hands work back.
- When the sender's `co handoff status`, or a running `co ai`, sees the
  acceptance, the recipient's agent becomes the sender's contact. The contact
  the handoff went to keeps its name and its mail address and gains the
  agent's address. Only the first valid acceptance counts, and a code
  presented as an invite code still onboards no one.

The next handoff to `parrot-test` still goes to the Gmail address. The person
reads that inbox and pastes the prompt from it. The agent address says who
they are; it is not a better place to deliver to.

## What comes next

Being a contact is still one bit today: you are in the list or you are not.
#2401 gives each contact its own policy, an allow/deny file like the ones
Codex and Claude Code use, read-only on the project by default. An AI writes
it from everything co rem knows about the person. It cites the evidence for
each grant, never counts the contact's own claims as evidence, never exceeds
a ceiling the owner sets, and asks before widening anything.
