---
description: Accept told the recipient how to hand work back, and that line failed for every sender on an agent mailbox. Every earlier test used a sender with a custom address, so the line had never been run.
tags: [Handoff]
---

# The way back that was never tried

When someone accepts a handoff, `co handoff accept` ends with the way back:

```
The sender 0xa46c…f283 is now your agent's contact 0xa46c6ebf21 (co trust list);
co handoff send 0xa46c6ebf21 hands work back.
```

Today we ran 1.9.2b14 from PyPI with a fresh identity on each machine. The
sender was this Mac and the recipient was Parrot, a Linux box with no co, no
uv and no pipx.

The handoff mail arrived, and co installed itself into its own venv as the
prompt says. The acceptance reached the sender in seconds. A question went
back, and the answer brought the sender's session with it. In that copy was
the line that held the answer: a comment in a config file that only a tool
call had ever read.

Then the recipient ran the line it had been given:

```
'0xa46c6ebf21' is neither an email nor a full 0x agent address (0x + 64 hex)
```

## A name that looks like an address

When a contact is saved, it is named after its mailbox. An agent mailbox is
`0x` and ten hex characters, so the contact's name is too. When `co handoff
send` read a name, anything starting with `0x` was treated as an address and
never looked up. A ten-character address is not a valid one, so the command
refused it.

Every earlier run had a sender at `aaron.xie@mail.openonion.ai`, whose contact
is called `aaron`. The way back was printed in every one of those runs, and
nobody ran it. A fresh identity has no custom address, so that is what a new
user has, and the way back failed for every one of them.

## The fix, and what it teaches

Names are looked up first. A full address or an email that is not a contact
name resolves as before. The test that pins it failed on main with the same
error Parrot printed. The same line on Parrot now drafts to the right
mailbox, and the hand-back arrives in the sender's `co handoff inbox`.

A command we print as the next step is a promise. The test has to run what
we printed, as a person on a fresh machine would, not as the account we
happened to test with.
