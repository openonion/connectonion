---
description: Moving agent messages from email to an inbox was tested against production and passed. Then we noticed that one of our own machines would have silently stopped receiving handoffs.
tags: [Handoff, Release]
---

# The contact who would never have seen it

The new agent inbox went live this evening. We posted a message to a real
agent's inbox in production, read it back, and saw it arrive where `co handoff
status` looks. Every test was green. We were about to release.

Then we thought about the next test, which was supposed to send a handoff from
the Mac to our Linux machine. That machine had accepted a handoff a few hours
earlier, on the previous release. So the Mac had it saved as a contact, with
its agent address. The new rule said: if you know a contact's agent address,
send to its inbox. The Linux machine's co was one version behind, and that
version has never heard of an inbox. The handoff would have been delivered,
reported as sent, and never seen.

We had already handled half of this. A recipient on the new version checks
whether the sender's code is the new kind before replying through the inbox,
so an older sender keeps getting mail. What we missed was the other half: a
contact saved before the inbox existed. Knowing an agent's address and knowing
that the agent reads its inbox turned out to be two different facts, and we had
been treating the first as the second.

Contacts now carry a separate mark, set only when they took a handoff with a
new-style code. Everyone else still gets mail, which every version reads.

What saved us was planning a real test before release. The tests passed
because every agent in them ran the same version, and the machines we actually
own never do.
