# Sharing a Mailbox Is Not the Same as Giving It Away

A rental-outreach pipeline had a mailbox with a history: `rental@mail.openonion.ai`
had been the sender for months, replies landed there, and a CRM's dedupe rules
were written around that one address being the one identity. A newly deployed
agent needed to send the first-touch enquiries from that same address, and
ownership in the email system was exclusive — one account, one address, no
exceptions.

Every workaround was a worse trade than the problem. Moving the address to
the agent took it away from the person who still needed it. A new address for
the agent split the conversation across two inboxes that nothing reconciled,
and looked, to anyone replying, like mail from a stranger. Sharing the
private key solved the technical problem and created a real one: one
identity now sat on two machines, with no way to tell which had sent what,
and revoking access meant rotating the key for everyone who held it.

The system already had a mechanism for moving an address between accounts —
two signatures, a fixed-order message, one irreversible transaction. It's the
right tool for handing a mailbox over for good. It was the wrong tool here,
because nothing was ending: the person kept using the address exactly as
before, and the agent needed to use it too, starting now and stopping the
moment anyone changed their mind.

What was missing sat in between owning an address and losing it: a grant.
Revocable, and checked on every request rather than proven once with a
signature — the natural shape once you notice the server already sits in the
middle of every send. Nobody has to sign anything offline for a permission
the server can just look up. `co email share rental@mail.openonion.ai --with
<agent> --can send` writes one row; `co email unshare` deletes it. Attribution
falls out of the existing schema for free: every sent-mail record already
carried the identity of whoever actually sent it, so a shared address stays
one conversation, sent by two accounts, with no ambiguity about which one did
what.

The design question worth naming: not every "let account A act as account B"
problem needs cryptography. A signed, offline-verifiable grant is for the
case where nobody trustworthy is online to ask — a proxy dialing out through
a home connection at 3am, say. A mailbox share is answered on every request
by a server that was already the arbiter. Reaching for the stronger tool
there wouldn't have made the feature more correct. It would have solved a
problem this one doesn't have.
