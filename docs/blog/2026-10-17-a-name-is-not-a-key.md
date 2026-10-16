# A name is not a key

*2026-10-17*

A day after handoffs started boxing every message to the other agent's key, the release check turned
up the obvious next question: which key?

The sender had addressed one agent's own mailbox, `0xde0c2d75b2@mail.openonion.ai`. A different agent
accepted, with the link. That's allowed. A link is a capability, the first keyed reader holds the
handoff, and a forwarded link is how a teammate takes over. But when the acceptance came back, the
sender's contact book wrote the acceptor's key under the name `0xde0c2d75b2`. From then on, a send to
that name still mailed the right mailbox, and boxed the agent traffic for the wrong agent. The intended
agent couldn't open it. The one who had the forwarded link could.

When the address is a person's email, we don't know their agent until it accepts, so whoever accepts
is the person's agent. An agent mailbox is different: its name *is* an agent, the first ten hex of its
key. An acceptance from any other key is someone else, and the book now says so. The acceptor is
saved under its own mailbox name, the original name keeps its own key, and `co handoff status` says
"accepted it, not the agent you sent it to".

Encryption doesn't remove trust decisions. It moves them to the moment a key is written down.
