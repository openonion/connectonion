---
description: After a handoff was accepted, neither side could reach the other by name. Now each side saves the other as a contact, with their agent's address, and neither becomes a trust contact.
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

It was on purpose, and the reason still stands. co has a second kind of
contact, in the trust lists, and a trust contact may run commands on your
host. A handoff code arrives in an email, and an email can be forwarded. If
accepting a handoff made you a trust contact, anyone who got hold of the mail
could call your agent. So the acceptor was kept carefully apart from the
trust lists, and the address book was left out along with them.

## The fix

The address book and the trust lists are different things, and only the
trust lists carry power. Now:

- `co handoff accept` saves the sender as a contact, with their mailbox and
  their agent's address, and says `co handoff send <name>` hands work back.
- When the sender's `co handoff status` or a running `co ai` sees the
  acceptance, the contact the handoff went to keeps its name and its mail
  address and gains the recipient's agent address. Someone new is saved under
  their mailbox name. A name that is already taken gets a short suffix
  instead of being overwritten.
- `co handoff contacts` lists them.

The trust lists are unchanged. After the real run we checked both machines.
Each side listed the other in `co handoff contacts`, and neither side's
`co trust list` contained the other. Only an invite makes someone a trust
contact.

One thing did not change: the next handoff to `parrot-test` still goes to
the Gmail address. The person reads that inbox and pastes the prompt from
it. Their agent's address identifies them, but it is not a better place to
deliver to.
