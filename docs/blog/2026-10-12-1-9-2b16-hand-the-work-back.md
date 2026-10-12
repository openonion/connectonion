---
description: 1.9.2b16 closes the loop on a handoff. The person you handed work to can hand it back with the line their agent was given, and you can see who your handoffs introduced and why.
tags: [Release, Handoff]
---

# 1.9.2b16: hand the work back

A handoff goes both ways. When someone accepts your work, their agent is told
how to send it back to you, and in this preview that line works for every
sender, including a brand-new identity on an agent mailbox.

You can also see who your handoffs introduced. `co trust list --global` lists
the agents that became contacts of the identity `co ai` and `co handoff` use,
and `co approvals` says which handoff made each one a contact.

All three came out of one run: a fresh identity on this Mac handed a task to a
fresh identity on Parrot, using the release from PyPI. Install, accept,
questions, automatic answers and mistyped codes all worked. Hand-back was the
one step that failed, so that is what this preview fixes.
