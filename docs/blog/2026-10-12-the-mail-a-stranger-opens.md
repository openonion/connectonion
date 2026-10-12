---
description: The first handoff mail is often someone's first contact with ConnectOnion. We rewrote it for a person who has never heard of us, then had a design review take it apart.
tags: [Handoff, Design]
---

# The mail a stranger opens

A handoff to someone new starts with an email. Until today that email was
written for a person who already knew what it was: a title, two paragraphs,
then a long grey box of instructions for an AI agent and, below it, a block of
encoded text in tiny type. Our own team could read it. Someone receiving their
first one would see a wall of code from an address they did not recognise.

So we wrote it again for that person. It now says who sent it and what
ConnectOnion is, in one line, before anything else. Then the task, where it
stands and what is still undecided. Then three numbered steps, and a single
block to paste, with START and END printed above and below it, because no email
client will run a copy button.

Then we asked a design review to take it apart, and it found eight things. The
one we liked best: the summary and the block to paste were both light green
boxes, and the instructions said "copy the whole green box". On a phone, the
first green box you see is the summary. Now only the block is green.

Another finding changed what the email promises. Step three said the agent
"asks you before it changes anything". It does ask before it touches your
files, but it installs software and tells the sender first. The new line says
exactly that. Saying less and being right is how a first email earns trust.

Two problems were invisible on screen. Gmail cuts off long emails, and a long
session could have cut the block in half; the block now keeps the newest
messages and says how many it left out. And the hidden data at the bottom was
written in one-pixel white text, which is what spam looks like to a filter. It
is simply hidden now.

The lesson for us: a first message is read by someone who owes us nothing, on
a phone, deciding in a few seconds whether this is real. Design it for that
person, and have someone who is not us read it.
