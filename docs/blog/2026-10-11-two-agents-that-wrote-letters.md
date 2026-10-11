---
description: Two of our own agents, one on a Mac and one on a Linux box, were answering each other through Resend and Cloudflare. Mail now only finds the other agent; after that they use an inbox on our backend.
tags: [Handoff, Agents]
---

# Two agents that wrote each other letters

This afternoon a handoff went from a Mac to a Codex on our Linux machine. The
Codex accepted it, asked which commit to start from, and got an answer. It
worked. Then Aaron asked a simple question: where does that question actually
go?

We traced it. The Codex's agent called our API, which handed the question to
Resend, an outside mail provider. Resend sent it across the internet to
`@mail.openonion.ai`, where Cloudflare's mail routing picked it up and a worker
wrote it into our database. The Mac's agent then read it back out of the same
database. Both agents were ours. The message left our system twice to travel
between two rows of one database, and a full copy stayed in two tables with no
expiry.

Mail made sense for the first message. Nobody knows the other person's agent
yet; all they have is a person to write to. But the first exchange changes
that. The handoff code carries the sender's agent address, and the acceptance
carries the recipient's. From then on the two agents know each other, and
writing letters is the wrong tool.

So now mail does the discovery and nothing else. After it, a question, an
answer, or the next handoff to the same contact is one row in an
`agent_messages` table, addressed to the other agent, readable only by it, and
deleted after thirty days. Reading does not delete it, so the same identity on
a second machine sees the same messages.

There was one trap. A recipient on the new version would happily send its
acceptance to the inbox of a sender still on the old one, who would never look
there. The code now starts `coh2.` when its sender reads the inbox, and an old
`coh1.` code is still answered by mail.

The lesson is about defaults that outlive their reason. Mail was the right
choice when an agent had no other way to find another. It stayed the only route
after the agents had found each other, because nobody asked what the second
message needed.
